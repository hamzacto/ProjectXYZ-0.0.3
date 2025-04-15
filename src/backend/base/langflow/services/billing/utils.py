from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any
from uuid import UUID

from langflow.services.database.models.billing.models import (
    get_next_billing_cycle,
    BillingPeriod,
    SubscriptionPlan
)
from langflow.services.database.models.user import User
from langflow.services.database.models.flow import Flow
from sqlmodel import Session, select, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

async def get_user_quota(user_id: UUID, session: AsyncSession) -> float:
    """Get user's current quota with all overrides applied."""
    user = (await session.exec(select(User).where(User.id == user_id))).first()
    if not user:
        return 0.0
        
    # Get active billing period
    billing_period = (await session.exec(
        select(BillingPeriod)
        .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
        .order_by(BillingPeriod.start_date.desc())
    )).first()
    
    if not billing_period:
        # No active billing period, fall back to subscription plan
        if user.subscription_plan_id:
            plan = (await session.exec(select(SubscriptionPlan).where(
                SubscriptionPlan.id == user.subscription_plan_id
            ))).first()
            return plan.monthly_quota_credits if plan else 0.0
        return 0.0
    
    # Check for override in billing period
    if billing_period.quota_override is not None:
        return billing_period.quota_override
    
    # Use billing period's subscription plan (handles plan changes)
    if billing_period.subscription_plan_id:
        plan = (await session.exec(select(SubscriptionPlan).where(
            SubscriptionPlan.id == billing_period.subscription_plan_id
        ))).first()
        return plan.monthly_quota_credits if plan else 0.0
    
    # Fall back to user's subscription plan
    if user.subscription_plan_id:
        plan = (await session.exec(select(SubscriptionPlan).where(
            SubscriptionPlan.id == user.subscription_plan_id
        ))).first()
        return plan.monthly_quota_credits if plan else 0.0
    
    return 0.0


async def get_quota_remaining(user_id: UUID, session: AsyncSession) -> float:
    """Get user's remaining quota for the current period."""
    # Get active billing period
    billing_period = (await session.exec(
        select(BillingPeriod)
        .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
        .order_by(BillingPeriod.start_date.desc())
    )).first()
    
    if not billing_period:
        # No active billing period, create one
        billing_period = await create_billing_period(user_id, session)
        if not billing_period:
            return 0.0
    
    return billing_period.quota_remaining


async def check_user_limits(user_id: UUID, session: AsyncSession, operation_type: str = "flow_run") -> Tuple[bool, str]:
    """
    Check if user is within their plan limits for a specific operation.
    Returns (allowed, reason) tuple.
    """
    user = (await session.exec(select(User).where(User.id == user_id))).first()
    if not user:
        return False, "User not found"
        
    if not user.subscription_plan_id:
        # Check if user is in trial
        if user.subscription_status == "trial":
            if not user.trial_end_date or user.trial_end_date < datetime.now(timezone.utc):
                return False, "Trial period has expired"
            # Trial is active, allow operation
            return True, "Trial active"
        return False, "No active subscription plan"
    
    plan = (await session.exec(select(SubscriptionPlan).where(
        SubscriptionPlan.id == user.subscription_plan_id,
        SubscriptionPlan.is_active == True
    ))).first()
    
    if not plan:
        return False, "Subscription plan not found or inactive"
    
    # Check operation-specific limits
    if operation_type == "flow_run":
        # Reset daily counter if needed
        now = datetime.now(timezone.utc)
        if not user.daily_flow_runs_reset_at or (now - user.daily_flow_runs_reset_at).days > 0:
            user.daily_flow_runs = 0
            user.daily_flow_runs_reset_at = now
            session.add(user)
            await session.commit()
        
        # Check daily limit
        if plan.max_flow_runs_per_day > 0 and (user.daily_flow_runs or 0) >= plan.max_flow_runs_per_day:
            return False, f"Daily flow run limit of {plan.max_flow_runs_per_day} reached"
    
    elif operation_type == "create_flow":
        # Check max flows limit
        if plan.max_flows > 0:
            # Need to count flows asynchronously
            from sqlalchemy import func
            flow_count_result = await session.exec(select(func.count(Flow.id)).where(Flow.user_id == user_id))
            flow_count = flow_count_result.scalar_one()
            if flow_count >= plan.max_flows:
                return False, f"Maximum flow limit of {plan.max_flows} reached"
    
    elif operation_type == "kb_query":
        # Reset daily counter if needed
        now = datetime.now(timezone.utc)
        if not user.daily_kb_queries_reset_at or (now - user.daily_kb_queries_reset_at).days > 0:
            user.daily_kb_queries = 0
            user.daily_kb_queries_reset_at = now
            session.add(user)
            await session.commit()
        
        # Check daily limit
        if plan.max_kb_queries_per_day > 0 and (user.daily_kb_queries or 0) >= plan.max_kb_queries_per_day:
            return False, f"Daily KB query limit of {plan.max_kb_queries_per_day} reached"
    
    # Check quota
    active_period = (await session.exec(
        select(BillingPeriod)
        .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
    )).first()
    
    if not active_period:
        # Create billing period if none exists
        active_period = await create_billing_period(user_id, session)
        if not active_period:
            return False, "Could not create billing period"
    
    if (active_period.quota_remaining or 0) <= 0 and not plan.allows_overage:
        return False, "Credit quota exhausted"
    
    # All checks passed
    return True, "OK"


