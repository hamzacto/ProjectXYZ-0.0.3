from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from langflow.services.auth.utils import get_current_active_user
from langflow.services.manager import service_manager
from langflow.services.schema import ServiceType
from langflow.services.database.utils import get_session
from langflow.services.database.models.user import User

router = APIRouter(tags=["Billing"], prefix="/billing")


class UsageSummaryResponse(BaseModel):
    """Usage summary response for the dashboard"""
    user_id: str
    period_days: int
    total_runs: int
    total_cost: float
    cost_breakdown: dict
    model_usage: dict
    current_period: dict


@router.get("/usage/summary")
async def get_usage_summary(
    period_days: int = 30,
    current_user: User = Depends(get_current_active_user),
) -> UsageSummaryResponse:
    """Get usage summary for current user."""
    try:
        billing_service = service_manager.get(ServiceType.BILLING_SERVICE)
        if not billing_service:
            raise HTTPException(status_code=501, detail="Billing service not available")
        
        summary = billing_service.get_user_usage_summary(
            user_id=current_user.id,
            period_days=period_days
        )
        
        if "error" in summary:
            raise HTTPException(status_code=500, detail=summary["error"])
            
        return UsageSummaryResponse(**summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class QuotaResponse(BaseModel):
    """User's quota information"""
    total: float
    used: float
    remaining: float
    rollover_credits: float = 0.0  # Credits rolled over from previous period
    overage: float
    overage_cost: float
    period_start: str
    period_end: str
    plan_allows_rollover: bool = False  # Whether the user's plan allows rollover


@router.get("/quota")
async def get_quota(
    current_user: User = Depends(get_current_active_user),
) -> QuotaResponse:
    """Get current user's quota information."""
    from langflow.services.billing.utils import get_user_quota, get_quota_remaining
    from sqlmodel import select
    from langflow.services.database.models.billing.models import BillingPeriod, SubscriptionPlan
    
    try:
        with get_session() as session:
            # Get active billing period
            billing_period = session.exec(
                select(BillingPeriod)
                .where(BillingPeriod.user_id == current_user.id, BillingPeriod.status == "active")
                .order_by(BillingPeriod.start_date.desc())
            ).first()
            
            if not billing_period:
                # Create a new billing period
                from langflow.services.billing.utils import create_billing_period
                billing_period = create_billing_period(current_user.id, session)
                
                if not billing_period:
                    raise HTTPException(status_code=500, detail="Failed to create billing period")
            
            # Get total quota
            total_quota = get_user_quota(current_user.id, session)
            
            # Check if user's plan allows rollover
            plan_allows_rollover = False
            if current_user.subscription_plan_id:
                plan = session.exec(
                    select(SubscriptionPlan)
                    .where(SubscriptionPlan.id == current_user.subscription_plan_id)
                ).first()
                
                if plan:
                    # Check for allows_rollover attribute (for backward compatibility)
                    plan_allows_rollover = plan.allows_rollover if hasattr(plan, 'allows_rollover') else False
                    
                    # Fallback to name-based detection if field doesn't exist yet
                    if not hasattr(plan, 'allows_rollover'):
                        plan_name = plan.name.lower() if plan and plan.name else ""
                        plan_allows_rollover = ("pro" in plan_name or 
                                               "premium" in plan_name or 
                                               "business" in plan_name or 
                                               "enterprise" in plan_name)
            
            # Get rollover credits amount (may be 0 if the field doesn't exist yet)
            rollover_credits = billing_period.rollover_credits if hasattr(billing_period, 'rollover_credits') else 0.0
            
            return QuotaResponse(
                total=total_quota,
                used=billing_period.quota_used,
                remaining=billing_period.quota_remaining,
                rollover_credits=rollover_credits,
                overage=billing_period.overage_credits,
                overage_cost=billing_period.overage_cost,
                period_start=billing_period.start_date.isoformat(),
                period_end=billing_period.end_date.isoformat(),
                plan_allows_rollover=plan_allows_rollover
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SubscriptionPlanResponse(BaseModel):
    """User's subscription plan information"""
    id: str
    name: str
    description: Optional[str] = None
    monthly_quota_credits: float
    price_monthly_usd: float
    price_yearly_usd: float
    features: dict
    limits: dict
    allows_overage: bool = False
    allows_rollover: bool = False  # Whether the plan allows unused credits to roll over


@router.get("/subscription")
async def get_subscription(
    current_user: User = Depends(get_current_active_user),
) -> SubscriptionPlanResponse:
    """Get current user's subscription plan information."""
    from sqlmodel import select
    from langflow.services.database.models.billing.models import SubscriptionPlan
    
    try:
        with get_session() as session:
            if not current_user.subscription_plan_id:
                raise HTTPException(status_code=404, detail="User has no subscription plan")
                
            plan = session.exec(
                select(SubscriptionPlan)
                .where(SubscriptionPlan.id == current_user.subscription_plan_id)
            ).first()
            
            if not plan:
                raise HTTPException(status_code=404, detail="Subscription plan not found")
                
            # Check for allows_rollover attribute (for backward compatibility)
            allows_rollover = plan.allows_rollover if hasattr(plan, 'allows_rollover') else False
            
            # Fallback to name-based detection if field doesn't exist yet
            if not hasattr(plan, 'allows_rollover'):
                plan_name = plan.name.lower() if plan and plan.name else ""
                allows_rollover = ("pro" in plan_name or 
                                  "premium" in plan_name or 
                                  "business" in plan_name or 
                                  "enterprise" in plan_name)
                
            return SubscriptionPlanResponse(
                id=str(plan.id),
                name=plan.name,
                description=plan.description,
                monthly_quota_credits=plan.monthly_quota_credits,
                price_monthly_usd=plan.price_monthly_usd,
                price_yearly_usd=plan.price_yearly_usd,
                features=plan.features,
                allows_overage=plan.allows_overage,
                allows_rollover=allows_rollover,
                limits={
                    "max_flows": plan.max_flows,
                    "max_flow_runs_per_day": plan.max_flow_runs_per_day,
                    "max_concurrent_flows": plan.max_concurrent_flows,
                    "max_kb_storage_mb": plan.max_kb_storage_mb,
                    "max_kb_queries_per_day": plan.max_kb_queries_per_day,
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RunHistoryResponse(BaseModel):
    """Run history information"""
    id: str
    flow_id: str
    created_at: str
    total_cost: float
    summary: dict


@router.get("/runs")
async def get_run_history(
    limit: int = 10,
    current_user: User = Depends(get_current_active_user),
) -> list[RunHistoryResponse]:
    """Get run history for current user."""
    from sqlmodel import select
    from langflow.services.database.models.billing.models import UsageRecord
    
    try:
        with get_session() as session:
            records = session.exec(
                select(UsageRecord)
                .where(UsageRecord.user_id == current_user.id)
                .order_by(UsageRecord.created_at.desc())
                .limit(limit)
            ).all()
            
            result = []
            for record in records:
                # Get basic summary
                summary = {
                    "fixed_cost": record.fixed_cost,
                    "llm_cost": record.llm_cost,
                    "tools_cost": record.tools_cost,
                    "kb_cost": record.kb_cost,
                }
                
                result.append(RunHistoryResponse(
                    id=str(record.id),
                    flow_id=str(record.flow_id),
                    created_at=record.created_at.isoformat(),
                    total_cost=record.total_cost,
                    summary=summary
                ))
                
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RunDetailResponse(BaseModel):
    """Detailed run information"""
    id: str
    flow_id: str
    session_id: str
    created_at: str
    fixed_cost: float
    llm_cost: float
    tools_cost: float
    kb_cost: float
    total_cost: float
    llm_usage: list
    tool_usage: list
    kb_usage: list


@router.get("/runs/{run_id}")
async def get_run_detail(
    run_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> RunDetailResponse:
    """Get detailed information for a specific run."""
    from sqlmodel import select
    from langflow.services.database.models.billing.models import (
        UsageRecord, TokenUsageDetail, ToolUsageDetail, KBUsageDetail
    )
    
    try:
        with get_session() as session:
            record = session.exec(
                select(UsageRecord)
                .where(UsageRecord.id == run_id, UsageRecord.user_id == current_user.id)
            ).first()
            
            if not record:
                raise HTTPException(status_code=404, detail="Run not found")
                
            # Get token usage details
            token_details = session.exec(
                select(TokenUsageDetail)
                .where(TokenUsageDetail.usage_record_id == record.id)
            ).all()
            
            # Get tool usage details
            tool_details = session.exec(
                select(ToolUsageDetail)
                .where(ToolUsageDetail.usage_record_id == record.id)
            ).all()
            
            # Get KB usage details
            kb_details = session.exec(
                select(KBUsageDetail)
                .where(KBUsageDetail.usage_record_id == record.id)
            ).all()
            
            return RunDetailResponse(
                id=str(record.id),
                flow_id=str(record.flow_id),
                session_id=record.session_id,
                created_at=record.created_at.isoformat(),
                fixed_cost=record.fixed_cost,
                llm_cost=record.llm_cost,
                tools_cost=record.tools_cost,
                kb_cost=record.kb_cost,
                total_cost=record.total_cost,
                llm_usage=[
                    {
                        "model": detail.model_name,
                        "input_tokens": detail.input_tokens,
                        "output_tokens": detail.output_tokens,
                        "cost": detail.cost
                    }
                    for detail in token_details
                ],
                tool_usage=[
                    {
                        "tool": detail.tool_name,
                        "count": detail.count,
                        "is_premium": detail.is_premium,
                        "cost": detail.cost
                    }
                    for detail in tool_details
                ],
                kb_usage=[
                    {
                        "kb": detail.kb_name,
                        "count": detail.count,
                        "cost": detail.cost
                    }
                    for detail in kb_details
                ]
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/renew-billing-period")
async def test_renew_billing_period(
    current_user: User = Depends(get_current_active_user),
):
    """
    Test endpoint to manually renew the current user's billing period.
    This is useful for testing rollover credits without waiting for the normal renewal cycle.
    """
    try:
        from langflow.services.billing.cycle_manager import get_billing_cycle_manager
        
        # Get the billing cycle manager
        manager = get_billing_cycle_manager()
        
        # Manually trigger renewal
        result = await manager.manually_renew_user_billing_period(current_user.id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
            
        return {
            "message": "Billing period renewed successfully",
            "old_period_ended": True,
            "new_period_id": result.get("period_id"),
            "details": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/generate-invoice")
async def test_generate_invoice(
    overage_amount: float = 100.0,
    current_user: User = Depends(get_current_active_user),
):
    """
    Test endpoint to simulate overage and generate an invoice.
    This creates a completed billing period with overage and generates an invoice.
    """
    try:
        from langflow.services.deps import session_scope
        from langflow.services.database.models.billing.models import BillingPeriod, SubscriptionPlan, Invoice
        from langflow.services.billing.cycle_manager import get_billing_cycle_manager
        from sqlmodel import select
        from datetime import datetime, timezone
        
        # Step 1: Get and validate the active billing period
        async with session_scope() as session:
            billing_period = (await session.exec(
                select(BillingPeriod)
                .where(BillingPeriod.user_id == current_user.id, BillingPeriod.status == "active")
            )).first()
            
            if not billing_period:
                raise HTTPException(status_code=404, detail="No active billing period found")
                
            # Get subscription plan
            plan = None
            if billing_period.subscription_plan_id:
                plan = await session.get(SubscriptionPlan, billing_period.subscription_plan_id)
            
            if not plan:
                raise HTTPException(status_code=404, detail="No subscription plan found")
                
            # Check if plan allows overage
            if not plan.allows_overage:
                # Temporarily enable overage for testing
                plan.allows_overage = True
                session.add(plan)
                
            # Calculate overage
            current_remaining = billing_period.quota_remaining
            usage_amount = current_remaining + overage_amount
            
            # Update billing period to reflect overage
            billing_period.quota_used += usage_amount
            billing_period.quota_remaining -= usage_amount
            billing_period.overage_credits = overage_amount
            billing_period.overage_cost = overage_amount * plan.overage_price_per_credit
            billing_period.status = "completed"  # Mark as completed
            session.add(billing_period)
            
            # Generate invoice for this period
            invoice = Invoice(
                user_id=current_user.id,
                billing_period_id=billing_period.id,
                amount=plan.price_monthly_usd + billing_period.overage_cost,
                status="pending",
                created_at=datetime.now(timezone.utc)
            )
            session.add(invoice)
            
            # Return the invoice details
            invoice_data = {
                "invoice_id": str(invoice.id),
                "created_at": invoice.created_at.isoformat(),
                "billing_period": {
                    "id": str(billing_period.id),
                    "start_date": billing_period.start_date.isoformat(),
                    "end_date": billing_period.end_date.isoformat(),
                    "quota_used": billing_period.quota_used,
                    "quota_remaining": billing_period.quota_remaining,
                    "overage_credits": billing_period.overage_credits,
                    "overage_cost": billing_period.overage_cost
                },
                "plan": {
                    "name": plan.name,
                    "monthly_cost": plan.price_monthly_usd,
                    "overage_rate": plan.overage_price_per_credit
                },
                "total_amount": invoice.amount,
                "status": invoice.status
            }
            
            # Create a new billing period automatically
            manager = get_billing_cycle_manager()
            renewal_result = await manager.manually_renew_user_billing_period(current_user.id)
            if renewal_result["success"]:
                invoice_data["new_period_id"] = renewal_result.get("period_id")
            
            return invoice_data
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 