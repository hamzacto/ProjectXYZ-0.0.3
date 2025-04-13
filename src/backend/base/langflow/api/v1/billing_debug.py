from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from langflow.services.database.models.billing.models import (
    UsageRecord,
    TokenUsageDetail,
    ToolUsageDetail,
    KBUsageDetail,
    BillingPeriod,
    SubscriptionPlan,
    DailyUsageSummary,
    Invoice,
)
from langflow.services.database.models.user.model import User
from langflow.services.deps import get_session

router = APIRouter(tags=["Debug"])

@router.get("/billing", response_model=dict, include_in_schema=True)
async def get_all_billing_data(
    session: Session = Depends(get_session),
):
    """
    Retrieves all billing records for debugging purposes. 
    WARNING: This endpoint is for debugging only and returns potentially sensitive data.
    """
    
    usage_records = (await session.exec(select(UsageRecord))).all()
    token_details = (await session.exec(select(TokenUsageDetail))).all()
    tool_details = (await session.exec(select(ToolUsageDetail))).all()
    kb_details = (await session.exec(select(KBUsageDetail))).all()
    billing_periods = (await session.exec(select(BillingPeriod))).all()

    return {
        "usage_records": [record.model_dump() for record in usage_records],
        "token_details": [detail.model_dump() for detail in token_details],
        "tool_details": [detail.model_dump() for detail in tool_details],
        "kb_details": [detail.model_dump() for detail in kb_details],
        "billing_periods": [period.model_dump() for period in billing_periods],
    } 

@router.get("/users")
async def get_all_users(
    session: Session = Depends(get_session),
):
    users = (await session.exec(select(User))).all()
    return [user.model_dump() for user in users]

@router.get("/details", response_model=dict, include_in_schema=True)
async def get_billing_details(
    session: Session = Depends(get_session),
):
    """
    Retrieves all billing details for debugging purposes. 
    WARNING: This endpoint is for debugging only and returns potentially sensitive data.
    """
    subscription_plans = (await session.exec(select(SubscriptionPlan))).all()
    billing_periods = (await session.exec(select(BillingPeriod))).all()
    daily_usage_summaries = (await session.exec(select(DailyUsageSummary))).all()
    invoices = (await session.exec(select(Invoice))).all()

    return {
        "subscription_plans": [plan.model_dump() for plan in subscription_plans],
        "billing_periods": [period.model_dump() for period in billing_periods],
        "daily_usage_summaries": [summary.model_dump() for summary in daily_usage_summaries],
        "invoices": [invoice.model_dump() for invoice in invoices],
    }
