"""Tests for overage limit functionality in the BillingService."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from uuid import UUID

from langflow.services.billing.service import BillingService
from langflow.services.credit.service import TokenUsage
from langflow.services.database.models.billing.models import (
    BillingPeriod,
    SubscriptionPlan,
    UsageRecord,
    TokenUsageDetail
)
from langflow.services.database.models.user import User
from contextlib import asynccontextmanager

@pytest.mark.asyncio
async def test_check_overage_limit_under_limit(billing_service, mock_session, pro_plan):
    """Test when user is under their overage limit."""
    # Create a billing period with some overage
    billing_period = BillingPeriod(
        overage_limit_usd=20.0,
        is_overage_limited=True,
        has_reached_limit=False,
        quota_remaining=-500,  # Already in overage
        overage_credits=500,
        subscription_plan_id=pro_plan.id
    )
    
    # Setup mock to return plan when queried
    mock_session.get.return_value = pro_plan
    
    # Test with an additional cost that keeps user under limit
    # Current cost: $5.00 (500 credits × $0.01)
    # Additional cost: 1000 credits ($10.00)
    # Total cost: $15.00 (under $20 limit)
    result = await billing_service._check_overage_limit(mock_session, billing_period, 1000)
    
    # Should return True (under limit)
    assert result is True
    assert billing_period.has_reached_limit is False
    mock_session.add.assert_not_called()

@pytest.mark.asyncio
async def test_check_overage_limit_at_limit(billing_service, mock_session, pro_plan):
    """Test when user is exactly at their overage limit."""
    # Create a billing period right at the limit
    billing_period = BillingPeriod(
        overage_limit_usd=20.0,
        is_overage_limited=True,
        has_reached_limit=False,
        quota_remaining=-2000,  # Already in overage
        overage_credits=2000,
        subscription_plan_id=pro_plan.id
    )
    
    # Setup mock to return plan when queried
    mock_session.get.return_value = pro_plan
    
    # Test with an additional cost that puts user exactly at limit
    # Current cost: $20.00 (2000 credits × $0.01)
    # Additional cost: 0 credits ($0.00)
    # Total cost: $20.00 (at $20 limit)
    result = await billing_service._check_overage_limit(mock_session, billing_period, 0)
    
    # Should return True (at limit but not over)
    assert result is True
    assert billing_period.has_reached_limit is False
    mock_session.add.assert_not_called()

@pytest.mark.asyncio
async def test_check_overage_limit_over_limit(billing_service, mock_session, pro_plan):
    """Test when user exceeds their overage limit."""
    # Create a billing period right at the limit
    billing_period = BillingPeriod(
        overage_limit_usd=20.0,
        is_overage_limited=True,
        has_reached_limit=False,
        quota_remaining=-2000,  # Already in overage at $20
        overage_credits=2000,
        subscription_plan_id=pro_plan.id
    )
    
    # Setup mock to return plan when queried
    mock_session.get.return_value = pro_plan
    
    # Test with an additional cost that puts user over limit
    # Current cost: $20.00 (2000 credits × $0.01)
    # Additional cost: 100 credits ($1.00)
    # Total cost: $21.00 (over $20 limit)
    result = await billing_service._check_overage_limit(mock_session, billing_period, 100)
    
    # Should return False (over limit)
    assert result is False
    assert billing_period.has_reached_limit is True
    # Verify session.add was called to update the billing period
    mock_session.add.assert_called_once_with(billing_period)

@pytest.mark.asyncio
async def test_check_overage_limit_disabled(billing_service, mock_session, pro_plan):
    """Test when overage limiting is disabled."""
    # Create a billing period with limiting disabled
    billing_period = BillingPeriod(
        overage_limit_usd=20.0,
        is_overage_limited=False,  # Limiting disabled
        has_reached_limit=False,
        quota_remaining=-5000,  # Already far in overage
        overage_credits=5000,
        subscription_plan_id=pro_plan.id
    )
    
    # Test with a very large additional cost
    # Doesn't matter since limiting is disabled
    result = await billing_service._check_overage_limit(mock_session, billing_period, 10000)
    
    # Should return True (limiting disabled)
    assert result is True
    assert billing_period.has_reached_limit is False
    # Verify session.add was not called
    mock_session.add.assert_not_called()

@pytest.mark.asyncio
async def test_token_usage_rejected_at_limit(billing_service, mock_session, pro_plan, test_user):
    """Test that token usage is rejected when user is at their overage limit."""
    # Create a billing period at the limit
    billing_period = BillingPeriod(
        id=UUID('00000000-0000-0000-0000-000000000003'),
        user_id=test_user.id,
        subscription_plan_id=pro_plan.id,
        status="active",
        quota_used=12000,
        quota_remaining=-2000,  # Already 2000 credits in overage
        overage_credits=2000,
        overage_cost=20.0,  # Already at $20 cost
        overage_limit_usd=20.0,
        is_overage_limited=True,
        has_reached_limit=True  # Already reached limit
    )
    
    # Create a usage record
    usage_record = UsageRecord(
        id=UUID('00000000-0000-0000-0000-000000000004'),
        user_id=test_user.id,
        flow_id=UUID('00000000-0000-0000-0000-000000000005'),
        session_id="test_session",
        billing_period_id=billing_period.id,
        llm_cost=0,
        total_cost=0
    )
    
    # Setup token usage
    token_usage = TokenUsage(
        model_name="gpt-4",
        input_tokens=1000,
        output_tokens=1000
    )
    
    # Mock _find_usage_record
    billing_service._find_usage_record = AsyncMock(return_value=usage_record)
    
    # Mock _is_cached_usage
    billing_service._is_cached_usage = AsyncMock(return_value=False)
    
    # Mock session_scope
    @asynccontextmanager
    async def mock_session_scope():
        yield mock_session
        
    # Mock necessary queries
    mock_session.get.side_effect = lambda model, id: {
        SubscriptionPlan: pro_plan if id == pro_plan.id else None,
        BillingPeriod: billing_period if id == billing_period.id else None,
        User: test_user if id == test_user.id else None
    }.get(model)
    
    # Setup mock result for queries
    mock_count_result = MagicMock()
    mock_count_result.first.return_value = 0  # No duplicates
    mock_session.exec.return_value = mock_count_result
    
    with patch('langflow.services.deps.session_scope', mock_session_scope):
        # Call log_token_usage - should be rejected
        result = await billing_service.log_token_usage("test_run_id", token_usage, test_user.id)
        
        # Should return False (rejected due to limit)
        assert result is False

@pytest.mark.asyncio
async def test_finalize_run_sets_limit_flag(billing_service, mock_session, pro_plan, test_user):
    """Test that finalize_run includes the has_reached_limit flag in the result."""
    # Ensure the test_user has a negative credits_balance matching the billing period
    test_user.credits_balance = -1900.0
    print(f"TEST: Set test_user.credits_balance to {test_user.credits_balance}")
    
    # Create a billing period that has already reached its limit
    billing_period = BillingPeriod(
        id=UUID('00000000-0000-0000-0000-000000000003'),
        user_id=test_user.id,
        subscription_plan_id=pro_plan.id,
        status="active",
        quota_used=11900.0,  # Use float for consistency
        quota_remaining=-1900.0,  # 1900 credits in overage - match user's credits_balance
        overage_credits=1900.0,
        overage_cost=19.80,  # $19.80 - just $0.20 away from the limit
        overage_limit_usd=20.0,
        is_overage_limited=True,
        has_reached_limit=True  # Explicitly set to True
    )
    print(f"TEST: Created billing_period with has_reached_limit={billing_period.has_reached_limit}")

    # Create a usage record with costs
    usage_record = UsageRecord(
        id=UUID('00000000-0000-0000-0000-000000000004'),
        user_id=test_user.id,
        flow_id=UUID('00000000-0000-0000-0000-000000000005'),
        session_id="test_session",
        billing_period_id=billing_period.id,
        fixed_cost=10.0,
        llm_cost=40.0,
        tools_cost=30.0,
        kb_cost=0.0,
        total_cost=80.0,
        app_margin=0.0
    )

    # Mock _find_usage_record to return our usage record
    billing_service._find_usage_record = AsyncMock(return_value=usage_record)

    # Setup mock results for usage details queries
    mock_empty_result = MagicMock()
    mock_empty_result.all.return_value = []

    # Setup mock results for user and billing period queries
    mock_user_result = MagicMock()
    mock_user_result.first.return_value = test_user

    mock_bp_result = MagicMock()
    mock_bp_result.first.return_value = billing_period

    # Setup side effect for session.exec to return appropriate mock results
    def mock_exec_side_effect(query):
        query_str = str(query)
        print(f"TEST QUERY: {query_str}")

        if 'TokenUsageDetail' in query_str:
            return mock_empty_result
        elif 'ToolUsageDetail' in query_str:
            return mock_empty_result
        elif 'KBUsageDetail' in query_str:
            return mock_empty_result
        # Fix: Match any User query (the specific format varies)
        elif 'SELECT "user"' in query_str or 'FROM "user"' in query_str:
            print(f"TEST: Matched User query, returning user with credits_balance={test_user.credits_balance}")
            return mock_user_result
        # Fix: Match any BillingPeriod query
        elif 'SELECT billingperiod' in query_str or 'FROM billingperiod' in query_str:
            print(f"TEST: Matched BillingPeriod query, returning billing_period with has_reached_limit={billing_period.has_reached_limit}")
            return mock_bp_result
        return mock_empty_result

    mock_session.exec.side_effect = mock_exec_side_effect

    # Override session.add to print debug info
    original_add = mock_session.add
    def debug_add(obj):
        if isinstance(obj, BillingPeriod):
            print(f"TEST: Adding BillingPeriod to session with has_reached_limit={obj.has_reached_limit}")
        return original_add(obj)
    mock_session.add = debug_add
    
    # Setup session.get
    mock_session.get.side_effect = lambda model, id: {
        SubscriptionPlan: pro_plan if id == pro_plan.id else None,
        User: test_user if id == test_user.id else None,
        BillingPeriod: billing_period if id == billing_period.id else None
    }.get(model)
    
    # Mock session_scope
    @asynccontextmanager
    async def mock_session_scope():
        yield mock_session

    with patch('langflow.services.deps.session_scope', mock_session_scope):
        # Call finalize_run
        result = await billing_service.finalize_run("test_run_id", test_user.id)
        print(f"TEST: Result from finalize_run: {result}")
        
        # Verify that the result contains has_reached_limit=True
        assert "has_reached_limit" in result, "Expected 'has_reached_limit' to be included in the result"
        assert result["has_reached_limit"] is True, "Expected has_reached_limit to be True in the result"
        
        # Verify the app margin calculation
        assert usage_record.app_margin == 16.0  # 20% of 80.0
        assert usage_record.total_cost == 96.0  # 80.0 + 16.0 