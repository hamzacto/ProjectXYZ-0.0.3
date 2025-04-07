from typing import Dict, List, Optional
import logging
from loguru import logger
from pydantic import BaseModel
from uuid import UUID

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
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4o": {"input": 0.01, "output": 0.03},
    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
    "anthropic.claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
    # Add more models as needed
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
        total_tool_accesses = sum(tool.count for tool in tool_usages)
        return total_tool_accesses * TOOL_ACCESS_CREDITS
    
    def calculate_kb_cost(self, kb_usages: List[KBUsage]) -> float:
        """Calculate cost of knowledge base access in credits"""
        total_kb_accesses = sum(kb.count for kb in kb_usages)
        return total_kb_accesses * KB_ACCESS_CREDITS
    
    def finalize_run_cost(self, run_id: str) -> Optional[CreditCostBreakdown]:
        """Calculate and finalize the total cost for a completed run."""
        if run_id not in self.pending_usage:
            print(f"No pending usage data found for run_id {run_id} to finalize.")
            # Check if already finalized
            if run_id in self.finalized_costs:
                print(f"Cost for run_id {run_id} was already finalized.")
                return self.finalized_costs[run_id]
            return None

        pending = self.pending_usage.pop(run_id) # Remove from pending

        # Calculate individual costs from the logged lists
        total_llm_cost = self.calculate_total_llm_cost(pending.tokens)
        tools_cost = self.calculate_tools_cost(pending.tools)
        kb_cost = self.calculate_kb_cost(pending.kbs)

        # Calculate total cost
        total_cost = FIXED_COST_CREDITS + total_llm_cost + tools_cost + kb_cost

        # Create final cost breakdown, storing the detailed usage lists
        cost_breakdown = CreditCostBreakdown(
            fixed_cost=FIXED_COST_CREDITS,
            llm_cost=total_llm_cost,
            tools_cost=tools_cost,
            kb_cost=kb_cost,
            total_cost=total_cost,
            token_usages=pending.tokens, # Store the list
            tool_usages=pending.tools,
            kb_usages=pending.kbs
        )

        # Store the finalized cost record
        self.finalized_costs[run_id] = cost_breakdown

        # Log the final cost breakdown summary
        print(f"Finalized credit usage for run {run_id}: {total_cost:.2f} credits (${total_cost * CREDIT_TO_USD_RATIO:.6f})")
        print(f"  Breakdown: Fixed={FIXED_COST_CREDITS:.2f} | LLM={total_llm_cost:.2f} | Tools={tools_cost:.2f} | KB={kb_cost:.2f}")

        # Log detailed usage
        if pending.tokens:
            models_used = list(set(t.model_name for t in pending.tokens))
            total_input = sum(t.input_tokens for t in pending.tokens)
            total_output = sum(t.output_tokens for t in pending.tokens)
            print(f"  Token Usage: Models={models_used}, Input={total_input}, Output={total_output}")
        if pending.tools:
            tools_str = ", ".join([f"{tool.tool_name}({tool.count})" for tool in pending.tools])
            print(f"  Tool Usage: {tools_str}")
        if pending.kbs:
            kb_str = ", ".join([f"{kb.kb_name}({kb.count})" for kb in pending.kbs])
            print(f"  KB Usage: {kb_str}")

        # Clear KB tracking for this run_id to prevent skipping in future flow runs
        if hasattr(self, "_logged_kbs") and run_id in self._logged_kbs:
            print(f"[KB Tracking] Clearing KB tracking for run_id {run_id} to prepare for future runs")
            self._logged_kbs.pop(run_id)

        return cost_breakdown

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