async def create_billing_period(user_id: UUID, session: AsyncSession, start_date=None) -> Optional[BillingPeriod]:
    """
    Create a new billing period for a user with proper billing cycle dates.
    """
    user = (await session.exec(select(User).where(User.id == user_id))).first()
    if not user:
        return None
    
    # Get user's billing anchor day
    billing_day = user.billing_day or 1
    
    # Calculate billing period dates
    start_date, end_date = get_next_billing_cycle(start_date, billing_day)
    
    # Get user's subscription plan
    plan = None
    if user.subscription_plan_id:
        plan = (await session.exec(select(SubscriptionPlan).where(
            SubscriptionPlan.id == user.subscription_plan_id
        ))).first()
    
    # Calculate quota
    quota = plan.monthly_quota_credits if plan else 0.0
    
    # Create billing period
    billing_period = BillingPeriod(
        user_id=user_id,
        subscription_plan_id=user.subscription_plan_id,
        start_date=start_date,
        end_date=end_date,
        status="active",
        quota_remaining=quota
    )
    
    session.add(billing_period)
    await session.commit()
    await session.refresh(billing_period)
    return billing_period


async def change_subscription_plan(
    user_id: UUID, 
    new_plan_id: UUID, 
    session: AsyncSession, 
    prorate: bool = True
) -> Optional[BillingPeriod]:
    """Change a user's subscription plan, creating a new billing period with proper dates."""
    user = (await session.exec(select(User).where(User.id == user_id))).first()
    if not user:
        return None
    
    new_plan = (await session.exec(select(SubscriptionPlan).where(
        SubscriptionPlan.id == new_plan_id,
        SubscriptionPlan.is_active == True
    ))).first()
    
    if not new_plan:
        return None
    
    old_plan_id = user.subscription_plan_id
    
    # Update user's plan
    user.subscription_plan_id = new_plan_id
    user.subscription_status = "active"
    user.subscription_start_date = datetime.now(timezone.utc)
    
    # If coming from trial, mark trial as converted
    if user.trial_end_date and user.trial_end_date > datetime.now(timezone.utc):
        user.trial_converted = True
    
    # Get current billing period
    current_period = (await session.exec(
        select(BillingPeriod)
        .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
    )).first()
    
    now = datetime.now(timezone.utc)
    
    if current_period and prorate:
        # Mark current period as closed
        current_period.status = "closed"
        
        # Calculate prorated quota
        total_days = (current_period.end_date - current_period.start_date).days
        used_days = (now - current_period.start_date).days
        remaining_days = max(0, total_days - used_days)
        
        if total_days > 0:
            prorated_quota = (new_plan.monthly_quota_credits / total_days) * remaining_days
        else:
            prorated_quota = new_plan.monthly_quota_credits
        
        # Use current period's end date for consistency
        end_date = current_period.end_date
        
        # Create new billing period with new plan, starting now until original end date
        new_period = BillingPeriod(
            user_id=user_id,
            subscription_plan_id=new_plan_id,
            start_date=now,
            end_date=end_date,
            status="active",
            is_plan_change=True,
            previous_plan_id=old_plan_id,
            quota_override=prorated_quota,
            quota_remaining=prorated_quota
        )
    else:
        # Calculate proper billing cycle based on user's billing day
        start_date, end_date = get_next_billing_cycle(now, user.billing_day)
        
        # Create new billing period with new plan
        new_period = BillingPeriod(
            user_id=user_id,
            subscription_plan_id=new_plan_id,
            start_date=start_date,
            end_date=end_date,
            status="active",
            is_plan_change=True if old_plan_id else False,
            previous_plan_id=old_plan_id if old_plan_id else None,
            quota_remaining=new_plan.monthly_quota_credits
        )
    
    session.add(new_period)
    await session.commit()
    await session.refresh(new_period)
    return new_period


