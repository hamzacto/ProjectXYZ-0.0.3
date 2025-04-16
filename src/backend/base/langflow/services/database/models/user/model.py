from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

from langflow.schema.serialize import UUIDstr

if TYPE_CHECKING:
    from langflow.services.database.models.api_key import ApiKey
    from langflow.services.database.models.flow import Flow
    from langflow.services.database.models.folder import Folder
    from langflow.services.database.models.variable import Variable
    from langflow.services.database.models.integration_token.model import IntegrationToken
    from langflow.services.database.models.billing.models import (
        SubscriptionPlan, 
        BillingPeriod, 
        UsageRecord,
        Invoice, 
        DailyUsageSummary
    )

class User(SQLModel, table=True):  # type: ignore[call-arg]
    id: UUIDstr = Field(default_factory=uuid4, primary_key=True, unique=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    password: str = Field()
    profile_image: str | None = Field(default=None, nullable=True)
    is_active: bool = Field(default=False)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    verification_token: str | None = Field(default=None, nullable=True)
    verification_token_expiry: datetime | None = Field(default=None, nullable=True)
    oauth_provider: str | None = Field(default=None, nullable=True)
    create_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = Field(default=None, nullable=True)
    
    # Stripe Integration Fields
    stripe_customer_id: Optional[str] = Field(default=None, index=True, nullable=True)
    stripe_subscription_id: Optional[str] = Field(default=None, index=True, nullable=True)
    stripe_default_payment_method_id: Optional[str] = Field(default=None, nullable=True)
    
    # Billing and quota fields
    credits_balance: Optional[float] = Field(default=0.0, nullable=True)
    billing_day: Optional[int] = Field(default=1, nullable=True)
    
    # Subscription fields
    subscription_plan_id: Optional[UUID] = Field(
        foreign_key="subscriptionplan.id",
        nullable=True, index=True
    )
    subscription_status: Optional[str] = Field(default="trial", nullable=True)
    subscription_start_date: Optional[datetime] = Field(default=None, nullable=True)
    subscription_end_date: Optional[datetime] = Field(default=None, nullable=True)
    has_chosen_plan: bool = Field(default=False)
    
    # Trial tracking
    trial_start_date: Optional[datetime] = Field(default=None, nullable=True)
    trial_end_date: Optional[datetime] = Field(default=None, nullable=True)
    trial_converted: Optional[bool] = Field(default=False, nullable=True)
    
    # Usage tracking for daily limits
    daily_flow_runs: Optional[int] = Field(default=0, nullable=True)
    daily_flow_runs_reset_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=True)
    daily_kb_queries: Optional[int] = Field(default=0, nullable=True)
    daily_kb_queries_reset_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=True)
    
    # Existing relationships
    api_keys: list["ApiKey"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "delete"},
    )
    store_api_key: str | None = Field(default=None, nullable=True)
    flows: list["Flow"] = Relationship(back_populates="user")
    variables: list["Variable"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "delete"},
    )
    folders: list["Folder"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "delete"},
    )

    integrations: list["IntegrationToken"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "delete"}
    )
    
    # Billing relationships
    subscription_plan: Optional["SubscriptionPlan"] = Relationship(back_populates="users")
    billing_periods: list["BillingPeriod"] = Relationship(back_populates="user")
    usage_records: list["UsageRecord"] = Relationship(back_populates="user")
    invoices: list["Invoice"] = Relationship(back_populates="user")
    daily_usage_summaries: list["DailyUsageSummary"] = Relationship(back_populates="user")


class UserCreate(SQLModel):
    username: str = Field()
    email: str = Field()
    password: str = Field()


class UserRead(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    username: str = Field()
    email: str = Field()
    profile_image: str | None = Field()
    store_api_key: str | None = Field(nullable=True)
    is_active: bool = Field()
    is_verified: bool = Field()
    is_superuser: bool = Field()
    oauth_provider: str | None = Field(nullable=True)
    create_at: datetime = Field()
    updated_at: datetime = Field()
    last_login_at: datetime | None = Field(nullable=True)
    
    # Include subscription status in API response
    subscription_status: str = Field()
    credits_balance: Optional[float] = Field(nullable=True)
    trial_end_date: Optional[datetime] = Field(nullable=True)
    has_chosen_plan: bool = Field(default=False)


class UserUpdate(SQLModel):
    username: str | None = None
    email: str | None = None
    profile_image: str | None = None
    password: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    is_superuser: bool | None = None
    last_login_at: datetime | None = None
    
    # Allow updating subscription fields
    subscription_plan_id: Optional[UUID] = None
    subscription_status: Optional[str] = None
    credits_balance: Optional[float] = None
    has_chosen_plan: bool | None = None