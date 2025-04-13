"""Billing models for the database."""

from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Optional, List
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, String
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from langflow.services.database.models.user import User
    from langflow.services.database.models.flow.model import Flow

# Helper function for flexible billing periods
def get_next_billing_cycle(start_date=None, billing_day=1):
    """
    Calculate the next billing period start and end dates based on billing anchor day.
    
    Args:
        start_date: Optional starting date (defaults to now)
        billing_day: Day of month to anchor billing (1-28)
    
    Returns:
        Tuple of (start_date, end_date) for next billing period
    """
    if start_date is None:
        start_date = datetime.now(timezone.utc)
    
    # Ensure billing_day is valid (1-28 to avoid month length issues)
    billing_day = max(1, min(28, billing_day))
    
    # Calculate current period's start
    if start_date.day < billing_day:
        # We're before the billing day in current month
        current_start = datetime(start_date.year, start_date.month, billing_day, 
                               tzinfo=timezone.utc)
    else:
        # We're after billing day, so current period started on billing_day of current month
        current_start = datetime(start_date.year, start_date.month, billing_day, 
                               tzinfo=timezone.utc)
    
    # If we're before the current period's start, move back one month
    if start_date < current_start:
        # Move to previous month's billing day
        if current_start.month == 1:
            current_start = datetime(current_start.year - 1, 12, billing_day, 
                                   tzinfo=timezone.utc)
        else:
            current_start = datetime(current_start.year, current_start.month - 1, 
                                   billing_day, tzinfo=timezone.utc)
    
    # Calculate next period's start (one month after current start)
    if current_start.month == 12:
        next_start = datetime(current_start.year + 1, 1, billing_day, 
                            tzinfo=timezone.utc)
    else:
        next_start = datetime(current_start.year, current_start.month + 1, 
                            billing_day, tzinfo=timezone.utc)
    
    # Current period ends right before next one starts
    current_end = next_start - timedelta(seconds=1)
    
    return (current_start, current_end)


class SubscriptionPlan(SQLModel, table=True):
    """Model for subscription plans."""
    
    __tablename__ = "subscriptionplan"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None)
    monthly_quota_credits: float = Field(default=0.0)
    max_flows: int = Field(default=0)
    max_flow_runs_per_day: int = Field(default=0)
    max_concurrent_flows: int = Field(default=1)
    max_kb_storage_mb: int = Field(default=0)
    max_kbs_per_user: int = Field(default=0)
    max_kb_entries_per_kb: int = Field(default=0)
    max_tokens_per_kb_entry: int = Field(default=0)
    max_kb_queries_per_day: int = Field(default=0)
    allowed_models: dict = Field(sa_column=Column(JSON, nullable=False))
    price_monthly_usd: float = Field(default=0.0)
    price_yearly_usd: float = Field(default=0.0)
    features: dict = Field(sa_column=Column(JSON, nullable=False))
    allowed_premium_tools: dict = Field(sa_column=Column(JSON, nullable=False))
    overage_price_per_credit: float = Field(default=0.0)
    default_overage_limit_usd: float = Field(default=20.0)  # Default overage limit for this plan
    allows_overage: bool = Field(default=False)
    allows_rollover: bool = Field(default=False)  # Whether this plan allows credit rollover
    trial_days: int = Field(default=0)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    users: list["User"] = Relationship(back_populates="subscription_plan")
    billing_periods: list["BillingPeriod"] = Relationship(back_populates="subscription_plan")