async def renew_billing_period(
    self,
    billing_period_id: UUID,
    session = None
) -> Optional[BillingPeriod]:
    """
    Renew a billing period and handle Stripe integration for subscription renewal.
    
    Args:
        billing_period_id: ID of the billing period to renew
        session: Optional database session
        
    Returns:
        Newly created billing period or None if renewal fails
    """
    from langflow.services.deps import get_stripe_service, session_scope
    
    external_session = session is not None
    
    try:
        if not external_session:
            # Create a new session if one wasn't provided
            async with session_scope() as session:
                return await self._renew_billing_period(billing_period_id, session)
        else:
            # Use the provided session
            return await self._renew_billing_period(billing_period_id, session)
    except Exception as e:
        logger.error(f"Error renewing billing period {billing_period_id}: {e}")
        return None
        
async def _renew_billing_period(
    self,
    billing_period_id: UUID,
    session
) -> Optional[BillingPeriod]:
    """Internal implementation of billing period renewal with Stripe integration."""
    from langflow.services.deps import get_stripe_service
    from langflow.services.database.models.billing.models import BillingPeriod, get_next_billing_cycle
    from langflow.services.database.models.user import User
    
    # Get the billing period
    billing_period = await session.get(BillingPeriod, billing_period_id)
    if not billing_period:
        logger.error(f"Billing period {billing_period_id} not found")
        return None
        
    # Get the user
    user = await session.get(User, billing_period.user_id)
    if not user:
        logger.error(f"User {billing_period.user_id} not found")
        return None
        
    # Get the subscription plan
    plan = None
    if user.subscription_plan_id:
        plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
        
    if not plan:
        logger.error(f"No subscription plan found for user {user.id}")
        return None
        
    # Verify subscription status with Stripe
    stripe_service = get_stripe_service()
    
    # Only verify with Stripe if the user has a Stripe subscription
    if user.stripe_subscription_id:
        stripe_status = await stripe_service.get_subscription_status(user.stripe_subscription_id)
        
        if not stripe_status or stripe_status not in ["active", "trialing"]:
            logger.warning(f"User {user.id} Stripe subscription is not active: {stripe_status}")
            # Update user subscription status to match Stripe
            user.subscription_status = stripe_status or "inactive"
            session.add(user)
            
            # Mark current billing period as inactive
            billing_period.status = "inactive"
            session.add(billing_period)
            await session.commit()
            
            return None
            
    # Calculate overage for current period
    if billing_period.overage_credits > 0 and plan.allows_overage and not billing_period.invoiced:
        # Only create invoice if we have overage and the plan allows it
        overage_cost = billing_period.overage_credits * plan.overage_price_per_credit
        billing_period.overage_cost = overage_cost
        
        # Create invoice in Stripe if needed
        if overage_cost > 0 and user.stripe_customer_id:
            stripe_invoice_id = await stripe_service.create_invoice(user, billing_period)
            
            if stripe_invoice_id:
                # Create local invoice record
                from langflow.services.database.models.billing.models import Invoice
                
                invoice = Invoice(
                    user_id=user.id,
                    billing_period_id=billing_period.id,
                    amount=overage_cost,
                    status="pending",
                    stripe_invoice_id=stripe_invoice_id
                )
                
                session.add(invoice)
                billing_period.invoiced = True
                session.add(billing_period)
                
    # Mark current period as inactive
    billing_period.status = "inactive"
    session.add(billing_period)
    
    # Calculate rollover credits if applicable
    rollover_credits = 0.0
    if billing_period.quota_remaining > 0 and plan.allows_rollover:
        rollover_credits = billing_period.quota_remaining
        logger.info(f"Rolling over {rollover_credits} credits for user {user.id}")
        
    # Create new billing period
    # Use the next billing cycle dates
    billing_day = user.billing_day or 1  # Default to 1st of month if not set
    next_start, next_end = get_next_billing_cycle(
        start_date=billing_period.end_date,
        billing_day=billing_day
    )
    
    # Total quota includes base quota plus rollover
    total_quota = plan.monthly_quota_credits + rollover_credits
    
    new_period = BillingPeriod(
        user_id=user.id,
        start_date=next_start,
        end_date=next_end,
        subscription_plan_id=plan.id,
        status="active",
        quota_used=0.0,
        quota_remaining=total_quota,
        rollover_credits=rollover_credits,
        overage_credits=0.0,
        overage_cost=0.0,
        overage_limit_usd=plan.default_overage_limit_usd,
        is_overage_limited=True,
        has_reached_limit=False,
        is_plan_change=False,
        previous_plan_id=None,
        invoiced=False
    )
    
    session.add(new_period)
    
    # Update user's credit balance
    user.credits_balance = total_quota
    session.add(user)
    
    await session.commit()
    await session.refresh(new_period)
    
    logger.info(f"Created new billing period {new_period.id} for user {user.id}")
    return new_period


