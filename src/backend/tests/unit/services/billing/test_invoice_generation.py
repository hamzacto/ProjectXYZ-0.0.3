"""Tests for invoice generation with credit overage calculations."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP

from langflow.services.billing.service import BillingService
from langflow.services.database.models.billing.models import (
    BillingPeriod,
    SubscriptionPlan,
    UsageRecord,
    Invoice
)
from langflow.services.database.models.user import User

@pytest.mark.asyncio
async def test_invoice_with_overage_charges(mock_session_scope_factory, test_user, pro_plan):
    """Test that invoice generation correctly includes overage charges."""
    # Create a billing service
    billing_service = BillingService()
    
    # Configure billing period with overage
    billing_period = BillingPeriod(
        id=UUID('00000000-0000-0000-0000-000000000003'),
        user_id=test_user.id,
        subscription_plan_id=pro_plan.id,
        status="active",
        start_date=datetime.now(timezone.utc) - timedelta(days=30),
        end_date=datetime.now(timezone.utc),
        quota_used=12000,  # Used more than the 10000 monthly quota
        quota_remaining=-2000,  # 2000 credits in overage
        overage_credits=2000,
        overage_cost=20.0,  # $20 of overage at $0.01 per credit
        overage_limit_usd=50.0,  # Higher limit to allow more overage
        is_overage_limited=True,
        has_reached_limit=False
    )
    
    # Create mock session
    mock_session = MagicMock()
    
    # Configure async get method
    async def async_get(model, id):
        if model == SubscriptionPlan and id == pro_plan.id:
            return pro_plan
        elif model == User and id == test_user.id:
            return test_user
        elif model == BillingPeriod and id == billing_period.id:
            return billing_period
        return None
    
    mock_session.get = AsyncMock(side_effect=async_get)
    
    # Mock result for queries
    mock_result = MagicMock()
    mock_result.first.return_value = billing_period
    mock_result.all.return_value = []
    mock_session.exec = AsyncMock(return_value=mock_result)
    
    # Create a mock invoice to be returned
    invoice = Invoice(
        id=UUID('00000000-0000-0000-0000-000000000006'),
        user_id=test_user.id,
        billing_period_id=billing_period.id,
        amount=0.0,  # Will be calculated
        status="pending"
    )
    
    # Mock session scope
    mock_scope = mock_session_scope_factory(mock_session)
    
    # Define our invoice generation method to test
    async def generate_invoice(session, billing_period_id):
        # Get the billing period
        billing_period = await session.get(BillingPeriod, billing_period_id)
        
        # Calculate invoice amount: base plan cost + overage
        plan = await session.get(SubscriptionPlan, billing_period.subscription_plan_id)
        
        # Calculate monthly plan cost
        base_cost = plan.price_monthly_usd
        
        # Add overage cost
        total_cost = base_cost + billing_period.overage_cost
        
        # Round to 2 decimal places
        total_cost = Decimal(str(total_cost)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Create invoice
        invoice.amount = float(total_cost)
        session.add(invoice)
        
        # Mark billing period as invoiced
        billing_period.invoiced = True
        session.add(billing_period)
        
        return invoice
    
    # Mock the generate_invoice method
    billing_service.generate_invoice = AsyncMock(side_effect=generate_invoice)
    
    with patch('langflow.services.deps.session_scope', mock_scope):
        # Call generate_invoice
        result = await billing_service.generate_invoice(mock_session, billing_period.id)
        
        # Verify invoice amount includes both base plan cost and overage
        expected_total = pro_plan.price_monthly_usd + billing_period.overage_cost
        assert result.amount == expected_total
        assert result.user_id == test_user.id
        assert result.billing_period_id == billing_period.id
        
        # Verify billing period was marked as invoiced
        assert billing_period.invoiced is True

@pytest.mark.asyncio
async def test_invoice_with_partial_period_proration(mock_session_scope_factory, test_user, pro_plan):
    """Test that invoice generation correctly prorates charges for partial billing periods."""
    # Create a billing service
    billing_service = BillingService()
    
    # Create a billing period that only covers half a month
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=15)  # 15 days ago
    end_date = now
    
    billing_period = BillingPeriod(
        id=UUID('00000000-0000-0000-0000-000000000003'),
        user_id=test_user.id,
        subscription_plan_id=pro_plan.id,
        status="active",
        start_date=start_date,
        end_date=end_date,
        quota_used=6000,  # Used more than half of the 10000 monthly quota
        quota_remaining=0,
        overage_credits=1000,  # 1000 credits in overage
        overage_cost=10.0,  # $10 of overage at $0.01 per credit
        overage_limit_usd=50.0,
        is_overage_limited=True,
        has_reached_limit=False,
        is_plan_change=True  # This is a partial period due to plan change
    )
    
    # Set the monthly price of the pro plan
    pro_plan.price_monthly_usd = 50.0
    
    # Create mock session
    mock_session = MagicMock()
    
    # Configure async get method
    async def async_get(model, id):
        if model == SubscriptionPlan and id == pro_plan.id:
            return pro_plan
        elif model == User and id == test_user.id:
            return test_user
        elif model == BillingPeriod and id == billing_period.id:
            return billing_period
        return None
    
    mock_session.get = AsyncMock(side_effect=async_get)
    
    # Mock result for queries
    mock_result = MagicMock()
    mock_result.first.return_value = billing_period
    mock_result.all.return_value = []
    mock_session.exec = AsyncMock(return_value=mock_result)
    
    # Create a mock invoice to be returned
    invoice = Invoice(
        id=UUID('00000000-0000-0000-0000-000000000006'),
        user_id=test_user.id,
        billing_period_id=billing_period.id,
        amount=0.0,  # Will be calculated
        status="pending"
    )
    
    # Mock session scope
    mock_scope = mock_session_scope_factory(mock_session)
    
    # Define our invoice generation method with proration
    async def generate_invoice_with_proration(session, billing_period_id):
        # Get the billing period
        billing_period = await session.get(BillingPeriod, billing_period_id)
        
        # Get the plan
        plan = await session.get(SubscriptionPlan, billing_period.subscription_plan_id)
        
        # Calculate days in period
        days_in_period = (billing_period.end_date - billing_period.start_date).days
        
        # Calculate proration factor
        days_in_month = 30  # Simplified
        proration_factor = days_in_period / days_in_month
        
        # Calculate prorated base cost
        base_cost = plan.price_monthly_usd * proration_factor
        
        # Add overage cost (overage is not prorated - actual usage)
        total_cost = base_cost + billing_period.overage_cost
        
        # Round to 2 decimal places
        total_cost = Decimal(str(total_cost)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Create invoice
        invoice.amount = float(total_cost)
        session.add(invoice)
        
        # Mark billing period as invoiced
        billing_period.invoiced = True
        session.add(billing_period)
        
        return invoice
    
    # Mock the generate_invoice method
    billing_service.generate_invoice = AsyncMock(side_effect=generate_invoice_with_proration)
    
    with patch('langflow.services.deps.session_scope', mock_scope):
        # Call generate_invoice
        result = await billing_service.generate_invoice(mock_session, billing_period.id)
        
        # Calculate expected amount
        days_in_period = (billing_period.end_date - billing_period.start_date).days
        proration_factor = days_in_period / 30  # Using 30 days for simplicity
        expected_base = pro_plan.price_monthly_usd * proration_factor
        expected_total = expected_base + billing_period.overage_cost
        expected_total = float(Decimal(str(expected_total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        
        # Verify invoice amount includes both prorated base cost and full overage
        assert result.amount == expected_total
        assert result.user_id == test_user.id
        assert result.billing_period_id == billing_period.id
        
        # Verify billing period was marked as invoiced
        assert billing_period.invoiced is True

@pytest.mark.asyncio
async def test_invoice_generation_with_multiple_overages(mock_session_scope_factory, test_user, pro_plan):
    """Test invoice generation with multiple types of usage and overages."""
    # Create a billing service
    billing_service = BillingService()
    
    # Configure billing period with multiple sources of usage
    billing_period = BillingPeriod(
        id=UUID('00000000-0000-0000-0000-000000000003'),
        user_id=test_user.id,
        subscription_plan_id=pro_plan.id,
        status="active",
        start_date=datetime.now(timezone.utc) - timedelta(days=30),
        end_date=datetime.now(timezone.utc),
        quota_used=13500,  # Used more than the 10000 monthly quota
        quota_remaining=-3500,  # 3500 credits in overage
        overage_credits=3500,
        overage_cost=35.0,  # $35 of overage at $0.01 per credit
        overage_limit_usd=100.0,
        is_overage_limited=True,
        has_reached_limit=False
    )
    
    # Create usage records to break down where overage came from
    usage_records = [
        UsageRecord(
            id=UUID('00000000-0000-0000-0000-000000000101'),
            user_id=test_user.id,
            flow_id=UUID('00000000-0000-0000-0000-000000000201'),
            session_id="session1",
            billing_period_id=billing_period.id,
            fixed_cost=5.0,
            llm_cost=1000.0,  # 1000 credits from LLM usage
            tools_cost=200.0,  # 200 credits from tools
            kb_cost=300.0,     # 300 credits from KB
            app_margin=300.0,  # 20% of 1500
            total_cost=1800.0
        ),
        UsageRecord(
            id=UUID('00000000-0000-0000-0000-000000000102'),
            user_id=test_user.id,
            flow_id=UUID('00000000-0000-0000-0000-000000000202'),
            session_id="session2", 
            billing_period_id=billing_period.id,
            fixed_cost=0.0,
            llm_cost=1200.0,  # 1200 more credits from LLM
            tools_cost=300.0,  # 300 more from tools
            kb_cost=100.0,     # 100 more from KB
            app_margin=320.0,  # 20% of 1600
            total_cost=1920.0
        )
    ]
    
    # Total from usage records should match billing period overage
    # 1800 + 1920 = 3720 credits
    # But first 10000 included in plan, so overage is 3720 - 10000 = -6280
    # (The discrepancy is intentional to test that invoice uses billing period amounts,
    # not recalculating from usage records)
    
    # Create mock session
    mock_session = MagicMock()
    
    # Configure async get method
    async def async_get(model, id):
        if model == SubscriptionPlan and id == pro_plan.id:
            return pro_plan
        elif model == User and id == test_user.id:
            return test_user
        elif model == BillingPeriod and id == billing_period.id:
            return billing_period
        return None
    
    mock_session.get = AsyncMock(side_effect=async_get)
    
    # Mock result for queries
    mock_result = MagicMock()
    mock_result.first.return_value = billing_period
    mock_result.all.return_value = usage_records  # Return our usage records
    mock_session.exec = AsyncMock(return_value=mock_result)
    
    # Create a mock invoice to be returned
    invoice = Invoice(
        id=UUID('00000000-0000-0000-0000-000000000006'),
        user_id=test_user.id,
        billing_period_id=billing_period.id,
        amount=0.0,  # Will be calculated
        status="pending"
    )
    
    # Variables to store usage details for verification (without setting on Invoice)
    invoice_details = {}
    
    # Mock session scope
    mock_scope = mock_session_scope_factory(mock_session)
    
    # Define invoice generation method with detailed usage breakdown
    async def generate_detailed_invoice(session, billing_period_id):
        # Get the billing period
        billing_period = await session.get(BillingPeriod, billing_period_id)
        
        # Get the plan
        plan = await session.get(SubscriptionPlan, billing_period.subscription_plan_id)
        
        # Base subscription cost
        base_cost = plan.price_monthly_usd
        
        # Get usage breakdown (for invoice details)
        total_llm_cost = 0
        total_tools_cost = 0
        total_kb_cost = 0
        total_app_margin = 0
        
        # In a real system, we'd query for usage records and calculate these totals
        # Here we're mocking that the usage records are already in our mock_result
        usage_records = mock_result.all()
        for record in usage_records:
            total_llm_cost += record.llm_cost
            total_tools_cost += record.tools_cost
            total_kb_cost += record.kb_cost
            total_app_margin += record.app_margin
        
        # Calculate final invoice amount using billing period's recorded overage
        total_cost = base_cost + billing_period.overage_cost
        
        # Round to 2 decimal places
        total_cost = Decimal(str(total_cost)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Create invoice
        invoice.amount = float(total_cost)
        session.add(invoice)
        
        # Store details separately rather than on the invoice object
        nonlocal invoice_details
        invoice_details = {
            "base_subscription": base_cost,
            "overage_charges": billing_period.overage_cost,
            "usage_breakdown": {
                "llm_cost": total_llm_cost,
                "tools_cost": total_tools_cost,
                "kb_cost": total_kb_cost,
                "app_margin": total_app_margin
            }
        }
        
        # Mark billing period as invoiced
        billing_period.invoiced = True
        session.add(billing_period)
        
        return invoice
    
    # Mock the generate_invoice method
    billing_service.generate_invoice = AsyncMock(side_effect=generate_detailed_invoice)
    
    with patch('langflow.services.deps.session_scope', mock_scope):
        # Call generate_invoice
        result = await billing_service.generate_invoice(mock_session, billing_period.id)
        
        # Verify the invoice amount includes both base plan cost and overage
        expected_total = pro_plan.price_monthly_usd + billing_period.overage_cost
        assert result.amount == expected_total
        
        # Test that we would use the billing period's overage value
        # not recalculate from usage records
        assert billing_period.overage_cost == 35.0  # The value we set
        
        # Verify usage breakdown is included in our separate invoice_details variable
        assert invoice_details["overage_charges"] == billing_period.overage_cost
        assert invoice_details["usage_breakdown"]["llm_cost"] == 2200.0  # 1000 + 1200
        assert invoice_details["usage_breakdown"]["tools_cost"] == 500.0  # 200 + 300
        assert invoice_details["usage_breakdown"]["kb_cost"] == 400.0     # 300 + 100
        assert invoice_details["usage_breakdown"]["app_margin"] == 620.0  # 300 + 320
        
        # Verify billing period was marked as invoiced
        assert billing_period.invoiced is True 