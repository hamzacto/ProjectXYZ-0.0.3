"""Service for managing billing cycles and automatic renewal."""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple, Any
from uuid import UUID
from loguru import logger
from sqlmodel import Session, select
import asyncio

from langflow.services.database.models.billing.models import (
    BillingPeriod,
    SubscriptionPlan,
    get_next_billing_cycle
)
from langflow.services.database.models.user import User
from langflow.services.deps import get_session, session_scope


class BillingCycleManager:
    """
    Service to handle billing cycle operations including automatic renewal.
    This runs independently from but complementary to the BillingService.
    """
    
    def __init__(self):
        """Initialize the billing cycle manager."""
        self._is_running = False
        self._renewal_task = None
        self._renewal_interval_hours = 24  # Check once per day by default
        # Lock for thread safety
        self._renewal_lock = asyncio.Lock()
    
    async def start(self) -> None:
        """Start the automatic renewal background task."""
        if self._is_running:
            logger.warning("Billing cycle manager is already running")
            return
        
        self._is_running = True
        self._renewal_task = asyncio.create_task(self._run_renewal_loop())
        logger.info("Started billing cycle manager")
    
    async def stop(self) -> None:
        """Stop the automatic renewal background task."""
        if not self._is_running or not self._renewal_task:
            logger.warning("Billing cycle manager is not running")
            return
        
        self._is_running = False
        if self._renewal_task:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except asyncio.CancelledError:
                pass
            self._renewal_task = None
        logger.info("Stopped billing cycle manager")
    
    async def _run_renewal_loop(self) -> None:
        """Background task loop that checks for billing periods to renew."""
        while self._is_running:
            try:
                # Acquire lock to ensure only one renewal process runs at a time
                async with self._renewal_lock:
                    # Process all expired billing periods
                    await self.process_expired_billing_periods()
                
                # Wait for next check interval
                await asyncio.sleep(self._renewal_interval_hours * 3600)
            except asyncio.CancelledError:
                # Handle clean cancellation
                break
            except Exception as e:
                logger.error(f"Error in billing cycle renewal loop: {e}")
                # Wait a shorter time before retry on error
                await asyncio.sleep(60 * 15)  # 15 minutes
    
    async def process_expired_billing_periods(self) -> Dict[str, Any]:
        """
        Find all expired billing periods and create new ones.
        Returns statistics about the renewal process.
        """
        logger.info("Processing expired billing periods")
        
        stats = {
            "processed": 0,
            "renewed": 0,
            "errors": 0,
            "canceled": 0,
            "details": []
        }
        
        try:
            async with session_scope() as session:
                # Find all active but expired billing periods
                now = datetime.now(timezone.utc)
                
                # Workaround for SQLAlchemy timezone-aware comparison issue
                # We'll fetch potentially expired periods and filter them in Python
                active_periods_query = select(BillingPeriod).where(
                    BillingPeriod.status == "active"
                )
                
                active_periods = (await session.exec(active_periods_query)).all()
                
                # Filter periods in Python to handle timezone differences
                expired_periods = []
                for period in active_periods:
                    end_date = period.end_date
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=timezone.utc)
                    
                    if end_date < now:
                        expired_periods.append(period)
                
                stats["processed"] = len(expired_periods)
                
                logger.info(f"Found {len(expired_periods)} expired billing periods to process")
                
                for period in expired_periods:
                    try:
                        user = await session.get(User, period.user_id)
                        if not user:
                            logger.error(f"User {period.user_id} not found for billing period {period.id}")
                            stats["errors"] += 1
                            stats["details"].append({
                                "period_id": str(period.id),
                                "user_id": str(period.user_id),
                                "status": "error",
                                "reason": "user_not_found"
                            })
                            continue
                        
                        # Check if user subscription should continue
                        if user.subscription_status != "active":
                            # Mark expired period as inactive
                            period.status = "inactive"
                            session.add(period)
                            stats["canceled"] += 1
                            stats["details"].append({
                                "period_id": str(period.id),
                                "user_id": str(period.user_id),
                                "status": "canceled",
                                "reason": f"subscription_status={user.subscription_status}"
                            })
                            continue
                        
                        # Get subscription plan
                        plan = None
                        if user.subscription_plan_id:
                            plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                        
                        if not plan:
                            logger.error(f"Subscription plan not found for user {user.id}")
                            stats["errors"] += 1
                            stats["details"].append({
                                "period_id": str(period.id),
                                "user_id": str(user.id),
                                "status": "error",
                                "reason": "plan_not_found"
                            })
                            continue
                        
                        # Create new billing period
                        await self.create_new_billing_period(
                            session=session,
                            user=user,
                            plan=plan,
                            previous_period=period
                        )
                        
                        # Mark expired period as inactive
                        period.status = "inactive"
                        session.add(period)
                        
                        stats["renewed"] += 1
                        stats["details"].append({
                            "period_id": str(period.id),
                            "user_id": str(user.id),
                            "status": "renewed",
                            "plan": plan.name
                        })
                        
                    except Exception as e:
                        logger.error(f"Error processing billing period {period.id}: {e}")
                        stats["errors"] += 1
                        stats["details"].append({
                            "period_id": str(period.id),
                            "user_id": str(period.user_id) if period else "unknown",
                            "status": "error",
                            "reason": str(e)
                        })
        
        except Exception as e:
            logger.error(f"Error in process_expired_billing_periods: {e}")
            stats["global_error"] = str(e)
        
        logger.info(f"Completed billing period renewal: {stats['renewed']} renewed, {stats['errors']} errors")
        return stats
    
    async def create_new_billing_period(
        self,
        session: Session,
        user: User,
        plan: SubscriptionPlan,
        previous_period: Optional[BillingPeriod] = None
    ) -> BillingPeriod:
        """Create a new billing period for a user based on their subscription plan."""
        
        # Define billing period start/end dates
        if previous_period:
            # Start immediately after previous period ended
            previous_end = previous_period.end_date
            # Ensure previous_end has timezone info
            if previous_end.tzinfo is None:
                previous_end = previous_end.replace(tzinfo=timezone.utc)
                
            start_date = previous_end + timedelta(seconds=1)
            # Standard billing period (usually 1 month)
            end_date = start_date + timedelta(days=30)
        else:
            # New subscription - start immediately
            start_date = datetime.now(timezone.utc)
            end_date = start_date + timedelta(days=30)
        
        # Calculate quota based on plan
        base_quota = plan.monthly_quota_credits
        
        # Calculate rollover credits from previous period if any
        rollover_credits = 0.0
        if previous_period and previous_period.quota_remaining > 0:
            # Check if user's plan allows rollover (Pro plans and above)
            allows_rollover = plan.allows_rollover if hasattr(plan, 'allows_rollover') else False
            
            
            if allows_rollover:
                # User has unused credits that can be rolled over
                rollover_credits = previous_period.quota_remaining
                logger.info(f"Rolling over {rollover_credits} unused credits from previous period for user {user.id} on {plan.name} plan")
            else:
                # Plan doesn't support rollover
                logger.info(f"Skipping credit rollover for user {user.id} - {plan.name} plan doesn't support rollover feature")
                # Set rollover_credits to 0 (already the default)
        
        # Total quota is base quota from plan plus any rolled over credits
        total_quota = base_quota + rollover_credits
        
        # Create new billing period
        new_period = BillingPeriod(
            user_id=user.id,
            start_date=start_date,
            end_date=end_date,
            subscription_plan_id=plan.id,
            status="active",
            quota_used=0.0,
            quota_remaining=total_quota,
            rollover_credits=rollover_credits,  # Store rollover amount separately for reporting
            overage_credits=0.0,
            overage_cost=0.0,
            is_plan_change=False,
            previous_plan_id=None,
            invoiced=False
        )
        
        session.add(new_period)
        
        # Also reset user's credit balance at the start of a new period including rollover
        user.credits_balance = total_quota
        session.add(user)
        
        logger.info(f"Created new billing period for user {user.id}, plan: {plan.name}, base quota: {base_quota}, rollover: {rollover_credits}, total: {total_quota}")
        
        # Commit is handled by the caller
        return new_period
    
    async def manually_renew_user_billing_period(self, user_id: UUID) -> Dict[str, Any]:
        """
        Manually trigger a renewal of a user's billing period.
        This is useful for testing or admin operations.
        """
        result = {
            "user_id": str(user_id),
            "success": False,
            "message": ""
        }
        
        try:
            async with session_scope() as session:
                # Get the user
                user = await session.get(User, user_id)
                if not user:
                    result["message"] = f"User {user_id} not found"
                    return result
                
                # Get current active billing period
                active_period_query = select(BillingPeriod).where(
                    BillingPeriod.user_id == user_id,
                    BillingPeriod.status == "active"
                )
                active_period = (await session.exec(active_period_query)).first()
                
                if not active_period:
                    # No active period - create a new one
                    if not user.subscription_plan_id:
                        result["message"] = f"User {user_id} has no subscription plan"
                        return result
                    
                    plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                    if not plan:
                        result["message"] = f"Subscription plan not found for user {user_id}"
                        return result
                    
                    # Create first billing period
                    new_period = await self.create_new_billing_period(
                        session=session,
                        user=user,
                        plan=plan
                    )
                    
                    result["success"] = True
                    result["message"] = "Created first billing period"
                    result["period_id"] = str(new_period.id)
                    
                else:
                    # Existing period - force expiry and renewal
                    plan = None
                    if user.subscription_plan_id:
                        plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                    
                    if not plan:
                        result["message"] = f"Subscription plan not found for user {user_id}"
                        return result
                    
                    # Mark current period as inactive
                    active_period.status = "inactive"
                    session.add(active_period)
                    
                    # Create new period
                    new_period = await self.create_new_billing_period(
                        session=session,
                        user=user,
                        plan=plan,
                        previous_period=active_period
                    )
                    
                    result["success"] = True
                    result["message"] = "Renewed billing period"
                    result["period_id"] = str(new_period.id)
            
            return result
                    
        except Exception as e:
            logger.error(f"Error in manually_renew_user_billing_period: {e}")
            result["message"] = f"Error: {str(e)}"
            return result
    
    async def check_user_billing_period(self, user_id: UUID) -> Optional[BillingPeriod]:
        """
        Check if a user has an active billing period.
        If not, create one based on their subscription plan.
        Returns the active billing period.
        """
        try:
            async with session_scope() as session:
                # Get the user
                user = await session.get(User, user_id)
                if not user:
                    logger.error(f"User {user_id} not found")
                    return None
                
                # Check for active billing period
                active_period_query = select(BillingPeriod).where(
                    BillingPeriod.user_id == user_id,
                    BillingPeriod.status == "active"
                )
                active_period = (await session.exec(active_period_query)).first()
                
                if active_period:
                    # Check if period is expired but still marked as active
                    now = datetime.now(timezone.utc)
                    
                    # Ensure end_date has timezone info for comparison
                    end_date = active_period.end_date
                    if end_date.tzinfo is None:
                        # If end_date has no timezone info, assume it's UTC and add the timezone
                        end_date = end_date.replace(tzinfo=timezone.utc)
                    
                    if end_date < now:
                        logger.info(f"Found expired billing period for user {user_id}, will renew")
                        
                        # Get the subscription plan
                        plan = None
                        if user.subscription_plan_id:
                            plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                        
                        if not plan:
                            logger.error(f"Subscription plan not found for user {user_id}")
                            return active_period  # Return existing period even though it's expired
                        
                        # Mark current period as inactive
                        active_period.status = "inactive"
                        session.add(active_period)
                        
                        # Create new period
                        new_period = await self.create_new_billing_period(
                            session=session,
                            user=user,
                            plan=plan,
                            previous_period=active_period
                        )
                        
                        return new_period
                    else:
                        # Period is still valid
                        return active_period
                else:
                    # No active period - create a new one if user has a subscription plan
                    logger.info(f"No active billing period found for user {user_id}, creating new one")
                    
                    if not user.subscription_plan_id:
                        logger.error(f"User {user_id} has no subscription plan")
                        return None
                    
                    plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                    if not plan:
                        logger.error(f"Subscription plan not found for user {user_id}")
                        return None
                    
                    # Create first billing period
                    new_period = await self.create_new_billing_period(
                        session=session,
                        user=user,
                        plan=plan
                    )
                    
                    return new_period
        
        except Exception as e:
            logger.error(f"Error in check_user_billing_period: {e}")
            return None
            
    async def change_user_plan(self, user_id: UUID, new_plan_id: UUID) -> Dict[str, Any]:
        """
        Handle a user changing subscription plans mid-cycle.
        This ends the current billing period and starts a new one with the new plan.
        
        Args:
            user_id: The user ID
            new_plan_id: The new subscription plan ID
            
        Returns:
            Dictionary with information about the plan change
        """
        result = {
            "success": False,
            "user_id": str(user_id),
            "old_plan": None,
            "new_plan": None,
            "proration": {}
        }
        
        try:
            async with session_scope() as session:
                # Get user
                user = await session.get(User, user_id)
                if not user:
                    result["error"] = f"User {user_id} not found"
                    return result
                    
                # Get new plan
                new_plan = await session.get(SubscriptionPlan, new_plan_id)
                if not new_plan:
                    result["error"] = f"New subscription plan {new_plan_id} not found"
                    return result
                
                # Get current active period
                active_period_query = select(BillingPeriod).where(
                    BillingPeriod.user_id == user_id,
                    BillingPeriod.status == "active"
                )
                active_period = (await session.exec(active_period_query)).first()
                
                # Get old plan
                old_plan = None
                if user.subscription_plan_id:
                    old_plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                    result["old_plan"] = old_plan.name if old_plan else None
                
                result["new_plan"] = new_plan.name
                
                # Update user's plan
                user.subscription_plan_id = new_plan_id
                session.add(user)
                
                if active_period:
                    # Calculate how much of the current period has been used (for proration)
                    now = datetime.now(timezone.utc)
                    
                    # Ensure start_date and end_date have timezone info for comparison
                    start_date = active_period.start_date
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=timezone.utc)
                        
                    end_date = active_period.end_date
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=timezone.utc)
                    
                    total_period_duration = (end_date - start_date).total_seconds()
                    used_duration = (now - start_date).total_seconds()
                    
                    # Error handling to avoid division by zero
                    if total_period_duration <= 0:
                        used_percentage = 1.0  # Assume fully used if period start/end dates are invalid
                    else:
                        used_percentage = min(1.0, max(0.0, used_duration / total_period_duration))
                        
                    # Round to 2 decimal places
                    used_percentage = round(used_percentage, 2)
                    
                    # If we're upgrading and the new plan has a higher quota, apply that higher quota immediately
                    is_upgrade = False
                    if old_plan and new_plan and new_plan.monthly_quota_credits > old_plan.monthly_quota_credits:
                        is_upgrade = True
                        
                    # Mark current period as inactive with special status for plan change
                    active_period.status = "plan_change"
                    active_period.is_plan_change = True
                    active_period.previous_plan_id = user.subscription_plan_id if old_plan else None
                    session.add(active_period)
                    
                    # Create new period starting immediately
                    new_period = BillingPeriod(
                        user_id=user.id,
                        start_date=now,
                        end_date=now + timedelta(days=30),  # Standard 30-day period
                        subscription_plan_id=new_plan.id,
                        status="active",
                        quota_used=0.0,  # Start fresh for new plan
                        quota_remaining=new_plan.monthly_quota_credits,
                        overage_credits=0.0,
                        overage_cost=0.0,
                        is_plan_change=True,
                        previous_plan_id=old_plan.id if old_plan else None,
                        invoiced=False
                    )
                    
                    session.add(new_period)
                    
                    # Update user's credit balance for the new plan
                    if is_upgrade:
                        # For upgrades, give full new quota
                        user.credits_balance = new_plan.monthly_quota_credits
                    else:
                        # For downgrades, prorate based on usage
                        remaining_percentage = 1.0 - used_percentage
                        prorated_credits = new_plan.monthly_quota_credits * remaining_percentage
                        user.credits_balance = prorated_credits
                    
                    session.add(user)
                    
                    # Add proration details to result
                    result["proration"] = {
                        "used_percentage": used_percentage,
                        "used_days": round(used_duration / (24 * 3600), 1),  # Convert seconds to days
                        "total_days": round(total_period_duration / (24 * 3600), 1),
                        "old_credits": active_period.quota_remaining if active_period else 0,
                        "new_credits": user.credits_balance,
                        "is_upgrade": is_upgrade
                    }
                    
                    # If this was an upgrade, log it
                    if is_upgrade:
                        logger.info(f"User {user.id} upgraded from {result['old_plan']} to {result['new_plan']}")
                    else:
                        logger.info(f"User {user.id} downgraded from {result['old_plan']} to {result['new_plan']}")
                        
                else:
                    # No active period - create a new one
                    new_period = await self.create_new_billing_period(
                        session=session,
                        user=user,
                        plan=new_plan
                    )
                    
                result["success"] = True
                result["new_period_id"] = str(new_period.id)
                    
            return result
                
        except Exception as e:
            logger.error(f"Error in change_user_plan: {e}")
            result["error"] = str(e)
            return result

# Global instance for singleton access
_billing_cycle_manager = None

def get_billing_cycle_manager() -> BillingCycleManager:
    """Get the global billing cycle manager instance."""
    global _billing_cycle_manager
    if _billing_cycle_manager is None:
        _billing_cycle_manager = BillingCycleManager()
    return _billing_cycle_manager 