async def cancel_subscription(self, user_id: UUID) -> Dict[str, Any]:
    """
    Cancel a user's subscription.
    
    Args:
        user_id: ID of the user whose subscription to cancel
        
    Returns:
        Dictionary with status and message
    """
    from langflow.services.deps import get_stripe_service, session_scope
    
    result = {
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
            
            stripe_service = get_stripe_service()
            
            # Cancel in Stripe if needed
            if user.stripe_subscription_id:
                canceled = await stripe_service.cancel_subscription(user)
                if not canceled:
                    result["message"] = "Failed to cancel subscription in Stripe"
                    return result
            
            # Update user subscription status
            user.subscription_status = "canceled"
            session.add(user)
            
            # Get current active billing period
            active_period_query = select(BillingPeriod).where(
                BillingPeriod.user_id == user_id,
                BillingPeriod.status == "active"
            )
            active_period = (await session.exec(active_period_query)).first()
            
            if active_period:
                # Mark as canceled but let it run until the end
                active_period.status = "canceling"
                session.add(active_period)
            
            await session.commit()
            
            result["success"] = True
            result["message"] = "Subscription successfully canceled"
            return result
    
    except Exception as e:
        logger.error(f"Error canceling subscription for user {user_id}: {e}")
        result["message"] = f"Error: {str(e)}"
        return result

async def sync_with_stripe(self, user_id: UUID) -> Dict[str, Any]:
    """
    Synchronize a user's subscription status with Stripe.
    
    Args:
        user_id: ID of the user to synchronize
        
    Returns:
        Dictionary with status and message
    """
    from langflow.services.deps import get_stripe_service, session_scope
    
    result = {
        "success": False,
        "message": "",
        "changes": []
    }
    
    try:
        async with session_scope() as session:
            # Get the user
            user = await session.get(User, user_id)
            if not user:
                result["message"] = f"User {user_id} not found"
                return result
            
            stripe_service = get_stripe_service()
            
            if not user.stripe_customer_id:
                result["message"] = "User has no Stripe customer ID"
                return result
            
            changes = []
            
            # Sync subscription status
            if user.stripe_subscription_id:
                stripe_status = await stripe_service.get_subscription_status(user.stripe_subscription_id)
                
                if stripe_status and stripe_status != user.subscription_status:
                    # Update our status to match Stripe
                    old_status = user.subscription_status
                    user.subscription_status = stripe_status
                    session.add(user)
                    
                    changes.append(f"Updated subscription status from {old_status} to {stripe_status}")
            
            # Get active billing period
            active_period_query = select(BillingPeriod).where(
                BillingPeriod.user_id == user_id,
                BillingPeriod.status == "active"
            )
            active_period = (await session.exec(active_period_query)).first()
            
            # If status is not active but we have an active period, mark it accordingly
            if user.subscription_status not in ["active", "trialing"] and active_period:
                active_period.status = "canceling"
                session.add(active_period)
                changes.append("Marked billing period as canceling due to inactive subscription")
            
            await session.commit()
            
            result["success"] = True
            result["message"] = "Successfully synchronized with Stripe"
            result["changes"] = changes
            return result
    
    except Exception as e:
        logger.error(f"Error synchronizing with Stripe for user {user_id}: {e}")
        result["message"] = f"Error: {str(e)}"
        return result

async def load_stripe_product_ids_from_env(session) -> Dict[str, Any]:
    """
    Load Stripe product and price IDs from environment variables and
    update subscription plans in the database.
    
    Environment variables should be in the format:
    STRIPE_PRODUCT_ID_PLAN_NAME=prod_xyz
    STRIPE_PRICE_ID_PLAN_NAME=price_abc
    
    Where PLAN_NAME matches the name of the plan in the database (case insensitive).
    Example: STRIPE_PRODUCT_ID_PRO=prod_123456 for the "Pro" plan.
    """
    from langflow.services.database.models.billing.models import SubscriptionPlan
    import os
    from loguru import logger
    
    results = {
        "success": True,
        "updated": 0,
        "skipped": 0,
        "details": []
    }
    
    # Get all active subscription plans
    plans_query = select(SubscriptionPlan).where(SubscriptionPlan.is_active == True)
    plans = (await session.exec(plans_query)).all()
    
    # Map of lowercase plan names to plans
    plans_by_name = {plan.name.lower(): plan for plan in plans}
    
    # Find all environment variables for Stripe product IDs
    product_env_vars = {
        key.replace('STRIPE_PRODUCT_ID_', '').lower(): value
        for key, value in os.environ.items()
        if key.startswith('STRIPE_PRODUCT_ID_') and value
    }
    
    # Find all environment variables for Stripe price IDs
    price_env_vars = {
        key.replace('STRIPE_PRICE_ID_', '').lower(): value
        for key, value in os.environ.items()
        if key.startswith('STRIPE_PRICE_ID_') and value
    }
    
    # Update plans with environment variable values
    for plan_key, plan in plans_by_name.items():
        plan_env_key = plan_key.replace(' ', '_')  # Replace spaces with underscores for env var matching
        
        product_id = None
        price_id = None
        
        # Try exact match first
        if plan_env_key in product_env_vars:
            product_id = product_env_vars[plan_env_key]
        
        if plan_env_key in price_env_vars:
            price_id = price_env_vars[plan_env_key]
            
        # Try partial match if needed
        if not product_id or not price_id:
            for env_key in product_env_vars.keys():
                if env_key in plan_env_key or plan_env_key in env_key:
                    product_id = product_env_vars[env_key]
                    break
                    
            for env_key in price_env_vars.keys():
                if env_key in plan_env_key or plan_env_key in env_key:
                    price_id = price_env_vars[env_key]
                    break
        
        if product_id or price_id:
            updated = False
            
            if product_id and plan.stripe_product_id != product_id:
                plan.stripe_product_id = product_id
                updated = True
                
            if price_id and plan.stripe_default_price_id != price_id:
                plan.stripe_default_price_id = price_id
                updated = True
                
            if updated:
                session.add(plan)
                results["updated"] += 1
                results["details"].append({
                    "plan_id": str(plan.id),
                    "plan_name": plan.name,
                    "product_id": product_id,
                    "price_id": price_id,
                    "status": "updated"
                })
            else:
                results["skipped"] += 1
                results["details"].append({
                    "plan_id": str(plan.id),
                    "plan_name": plan.name,
                    "product_id": product_id,
                    "price_id": price_id,
                    "status": "unchanged"
                })
        else:
            results["skipped"] += 1
            results["details"].append({
                "plan_id": str(plan.id),
                "plan_name": plan.name,
                "status": "skipped",
                "reason": "No matching environment variables found"
            })
    
    # Commit changes
    await session.commit()
    
    if results["updated"] > 0:
        logger.info(f"Updated {results['updated']} subscription plans with Stripe IDs from environment variables")
    
    return results

