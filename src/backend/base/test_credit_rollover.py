"""
Test script for credit rollover functionality.

This script demonstrates how the credit rollover feature works by:
1. Creating test users with different subscription plans
2. Adding credits to their accounts
3. Simulating billing period renewals
4. Verifying that rollover credits are applied correctly based on the plan

Usage:
    python -m test_credit_rollover <user_id>

If user_id is provided, it will test rollover for that specific user.
Otherwise, it will create test users with different plans.
"""

import asyncio
import sys
from uuid import UUID
from datetime import datetime, timezone, timedelta

# Add the current directory to the path so we can import langflow modules
import os
import sys
sys.path.insert(0, os.path.abspath('.'))

async def test_rollover_for_user(user_id: UUID):
    """Test rollover for an existing user."""
    print(f"Testing credit rollover for user {user_id}")
    
    # Import required modules
    from langflow.services.deps import session_scope
    from langflow.services.database.models.user import User
    from langflow.services.database.models.billing.models import BillingPeriod, SubscriptionPlan
    from langflow.services.billing.cycle_manager import get_billing_cycle_manager
    from sqlmodel import select
    
    # Get the billing cycle manager
    manager = get_billing_cycle_manager()
    
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
            
        # Check if plan allows rollover
        allows_rollover = plan.allows_rollover if hasattr(plan, 'allows_rollover') else False
        
        print("\nUser Information:")
        print(f"  Email: {user.email}")
        print(f"  Plan: {plan.name}")
        print(f"  Allows Rollover: {allows_rollover}")
        print(f"  Current Credits: {user.credits_balance}")
        
        print("\nCurrent Billing Period:")
        print(f"  ID: {billing_period.id}")
        print(f"  Start: {billing_period.start_date}")
        print(f"  End: {billing_period.end_date}")
        print(f"  Quota Used: {billing_period.quota_used}")
        print(f"  Quota Remaining: {billing_period.quota_remaining}")
        if hasattr(billing_period, 'rollover_credits'):
            print(f"  Rollover Credits: {billing_period.rollover_credits}")
        
        # To simulate unused credits, we need to ensure there are some credits remaining
        # Let's modify the credits if needed for testing
        if billing_period.quota_remaining < 10:
            test_credits = billing_period.quota_used + 100  # Add 100 credits for testing
            print(f"\nSetting test credits to {test_credits} for demonstration")
            billing_period.quota_remaining = 100
            user.credits_balance = test_credits
            session.add(billing_period)
            session.add(user)
            # The session will be committed when the context manager exits
    
    # Now manually trigger a billing period renewal to test rollover
    print("\nTriggering manual renewal to test rollover...")
    result = await manager.manually_renew_user_billing_period(user_id)
    
    if result["success"]:
        print(f"Renewal successful! New period ID: {result.get('period_id')}")
    else:
        print(f"Renewal failed: {result.get('message')}")
        return
    
    # Let's check the new billing period and see if rollover was applied
    async with session_scope() as session:
        # Get the new billing period
        new_period = await session.get(BillingPeriod, UUID(result.get("period_id")))
        if not new_period:
            print("Error: Could not find new billing period")
            return
            
        # Also get updated user
        user = await session.get(User, user_id)
        
        print("\nNew Billing Period:")
        print(f"  ID: {new_period.id}")
        print(f"  Start: {new_period.start_date}")
        print(f"  End: {new_period.end_date}")
        print(f"  Quota Used: {new_period.quota_used}")
        print(f"  Quota Remaining: {new_period.quota_remaining}")
        if hasattr(new_period, 'rollover_credits'):
            print(f"  Rollover Credits: {new_period.rollover_credits}")
        
        print(f"\nUser's new credit balance: {user.credits_balance}")
        
        # Explain the results
        if allows_rollover:
            if hasattr(new_period, 'rollover_credits') and new_period.rollover_credits > 0:
                print("\nSUCCESS: Credits were rolled over as expected for this Pro/Premium plan!")
                print(f"  - Base credits from plan: {new_period.quota_remaining - new_period.rollover_credits}")
                print(f"  - Rollover credits: {new_period.rollover_credits}")
                print(f"  - Total credits: {new_period.quota_remaining}")
            else:
                print("\nWARNING: Plan should allow rollover, but no rollover credits were found.")
                print("This could be because:")
                print("  - There were no unused credits in the previous period")
                print("  - The rollover feature is not working correctly")
                print("  - The database schema update for rollover_credits hasn't been applied")
        else:
            if hasattr(new_period, 'rollover_credits') and new_period.rollover_credits > 0:
                print("\nWARNING: Plan should NOT allow rollover, but rollover credits were found.")
            else:
                print("\nSUCCESS: No credits were rolled over, as expected for this non-Pro plan.")
                print(f"  - Credits were reset to the base plan amount: {new_period.quota_remaining}")

async def main():
    """Main entry point for the script."""
    # Check if a user ID was provided
    if len(sys.argv) > 1:
        try:
            user_id = UUID(sys.argv[1])
            await test_rollover_for_user(user_id)
        except ValueError:
            print(f"Error: Invalid UUID format: {sys.argv[1]}")
    else:
        print("Please provide a user ID to test rollover.")
        print("Usage: python -m test_credit_rollover <user_id>")

if __name__ == "__main__":
    asyncio.run(main()) 