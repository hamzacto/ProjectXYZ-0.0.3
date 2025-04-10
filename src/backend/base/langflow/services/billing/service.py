from typing import Dict, List, Optional, Union, Set, Tuple, Any
from uuid import UUID
from datetime import datetime, timezone, timedelta
from loguru import logger
from sqlmodel import Session, select
from sqlalchemy import func, or_
from contextlib import asynccontextmanager

from langflow.services.base import Service
from langflow.services.schema import ServiceType
from langflow.services.database.models.billing.models import (
    UsageRecord, 
    TokenUsageDetail, 
    ToolUsageDetail, 
    KBUsageDetail,
    BillingPeriod,
    SubscriptionPlan
)
from langflow.services.database.models.user import User
from langflow.services.database.models.flow import Flow
from langflow.services.deps import get_session

# Import the existing constants from credit service
from langflow.services.credit.service import (
    FIXED_COST_CREDITS,
    TOOL_ACCESS_CREDITS,
    KB_ACCESS_CREDITS,
    MODEL_COSTS,
    DEFAULT_MODEL_COST,
    TokenUsage,
    ToolUsage,
    KBUsage
)

# Import parsing tools
import re
import uuid
import time
import hashlib
from collections import defaultdict
import asyncio

class BillingService(Service):
    """Service to handle billing, usage tracking and quota management."""
    name = ServiceType.BILLING_SERVICE
    
    def __init__(self):
        super().__init__()
        # Remove single-user context reliance
        # self.current_user_id = None  # Removed in favor of per-operation user_id
        # Add a mapping dictionary to store UUID -> session_id mappings
        # Format: {uuid_str: session_id_str}
        self._uuid_to_session_mappings = {}
        # Format: {session_id_prefix: session_id_full}
        # This helps when we get "Session Apr 08, 22:11:35" but the original is "Session Apr 08, 20:11:22"
        self._session_prefix_mappings = {}
        
        # Add in-memory deduplication cache with expiration
        # Format: {usage_hash: (timestamp, count)}
        self._token_usage_cache = {}
        self._tool_usage_cache = {}
        self._kb_usage_cache = {}
        # Lock for thread-safe cache access
        self._cache_lock = asyncio.Lock()
        # Cache TTL in seconds
        self._cache_ttl = 60
    
    # Keep this method for backward compatibility but add deprecation warning
    def set_user_context(self, user_id: UUID):
        """
        DEPRECATED: This method is maintained for backward compatibility only.
        Instead, pass user_id explicitly to each billing operation.
        """
        logger.warning(
            "set_user_context is deprecated and will be removed in a future version. "
            "Pass user_id explicitly to each billing operation instead."
        )
        # No longer store the user_id at instance level
        pass
    
    @asynccontextmanager
    async def user_context(self, user_id: UUID):
        """Context manager for user operations to ensure proper isolation."""
        # This creates an isolated context for operations with a specific user
        if not user_id:
            raise ValueError("user_id is required for billing operations")
        try:
            yield user_id
        finally:
            # Clean up any user-specific resources if needed
            pass
    
    async def log_flow_run(self, flow_id: UUID, session_id: str, user_id: UUID) -> Optional[UsageRecord]:
        """Create a new usage record for a flow run."""
        if not user_id:
            logger.error("User ID is required for logging flow run")
            return None
            
        try:
            print(f"[BILLING_DEBUG] log_flow_run: Starting for flow_id={flow_id}, session_id={session_id}, user_id={user_id}")
            
            # Keep track of both session_id and flow_id formats
            actual_session_id = session_id
            # If session_id is a UUID but we typically use "Session Apr..." format, store the relationship
            if len(session_id) == 36 and not session_id.startswith("Session"):
                print(f"[BILLING_DEBUG] log_flow_run: Flow ID {session_id} is in UUID format, tracking relationship.")
            
            from langflow.services.deps import session_scope
            
            async with session_scope() as session:
                print(f"[BILLING_DEBUG] log_flow_run: Session created.")
                # Record flow run in daily usage
                user = (await session.exec(select(User).where(User.id == user_id))).first()
                if user:
                    print(f"[BILLING_DEBUG] log_flow_run: Found user {user.id}.")
                    # Reset daily counter if needed
                    now = datetime.now(timezone.utc)
                    # Ensure the database timestamp is treated as UTC for comparison
                    user_reset_at_utc = user.daily_flow_runs_reset_at
                    if user_reset_at_utc and user_reset_at_utc.tzinfo is None:
                        user_reset_at_utc = user_reset_at_utc.replace(tzinfo=timezone.utc)
                        print(f"[BILLING_DEBUG] log_flow_run: Made daily_flow_runs_reset_at timezone-aware (UTC).")

                    if not user_reset_at_utc or (now - user_reset_at_utc).days > 0:
                        print(f"[BILLING_DEBUG] log_flow_run: Resetting daily flow runs counter for user {user.id}.")
                        user.daily_flow_runs = 0
                        user.daily_flow_runs_reset_at = now # Store the timezone-aware timestamp
                    
                    # Increment flow runs counter
                    user.daily_flow_runs = (user.daily_flow_runs or 0) + 1
                    session.add(user)
                    print(f"[BILLING_DEBUG] log_flow_run: Added user update to session. New count: {user.daily_flow_runs}.")
                else:
                    print(f"[BILLING_DEBUG] log_flow_run: User not found for ID: {user_id}")
                    
                # Get active billing period
                billing_period = (await session.exec(
                    select(BillingPeriod)
                    .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
                )).first()
                
                if billing_period:
                    print(f"[BILLING_DEBUG] log_flow_run: Found active billing period: {billing_period.id}")
                else:
                    print(f"[BILLING_DEBUG] log_flow_run: No active billing period found for user.")
                
                # Create usage record
                usage_record = UsageRecord(
                    user_id=user_id,
                    flow_id=flow_id,
                    session_id=actual_session_id,
                    billing_period_id=billing_period.id if billing_period else None,
                    fixed_cost=FIXED_COST_CREDITS,  # Start with fixed cost
                    total_cost=FIXED_COST_CREDITS   # Will be updated as usage is logged
                )
                
                print(f"[BILLING_DEBUG] log_flow_run: Created UsageRecord object in memory: session_id={usage_record.session_id}")
                session.add(usage_record)
                print(f"[BILLING_DEBUG] log_flow_run: Added UsageRecord to session.")
                
                # Commit will happen automatically when session_scope exits
                # No need for flush, refresh, commit, refresh cycle
                print(f"[BILLING_DEBUG] log_flow_run: Operations added to session. Commit will happen on scope exit.")
                
                # Store both UUID -> session_id and session_id prefix -> full session_id mappings
                flow_id_str = str(flow_id)
                self._uuid_to_session_mappings[flow_id_str] = session_id
                
                # Also store a mapping from the day portion (Session Apr 08) to the full session_id
                if session_id.startswith("Session "):
                    try:
                        # Extract Session Apr 08 portion
                        day_prefix = session_id.split(",")[0]
                        if day_prefix and len(day_prefix) > 10:  # Reasonable min length for "Session Apr 08"
                            self._session_prefix_mappings[day_prefix] = session_id
                            print(f"[BILLING_DEBUG] log_flow_run: Stored session prefix mapping: {day_prefix} -> {session_id}")
                    except Exception as e_prefix:
                        print(f"[BILLING_DEBUG] log_flow_run: Error storing session prefix mapping: {e_prefix}")
                
                print(f"[BILLING_DEBUG] log_flow_run: Stored in-memory UUID -> Session mapping: {flow_id_str} -> {session_id}")
                
                # Clear any usage caches for this flow/session
                await self._clear_usage_caches(flow_id_str)
                await self._clear_usage_caches(session_id)
                
                return usage_record
        except Exception as e:
            print(f"[BILLING_DEBUG] log_flow_run: Error: {str(e)}")
            logger.error(f"Error logging flow run: {e}")
            return None
    
    async def _clear_usage_caches(self, run_id: str):
        """Clear cached usage data for a specific run ID."""
        async with self._cache_lock:
            # Create hashes that could be related to this run_id
            for cache in [self._token_usage_cache, self._tool_usage_cache, self._kb_usage_cache]:
                keys_to_remove = []
                for key in cache.keys():
                    if run_id in key:
                        keys_to_remove.append(key)
                
                for key in keys_to_remove:
                    cache.pop(key, None)
            
            print(f"[BILLING_DEBUG] Cleared usage caches for run_id={run_id}")
    
    def _generate_token_usage_hash(self, run_id: str, token_usage: TokenUsage) -> str:
        """Generate a unique hash for token usage to detect duplicates."""
        hash_input = f"{run_id}:{token_usage.model_name}:{token_usage.input_tokens}:{token_usage.output_tokens}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def _generate_tool_usage_hash(self, run_id: str, tool_usage: ToolUsage) -> str:
        """Generate a unique hash for tool usage to detect duplicates."""
        hash_input = f"{run_id}:{tool_usage.tool_name}:{tool_usage.count}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def _generate_kb_usage_hash(self, run_id: str, kb_usage: KBUsage) -> str:
        """Generate a unique hash for KB usage to detect duplicates."""
        hash_input = f"{run_id}:{kb_usage.kb_name}:{kb_usage.count}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    async def _is_cached_usage(self, cache: Dict[str, Tuple[float, int]], usage_hash: str) -> bool:
        """Check if usage is already cached and update the counter if it is."""
        async with self._cache_lock:
            current_time = time.time()
            
            # Clean expired entries
            expired_keys = [k for k, (timestamp, _) in cache.items() 
                          if current_time - timestamp > self._cache_ttl]
            for k in expired_keys:
                cache.pop(k, None)
            
            if usage_hash in cache:
                timestamp, count = cache[usage_hash]
                cache[usage_hash] = (timestamp, count + 1)
                return True
            
            # Not in cache, add it
            cache[usage_hash] = (current_time, 1)
            return False

    async def log_token_usage(self, 
                         run_id: str, 
                         token_usage: TokenUsage, 
                         user_id: UUID) -> bool:
        """Log token usage for a specific run and update costs."""
        if not user_id or not run_id:
            logger.error(f"Missing user_id or run_id for token logging: {user_id}, {run_id}")
            return False
            
        try:
            # Check in-memory cache first for ultra-fast duplicate prevention
            usage_hash = self._generate_token_usage_hash(run_id, token_usage)
            if await self._is_cached_usage(self._token_usage_cache, usage_hash):
                print(f"[BILLING_DEBUG] log_token_usage: MEMORY CACHE HIT - Skipping duplicate token usage for run_id={run_id}")
                return True
                
            print(f"[BILLING_DEBUG] log_token_usage: Starting for run_id={run_id}, user_id={user_id}")
            print(f"[BILLING_DEBUG] log_token_usage: Token usage details: model={token_usage.model_name}, input={token_usage.input_tokens}, output={token_usage.output_tokens}")
            from langflow.services.deps import session_scope
            
            async with session_scope() as session:
                print(f"[BILLING_DEBUG] log_token_usage: Session created.")
                
                # Use the helper method to find the usage record
                usage_record = await self._find_usage_record(session, run_id, user_id)
                
                if not usage_record:
                    logger.warning(f"No usage record found for run_id: {run_id}")
                    print(f"[BILLING_DEBUG] log_token_usage: Failed to find UsageRecord for run_id={run_id}")
                    return False
                
                print(f"[BILLING_DEBUG] log_token_usage: Found UsageRecord ID: {usage_record.id} for session: {usage_record.session_id}")
                
                # DEDUPLICATION CHECK: Check for recent identical token usage to prevent duplicates
                # Look for identical token usage recorded in the last minute (more robust window)
                dedup_window_seconds = 60  # Extended window for deduplication
                dedup_cutoff = datetime.now(timezone.utc) - timedelta(seconds=dedup_window_seconds)
                
                recent_identical_count = (await session.exec(
                    select(func.count())
                    .where(
                        TokenUsageDetail.usage_record_id == usage_record.id,
                        TokenUsageDetail.model_name == token_usage.model_name,
                        TokenUsageDetail.input_tokens == token_usage.input_tokens,
                        TokenUsageDetail.output_tokens == token_usage.output_tokens,
                        TokenUsageDetail.created_at >= dedup_cutoff
                    )
                )).first()
                
                if recent_identical_count > 0:
                    print(f"[BILLING_DEBUG] log_token_usage: DEDUPLICATION - Found {recent_identical_count} identical recent entries. Skipping to prevent duplication.")
                    return True  # Return True so caller thinks it succeeded, but we're actually skipping the duplicate
                
                # Calculate token cost
                model_name = token_usage.model_name.lower().strip()
                model_cost = MODEL_COSTS.get(model_name, DEFAULT_MODEL_COST)
                input_cost_usd = (token_usage.input_tokens / 1000) * model_cost["input"]
                output_cost_usd = (token_usage.output_tokens / 1000) * model_cost["output"]
                total_cost_usd = input_cost_usd + output_cost_usd
                credit_cost = total_cost_usd / 0.001  # Convert USD to credits
                
                print(f"[BILLING_DEBUG] log_token_usage: Calculated credit cost: {credit_cost} for token usage.")
                
                # Create token usage detail
                token_detail = TokenUsageDetail(
                    usage_record_id=usage_record.id,
                    model_name=token_usage.model_name,
                    input_tokens=token_usage.input_tokens,
                    output_tokens=token_usage.output_tokens,
                    cost=credit_cost
                )
                
                # Update usage record totals (add directly, no need to query and update separately)
                usage_record.llm_cost = (usage_record.llm_cost or 0) + credit_cost
                usage_record.total_cost = (usage_record.total_cost or 0) + credit_cost
                
                # Batch updates to reduce database operations
                updates = [token_detail, usage_record]
                
                # Update billing period quota if applicable
                billing_period = None
                if usage_record.billing_period_id:
                    billing_period = await session.get(BillingPeriod, usage_record.billing_period_id)
                    if billing_period:
                        print(f"[BILLING_DEBUG] log_token_usage: Found billing period {billing_period.id}. Updating quota.")
                        billing_period.quota_used = (billing_period.quota_used or 0) + credit_cost
                        billing_period.quota_remaining = (billing_period.quota_remaining or 0) - credit_cost
                        
                        # Handle overage if applicable
                        if billing_period.quota_remaining < 0:
                            print(f"[BILLING_DEBUG] log_token_usage: Quota remaining is negative ({billing_period.quota_remaining}). Checking overage.")
                            user = await session.get(User, user_id)
                            if user and user.subscription_plan_id:
                                plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                                if plan and plan.allows_overage:
                                    overage_amount = abs(billing_period.quota_remaining)
                                    billing_period.overage_credits = (billing_period.overage_credits or 0) + overage_amount
                                    billing_period.overage_cost = (billing_period.overage_cost or 0) + overage_amount * plan.overage_price_per_credit
                                    print(f"[BILLING_DEBUG] log_token_usage: Updated overage credits: {billing_period.overage_credits}, cost: {billing_period.overage_cost}")
                        
                        updates.append(billing_period)
                        print(f"[BILLING_DEBUG] log_token_usage: Added BillingPeriod to batch updates. Quota: used={billing_period.quota_used}, remaining={billing_period.quota_remaining}")
                    else:
                        print(f"[BILLING_DEBUG] log_token_usage: Billing period ID {usage_record.billing_period_id} not found.")
                else:
                     print(f"[BILLING_DEBUG] log_token_usage: UsageRecord {usage_record.id} has no associated billing period.")
                
                # Add all updates in one batch
                for entity in updates:
                    session.add(entity)
                
                print(f"[BILLING_DEBUG] log_token_usage: Added {len(updates)} entities to session in a single batch.")
                
                # Successfully recorded, update in-memory cache with a new timestamp
                async with self._cache_lock:
                    self._token_usage_cache[usage_hash] = (time.time(), 1)
                
                # The commit happens automatically when session_scope exits
                print(f"[BILLING_DEBUG] log_token_usage: All operations added to session. Commit will happen on scope exit.")
                
                return True
                
        except Exception as e:
            print(f"[BILLING_DEBUG] log_token_usage: Error: {str(e)}")
            logger.error(f"Error logging token usage: {e}")
            return False
    
    async def log_tool_usage(self, 
                        run_id: str, 
                        tool_usage: ToolUsage, 
                        user_id: UUID) -> bool:
        """Log tool usage for a specific run and update costs."""
        if not user_id or not run_id:
            logger.error(f"Missing user_id or run_id for tool logging: {user_id}, {run_id}")
            return False
            
        try:
            # Check in-memory cache first for ultra-fast duplicate prevention
            usage_hash = self._generate_tool_usage_hash(run_id, tool_usage)
            if await self._is_cached_usage(self._tool_usage_cache, usage_hash):
                print(f"[BILLING_DEBUG] log_tool_usage: MEMORY CACHE HIT - Skipping duplicate tool usage for run_id={run_id}")
                return True
                
            print(f"[BILLING_DEBUG] log_tool_usage: Starting for run_id={run_id}, tool={tool_usage.tool_name}, count={tool_usage.count}")
            from langflow.services.deps import session_scope
            
            async with session_scope() as session:
                print(f"[BILLING_DEBUG] log_tool_usage: Session created.")
                # Import premium tools info
                from langflow.callbacks.cost_tracking import PREMIUM_TOOLS
                
                # Use the helper method to find the usage record
                usage_record = await self._find_usage_record(session, run_id, user_id)
                
                if not usage_record:
                    logger.warning(f"No usage record found for run_id: {run_id}")
                    print(f"[BILLING_DEBUG] log_tool_usage: Failed to find UsageRecord for run_id={run_id}")
                    return False
                
                print(f"[BILLING_DEBUG] log_tool_usage: Found UsageRecord ID: {usage_record.id} for session: {usage_record.session_id}")
                
                # DEDUPLICATION CHECK: Check for recent identical tool usage to prevent duplicates
                # Look for identical tool usage recorded in the last minute (more robust window)
                dedup_window_seconds = 60  # Extended window for deduplication
                dedup_cutoff = datetime.now(timezone.utc) - timedelta(seconds=dedup_window_seconds)
                
                recent_identical_count = (await session.exec(
                    select(func.count())
                    .where(
                        ToolUsageDetail.usage_record_id == usage_record.id,
                        ToolUsageDetail.tool_name == tool_usage.tool_name,
                        ToolUsageDetail.count == tool_usage.count,
                        ToolUsageDetail.created_at >= dedup_cutoff
                    )
                )).first()
                
                if recent_identical_count > 0:
                    print(f"[BILLING_DEBUG] log_tool_usage: DEDUPLICATION - Found {recent_identical_count} identical recent entries. Skipping to prevent duplication.")
                    return True  # Return True so caller thinks it succeeded, but we're actually skipping the duplicate
                
                # Calculate tool cost
                tool_name = tool_usage.tool_name
                is_premium = tool_name in PREMIUM_TOOLS
                
                if is_premium:
                    tool_cost = PREMIUM_TOOLS[tool_name] * tool_usage.count
                    print(f"[BILLING_DEBUG] log_tool_usage: Premium tool '{tool_name}'. Calculated cost: {tool_cost}")
                else:
                    tool_cost = TOOL_ACCESS_CREDITS * tool_usage.count
                    print(f"[BILLING_DEBUG] log_tool_usage: Standard tool '{tool_name}'. Calculated cost: {tool_cost}")
                
                # Create tool usage detail
                tool_detail = ToolUsageDetail(
                    usage_record_id=usage_record.id,
                    tool_name=tool_name,
                    count=tool_usage.count,
                    cost=tool_cost,
                    is_premium=is_premium
                )
                
                # Update usage record totals in memory
                usage_record.tools_cost = (usage_record.tools_cost or 0) + tool_cost
                usage_record.total_cost = (usage_record.total_cost or 0) + tool_cost
                
                # Prepare batch updates
                updates = [tool_detail, usage_record]
                
                # Update billing period quota if applicable
                if usage_record.billing_period_id:
                    billing_period = await session.get(BillingPeriod, usage_record.billing_period_id)
                    if billing_period:
                        print(f"[BILLING_DEBUG] log_tool_usage: Found billing period {billing_period.id}. Updating quota.")
                        billing_period.quota_used = (billing_period.quota_used or 0) + tool_cost
                        billing_period.quota_remaining = (billing_period.quota_remaining or 0) - tool_cost
                        
                        # Handle overage if applicable
                        if billing_period.quota_remaining < 0:
                            print(f"[BILLING_DEBUG] log_tool_usage: Quota remaining is negative ({billing_period.quota_remaining}). Checking overage.")
                            user = await session.get(User, user_id)
                            if user and user.subscription_plan_id:
                                plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                                if plan and plan.allows_overage:
                                    overage_amount = abs(billing_period.quota_remaining)
                                    billing_period.overage_credits = (billing_period.overage_credits or 0) + overage_amount
                                    billing_period.overage_cost = (billing_period.overage_cost or 0) + overage_amount * plan.overage_price_per_credit
                                    print(f"[BILLING_DEBUG] log_tool_usage: Updated overage credits: {billing_period.overage_credits}, cost: {billing_period.overage_cost}")
                            
                        updates.append(billing_period)
                        print(f"[BILLING_DEBUG] log_tool_usage: Added BillingPeriod to batch updates.")
                    else:
                        print(f"[BILLING_DEBUG] log_tool_usage: Billing period ID {usage_record.billing_period_id} not found.")
                else:
                    print(f"[BILLING_DEBUG] log_tool_usage: UsageRecord {usage_record.id} has no associated billing period.")
                
                # Add all updates in one batch
                for entity in updates:
                    session.add(entity)
                
                print(f"[BILLING_DEBUG] log_tool_usage: Added {len(updates)} entities to session in a single batch.")
                
                # Successfully recorded, update in-memory cache with a new timestamp
                async with self._cache_lock:
                    self._tool_usage_cache[usage_hash] = (time.time(), 1)
                
                # The commit happens automatically when session_scope exits
                print(f"[BILLING_DEBUG] log_tool_usage: All operations added to session. Commit will happen on scope exit.")
                
                return True
                
        except Exception as e:
            print(f"[BILLING_DEBUG] log_tool_usage: Error: {str(e)}")
            logger.error(f"Error logging tool usage: {e}")
            return False
    
    async def log_kb_usage(self, 
                     run_id: str, 
                     kb_usage: KBUsage, 
                     user_id: UUID) -> bool:
        """Log knowledge base usage for a specific run and update costs."""
        if not user_id or not run_id:
            logger.error(f"Missing user_id or run_id for KB logging: {user_id}, {run_id}")
            return False
            
        try:
            # Check in-memory cache first for ultra-fast duplicate prevention
            usage_hash = self._generate_kb_usage_hash(run_id, kb_usage)
            if await self._is_cached_usage(self._kb_usage_cache, usage_hash):
                print(f"[BILLING_DEBUG] log_kb_usage: MEMORY CACHE HIT - Skipping duplicate KB usage for run_id={run_id}")
                return True
                
            print(f"[BILLING_DEBUG] log_kb_usage: Starting for run_id={run_id}, kb={kb_usage.kb_name}, count={kb_usage.count}")
            from langflow.services.deps import session_scope
            
            async with session_scope() as session:
                print(f"[BILLING_DEBUG] log_kb_usage: Session created.")
                
                # Use the helper method to find the usage record
                usage_record = await self._find_usage_record(session, run_id, user_id)
                
                if not usage_record:
                    logger.warning(f"No usage record found for run_id: {run_id}")
                    print(f"[BILLING_DEBUG] log_kb_usage: Failed to find UsageRecord for run_id={run_id}")
                    return False
                
                print(f"[BILLING_DEBUG] log_kb_usage: Found UsageRecord ID: {usage_record.id} for session: {usage_record.session_id}")
                
                # DEDUPLICATION CHECK: Check for recent identical KB usage to prevent duplicates
                # Look for identical KB usage recorded in the last minute (more robust window)
                dedup_window_seconds = 60  # Extended window for deduplication
                dedup_cutoff = datetime.now(timezone.utc) - timedelta(seconds=dedup_window_seconds)
                
                recent_identical_count = (await session.exec(
                    select(func.count())
                    .where(
                        KBUsageDetail.usage_record_id == usage_record.id,
                        KBUsageDetail.kb_name == kb_usage.kb_name,
                        KBUsageDetail.count == kb_usage.count,
                        KBUsageDetail.created_at >= dedup_cutoff
                    )
                )).first()
                
                if recent_identical_count > 0:
                    print(f"[BILLING_DEBUG] log_kb_usage: DEDUPLICATION - Found {recent_identical_count} identical recent entries. Skipping to prevent duplication.")
                    return True  # Return True so caller thinks it succeeded, but we're actually skipping the duplicate
                
                # Prepare batch updates list
                updates = []
                
                # Record KB query in daily usage
                user = (await session.exec(select(User).where(User.id == user_id))).first()
                if user:
                    print(f"[BILLING_DEBUG] log_kb_usage: Found user {user.id} for daily KB query logging.")
                    # Reset daily counter if needed
                    now = datetime.now(timezone.utc)
                    # Ensure the database timestamp is treated as UTC for comparison
                    user_kb_reset_at_utc = user.daily_kb_queries_reset_at
                    if user_kb_reset_at_utc and user_kb_reset_at_utc.tzinfo is None:
                        user_kb_reset_at_utc = user_kb_reset_at_utc.replace(tzinfo=timezone.utc)
                        print(f"[BILLING_DEBUG] log_kb_usage: Made daily_kb_queries_reset_at timezone-aware (UTC).")

                    if not user_kb_reset_at_utc or (now - user_kb_reset_at_utc).days > 0:
                        print(f"[BILLING_DEBUG] log_kb_usage: Resetting daily KB queries counter for user {user.id}.")
                        user.daily_kb_queries = 0
                        user.daily_kb_queries_reset_at = now # Store the timezone-aware timestamp
                    
                    # Increment query counter
                    user.daily_kb_queries = (user.daily_kb_queries or 0) + 1
                    updates.append(user)
                    print(f"[BILLING_DEBUG] log_kb_usage: Added user update to batch. New KB query count: {user.daily_kb_queries}")
                else:
                    print(f"[BILLING_DEBUG] log_kb_usage: User not found for ID: {user_id}")
                
                # Calculate KB cost
                kb_cost = KB_ACCESS_CREDITS * kb_usage.count
                print(f"[BILLING_DEBUG] log_kb_usage: Calculated KB cost: {kb_cost}")
                
                # Create KB usage detail
                kb_detail = KBUsageDetail(
                    usage_record_id=usage_record.id,
                    kb_name=kb_usage.kb_name,
                    count=kb_usage.count,
                    cost=kb_cost
                )
                updates.append(kb_detail)
                
                # Update usage record totals in memory
                usage_record.kb_cost = (usage_record.kb_cost or 0) + kb_cost
                usage_record.total_cost = (usage_record.total_cost or 0) + kb_cost
                updates.append(usage_record)
                
                # Update billing period quota if applicable
                if usage_record.billing_period_id:
                    billing_period = await session.get(BillingPeriod, usage_record.billing_period_id)
                    if billing_period:
                        print(f"[BILLING_DEBUG] log_kb_usage: Found billing period {billing_period.id}. Updating quota.")
                        billing_period.quota_used = (billing_period.quota_used or 0) + kb_cost
                        billing_period.quota_remaining = (billing_period.quota_remaining or 0) - kb_cost
                        
                        # Handle overage if applicable
                        if billing_period.quota_remaining < 0:
                            print(f"[BILLING_DEBUG] log_kb_usage: Quota remaining is negative ({billing_period.quota_remaining}). Checking overage.")
                            # Already have user from above
                            if user and user.subscription_plan_id:
                                plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                                if plan and plan.allows_overage:
                                    overage_amount = abs(billing_period.quota_remaining)
                                    billing_period.overage_credits = (billing_period.overage_credits or 0) + overage_amount
                                    billing_period.overage_cost = (billing_period.overage_cost or 0) + overage_amount * plan.overage_price_per_credit
                                    print(f"[BILLING_DEBUG] log_kb_usage: Updated overage credits: {billing_period.overage_credits}, cost: {billing_period.overage_cost}")
                        
                        updates.append(billing_period)
                        print(f"[BILLING_DEBUG] log_kb_usage: Added BillingPeriod to batch updates.")
                    else:
                        print(f"[BILLING_DEBUG] log_kb_usage: Billing period ID {usage_record.billing_period_id} not found.")
                else:
                    print(f"[BILLING_DEBUG] log_kb_usage: UsageRecord {usage_record.id} has no associated billing period.")
                
                # Add all updates in one batch
                for entity in updates:
                    session.add(entity)
                
                print(f"[BILLING_DEBUG] log_kb_usage: Added {len(updates)} entities to session in a single batch.")
                
                # Successfully recorded, update in-memory cache with a new timestamp
                async with self._cache_lock:
                    self._kb_usage_cache[usage_hash] = (time.time(), 1)
                
                # The commit happens automatically when session_scope exits
                print(f"[BILLING_DEBUG] log_kb_usage: All operations added to session. Commit will happen on scope exit.")
                
                return True
                
        except Exception as e:
            print(f"[BILLING_DEBUG] log_kb_usage: Error: {str(e)}")
            logger.error(f"Error logging KB usage: {e}")
            return False
    
    async def finalize_run(self, run_id: str, user_id: UUID) -> Dict:
        """Finalize a run, calculate total cost, and update user balance."""
        if not user_id or not run_id:
            return {"error": f"Missing user_id or run_id: {user_id}, {run_id}"}
            
        try:
            print(f"[BILLING_DEBUG] Starting finalize_run for run_id={run_id}, user_id={user_id}")
            from langflow.services.deps import session_scope
            
            async with session_scope() as session:
                print(f"[BILLING_DEBUG] Session created successfully for finalize_run")
                
                # Use the helper method to find the usage record
                usage_record = await self._find_usage_record(session, run_id, user_id)
                
                if not usage_record:
                    return {"error": f"No usage record found for run_id: {run_id}"}
                
                print(f"[BILLING_DEBUG] Found usage record: {usage_record.id} for session: {usage_record.session_id}")
                
                # Get all usage details in a more efficient way (fewer queries)
                # Load everything in three queries instead of potentially many individual ones
                token_details = (await session.exec(
                    select(TokenUsageDetail).where(TokenUsageDetail.usage_record_id == usage_record.id)
                )).all()
                print(f"[BILLING_DEBUG] Found {len(token_details)} token usage details")
                
                tool_details = (await session.exec(
                    select(ToolUsageDetail).where(ToolUsageDetail.usage_record_id == usage_record.id)
                )).all()
                print(f"[BILLING_DEBUG] Found {len(tool_details)} tool usage details")
                
                kb_details = (await session.exec(
                    select(KBUsageDetail).where(KBUsageDetail.usage_record_id == usage_record.id)
                )).all()
                print(f"[BILLING_DEBUG] Found {len(kb_details)} KB usage details")
                
                # Fetch both user and active billing period in a single query if possible
                # First try to get user with their subscription plan
                user = (await session.exec(
                    select(User)
                    .where(User.id == user_id)
                )).first()
                
                active_period = None
                if user:
                    print(f"[BILLING_DEBUG] Found user {user.id}, current credits: {user.credits_balance}")
                    # Update user's credit balance
                    user.credits_balance = (user.credits_balance or 0) - usage_record.total_cost
                    
                    # Get active billing period in the same transaction
                    active_period = (await session.exec(
                        select(BillingPeriod)
                        .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
                    )).first()
                    
                    # Add user to session for update
                    session.add(user)
                    print(f"[BILLING_DEBUG] Updated user credits balance to: {user.credits_balance}")
                else:
                    print(f"[BILLING_DEBUG] User not found for ID: {user_id}")
                
                # Generate a detailed summary
                summary = {
                    "run_id": run_id,
                    "fixed_cost": usage_record.fixed_cost,
                    "llm_cost": usage_record.llm_cost,
                    "tools_cost": usage_record.tools_cost,
                    "kb_cost": usage_record.kb_cost,
                    "total_cost": usage_record.total_cost,
                    "created_at": usage_record.created_at.isoformat(),
                    "llm_usage": [
                        {
                            "model": detail.model_name,
                            "input_tokens": detail.input_tokens,
                            "output_tokens": detail.output_tokens,
                            "cost": detail.cost
                        }
                        for detail in token_details
                    ],
                    "tool_usage": [
                        {
                            "tool": detail.tool_name,
                            "count": detail.count,
                            "is_premium": detail.is_premium,
                            "cost": detail.cost
                        }
                        for detail in tool_details
                    ],
                    "kb_usage": [
                        {
                            "kb": detail.kb_name,
                            "count": detail.count,
                            "cost": detail.cost
                        }
                        for detail in kb_details
                    ]
                }
                
                # Get user's current quota info
                if active_period:
                    summary["quota_used"] = active_period.quota_used
                    summary["quota_remaining"] = active_period.quota_remaining
                    summary["overage_credits"] = active_period.overage_credits
                    summary["overage_cost"] = active_period.overage_cost
                    print(f"[BILLING_DEBUG] Added quota info to summary: used={active_period.quota_used}, remaining={active_period.quota_remaining}")
                
                # Log the summary for debugging
                logger.info(f"Run {run_id} finalized with cost: {usage_record.total_cost} credits")
                print(f"[BILLING_DEBUG] Finalized run with total cost: {usage_record.total_cost} credits")
                print(f"[BILLING_DEBUG] finalize_run completed successfully")
                
                return summary
                
        except Exception as e:
            print(f"[BILLING_DEBUG] Error in finalize_run: {str(e)}")
            logger.error(f"Error finalizing run: {e}")
            return {"error": str(e)}
    
    async def get_user_usage_summary(self, user_id: UUID, period_days: int = 30) -> Dict:
        """Get usage summary for a user over a period of time."""
        if not user_id:
            logger.error("User ID is required for usage summary")
            return {"error": "Missing user_id parameter"}
            
        try:
            from langflow.services.deps import session_scope
            
            async with session_scope() as session:
                # Calculate date range
                now = datetime.now(timezone.utc)
                start_date = now - timedelta(days=period_days)
                
                # Get all usage records for this user in the period
                usage_records = (await session.exec(
                    select(UsageRecord)
                    .where(
                        UsageRecord.user_id == user_id,
                        UsageRecord.created_at >= start_date
                    )
                )).all()
                
                # Calculate aggregates
                total_cost = sum(record.total_cost for record in usage_records)
                llm_cost = sum(record.llm_cost for record in usage_records)
                tools_cost = sum(record.tools_cost for record in usage_records)
                kb_cost = sum(record.kb_cost for record in usage_records)
                fixed_cost = sum(record.fixed_cost for record in usage_records)
                
                # Get token usage
                token_details = []
                for record in usage_records:
                    details = (await session.exec(
                        select(TokenUsageDetail)
                        .where(TokenUsageDetail.usage_record_id == record.id)
                    )).all()
                    token_details.extend(details)
                
                # Aggregate by model
                model_usage = {}
                for detail in token_details:
                    if detail.model_name not in model_usage:
                        model_usage[detail.model_name] = {
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cost": 0
                        }
                    
                    model_usage[detail.model_name]["input_tokens"] += detail.input_tokens
                    model_usage[detail.model_name]["output_tokens"] += detail.output_tokens
                    model_usage[detail.model_name]["cost"] += detail.cost
                
                # Get current billing period
                active_period = (await session.exec(
                    select(BillingPeriod)
                    .where(BillingPeriod.user_id == user_id, BillingPeriod.status == "active")
                )).first()
                
                # Build summary
                summary = {
                    "user_id": str(user_id),
                    "period_days": period_days,
                    "total_runs": len(usage_records),
                    "total_cost": total_cost,
                    "cost_breakdown": {
                        "fixed": fixed_cost,
                        "llm": llm_cost,
                        "tools": tools_cost,
                        "kb": kb_cost
                    },
                    "model_usage": model_usage,
                    "current_period": {
                        "start_date": active_period.start_date.isoformat() if active_period else None,
                        "end_date": active_period.end_date.isoformat() if active_period else None,
                        "quota_used": active_period.quota_used if active_period else 0,
                        "quota_remaining": active_period.quota_remaining if active_period else 0
                    }
                }
                
                return summary
                
        except Exception as e:
            logger.error(f"Error getting user usage summary: {e}")
            return {"error": str(e)}
    
    async def teardown(self) -> None:
        """Clean up resources when service is shut down"""
        print("Tearing down Billing Service")
    
    async def check_user_billing_setup(self, user_id: UUID) -> Dict:
        """Check if a user has the necessary billing period setup"""
        if not user_id:
            return {"error": "No user ID provided"}
            
        try:
            print(f"[BILLING_DEBUG] Checking billing setup for user_id={user_id}")
            from langflow.services.deps import session_scope
            
            async with session_scope() as session:
                print(f"[BILLING_DEBUG] Session created successfully for check_user_billing_setup")
                
                # Get user and plan in a single query if possible
                user = (await session.exec(select(User).where(User.id == user_id))).first()
                if not user:
                    print(f"[BILLING_DEBUG] User not found for ID: {user_id}")
                    return {"error": f"User not found for ID: {user_id}"}
                
                print(f"[BILLING_DEBUG] Found user: {user.id}, email: {user.email}")
                
                # Load required data with the minimum number of queries
                subscription_plan = None
                if user.subscription_plan_id:
                    subscription_plan = await session.get(SubscriptionPlan, user.subscription_plan_id)
                    if subscription_plan:
                        print(f"[BILLING_DEBUG] User has subscription plan: {subscription_plan.name}")
                    else:
                        print(f"[BILLING_DEBUG] User has invalid subscription_plan_id: {user.subscription_plan_id}")
                else:
                    print(f"[BILLING_DEBUG] User has no subscription plan")
                
                # Get all billing periods and usage records with minimal queries
                billing_periods = (await session.exec(
                    select(BillingPeriod)
                    .where(BillingPeriod.user_id == user_id)
                )).all()
                
                # Extract active period from all periods
                active_period = next((period for period in billing_periods if period.status == "active"), None)
                
                if active_period:
                    print(f"[BILLING_DEBUG] Found active billing period: {active_period.id}")
                    print(f"[BILLING_DEBUG] Period: {active_period.start_date} to {active_period.end_date}")
                    print(f"[BILLING_DEBUG] Quota used: {active_period.quota_used}, remaining: {active_period.quota_remaining}")
                else:
                    print(f"[BILLING_DEBUG] No active billing period found for user")
                    
                    if billing_periods:
                        print(f"[BILLING_DEBUG] Found {len(billing_periods)} inactive billing periods")
                        for period in billing_periods:
                            print(f"[BILLING_DEBUG] Period ID: {period.id}, Status: {period.status}, Dates: {period.start_date} to {period.end_date}")
                    else:
                        print(f"[BILLING_DEBUG] No billing periods found for user")
                        
                        # Create a default billing period for testing
                        print(f"[BILLING_DEBUG] Creating a default billing period for testing")
                        from datetime import datetime, timezone, timedelta
                        
                        now = datetime.now(timezone.utc)
                        new_period = BillingPeriod(
                            user_id=user_id,
                            start_date=now,
                            end_date=now + timedelta(days=30),
                            status="active",
                            quota_used=0.0,
                            quota_remaining=1000.0,  # Default 1000 credits
                            subscription_plan_id=user.subscription_plan_id
                        )
                        
                        session.add(new_period)
                        active_period = new_period
                        print(f"[BILLING_DEBUG] Created test billing period (will be committed at the end of the session)")
                
                # Get recent usage records in a single query
                usage_records = (await session.exec(
                    select(UsageRecord)
                    .where(UsageRecord.user_id == user_id)
                    .order_by(UsageRecord.created_at.desc())
                    .limit(5)
                )).all()
                
                if usage_records:
                    print(f"[BILLING_DEBUG] Found {len(usage_records)} usage records for user")
                    for record in usage_records:
                        print(f"[BILLING_DEBUG] Record ID: {record.id}, Session: {record.session_id}, Cost: {record.total_cost}")
                else:
                    print(f"[BILLING_DEBUG] No usage records found for user")
                
                # Create test record
                test_record = UsageRecord(
                    user_id=user_id,
                    flow_id=UUID('00000000-0000-0000-0000-000000000000'),  # Dummy UUID
                    session_id="TEST_SESSION_ID",
                    billing_period_id=active_period.id if active_period else None,
                    fixed_cost=1.0,
                    llm_cost=2.0,
                    tools_cost=3.0,
                    kb_cost=0.0,
                    total_cost=6.0
                )
                
                session.add(test_record)
                print(f"[BILLING_DEBUG] Added test UsageRecord to session (will be committed at the end of the session)")
                
                # All database operations will be committed together when the session scope exits
                # This reduces the number of database round-trips
                
                return {
                    "user_id": str(user.id),
                    "email": user.email,
                    "subscription_plan": subscription_plan.name if subscription_plan else None,
                    "has_active_billing_period": active_period is not None,
                    "billing_period_id": str(active_period.id) if active_period else None,
                    "usage_records_count": len(usage_records),
                    "test_record_created": True
                }
                
        except Exception as e:
            print(f"[BILLING_DEBUG] Error in check_user_billing_setup: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    async def _find_usage_record(self, session, run_id, user_id):
        """Enhanced helper method to find usage record with an ID disambiguation system."""
        if not user_id:
            logger.error("User ID is required for finding usage record")
            return None
            
        print(f"[BILLING_DEBUG] _find_usage_record: Finding usage record for run_id='{run_id}', user_id={user_id}")
        
        # Create a list of possible session IDs to search for
        possible_ids = [run_id]
        
        # Check if we have a mapping for this run_id
        if run_id in self._uuid_to_session_mappings:
            mapped_session_id = self._uuid_to_session_mappings[run_id]
            possible_ids.append(mapped_session_id)
            print(f"[BILLING_DEBUG] _find_usage_record: Added mapping from memory: {run_id} -> {mapped_session_id}")
        
        # Check for session prefix mapping
        if isinstance(run_id, str) and run_id.startswith("Session "):
            try:
                day_prefix = run_id.split(",")[0]
                if day_prefix in self._session_prefix_mappings:
                    mapped_full_session = self._session_prefix_mappings[day_prefix]
                    possible_ids.append(mapped_full_session)
                    print(f"[BILLING_DEBUG] _find_usage_record: Added prefix mapping from memory: {day_prefix} -> {mapped_full_session}")
            except Exception as e_prefix:
                print(f"[BILLING_DEBUG] _find_usage_record: Error checking session prefix mapping: {e_prefix}")
        
        # Add pattern for "Session " format
        like_pattern = None
        if isinstance(run_id, str) and run_id.startswith("Session "):
            try:
                pattern_parts = run_id.split(", ")[0]
                like_pattern = f"{pattern_parts}%"
                print(f"[BILLING_DEBUG] _find_usage_record: Added like pattern: '{like_pattern}'")
            except Exception:
                pass
        
        # Create a single query for all possible IDs
        query = select(UsageRecord).where(UsageRecord.user_id == user_id)
        
        # Add OR conditions for all possible IDs
        from sqlalchemy import or_
        conditions = []
        for pid in possible_ids:
            conditions.append(UsageRecord.session_id == pid)
        
        # Add LIKE pattern if available
        if like_pattern:
            conditions.append(UsageRecord.session_id.like(like_pattern))
        
        # Add the combined conditions to the query
        if conditions:
            query = query.where(or_(*conditions))
        
        # Order by most recent first and limit results
        query = query.order_by(UsageRecord.created_at.desc()).limit(5)
        
        # Execute the query - a single database operation regardless of how many IDs we're checking
        usage_records = (await session.exec(query)).all()
        
        if usage_records:
            # Get the most recent record
            usage_record = usage_records[0]
            print(f"[BILLING_DEBUG] _find_usage_record: Found record using optimized query: ID={usage_record.id}, session={usage_record.session_id}")
            
            # Learn from this for future lookups
            if usage_record.session_id != run_id:
                # Store mapping for future use
                self._uuid_to_session_mappings[run_id] = usage_record.session_id
                print(f"[BILLING_DEBUG] _find_usage_record: Saved new mapping: {run_id} -> {usage_record.session_id}")
                
                # Store prefix mapping if applicable
                if isinstance(run_id, str) and run_id.startswith("Session "):
                    try:
                        prefix = run_id.split(",")[0]
                        self._session_prefix_mappings[prefix] = usage_record.session_id
                        print(f"[BILLING_DEBUG] _find_usage_record: Saved new prefix mapping: {prefix} -> {usage_record.session_id}")
                    except Exception:
                        pass
            
            return usage_record
        
        # APPROACH 5: Last resort - most recent record
        print(f"[BILLING_DEBUG] _find_usage_record: No record found for possible IDs. Falling back to most recent record.")
        absolute_recent = (await session.exec(
            select(UsageRecord)
            .where(UsageRecord.user_id == user_id)
            .order_by(UsageRecord.created_at.desc())
            .limit(1)
        )).first()
        
        if absolute_recent:
            print(f"[BILLING_DEBUG] _find_usage_record: Using most recent record as last resort: ID={absolute_recent.id}, session={absolute_recent.session_id}")
            
            # Learn from this for future lookups
            self._uuid_to_session_mappings[run_id] = absolute_recent.session_id
            print(f"[BILLING_DEBUG] _find_usage_record: Saved new mapping: {run_id} -> {absolute_recent.session_id}")
            
            if isinstance(run_id, str) and run_id.startswith("Session "):
                try:
                    # Store prefix mapping for future use
                    prefix = run_id.split(",")[0]
                    self._session_prefix_mappings[prefix] = absolute_recent.session_id
                    print(f"[BILLING_DEBUG] _find_usage_record: Saved new prefix mapping: {prefix} -> {absolute_recent.session_id}")
                except Exception:
                    pass
                    
            return absolute_recent
            
        # If we get here, no record was found with any method
        print(f"[BILLING_DEBUG] _find_usage_record: No usage record found for run_id: {run_id} after all checks.")
        return None 