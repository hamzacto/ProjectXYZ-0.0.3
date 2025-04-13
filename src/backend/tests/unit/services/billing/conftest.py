"""Fixtures for billing service tests."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta
from uuid import UUID
from contextlib import asynccontextmanager

from langflow.services.billing.service import BillingService
from langflow.services.database.models.billing.models import (
    BillingPeriod, 
    SubscriptionPlan,
    UsageRecord
)
from langflow.services.database.models.user import User

@pytest.fixture
def billing_service():
    """Return a BillingService instance."""
    return BillingService()

@pytest.fixture
def mock_session():
    """Return a mock database session."""
    session = MagicMock()
    session.add = MagicMock()
    session.exec = AsyncMock()
    session.get = AsyncMock()
    return session

@pytest.fixture
def mock_session_scope(mock_session):
    """Return a mock session_scope context manager."""
    @asynccontextmanager
    async def _mock_session_scope():
        yield mock_session
    return _mock_session_scope

@pytest.fixture
def mock_session_scope_factory():
    """Return a factory function that creates a mock session_scope with the provided session."""
    def _factory(session=None):
        session = session or MagicMock()
        
        @asynccontextmanager
        async def _mock_session_scope():
            yield session
            
        return _mock_session_scope
    
    return _factory

@pytest.fixture
def pro_plan():
    """Return a Pro subscription plan that allows rollover and overage."""
    return SubscriptionPlan(
        id=UUID('00000000-0000-0000-0000-000000000001'),
        name="Pro Plan",
        monthly_quota_credits=10000.0,
        allows_rollover=True,
        allows_overage=True,
        overage_price_per_credit=0.01,
        default_overage_limit_usd=20.0
    )

@pytest.fixture
def basic_plan():
    """Return a Basic subscription plan that doesn't allow rollover or overage."""
    return SubscriptionPlan(
        id=UUID('00000000-0000-0000-0000-000000000002'),
        name="Basic Plan",
        monthly_quota_credits=5000.0,
        allows_rollover=False,
        allows_overage=False,
        overage_price_per_credit=0.0,
        default_overage_limit_usd=0.0
    )

@pytest.fixture
def test_user(pro_plan):
    """Return a test user with the Pro plan."""
    return User(
        id=UUID('00000000-0000-0000-0000-000000000010'),
        email="test@example.com",
        subscription_plan_id=pro_plan.id,
        credits_balance=5000.0
    )

@pytest.fixture
def active_billing_period(test_user, pro_plan):
    """Return an active billing period with plenty of credits remaining."""
    now = datetime.now(timezone.utc)
    return BillingPeriod(
        id=UUID('00000000-0000-0000-0000-000000000020'),
        user_id=test_user.id,
        subscription_plan_id=pro_plan.id,
        start_date=now - timedelta(days=15),  # Started 15 days ago
        end_date=now + timedelta(days=15),    # Ends in 15 days
        status="active",
        quota_used=5000.0,
        quota_remaining=5000.0,  # Half used
        rollover_credits=0.0,
        overage_credits=0.0,
        overage_cost=0.0,
        overage_limit_usd=20.0,
        is_overage_limited=True,
        has_reached_limit=False
    )

@pytest.fixture
def usage_record(test_user, active_billing_period):
    """Return a usage record for testing."""
    return UsageRecord(
        id=UUID('00000000-0000-0000-0000-000000000030'),
        user_id=test_user.id,
        flow_id=UUID('00000000-0000-0000-0000-000000000040'),
        session_id="test_session_id",
        billing_period_id=active_billing_period.id,
        fixed_cost=10.0,
        llm_cost=0.0,
        tools_cost=0.0,
        kb_cost=0.0,
        total_cost=10.0
    ) 