"""Service for managing billing cycles and automatic renewal."""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple, Any
from uuid import UUID
from loguru import logger
from sqlmodel import Session, select
import asyncio
import stripe

from langflow.services.database.models.billing.models import (
    BillingPeriod,
    SubscriptionPlan,
    get_next_billing_cycle,
    Invoice
)
from langflow.services.database.models.user import User
from langflow.services.deps import get_session, session_scope, get_stripe_service


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
                    
                    # Also handle unpaid invoices
                    await self.handle_unpaid_invoices()
                
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
            "invoiced": 0,
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
                        
                        # Generate invoice for the expired period
                        if not period.invoiced:
                            invoice_result = await self.generate_invoice_for_period(session, period, user)
                            if invoice_result.get("success"):
                                stats["invoiced"] += 1
                                stats["details"].append({
                                    "period_id": str(period.id),
                                    "user_id": str(user.id),
                                    "status": "invoiced",
                                    "invoice_id": invoice_result.get("invoice_id"),
                                    "amount": invoice_result.get("amount")
                                })
                            else:
                                stats["details"].append({
                                    "period_id": str(period.id),
                                    "user_id": str(user.id),
                                    "status": "invoice_failed",
                                    "reason": invoice_result.get("error")
                                })
                        
                        # Check if user subscription should continue
                        if user.subscription_status != "active":
                            # Mark expired period as inactive
                            period.status = "inactive"
                            session.add(period)
                            stats["canceled"] += 1
                            stats["details"].append({
                                "period_id": str(period.id),
                                "user_id": str(user.id),
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
        
        logger.info(f"Completed billing period renewal: {stats['renewed']} renewed, {stats['invoiced']} invoiced, {stats['errors']} errors")
        return stats
    
    async def generate_invoice_for_period(
        self, 
        session: Session, 
        period: BillingPeriod, 
        user: User
    ) -> Dict[str, Any]:
        """
        Generate a Stripe invoice for an expired billing period.
        This handles both the subscription fee and any overages.
        
        Args:
            session: Database session
            period: The billing period to invoice
            user: The user associated with the billing period
            
        Returns:
            Dictionary with invoice generation results
        """
        result = {
            "success": False,
            "period_id": str(period.id),
            "user_id": str(user.id)
        }
        
        try:
            # If already invoiced, skip
            if period.invoiced:
                result["success"] = True
                result["status"] = "already_invoiced"
                return result
            
            # Get Stripe service
            stripe_service = get_stripe_service()
            
            # Check if user has Stripe customer ID
            if not user.stripe_customer_id:
                result["error"] = "User has no Stripe customer ID"
                return result
            
            # Get subscription plan
            plan = None
            if period.subscription_plan_id:
                plan = await session.get(SubscriptionPlan, period.subscription_plan_id)
            
            if not plan:
                result["error"] = "No subscription plan found for billing period"
                return result
            
            # Calculate total invoice amount
            base_amount = 0
            overage_amount = 0
            
            # If this was a partial period (due to plan change), prorate the base amount
            if period.is_plan_change:
                # Calculate period duration in days
                start_date = period.start_date
                if start_date.tzinfo is None:
                    start_date = start_date.replace(tzinfo=timezone.utc)
                
                end_date = period.end_date
                if end_date.tzinfo is None:
                    end_date = end_date.replace(tzinfo=timezone.utc)
                
                period_days = (end_date - start_date).days + 1
                
                # Prorate monthly subscription cost based on days
                base_amount = (plan.price_monthly_usd / 30) * period_days
            else:
                # Use full monthly price
                base_amount = plan.price_monthly_usd
            
            # Add overage costs if any
            if period.overage_credits > 0 and plan.allows_overage:
                overage_amount = period.overage_credits * plan.overage_price_per_credit
                
                # Cap overage to the configured limit if overage limiting is enabled
                if period.is_overage_limited and overage_amount > period.overage_limit_usd:
                    overage_amount = period.overage_limit_usd
            
            # Total amount for invoice
            total_amount = base_amount + overage_amount
            
            # Round to 2 decimal places
            total_amount = round(total_amount, 2)
            
            # Skip if amount is zero
            if total_amount <= 0:
                result["success"] = True
                result["status"] = "zero_amount"
                result["amount"] = 0
                
                # Mark period as invoiced
                period.invoiced = True
                session.add(period)
                return result
            
            # Create line items for Stripe invoice
            invoice_items = []
            
            # Add base subscription line item
            if base_amount > 0:
                subscription_description = f"{plan.name} Plan - {period.start_date.strftime('%Y-%m-%d')} to {period.end_date.strftime('%Y-%m-%d')}"
                
                base_invoice_item = await stripe_service._make_request(
                    stripe.InvoiceItem.create,
                    customer=user.stripe_customer_id,
                    amount=int(base_amount * 100),  # Convert to cents
                    currency="usd",
                    description=subscription_description
                )
                
                invoice_items.append(base_invoice_item.id)
            
            # Add overage line item if applicable
            if overage_amount > 0:
                overage_description = f"Usage Overage - {period.overage_credits} credits at ${plan.overage_price_per_credit} each"
                
                overage_invoice_item = await stripe_service._make_request(
                    stripe.InvoiceItem.create,
                    customer=user.stripe_customer_id,
                    amount=int(overage_amount * 100),  # Convert to cents
                    currency="usd",
                    description=overage_description
                )
                
                invoice_items.append(overage_invoice_item.id)
            
            # Generate the invoice in Stripe
            stripe_invoice = await stripe_service._make_request(
                stripe.Invoice.create,
                customer=user.stripe_customer_id,
                auto_advance=True,  # Finalize the invoice and attempt payment
                metadata={
                    "billing_period_id": str(period.id),
                    "user_id": str(user.id)
                }
            )
            
            # Create local invoice record
            invoice = Invoice(
                user_id=user.id,
                billing_period_id=period.id,
                amount=total_amount,
                status="pending" if stripe_invoice.status == "draft" else stripe_invoice.status,
                stripe_invoice_id=stripe_invoice.id,
                stripe_invoice_url=stripe_invoice.hosted_invoice_url
            )
            
            session.add(invoice)
            
            # Mark period as invoiced
            period.invoiced = True
            session.add(period)
            
            # Send invoice to customer
            finalized_invoice = await stripe_service._make_request(
                stripe.Invoice.finalize_invoice,
                stripe_invoice.id
            )
            
            invoice.stripe_invoice_url = finalized_invoice.hosted_invoice_url
            session.add(invoice)
            
            # Return success
            result["success"] = True
            result["invoice_id"] = stripe_invoice.id
            result["amount"] = total_amount
            result["base_amount"] = base_amount
            result["overage_amount"] = overage_amount
            result["invoice_url"] = finalized_invoice.hosted_invoice_url
            
            logger.info(f"Generated invoice {stripe_invoice.id} for user {user.id}, amount: ${total_amount}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating invoice for period {period.id}: {e}")
            result["error"] = str(e)
            return result
    
    async def create_new_billing_period(
        self,
        session: Session,
        user: User,
        plan: SubscriptionPlan,
        previous_period: Optional[BillingPeriod] = None,
        previous_plan_id: Optional[UUID] = None
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
        
        # Determine if this is a plan change
        is_plan_change = previous_plan_id is not None
        
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
            is_plan_change=is_plan_change,
            previous_plan_id=previous_plan_id,  # Use the provided previous_plan_id
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
                
                # Store old plan ID before updating user
                old_plan_id = user.subscription_plan_id
                
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
                        previous_plan_id=old_plan_id,  # Set the previous plan ID on the new period
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

    async def handle_unpaid_invoices(self) -> Dict[str, Any]:
        """
        Find and process unpaid invoices that have been open for too long.
        Organizations can configure how to handle unpaid invoices:
        - Suspend user access
        - Send reminders
        - Cancel subscription
        """
        logger.info("Processing unpaid invoices")
        
        stats = {
            "processed": 0,
            "paid": 0,
            "suspended": 0,
            "canceled": 0,
            "errors": 0,
            "details": []
        }
        
        try:
            async with session_scope() as session:
                # Find invoices that are still pending/unpaid
                # And were created more than X days ago (e.g., 7 days)
                grace_period_days = 7  # Could be configurable
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=grace_period_days)
                
                # Query for overdue invoices
                unpaid_invoices_query = select(Invoice).where(
                    Invoice.status.in_(["pending", "open", "uncollectible"]),
                    Invoice.created_at < cutoff_date
                )
                
                unpaid_invoices = (await session.exec(unpaid_invoices_query)).all()
                stats["processed"] = len(unpaid_invoices)
                
                logger.info(f"Found {len(unpaid_invoices)} unpaid invoices overdue by {grace_period_days}+ days")
                
                # Get Stripe service
                stripe_service = get_stripe_service()
                
                for invoice in unpaid_invoices:
                    try:
                        # Get the user
                        user = await session.get(User, invoice.user_id)
                        if not user:
                            logger.error(f"User {invoice.user_id} not found for invoice {invoice.id}")
                            stats["errors"] += 1
                            continue
                            
                        # Check Stripe status (it might have been paid but our records aren't updated)
                        if invoice.stripe_invoice_id:
                            try:
                                stripe_invoice = await stripe_service._make_request(
                                    stripe.Invoice.retrieve,
                                    invoice.stripe_invoice_id
                                )
                                
                                if stripe_invoice.status == "paid":
                                    # Update our records
                                    invoice.status = "paid"
                                    invoice.paid_at = datetime.now(timezone.utc)
                                    session.add(invoice)
                                    
                                    stats["paid"] += 1
                                    stats["details"].append({
                                        "invoice_id": str(invoice.id),
                                        "user_id": str(user.id),
                                        "status": "reconciled",
                                        "amount": invoice.amount
                                    })
                                    continue
                            except Exception as e:
                                logger.warning(f"Error checking Stripe invoice {invoice.stripe_invoice_id}: {e}")
                        
                        # Invoice is truly unpaid - take action based on policy
                        # Option 1: Suspend user access
                        if user.subscription_status == "active":
                            user.subscription_status = "past_due"
                            session.add(user)
                            
                            stats["suspended"] += 1
                            stats["details"].append({
                                "invoice_id": str(invoice.id),
                                "user_id": str(user.id),
                                "status": "suspended",
                                "amount": invoice.amount
                            })
                            
                            # Could trigger notification/email to user here
                        
                        # Option 2: For very old unpaid invoices, cancel subscription
                        # This would be for invoices that are extremely overdue (e.g., 30+ days)
                        extreme_overdue_days = 30
                        extreme_cutoff = datetime.now(timezone.utc) - timedelta(days=extreme_overdue_days)
                        
                        if invoice.created_at < extreme_cutoff and user.subscription_status == "past_due":
                            if user.stripe_subscription_id:
                                # Cancel the subscription in Stripe
                                try:
                                    await stripe_service._make_request(
                                        stripe.Subscription.delete,
                                        user.stripe_subscription_id
                                    )
                                    
                                    # Update user record
                                    user.subscription_status = "canceled"
                                    session.add(user)
                                    
                                    stats["canceled"] += 1
                                    stats["details"].append({
                                        "invoice_id": str(invoice.id),
                                        "user_id": str(user.id),
                                        "status": "canceled",
                                        "amount": invoice.amount,
                                        "days_overdue": extreme_overdue_days
                                    })
                                except Exception as e:
                                    logger.error(f"Error canceling subscription for user {user.id}: {e}")
                                    stats["errors"] += 1
                            
                    except Exception as e:
                        logger.error(f"Error processing unpaid invoice {invoice.id}: {e}")
                        stats["errors"] += 1
                        stats["details"].append({
                            "invoice_id": str(invoice.id),
                            "status": "error",
                            "reason": str(e)
                        })
            
            await session.commit()
            logger.info(f"Completed unpaid invoice processing: {stats['paid']} reconciled, {stats['suspended']} accounts suspended")
            return stats
            
        except Exception as e:
            logger.error(f"Error in handle_unpaid_invoices: {e}")
            stats["global_error"] = str(e)
            return stats
    
    async def manually_generate_invoice(self, user_id: UUID, description: str = None, amount: float = 0.0, items: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Manually generate an invoice for a user.
        This can be used for one-time charges outside the regular billing cycle.
        
        Args:
            user_id: The user ID to invoice
            description: Optional overall invoice description
            amount: Total amount to invoice (ignored if items provided)
            items: List of line items, each with 'description' and 'amount' keys
            
        Returns:
            Dictionary with invoice generation results
        """
        result = {
            "success": False,
            "user_id": str(user_id)
        }
        
        try:
            async with session_scope() as session:
                # Get the user
                user = await session.get(User, user_id)
                if not user:
                    result["error"] = f"User {user_id} not found"
                    return result
                
                # Check if user has Stripe customer ID
                if not user.stripe_customer_id:
                    result["error"] = "User has no Stripe customer ID"
                    return result
                
                # Get Stripe service
                stripe_service = get_stripe_service()
                
                # Prepare line items
                line_items = []
                total_amount = 0.0
                
                if items:
                    # Use provided line items
                    for item in items:
                        item_desc = item.get("description", "Service charge")
                        item_amount = item.get("amount", 0.0)
                        
                        if item_amount <= 0:
                            continue
                            
                        # Create Stripe invoice item
                        invoice_item = await stripe_service._make_request(
                            stripe.InvoiceItem.create,
                            customer=user.stripe_customer_id,
                            amount=int(item_amount * 100),  # Convert to cents
                            currency="usd",
                            description=item_desc
                        )
                        
                        line_items.append(invoice_item.id)
                        total_amount += item_amount
                else:
                    # Use single amount
                    if amount <= 0:
                        result["error"] = "Invoice amount must be greater than zero"
                        return result
                        
                    invoice_item = await stripe_service._make_request(
                        stripe.InvoiceItem.create,
                        customer=user.stripe_customer_id,
                        amount=int(amount * 100),  # Convert to cents
                        currency="usd",
                        description=description or "One-time charge"
                    )
                    
                    line_items.append(invoice_item.id)
                    total_amount = amount
                
                # Create the invoice in Stripe
                stripe_invoice = await stripe_service._make_request(
                    stripe.Invoice.create,
                    customer=user.stripe_customer_id,
                    auto_advance=True,  # Finalize and try to collect
                    description=description,
                    metadata={
                        "user_id": str(user.id),
                        "type": "manual"
                    }
                )
                
                # Create local invoice record
                invoice = Invoice(
                    user_id=user.id,
                    amount=total_amount,
                    status="pending" if stripe_invoice.status == "draft" else stripe_invoice.status,
                    stripe_invoice_id=stripe_invoice.id,
                    stripe_invoice_url=stripe_invoice.hosted_invoice_url
                )
                
                # Get user's current billing period if any
                current_period_query = select(BillingPeriod).where(
                    BillingPeriod.user_id == user_id,
                    BillingPeriod.status == "active"
                )
                current_period = (await session.exec(current_period_query)).first()
                
                if current_period:
                    invoice.billing_period_id = current_period.id
                
                session.add(invoice)
                
                # Finalize and send the invoice
                finalized_invoice = await stripe_service._make_request(
                    stripe.Invoice.finalize_invoice,
                    stripe_invoice.id
                )
                
                invoice.stripe_invoice_url = finalized_invoice.hosted_invoice_url
                session.add(invoice)
                
                await session.commit()
                
                # Return success
                result["success"] = True
                result["invoice_id"] = stripe_invoice.id
                result["amount"] = total_amount
                result["invoice_url"] = finalized_invoice.hosted_invoice_url
                
                logger.info(f"Generated manual invoice {stripe_invoice.id} for user {user.id}, amount: ${total_amount}")
                
                return result
                
        except Exception as e:
            logger.error(f"Error generating manual invoice for user {user_id}: {e}")
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