class BillingPeriod(SQLModel, table=True):
    """Model for billing periods."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    start_date: datetime = Field()
    end_date: datetime = Field()
    subscription_plan_id: Optional[UUID] = Field(foreign_key="subscriptionplan.id", index=True, default=None)
    status: str = Field(default="active", sa_column=Column(String, index=True, nullable=False))
    quota_override: Optional[float] = Field(default=None)
    quota_used: float = Field(default=0.0)
    quota_remaining: float = Field(default=0.0)
    rollover_credits: float = Field(default=0.0)  # Credits rolled over from previous period
    overage_credits: float = Field(default=0.0)
    overage_cost: float = Field(default=0.0)
    overage_limit_usd: float = Field(default=20.0)  # Default $20 overage limit in USD
    is_overage_limited: bool = Field(default=True)  # Whether overage limiting is enabled
    has_reached_limit: bool = Field(default=False)  # Whether the user has reached their overage limit
    is_plan_change: bool = Field(default=False)
    previous_plan_id: Optional[UUID] = Field(default=None)
    invoiced: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user: "User" = Relationship(back_populates="billing_periods")
    subscription_plan: Optional["SubscriptionPlan"] = Relationship(back_populates="billing_periods")
    usage_records: list["UsageRecord"] = Relationship(back_populates="billing_period")
    invoices: list["Invoice"] = Relationship(back_populates="billing_period")


class UsageRecord(SQLModel, table=True):
    """Model for usage records."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    flow_id: UUID = Field(foreign_key="flow.id", index=True)
    session_id: str = Field(index=True)
    fixed_cost: float = Field(default=0.0)
    llm_cost: float = Field(default=0.0)
    tools_cost: float = Field(default=0.0)
    kb_cost: float = Field(default=0.0)
    app_margin: float = Field(default=0.0)  # 20% app margin
    total_cost: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    billing_period_id: Optional[UUID] = Field(default=None, foreign_key="billingperiod.id")
    
    # Relationships
    user: "User" = Relationship(back_populates="usage_records")
    flow: "Flow" = Relationship(back_populates="usage_records")
    billing_period: Optional["BillingPeriod"] = Relationship(back_populates="usage_records")
    token_usages: list["TokenUsageDetail"] = Relationship(back_populates="usage_record")
    tool_usages: list["ToolUsageDetail"] = Relationship(back_populates="usage_record")
    kb_usages: list["KBUsageDetail"] = Relationship(back_populates="usage_record")


class TokenUsageDetail(SQLModel, table=True):
    """Model for token usage details."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    usage_record_id: UUID = Field(foreign_key="usagerecord.id", index=True)
    model_name: str = Field()
    input_tokens: int = Field()
    output_tokens: int = Field()
    cost: float = Field()
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    usage_record: "UsageRecord" = Relationship(back_populates="token_usages")


class ToolUsageDetail(SQLModel, table=True):
    """Model for tool usage details."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    usage_record_id: UUID = Field(foreign_key="usagerecord.id", index=True)
    tool_name: str = Field()
    count: int = Field(default=1)
    cost: float = Field()
    is_premium: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    usage_record: "UsageRecord" = Relationship(back_populates="tool_usages")


class KBUsageDetail(SQLModel, table=True):
    """Model for knowledge base usage details."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    usage_record_id: UUID = Field(foreign_key="usagerecord.id", index=True)
    kb_name: str = Field()
    count: int = Field(default=1)
    cost: float = Field()
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    usage_record: "UsageRecord" = Relationship(back_populates="kb_usages")


class DailyUsageSummary(SQLModel, table=True):
    """Model for daily usage summaries."""
    __tablename__ = "daily_usage_summary"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    date: datetime = Field(index=True)
    flow_runs: int = Field(default=0)
    kb_queries: int = Field(default=0)
    api_calls: int = Field(default=0)
    tokens_used: int = Field(default=0)
    total_cost: float = Field(default=0.0)
    
    # Relationships
    user: "User" = Relationship(back_populates="daily_usage_summaries")


class Invoice(SQLModel, table=True):
    """Model for invoices."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    billing_period_id: UUID = Field(foreign_key="billingperiod.id")
    amount: float = Field()
    status: str = Field(default="pending")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    paid_at: Optional[datetime] = Field(default=None)
    
    # Relationships
    user: "User" = Relationship(back_populates="invoices")
    billing_period: "BillingPeriod" = Relationship(back_populates="invoices")


# Define relationships
BillingPeriod.user = Relationship(back_populates="billing_periods")
BillingPeriod.subscription_plan = Relationship(back_populates="billing_periods")
BillingPeriod.usage_records = Relationship(back_populates="billing_period")
BillingPeriod.invoices = Relationship(back_populates="billing_period")

UsageRecord.user = Relationship(back_populates="usage_records")
UsageRecord.flow = Relationship(back_populates="usage_records")
UsageRecord.billing_period = Relationship(back_populates="usage_records")
UsageRecord.token_usages = Relationship(back_populates="usage_record")
UsageRecord.tool_usages = Relationship(back_populates="usage_record")
UsageRecord.kb_usages = Relationship(back_populates="usage_record")

SubscriptionPlan.users = Relationship(back_populates="subscription_plan")
SubscriptionPlan.billing_periods = Relationship(back_populates="subscription_plan") 