from typing import Dict, List, Optional
import logging
from loguru import logger
from pydantic import BaseModel
from uuid import UUID
import uuid
import asyncio

from langflow.services.base import Service
from langflow.services.schema import ServiceType

# Credit cost constants
FIXED_COST_CREDITS = 4  # Fixed platform cost per task
TOOL_ACCESS_CREDITS = 3  # Cost per tool use
KB_ACCESS_CREDITS = 2  # Cost per knowledge base access
CREDIT_TO_USD_RATIO = 0.001  # 1 credit = $0.001 USD
LLM_MARKUP_PERCENTAGE = 0.2  # 20% markup on LLM costs

# Model costs per 1K tokens in USD (estimated)
MODEL_COSTS = {
    #OpenAI models
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015}, #correct
    "gpt-4": {"input": 0.03, "output": 0.06}, #correct
    "gpt-4o": {"input": 0.0025, "output": 0.01}, #correct
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006}, #correct
    "gpt-4-turbo": {"input": 0.01, "output": 0.03}, #correct
    "gpt-4.5": {"input": 0.075, "output": 0.15}, #correct
    "gpt-3.5-turbo-0125": {"input": 0.0005, "output": 0.0015}, #correct
    "openai-o1": {"input": 0.015, "output": 0.06}, #correct
    "openai-o3-mini": {"input": 0.0011, "output": 0.0044}, #correct
    #Gemini models
    "gemini-2.5-pro": {"input": 0.00125, "output": 0.01},  # For <= 200k tokens
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},  # text/image/video
    "gemini-2.0-flash-lite": {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},  # For <= 128k tokens
    "gemini-1.5-flash-8b": {"input": 0.0000375, "output": 0.00015},  # For <= 128k tokens
    "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},  # For <= 128k tokens
    #Anthropic models
    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
    "anthropic.claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
}
# Default model cost if specific model not found
DEFAULT_MODEL_COST = {"input": 0.001, "output": 0.002}


class ToolUsage(BaseModel):
    """Model to track tool usage for an AI agent run"""
    tool_name: str
    count: int = 1


class KBUsage(BaseModel):
    """Model to track knowledge base access for an AI agent run"""
    kb_name: str
    count: int = 1


class TokenUsage(BaseModel):
    """Model to track token usage for an AI agent run"""
    model_name: str
    input_tokens: int = 0
    output_tokens: int = 0


class CreditCostBreakdown(BaseModel):
    """Detailed breakdown of credit costs for an AI agent run"""
    fixed_cost: float = FIXED_COST_CREDITS
    llm_cost: float = 0
    tools_cost: float = 0
    kb_cost: float = 0
    total_cost: float = 0
    # We store the detailed lists in the finalized breakdown
    token_usages: List[TokenUsage] = []
    tool_usages: List[ToolUsage] = []
    kb_usages: List[KBUsage] = []


# New model to hold pending usage data
class PendingUsage(BaseModel):
    tokens: List[TokenUsage] = []
    tools: List[ToolUsage] = []
    kbs: List[KBUsage] = []


