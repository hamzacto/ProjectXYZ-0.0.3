"""
Test script for invoice generation and overage calculations.

This script demonstrates how to:
1. Simulate a user exceeding their quota (generating overage)
2. Force completion of a billing period
3. Generate an invoice for the period
4. View overage calculations

Usage:
    python -m test_invoice_overage <user_id>

If user_id is provided, it will test invoicing for that specific user.
"""

import asyncio
import sys
from uuid import UUID
from datetime import datetime, timezone, timedelta

# Add the current directory to the path so we can import langflow modules
import os
import sys
sys.path.insert(0, os.path.abspath('.'))

async def simulate_overage(user_id: UUID, overage_amount: float = 100.0):
    """Simulate a user exceeding their quota by the specified amount."""
    from langflow.services.deps import session_scope
    from langflow.services.database.models.user import User
    from langflow.services.database.models.billing.models import BillingPeriod, SubscriptionPlan
    from sqlmodel import select
    
    async with session_scope() as session:
        # Get active billing period
        billing_period = (await session.exec(
            select(BillingPeriod)
            .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
        )).first()
        
        if not billing_period:
            print(f"Error: User {user_id} has no active billing period")
            return False
            
        # Get subscription plan
        plan = None
        if billing_period.subscription_plan_id:
            plan = await session.get(SubscriptionPlan, billing_period.subscription_plan_id)
        
        if not plan:
            print(f"Error: No subscription plan found for billing period {billing_period.id}")
            return False
            
        # Check if plan allows overage
        if not plan.allows_overage:
            print(f"Warning: Plan {plan.name} does not allow overage. Setting allows_overage=True for testing...")
            plan.allows_overage = True
            session.add(plan)
        
        # Calculate current usage and ensure we have enough remaining to exceed
        current_remaining = billing_period.quota_remaining
        
        # We'll simulate usage that causes the specified overage
        usage_amount = current_remaining + overage_amount
        
        print(f"\nSimulating usage of {usage_amount} credits (exceeds quota by {overage_amount})...")
        
        # Update billing period to reflect overage
        billing_period.quota_used += usage_amount
        billing_period.quota_remaining -= usage_amount
        
        # Calculate overage
        billing_period.overage_credits = overage_amount
        billing_period.overage_cost = overage_amount * plan.overage_price_per_credit
        
        session.add(billing_period)
        print(f"Updated billing period to simulate overage: {overage_amount} credits")
        print(f"Overage cost: {billing_period.overage_cost} (at rate: ${plan.overage_price_per_credit}/credit)")
        
        return True

async def complete_billing_period(user_id: UUID):
    """Mark the current billing period as complete and ready for invoicing."""
    from langflow.services.deps import session_scope
    from langflow.services.database.models.billing.models import BillingPeriod
    from sqlmodel import select
    
    async with session_scope() as session:
        # Get active billing period
        billing_period = (await session.exec(
            select(BillingPeriod)
            .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
        )).first()
        
        if not billing_period:
            print(f"Error: User {user_id} has no active billing period")
            return None
            
        # Update billing period status
        billing_period.status = "completed"
        session.add(billing_period)
        
        print(f"\nMarked billing period {billing_period.id} as completed")
        print(f"Period: {billing_period.start_date} to {billing_period.end_date}")
        print(f"Final usage: {billing_period.quota_used} credits")
        print(f"Overage: {billing_period.overage_credits} credits (${billing_period.overage_cost})")
        
        return billing_period.id

async def generate_invoice(user_id: UUID, billing_period_id: UUID):
    """Generate an invoice for the completed billing period."""
    from langflow.services.deps import session_scope
    from langflow.services.database.models.user import User
    from langflow.services.database.models.billing.models import BillingPeriod, Invoice, SubscriptionPlan
    from sqlmodel import select
    
    async with session_scope() as session:
        # Get the billing period
        billing_period = await session.get(BillingPeriod, billing_period_id)
        if not billing_period:
            print(f"Error: Billing period {billing_period_id} not found")
            return None
            
        # Get plan
        plan = None
        if billing_period.subscription_plan_id:
            plan = await session.get(SubscriptionPlan, billing_period.subscription_plan_id)
        
        # Calculate invoice amount
        # Base amount from subscription plan
        base_amount = plan.price_monthly_usd if plan else 0
        
        # Add overage costs
        total_amount = base_amount + billing_period.overage_cost
        
        # Create invoice
        invoice = Invoice(
            user_id=user_id,
            billing_period_id=billing_period_id,
            amount=total_amount,
            status="pending",
            created_at=datetime.now(timezone.utc)
        )
        
        session.add(invoice)
        
        # Return the invoice details as a dictionary
        return {
            "invoice_id": invoice.id,
            "user_id": str(user_id),
            "billing_period_id": str(billing_period_id),
            "created_at": invoice.created_at.isoformat(),
            "subscription_base": base_amount,
            "overage_credits": billing_period.overage_credits,
            "overage_cost": billing_period.overage_cost,
            "total_amount": total_amount,
            "status": invoice.status
        }

