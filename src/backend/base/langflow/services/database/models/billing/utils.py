from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Any

from alembic.util.exc import CommandError
from loguru import logger
from sqlmodel import text, select
from sqlmodel.ext.asyncio.session import AsyncSession
from uuid import uuid4


async def create_default_subscription_plans(session) -> Dict[str, Any]:
    """
    Creates or updates default subscription plans.
    Returns a dictionary of plans by key name.
    """
    from langflow.services.database.models.billing.models import SubscriptionPlan
    from sqlmodel import select
    from uuid import uuid4
    
    # Define our default plans
    default_plans = {
        "free": {
            "name": "Free",
            "description": "Get started with basic features",
            "monthly_quota_credits": 500,
            "max_flows": 3,
            "max_flow_runs_per_day": 10,
            "max_concurrent_flows": 1,
            "max_kb_storage_mb": 5,
            "max_kbs_per_user": 1,
            "max_kb_entries_per_kb": 100,
            "max_tokens_per_kb_entry": 1000,
            "max_kb_queries_per_day": 10,
            "allowed_models": {
                "gpt-3.5-turbo": True
            },
            "price_monthly_usd": 0.0,
            "price_yearly_usd": 0.0,
            "features": {
                "basic_templates": True,
                "community_support": True
            },
            "allowed_premium_tools": {},
            "overage_price_per_credit": 0.0,
            "allows_overage": False,
            "allows_rollover": False,   
            "trial_days": 0,
            "is_active": True
        },
        "lite": {
            "name": "Lite",
            "description": "Affordable plan for light use",
            "monthly_quota_credits": 4000,
            "max_flows": 5,
            "max_flow_runs_per_day": 25,
            "max_concurrent_flows": 1,
            "max_kb_storage_mb": 25,
            "max_kbs_per_user": 3,
            "max_kb_entries_per_kb": 250,
            "max_tokens_per_kb_entry": 1500,
            "max_kb_queries_per_day": 50,
            "allowed_models": {
                "gpt-3.5-turbo": True
            },
            "price_monthly_usd": 4.99,
            "price_yearly_usd": 49.90,
            "features": {
                "all_templates": True,
                "community_support": True
            },
            "allowed_premium_tools": {},
            "overage_price_per_credit": 0.015,
            "allows_overage": True,
            "allows_rollover": False,
            "trial_days": 7,
            "is_active": True
        },
        "pro": {
            "name": "Pro",
            "description": "Ideal for creators and solo builders",
            "monthly_quota_credits": 5,
            "max_flows": 10,
            "max_flow_runs_per_day": 50,
            "max_concurrent_flows": 2,
            "max_kb_storage_mb": 100,
            "max_kbs_per_user": 5,
            "max_kb_entries_per_kb": 500,
            "max_tokens_per_kb_entry": 2000,
            "max_kb_queries_per_day": 100,
            "allowed_models": {
                "gpt-3.5-turbo": True,
                "gpt-4": True,
                "claude-3-sonnet": True
            },
            "price_monthly_usd": 19.99,
            "price_yearly_usd": 199.90,
            "features": {
                "priority_support": True,
                "all_templates": True,
                "community_support": True
            },
            "allowed_premium_tools": {},
            "overage_price_per_credit": 0.01,
            "allows_overage": True,
            "allows_rollover": True,
            "trial_days": 14,
            "is_active": True
        },
        "pro_plus": {
            "name": "Pro Plus",
            "description": "Unlock advanced features and performance",
            "monthly_quota_credits": 45000,
            "max_flows": 50,
            "max_flow_runs_per_day": 0,  # Unlimited
            "max_concurrent_flows": 5,
            "max_kb_storage_mb": 500,
            "max_kbs_per_user": 20,
            "max_kb_entries_per_kb": 1000,
            "max_tokens_per_kb_entry": 4000,
            "max_kb_queries_per_day": 0,  # Unlimited
            "allowed_models": {
                "gpt-3.5-turbo": True,
                "gpt-4": True,
                "gpt-4o": True,
                "claude-3-sonnet": True,
                "claude-3-opus": True
            },
            "price_monthly_usd": 49.99,
            "price_yearly_usd": 499.90,
            "features": {
                "priority_support": True,
                "all_templates": True,
                "custom_domain": True,
                "advanced_analytics": True
            },
            "allowed_premium_tools": {
                "google_search": True,
                "alpha_vantage": True
            },
            "overage_price_per_credit": 0.01,
            "allows_overage": True,
            "allows_rollover": True,
            "trial_days": 14,
            "is_active": True
        },
        "team": {
            "name": "Team",
            "description": "Built for collaboration and shared resources",
            "monthly_quota_credits": 90000,
            "max_flows": 100,
            "max_flow_runs_per_day": 0,  # Unlimited
            "max_concurrent_flows": 10,
            "max_kb_storage_mb": 1000,
            "max_kbs_per_user": 50,
            "max_kb_entries_per_kb": 2000,
            "max_tokens_per_kb_entry": 8000,
            "max_kb_queries_per_day": 0,  # Unlimited
            "allowed_models": {
                "gpt-4": True,
                "gpt-4o": True,
                "claude-3-sonnet": True,
                "claude-3-opus": True
            },
            "price_monthly_usd": 99.99,
            "price_yearly_usd": 999.90,
            "features": {
                "priority_support": True,
                "all_templates": True,
                "custom_domain": True,
                "advanced_analytics": True,
                "shared_workspaces": True
            },
            "allowed_premium_tools": {
                "google_search": True,
                "alpha_vantage": True
            },
            "overage_price_per_credit": 0.009,
            "allows_overage": True,
            "allows_rollover": True,
            "trial_days": 14,
            "is_active": True
        },
        "business": {
            "name": "Business",
            "description": "Custom infrastructure, support, and scalability",
            "monthly_quota_credits": 180000,
            "max_flows": 0,  # Unlimited
            "max_flow_runs_per_day": 0,  # Unlimited
            "max_concurrent_flows": 20,
            "max_kb_storage_mb": 5000,
            "max_kbs_per_user": 0,  # Unlimited
            "max_kb_entries_per_kb": 0,  # Unlimited
            "max_tokens_per_kb_entry": 0,  # Unlimited
            "max_kb_queries_per_day": 0,  # Unlimited
            "allowed_models": {},  # All models allowed
            "price_monthly_usd": 199.99,
            "price_yearly_usd": 1999.90,
            "features": {
                "priority_support": True,
                "all_templates": True,
                "custom_domain": True,
                "advanced_analytics": True,
                "sso_integration": True,
                "dedicated_support": True
            },
            "allowed_premium_tools": {},  # All premium tools allowed
            "overage_price_per_credit": 0.008,
            "allows_overage": True,
            "allows_rollover": True,
            "trial_days": 30,
            "is_active": True
        }
    }
    
    # Dictionary to store created plans by key
    created_plans = {}
    
    # First check for existing plans
    for plan_key, plan_data in default_plans.items():
        # Try to find an existing plan with this name
        stmt = select(SubscriptionPlan).where(SubscriptionPlan.name == plan_data["name"])
        result = await session.exec(stmt)
        existing_plan = result.first()
        
        if existing_plan:
            # Update fields if needed - typically you might want to update descriptions or features
            # but keep core parameters stable to avoid disrupting existing subscriptions
            existing_plan.description = plan_data["description"]
            existing_plan.is_active = plan_data["is_active"]
            
            # Update limits and quotas
            existing_plan.monthly_quota_credits = plan_data["monthly_quota_credits"]
            existing_plan.max_flows = plan_data["max_flows"]
            existing_plan.max_flow_runs_per_day = plan_data["max_flow_runs_per_day"]
            existing_plan.max_concurrent_flows = plan_data["max_concurrent_flows"]
            existing_plan.max_kb_storage_mb = plan_data["max_kb_storage_mb"]
            existing_plan.max_kbs_per_user = plan_data["max_kbs_per_user"]
            existing_plan.max_kb_entries_per_kb = plan_data["max_kb_entries_per_kb"]
            existing_plan.max_tokens_per_kb_entry = plan_data["max_tokens_per_kb_entry"]
            existing_plan.max_kb_queries_per_day = plan_data["max_kb_queries_per_day"]
            
            # Update pricing
            existing_plan.price_monthly_usd = plan_data["price_monthly_usd"]
            existing_plan.price_yearly_usd = plan_data["price_yearly_usd"]
            existing_plan.overage_price_per_credit = plan_data["overage_price_per_credit"]
            existing_plan.allows_overage = plan_data["allows_overage"]
            existing_plan.trial_days = plan_data["trial_days"]
            
            # Update features and allowed models/tools
            existing_plan.features = plan_data["features"]
            existing_plan.allowed_models = plan_data["allowed_models"]
            existing_plan.allowed_premium_tools = plan_data["allowed_premium_tools"]
            
            # Add to our return dictionary
            created_plans[plan_key] = existing_plan
            session.add(existing_plan)
        else:
            # Create a new plan
            new_plan = SubscriptionPlan(
                id=uuid4(),
                **plan_data
            )
            session.add(new_plan)
            created_plans[plan_key] = new_plan
    
    # Commit all changes
    await session.commit()
    
    # Refresh all plans to ensure we have the latest data
    for plan in created_plans.values():
        await session.refresh(plan)
    
    return created_plans