class CreditService(Service):
    """Service for tracking AI agent usage costs."""
    name = ServiceType.CREDIT_SERVICE
    
    def __init__(self):
        super().__init__()
        # Store pending usage data per run_id
        self.pending_usage: Dict[str, PendingUsage] = {}
        # Store finalized cost breakdowns per run_id
        self.finalized_costs: Dict[str, CreditCostBreakdown] = {}
        # Track already logged KBs to prevent double-counting
        self._logged_kbs: Dict[str, set] = {}
        
    def _get_or_create_pending(self, run_id: str) -> PendingUsage:
        if run_id not in self.pending_usage:
            print(f"Creating new pending usage entry for run_id: {run_id}")
            self.pending_usage[run_id] = PendingUsage()
        return self.pending_usage[run_id]

    def log_token_usage(self, run_id: str, token_usage: TokenUsage):
        """Logs token usage for a specific run."""
        if not run_id:
            print("Cannot log token usage without a run_id.")
            return
        pending = self._get_or_create_pending(run_id)
        pending.tokens.append(token_usage)
        print(f"Logged token usage for run {run_id}: {token_usage.model_dump_json()}")

    def log_tool_usage(self, run_id: str, tool_usage: ToolUsage):
        """Logs tool usage for a specific run."""
        if not run_id:
            print("Cannot log tool usage without a run_id.")
            return
        pending = self._get_or_create_pending(run_id)
        pending.tools.append(tool_usage)
        print(f"Logged tool usage for run {run_id}: {tool_usage.model_dump_json()}")

    def log_kb_usage(self, run_id: str, kb_usage: KBUsage):
        """Logs knowledge base usage for a specific run."""
        if not run_id:
            print("Cannot log KB usage without a run_id.")
            return
            
        # Check if this KB has already been logged for this run to prevent double-counting
        if run_id not in self._logged_kbs:
            self._logged_kbs[run_id] = set()
            
        # If this KB was already logged, don't log it again
        if kb_usage.kb_name in self._logged_kbs[run_id]:
            print(f"KB {kb_usage.kb_name} already logged for run {run_id}, skipping to prevent double-counting")
            return
            
        # Add to tracked KBs and proceed with logging
        self._logged_kbs[run_id].add(kb_usage.kb_name)
        pending = self._get_or_create_pending(run_id)
        pending.kbs.append(kb_usage)
        print(f"Logged KB usage for run {run_id}: {kb_usage.model_dump_json()}")

    def _calculate_single_llm_cost(self, token_usage: TokenUsage) -> float:
        """Calculate LLM cost in credits for a single token usage entry."""
        # Renamed original calculate_llm_cost to avoid conflict
        model_name = token_usage.model_name.lower().strip()
        model_cost = MODEL_COSTS.get(model_name, DEFAULT_MODEL_COST)
        input_cost_usd = (token_usage.input_tokens / 1000) * model_cost["input"]
        output_cost_usd = (token_usage.output_tokens / 1000) * model_cost["output"]
        total_cost_usd = input_cost_usd + output_cost_usd
        marked_up_cost_usd = total_cost_usd * (1 + LLM_MARKUP_PERCENTAGE)
        credit_cost = marked_up_cost_usd / CREDIT_TO_USD_RATIO
        return credit_cost

    def calculate_total_llm_cost(self, token_usages: List[TokenUsage]) -> float:
        """Calculate the total LLM cost for a list of token usage entries."""
        return sum(self._calculate_single_llm_cost(usage) for usage in token_usages)

    def calculate_tools_cost(self, tool_usages: List[ToolUsage]) -> float:
        """Calculate cost of tool usage in credits"""
        # Import premium tools constants
        try:
            from langflow.callbacks.cost_tracking import PREMIUM_TOOLS
        except ImportError:
            # Fallback if import fails
            PREMIUM_TOOLS = {}
        
        total_cost = 0
        for tool in tool_usages:
            tool_name = tool.tool_name
            # Check if it's a premium tool with specific pricing
            if tool_name in PREMIUM_TOOLS:
                premium_cost = PREMIUM_TOOLS[tool_name] * tool.count
                total_cost += premium_cost
                print(f"Premium tool '{tool_name}' cost: {premium_cost} credits")
            else:
                # Standard tool pricing
                total_cost += TOOL_ACCESS_CREDITS * tool.count
            
        return total_cost
    
    def calculate_kb_cost(self, kb_usages: List[KBUsage]) -> float:
        """Calculate cost of knowledge base access in credits"""
        total_kb_accesses = sum(kb.count for kb in kb_usages)
        return total_kb_accesses * KB_ACCESS_CREDITS
    
    async def finalize_run_cost(self, run_id: str) -> Optional[CreditCostBreakdown]:
        """Calculate and finalize the total cost for a completed run, attempting consolidation."""
        logger.info(f"Starting finalization in CreditService for primary run_id: {run_id}")
        print(f"[CreditService] Starting finalization for primary run_id: {run_id}")

        # --- Consolidation Attempt (REVISED) ---
        consolidated_pending = PendingUsage()
        related_ids_to_remove = set()
        potential_component_prefix = f"{run_id}_" # Prefix for component-specific IDs

        # Function to safely extend lists (unchanged)
        def safe_extend(target_list, source_list):
             if source_list:
                 target_list.extend(source_list)

        # 1. Add the primary run_id itself
        ids_to_check = {run_id}

        # 2. Add potential related primary IDs (UUID <-> Session)
        potential_other_primary_id = None
        is_session_id = run_id.startswith("Session")
        is_uuid = False
        try:
            uuid.UUID(run_id)
            is_uuid = True
        except ValueError:
            pass

        # If primary is Session, look for any UUID key in pending_usage
        if is_session_id:
            for key in self.pending_usage.keys():
                try:
                    uuid.UUID(key)
                    # Found a potential UUID counterpart
                    potential_other_primary_id = key
                    logger.debug(f"Found potential UUID counterpart {key} for Session ID {run_id}")
                    print(f"[CreditService] Found potential UUID counterpart {key} for Session ID {run_id}")
                    break # Assume only one for now
                except ValueError:
                    continue
        # If primary is UUID, look for *any* Session key (less precise)
        # This is harder - maybe the most recent? Let's just log for now.
        elif is_uuid:
            # Finding the 'correct' Session ID is ambiguous here without more context.
            # The sync logic in api/build.py is supposed to handle this direction.
            logger.debug(f"Finalizing with UUID {run_id}. Relying on prior sync for Session ID data.")
            print(f"[CreditService] Finalizing with UUID {run_id}. Relying on prior sync for Session ID data.")

        if potential_other_primary_id:
            ids_to_check.add(potential_other_primary_id)

        # 3. Add component IDs derived from *all* potential primary IDs found
        component_prefixes_to_check = set()
        for primary_id in ids_to_check:
            component_prefixes_to_check.add(f"{primary_id}_")

        # Gather usage associated with all identified IDs and their component derivatives
        for pending_id, pending_data in list(self.pending_usage.items()):
            # Check if it's one of the primary IDs
            if pending_id in ids_to_check:
                logger.debug(f"Consolidating primary usage from ID: {pending_id}")
                print(f"[CreditService] Consolidating primary usage from ID: {pending_id}")
                safe_extend(consolidated_pending.tokens, pending_data.tokens)
                safe_extend(consolidated_pending.tools, pending_data.tools)
                safe_extend(consolidated_pending.kbs, pending_data.kbs)
                related_ids_to_remove.add(pending_id)
                continue # Added, move to next item

            # Check if it's a component ID derived from any potential primary ID
            for prefix in component_prefixes_to_check:
                if pending_id.startswith(prefix):
                    logger.debug(f"Consolidating component usage from ID: {pending_id} (prefix: {prefix})")
                    print(f"[CreditService] Consolidating component usage from ID: {pending_id}")
                    safe_extend(consolidated_pending.tokens, pending_data.tokens)
                    safe_extend(consolidated_pending.tools, pending_data.tools)
                    safe_extend(consolidated_pending.kbs, pending_data.kbs)
                    related_ids_to_remove.add(pending_id)
                    break # Added, move to next item

        # Remove the consolidated entries from pending_usage (unchanged)
        cleared_count = 0
        for id_to_remove in related_ids_to_remove:
            if id_to_remove in self.pending_usage:
                self.pending_usage.pop(id_to_remove)
                cleared_count += 1
        if cleared_count > 0:
            logger.debug(f"Removed {cleared_count} consolidated pending entries related to {run_id}")
            print(f"[CreditService] Removed {cleared_count} consolidated pending entries for {run_id}")


        # If no usage was found after expanded consolidation attempt (unchanged)
        if not consolidated_pending.tokens and not consolidated_pending.tools and not consolidated_pending.kbs:
             logger.warning(f"No pending usage data found for run_id {run_id} (or related IDs) to finalize.")
             print(f"[CreditService] No pending usage data found for run_id {run_id} (or related IDs) to finalize.")
             # Check if already finalized using the primary ID
             if run_id in self.finalized_costs:
                 logger.info(f"Cost for run_id {run_id} was already finalized. Returning cached result.")
                 print(f"[CreditService] Cost for run_id {run_id} was already finalized.")
                 return self.finalized_costs[run_id]
             return None # No usage found


        # --- Proceed with calculation using consolidated_pending --- (unchanged)
        pending = consolidated_pending

        # Deduplicate token usage (unchanged)
        if pending.tokens:
            unique_tokens = []
            token_signatures = set()
            for token_usage in pending.tokens:
                 # Using a simple signature for deduplication
                signature = f"{token_usage.model_name}:{token_usage.input_tokens}:{token_usage.output_tokens}"
                # Handle potential collisions if exact same usage happens multiple times
                temp_signature = signature
                count = 0
                while temp_signature in token_signatures:
                    count += 1
                    temp_signature = f"{signature}_call_{count}"

                # Only add if the unique signature hasn't been seen
                if temp_signature not in token_signatures:
                    token_signatures.add(temp_signature)
                    unique_tokens.append(token_usage)
                # else: # Log the duplicate if needed for debugging
                #     logger.debug(f"Deduplicating token entry: {signature}")


            if len(unique_tokens) < len(pending.tokens):
                duplicates_removed = len(pending.tokens) - len(unique_tokens)
                logger.info(f"[Deduplication] Removed {duplicates_removed} duplicate token entries for run {run_id}")
                print(f"[CreditService][Deduplication] Removed {duplicates_removed} duplicate token entries")
                pending.tokens = unique_tokens


        # Calculate individual costs (unchanged)
        total_llm_cost = self.calculate_total_llm_cost(pending.tokens)
        tools_cost = self.calculate_tools_cost(pending.tools)
        kb_cost = self.calculate_kb_cost(pending.kbs)
        total_cost = FIXED_COST_CREDITS + total_llm_cost + tools_cost + kb_cost

        # Create final cost breakdown (unchanged)
        cost_breakdown = CreditCostBreakdown(
            fixed_cost=FIXED_COST_CREDITS,
            llm_cost=total_llm_cost,
            tools_cost=tools_cost,
            kb_cost=kb_cost,
            total_cost=total_cost,
            token_usages=pending.tokens, # Store the consolidated list
            tool_usages=pending.tools,   # Store the consolidated list
            kb_usages=pending.kbs      # Store the consolidated list
        )


        # Store the finalized cost record using the primary run_id (unchanged)
        self.finalized_costs[run_id] = cost_breakdown
        logger.info(f"Finalized cost stored for run_id: {run_id}")

        # --- Logging (Enhanced for Reconciliation) --- (unchanged)
        # Keep existing detailed logging but add a clear final statement
        # ... (existing logging code for breakdown - ensure it uses the 'pending' variable) ...
        llm_calls_count = len(pending.tokens)
        total_input_tokens = sum(t.input_tokens for t in pending.tokens)
        total_output_tokens = sum(t.output_tokens for t in pending.tokens)
        unique_models = list(set(t.model_name for t in pending.tokens))

        tools_count = len(pending.tools)
        unique_tools = list(set(t.tool_name for t in pending.tools))
        kb_count = len(pending.kbs)
        unique_kbs = list(set(kb.kb_name for kb in pending.kbs))

        # Enhanced log header with run context
        print("\n" + "="*70)
        # Log with primary run_id for easier tracking
        print(f"CREDIT SERVICE FINAL COST SUMMARY (Run ID: {run_id})")
        print("="*70)

        # Log the final cost breakdown summary with enhanced metrics
        # Clearly state this is the CreditService calculation
        print(f"✅ Total Final Credits Calculated by CreditService: {total_cost:.4f} credits")
        print(f"   (Equivalent to ${total_cost * CREDIT_TO_USD_RATIO:.6f})")
        print(f"   Breakdown: Fixed={FIXED_COST_CREDITS:.2f} | LLM={total_llm_cost:.4f} | Tools={tools_cost:.2f} | KB={kb_cost:.2f}")

        # LLM Usage Section
        if pending.tokens:
            print("\n📊 LLM USAGE METRICS:")
            print(f"  • Total LLM calls: {llm_calls_count}")
            print(f"  • Models used: {', '.join(unique_models)}")
            print(f"  • Total tokens: {total_input_tokens + total_output_tokens} (Input: {total_input_tokens}, Output: {total_output_tokens})")

            # Detailed per-model breakdown if multiple models used
            if len(unique_models) > 1:
                print("  • Per-model breakdown:")
                for model in unique_models:
                    model_tokens = [t for t in pending.tokens if t.model_name == model]
                    model_input = sum(t.input_tokens for t in model_tokens)
                    model_output = sum(t.output_tokens for t in model_tokens)
                    model_calls = len(model_tokens)
                    print(f"    - {model}: {model_calls} calls, {model_input} input, {model_output} output")

        # Tools Usage Section
        if pending.tools:
            print("\n🔧 TOOLS USAGE METRICS:")
            print(f"  • Total tool invocations: {tools_count}")
            print(f"  • Unique tools used: {len(unique_tools)}")
            # Consolidate tool counts for logging
            tool_counts = {}
            for tool in pending.tools:
                tool_counts[tool.tool_name] = tool_counts.get(tool.tool_name, 0) + tool.count
            tools_str = ", ".join([f"{name}({count})" for name, count in tool_counts.items()])
            print(f"  • Tools breakdown: {tools_str}")

            # Check for premium tools
            try:
                from langflow.callbacks.cost_tracking import PREMIUM_TOOLS
                premium_tool_usage = {name: count for name, count in tool_counts.items() if name in PREMIUM_TOOLS}
                if premium_tool_usage:
                    print("  • Premium tools:")
                    for name, count in premium_tool_usage.items():
                        print(f"    - {name}: {count} uses, {PREMIUM_TOOLS.get(name, 0) * count} credits")
            except ImportError:
                pass

        # KB Usage Section
        if pending.kbs:
            print("\n📚 KNOWLEDGE BASE USAGE METRICS:")
            print(f"  • Total KB accesses: {kb_count}")
            print(f"  • Unique KBs accessed: {len(unique_kbs)}")
            # Consolidate KB counts for logging
            kb_counts = {}
            for kb in pending.kbs:
                kb_counts[kb.kb_name] = kb_counts.get(kb.kb_name, 0) + kb.count
            kb_str = ", ".join([f"{name}({count})" for name, count in kb_counts.items()])
            print(f"  • KB breakdown: {kb_str}")

        # Add Reconciliation Note
        print("---")
        print("NOTE: Compare this total with the 'total_cost' in the 'UsageRecord' table ")
        print(f"      for the user associated with run_id (session_id in DB): {run_id}")
        print("="*70 + "\n")
        logger.info(f"CreditService Final Cost for Run ID {run_id}: {total_cost:.4f} credits.")


        # --- Update BillingService with Detailed Usage ---
        try:
            from langflow.services.manager import service_manager
            billing_service = service_manager.get(ServiceType.BILLING_SERVICE)
            if billing_service:
                # Get user_id from TokenUsageRegistry if available
                user_id = None
                try:
                    from langflow.utils.token_usage_registry import TokenUsageRegistry
                    registry = TokenUsageRegistry.get_instance()
                    user_id = registry._get_user_id_for_flow(run_id)
                    
                    # If no user_id found for this run_id, check related IDs
                    if not user_id and hasattr(registry, "_id_mapping"):
                        # Check if this run_id maps to another ID
                        if run_id in registry._id_mapping:
                            mapped_id = registry._id_mapping[run_id]
                            user_id = registry._get_user_id_for_flow(mapped_id)
                            if user_id:
                                print(f"[CreditService] Found user_id from mapped flow ID: {mapped_id}")
                        
                        # Also check if any other ID maps to this run_id
                        for source_id, target_id in registry._id_mapping.items():
                            if target_id == run_id:
                                user_id = registry._get_user_id_for_flow(source_id)
                                if user_id:
                                    print(f"[CreditService] Found user_id from reverse mapped flow ID: {source_id}")
                                    break
                    
                    if user_id:
                        print(f"[CreditService] Found user_id: {user_id} for run: {run_id}")
                    else:
                        print(f"[CreditService] WARNING: No user_id found for run: {run_id}")
                except Exception as e:
                    print(f"[CreditService] Error getting user_id from TokenUsageRegistry: {e}")
                
                # If we couldn't get a user_id, we need to skip calling BillingService
                if not user_id:
                    print(f"[CreditService] Skipping BillingService updates - missing user_id for run: {run_id}")
                    return cost_breakdown
                
                # Schedule individual logging tasks for each usage type
                tasks = []
                if cost_breakdown.token_usages:
                    for token_usage in cost_breakdown.token_usages:
                        tasks.append(billing_service.log_token_usage(run_id=run_id, token_usage=token_usage, user_id=user_id))
                
                if cost_breakdown.tool_usages:
                    for tool_usage in cost_breakdown.tool_usages:
                         tasks.append(billing_service.log_tool_usage(run_id=run_id, tool_usage=tool_usage, user_id=user_id))
                
                if cost_breakdown.kb_usages:
                     for kb_usage in cost_breakdown.kb_usages:
                         tasks.append(billing_service.log_kb_usage(run_id=run_id, kb_usage=kb_usage, user_id=user_id))
                
                if tasks:
                    # Run all logging tasks concurrently
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    # Check for errors
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            logger.error(f"Error logging usage detail {i} to BillingService for run {run_id}: {result}")
                            print(f"[CreditService] Error logging usage detail {i} to BillingService: {result}")
                        elif result is False: # Assuming False indicates logging failure
                             logger.warning(f"Failed to log usage detail {i} to BillingService for run {run_id}")
                             print(f"[CreditService] Failed to log usage detail {i} to BillingService")
                    print(f"[CreditService] Sent {len(tasks)} usage details to BillingService for run {run_id}")
                else:
                    print(f"[CreditService] No detailed usage to send to BillingService for run {run_id}")
        except Exception as e:
            logger.error(f"Failed to get or update BillingService for run {run_id}: {e}")
            print(f"[CreditService] Failed to get or update BillingService: {e}")


        # Clear KB tracking for the primary run_id and related component IDs (REVISED to use ids_to_check)
        ids_to_clear_kb = set()
        if hasattr(self, "_logged_kbs"): # Ensure attribute exists
            for primary_id in ids_to_check: # Check against all potential primary IDs
                ids_to_clear_kb.add(primary_id)
                kb_prefix = f"{primary_id}_"
                for kb_run_id in list(self._logged_kbs.keys()):
                    if kb_run_id.startswith(kb_prefix):
                        ids_to_clear_kb.add(kb_run_id)

            cleared_kb_count = 0
            for id_to_clear in ids_to_clear_kb:
                if id_to_clear in self._logged_kbs:
                    self._logged_kbs.pop(id_to_clear)
                    cleared_kb_count += 1
            if cleared_kb_count > 0:
                 logger.debug(f"[KB Tracking] Cleared {cleared_kb_count} KB tracking entries related to run {run_id}")
                 print(f"[CreditService][KB Tracking] Cleared {cleared_kb_count} KB tracking entries related to run {run_id}")


        return cost_breakdown

    # Keep the clear_related_pending helper as it might be useful
    def clear_related_pending(self, primary_run_id: str):
        """Clears pending usage for the primary ID and potentially related component IDs."""
        ids_to_clear = {primary_run_id}
        prefix = f"{primary_run_id}_"
        for key in list(self.pending_usage.keys()):
             if key.startswith(prefix):
                  ids_to_clear.add(key)

        cleared_count = 0
        for run_id in ids_to_clear:
            if run_id in self.pending_usage:
                self.pending_usage.pop(run_id)
                cleared_count += 1
        if cleared_count > 0:
             logger.info(f"Cleared {cleared_count} pending usage entries related to {primary_run_id}.")
             print(f"[CreditService] Cleared {cleared_count} pending usage entries related to {primary_run_id}.")

    def get_cost_breakdown(self, run_id: str) -> Optional[CreditCostBreakdown]:
        """Get the finalized cost breakdown for a specific run."""
        cost = self.finalized_costs.get(run_id)
        if not cost:
            print(f"No finalized cost breakdown found for run_id: {run_id}")
        return cost
    
    def extract_token_usage_from_llm_response(self, response_metadata: dict) -> Optional[TokenUsage]:
        """Extract token usage information from LLM response metadata"""
        model_name = response_metadata.get("model_name", "default")
        
        # Handle OpenAI format
        if "token_usage" in response_metadata:
            token_usage = response_metadata["token_usage"]
            return TokenUsage(
                model_name=model_name,
                input_tokens=token_usage.get("prompt_tokens", 0),
                output_tokens=token_usage.get("completion_tokens", 0)
            )
        
        # Handle Anthropic format
        elif "usage" in response_metadata:
            usage = response_metadata["usage"]
            return TokenUsage(
                model_name=model_name,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0)
            )
        
        return None
    
    async def teardown(self) -> None:
        """Clean up resources when service is shut down"""
        # In a real implementation, this would persist any unsaved data
        print("Tearing down Credit Service")
        # Clear in-memory stores on teardown for clean slate if service restarts
        self.pending_usage.clear()
        self.finalized_costs.clear() 