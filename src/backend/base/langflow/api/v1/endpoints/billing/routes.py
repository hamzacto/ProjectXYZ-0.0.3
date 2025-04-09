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
    overage: float
    overage_cost: float
    period_start: str
    period_end: str


@router.get("/quota")
async def get_quota(
    current_user: User = Depends(get_current_active_user),
) -> QuotaResponse:
    """Get current user's quota information."""
    from langflow.services.billing.utils import get_user_quota, get_quota_remaining
    from sqlmodel import select
    from langflow.services.database.models.billing.models import BillingPeriod
    
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
            
            return QuotaResponse(
                total=total_quota,
                used=billing_period.quota_used,
                remaining=billing_period.quota_remaining,
                overage=billing_period.overage_credits,
                overage_cost=billing_period.overage_cost,
                period_start=billing_period.start_date.isoformat(),
                period_end=billing_period.end_date.isoformat()
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
                
            return SubscriptionPlanResponse(
                id=str(plan.id),
                name=plan.name,
                description=plan.description,
                monthly_quota_credits=plan.monthly_quota_credits,
                price_monthly_usd=plan.price_monthly_usd,
                price_yearly_usd=plan.price_yearly_usd,
                features=plan.features,
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