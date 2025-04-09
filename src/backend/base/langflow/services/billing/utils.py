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


async def create_default_subscription_plans(session: AsyncSession) -> Dict[str, SubscriptionPlan]:
    """Create default subscription plans if they don't exist."""
    # Check if any plans exist
    existing_plans_result = await session.exec(select(SubscriptionPlan))
    existing_plans = existing_plans_result.all()
    if existing_plans:
        return {plan.name: plan for plan in existing_plans}
    
    # Create default plans
    plans = {
        "free": SubscriptionPlan(
            name="Free",
            description="Basic plan with limited resources",
            monthly_quota_credits=10.0,
            max_flows=3,
            max_flow_runs_per_day=10,
            max_concurrent_flows=1,
            max_kb_storage_mb=5,
            max_kbs_per_user=1,
            max_kb_entries_per_kb=100,
            max_tokens_per_kb_entry=1000,
            max_kb_queries_per_day=10,
            allowed_models=["gpt-3.5-turbo"],
            allowed_premium_tools={},
            price_monthly_usd=0.0,
            price_yearly_usd=0.0,
            features={"basic_templates": True, "community_support": True},
            overage_price_per_credit=0.0,
            allows_overage=False,
            trial_days=0,
            is_active=True,
        ),
        "starter": SubscriptionPlan(
            name="Starter",
            description="Good for individuals and small projects",
            monthly_quota_credits=100.0,
            max_flows=10,
            max_flow_runs_per_day=50,
            max_concurrent_flows=2,
            max_kb_storage_mb=100,
            max_kbs_per_user=5,
            max_kb_entries_per_kb=500,
            max_tokens_per_kb_entry=2000,
            max_kb_queries_per_day=100,
            allowed_models=["gpt-3.5-turbo", "gpt-4", "claude-3-sonnet"],
            allowed_premium_tools={},
            price_monthly_usd=19.99,
            price_yearly_usd=199.90,
            features={
                "priority_support": True,
                "all_templates": True,
                "community_support": True,
            },
            overage_price_per_credit=0.01,
            allows_overage=True,
            trial_days=14,
            is_active=True,
        ),
        "pro": SubscriptionPlan(
            name="Professional",
            description="For professional users with higher demands",
            monthly_quota_credits=500.0,
            max_flows=50,
            max_flow_runs_per_day=0,  # unlimited
            max_concurrent_flows=5,
            max_kb_storage_mb=500,
            max_kbs_per_user=20,
            max_kb_entries_per_kb=1000,
            max_tokens_per_kb_entry=4000,
            max_kb_queries_per_day=0,  # unlimited
            allowed_models=["gpt-3.5-turbo", "gpt-4", "gpt-4o", "claude-3-sonnet", "claude-3-opus"],
            allowed_premium_tools={"google_search": True, "alpha_vantage": True},
            price_monthly_usd=49.99,
            price_yearly_usd=499.90,
            features={
                "priority_support": True,
                "all_templates": True,
                "custom_domain": True,
                "advanced_analytics": True
            },
            overage_price_per_credit=0.01,
            allows_overage=True,
            trial_days=14,
            is_active=True,
        ),
        "enterprise": SubscriptionPlan(
            name="Enterprise",
            description="For organizations with advanced needs",
            monthly_quota_credits=2000.0,
            max_flows=0,  # unlimited
            max_flow_runs_per_day=0,  # unlimited
            max_concurrent_flows=20,
            max_kb_storage_mb=5000,
            max_kbs_per_user=0,
            max_kb_entries_per_kb=0,
            max_tokens_per_kb_entry=0,
            max_kb_queries_per_day=0,  # unlimited
            allowed_models=[],  # all models
            allowed_premium_tools={},
            price_monthly_usd=199.99,
            price_yearly_usd=1999.90,
            features={
                "priority_support": True,
                "all_templates": True,
                "custom_domain": True,
                "advanced_analytics": True,
                "sso_integration": True,
                "dedicated_support": True
            },
            allows_overage=True,
            overage_price_per_credit=0.008,
            trial_days=30,
            is_active=True,
        )
    }
    
    # Add plans to the session
    for plan in plans.values():
        session.add(plan)
    
    await session.commit()
    
    # Refresh plans to get their IDs
    for plan in plans.values():
        await session.refresh(plan)
    
    return plans 