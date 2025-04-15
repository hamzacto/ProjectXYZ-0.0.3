"""API endpoints for billing operations."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlmodel import select
from pydantic import BaseModel

from langflow.services.auth.utils import get_current_active_user, get_current_active_superuser
from langflow.services.database.models.user import User
from langflow.services.database.models.billing.models import BillingPeriod, SubscriptionPlan
from langflow.api.utils import get_session, DbSession
from langflow.services.billing.cycle_manager import get_billing_cycle_manager
from langflow.services.billing.service import BillingService
from langflow.services.manager import service_manager
from langflow.services.schema import ServiceType


# API router
router = APIRouter(prefix="/billing", tags=["Billing"])


# Response models
class BillingPeriodResponse(BaseModel):
    id: str
    user_id: str
    start_date: str
    end_date: str
    status: str
    quota_used: float
    quota_remaining: float
    plan_name: Optional[str] = None


class UsageSummaryResponse(BaseModel):
    user_id: str
    period_days: int
    total_runs: int
    total_cost: float
    cost_breakdown: Dict[str, float]
    current_period: Dict[str, Any]


class SubscriptionPlanResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    monthly_quota_credits: float
    max_flows: int
    max_flow_runs_per_day: int
    max_concurrent_flows: int
    max_kb_storage_mb: int
    max_kbs_per_user: int
    max_kb_entries_per_kb: int
    max_tokens_per_kb_entry: int
    max_kb_queries_per_day: int
    allowed_models: Dict[str, bool]
    price_monthly_usd: float
    price_yearly_usd: float
    features: Dict[str, bool]
    allowed_premium_tools: Dict[str, bool]
    overage_price_per_credit: float
    default_overage_limit_usd: float
    allows_overage: bool
    allows_rollover: bool
    trial_days: int
    is_active: bool
    stripe_product_id: Optional[str] = None
    stripe_default_price_id: Optional[str] = None


# # API endpoints
# @router.get("/usage/summary", response_model=UsageSummaryResponse)
# async def get_usage_summary(
#     period_days: int = 30,
#     current_user: User = Depends(get_current_active_user),
#     session: DbSession = Depends(get_session),
# ) -> Dict[str, Any]:
#     """Get usage summary for the current user."""
#     billing_service = service_manager.get(ServiceType.BILLING_SERVICE)
#     if not billing_service:
#         raise HTTPException(status_code=503, detail="Billing service unavailable")
    
#     summary = await billing_service.get_user_usage_summary(user_id=current_user.id, period_days=period_days)
#     if "error" in summary:
#         raise HTTPException(status_code=500, detail=summary["error"])
    
#     return summary


@router.get("/subscription-plans", response_model=List[SubscriptionPlanResponse])
async def get_subscription_plans(
    session: DbSession,
    include_inactive: bool = False,
) -> List[Dict[str, Any]]:
    """Get all subscription plans available for purchase."""
    try:
        # Query for all active subscription plans
        if include_inactive:
            plans_query = select(SubscriptionPlan)
        else:
            plans_query = select(SubscriptionPlan).where(SubscriptionPlan.is_active == True)
        
        plans = (await session.exec(plans_query)).all()
        
        # Format plans for response
        result = []
        for plan in plans:
            result.append({
                "id": str(plan.id),
                "name": plan.name,
                "description": plan.description,
                "monthly_quota_credits": plan.monthly_quota_credits,
                "max_flows": plan.max_flows,
                "max_flow_runs_per_day": plan.max_flow_runs_per_day,
                "max_concurrent_flows": plan.max_concurrent_flows,
                "max_kb_storage_mb": plan.max_kb_storage_mb,
                "max_kbs_per_user": plan.max_kbs_per_user,
                "max_kb_entries_per_kb": plan.max_kb_entries_per_kb,
                "max_tokens_per_kb_entry": plan.max_tokens_per_kb_entry,
                "max_kb_queries_per_day": plan.max_kb_queries_per_day,
                "allowed_models": plan.allowed_models,
                "price_monthly_usd": plan.price_monthly_usd,
                "price_yearly_usd": plan.price_yearly_usd,
                "features": plan.features,
                "allowed_premium_tools": plan.allowed_premium_tools,
                "overage_price_per_credit": plan.overage_price_per_credit,
                "default_overage_limit_usd": plan.default_overage_limit_usd,
                "allows_overage": plan.allows_overage,
                "allows_rollover": plan.allows_rollover,
                "trial_days": plan.trial_days,
                "is_active": plan.is_active,
                "stripe_product_id": plan.stripe_product_id,
                "stripe_default_price_id": plan.stripe_default_price_id
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving subscription plans: {str(e)}")


@router.get("/periods/current", response_model=BillingPeriodResponse)
async def get_current_billing_period(
    session: DbSession,
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Get the current user's active billing period."""
    try:
        # Get the billing cycle manager
        manager = get_billing_cycle_manager()
        
        # Check and potentially create/renew billing period
        billing_period = await manager.check_user_billing_period(current_user.id)
        
        if not billing_period:
            raise HTTPException(status_code=404, detail="No active billing period found")
        
        # Get plan name if applicable
        plan_name = None
        if billing_period.subscription_plan_id:
            plan = await session.get(SubscriptionPlan, billing_period.subscription_plan_id)
            plan_name = plan.name if plan else None
        
        # Format response
        return {
            "id": str(billing_period.id),
            "user_id": str(billing_period.user_id),
            "start_date": billing_period.start_date.isoformat(),
            "end_date": billing_period.end_date.isoformat(),
            "status": billing_period.status,
            "quota_used": billing_period.quota_used,
            "quota_remaining": billing_period.quota_remaining,
            "plan_name": plan_name
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving billing period: {str(e)}")


@router.get("/periods/renew", response_model=Dict[str, Any])
async def renew_billing_period(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Manually renew the current user's billing period."""
    try:
        # Get the billing cycle manager
        manager = get_billing_cycle_manager()
        
        # Renew the billing period
        result = await manager.manually_renew_user_billing_period(current_user.id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renewing billing period: {str(e)}")


@router.post("/periods/process-expired", response_model=Dict[str, Any])
async def process_expired_billing_periods(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_superuser),
) -> Dict[str, Any]:
    """Process all expired billing periods - admin only."""
    try:
        # Get the billing cycle manager
        manager = get_billing_cycle_manager()
        
        # Run in background to avoid timeout for large operations
        background_tasks.add_task(manager.process_expired_billing_periods)
        
        return {
            "success": True,
            "message": "Processing expired billing periods in the background"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing expired periods: {str(e)}")


@router.get("/test/renew/{user_id}", response_model=Dict[str, Any])
async def test_renew_billing_period(
    user_id: UUID,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """
    Test endpoint to manually renew a user's billing period without authentication.
    This endpoint should ONLY be used for testing purposes.
    """
    try:
        # Get the billing cycle manager
        manager = get_billing_cycle_manager()
        
        # Renew the billing period for the specified user
        result = await manager.manually_renew_user_billing_period(user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renewing billing period: {str(e)}")


@router.get("/periods/history", response_model=List[BillingPeriodResponse])
async def get_billing_period_history(
    session: DbSession,
    current_user: User = Depends(get_current_active_user),
) -> List[Dict[str, Any]]:
    """Get the billing period history for the current user."""
    try:
        # Query for all billing periods for this user
        periods_query = select(BillingPeriod).where(
            BillingPeriod.user_id == current_user.id
        ).order_by(BillingPeriod.start_date.desc())
        
        periods = (await session.exec(periods_query)).all()
        
        # Build response
        result = []
        for period in periods:
            # Get plan name if applicable
            plan_name = None
            if period.subscription_plan_id:
                plan = await session.get(SubscriptionPlan, period.subscription_plan_id)
                plan_name = plan.name if plan else None
            
            result.append({
                "id": str(period.id),
                "user_id": str(period.user_id),
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
                "status": period.status,
                "quota_used": period.quota_used,
                "quota_remaining": period.quota_remaining,
                "plan_name": plan_name
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving billing history: {str(e)}")


class ChangePlanRequest(BaseModel):
    """Request model for changing subscription plan."""
    plan_id: str


@router.post("/plan/change", response_model=Dict[str, Any])
async def change_subscription_plan(
    session: DbSession,
    plan_request: ChangePlanRequest,
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Change the user's subscription plan with proration for the current billing period."""
    try:
        # Validate plan ID is valid UUID
        try:
            plan_id = UUID(plan_request.plan_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid plan ID format")
        
        # Check if plan exists
        plan = await session.get(SubscriptionPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Subscription plan not found")
        
        # Check if user already has this plan
        if current_user.subscription_plan_id == plan_id:
            return {
                "success": True,
                "message": f"You are already subscribed to the {plan.name} plan",
                "plan_name": plan.name,
                "no_change": True
            }
            
        # Get billing cycle manager and initiate plan change
        manager = get_billing_cycle_manager()
        result = await manager.change_user_plan(current_user.id, plan_id)
        
        if not result["success"]:
            raise HTTPException(
                status_code=400, 
                detail=result.get("error", "Failed to change subscription plan")
            )
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error changing subscription plan: {str(e)}"
        ) 