async def test_invoice_and_overage(user_id: UUID):
    """Test the full process of overage and invoice generation."""
    print(f"Testing invoice generation and overage for user {user_id}")
    
    # Import required modules
    from langflow.services.deps import session_scope
    from langflow.services.database.models.user import User
    from langflow.services.database.models.billing.models import BillingPeriod, SubscriptionPlan
    from sqlmodel import select
    
    # First, get user information and current billing period
    async with session_scope() as session:
        user = await session.get(User, user_id)
        if not user:
            print(f"Error: User {user_id} not found")
            return
            
        # Get user's subscription plan
        plan = None
        if user.subscription_plan_id:
            plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
        
        if not plan:
            print(f"Error: User {user_id} has no subscription plan")
            return
            
        # Get active billing period
        billing_period = (await session.exec(
            select(BillingPeriod)
            .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
        )).first()
        
        if not billing_period:
            print(f"Error: User {user_id} has no active billing period")
            return
        
        print("\nUser Information:")
        print(f"  Email: {user.email}")
        print(f"  Plan: {plan.name}")
        print(f"  Allows Overage: {plan.allows_overage}")
        print(f"  Overage Rate: ${plan.overage_price_per_credit}/credit")
        
        print("\nCurrent Billing Period:")
        print(f"  ID: {billing_period.id}")
        print(f"  Start: {billing_period.start_date}")
        print(f"  End: {billing_period.end_date}")
        print(f"  Quota Used: {billing_period.quota_used}")
        print(f"  Quota Remaining: {billing_period.quota_remaining}")
        print(f"  Status: {billing_period.status}")
    
    # Step 1: Simulate overage
    overage_amount = 150.0  # Exceed quota by 150 credits
    success = await simulate_overage(user_id, overage_amount)
    if not success:
        return
    
    # Step 2: Complete the billing period
    billing_period_id = await complete_billing_period(user_id)
    if not billing_period_id:
        return
    
    # Step 3: Generate invoice
    invoice = await generate_invoice(user_id, billing_period_id)
    if not invoice:
        print("Error generating invoice")
        return
    
    # Display invoice details
    print("\n------- INVOICE -------")
    print(f"Invoice ID: {invoice['invoice_id']}")
    print(f"Created: {invoice['created_at']}")
    print(f"Status: {invoice['status']}")
    print("\nBilling Summary:")
    print(f"  Base Subscription: ${invoice['subscription_base']:.2f}")
    print(f"  Overage Credits: {invoice['overage_credits']}")
    print(f"  Overage Cost: ${invoice['overage_cost']:.2f}")
    print(f"\nTotal Amount: ${invoice['total_amount']:.2f}")
    print("----------------------")
    
    # Explain the results
    print("\nExplanation:")
    print(f"1. User exceeded their quota by {overage_amount} credits")
    print(f"2. At the overage rate of ${plan.overage_price_per_credit}/credit, this resulted")
    print(f"   in an overage charge of ${invoice['overage_cost']:.2f}")
    print(f"3. This was added to the base subscription cost (${invoice['subscription_base']:.2f})")
    print(f"4. Resulting in a total invoice amount of ${invoice['total_amount']:.2f}")
    
    # Clean up - create a new active billing period
    async with session_scope() as session:
        from langflow.services.billing.cycle_manager import get_billing_cycle_manager
        
        # Get the billing cycle manager
        manager = get_billing_cycle_manager()
        
        # Create a new billing period
        result = await manager.manually_renew_user_billing_period(user_id)
        if result["success"]:
            print("\nCreated new active billing period to replace the completed one")
            print(f"New period ID: {result.get('period_id')}")
        else:
            print(f"\nWarning: Failed to create new billing period: {result.get('message')}")

async def main():
    """Main entry point for the script."""
    # Check if a user ID was provided
    if len(sys.argv) > 1:
        try:
            user_id = UUID(sys.argv[1])
            await test_invoice_and_overage(user_id)
        except ValueError:
            print(f"Error: Invalid UUID format: {sys.argv[1]}")
    else:
        print("Please provide a user ID to test invoice generation.")
        print("Usage: python -m test_invoice_overage <user_id>")

if __name__ == "__main__":
    asyncio.run(main()) 