from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from langflow.services.database.models.billing.models import (
    UsageRecord,
    TokenUsageDetail,
    ToolUsageDetail,
    KBUsageDetail,
    BillingPeriod,
)
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