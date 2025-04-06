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
    
    # Raw token usage
    token_usage: Optional[TokenUsage] = None
    
    # Tool and KB usage counts
    tool_usages: List[ToolUsage] = []
    kb_usages: List[KBUsage] = []


class CreditService(Service):
    """Service for tracking AI agent usage costs."""
    name = ServiceType.CREDIT_SERVICE
    
    def __init__(self):
        super().__init__()
        # In-memory storage for tracking costs - in a production system, this would be persisted to a database
        self.cost_records: Dict[str, CreditCostBreakdown] = {}
        
    def calculate_llm_cost(self, token_usage: TokenUsage) -> float:
        """Calculate LLM cost in credits based on token usage and model"""
        model_name = token_usage.model_name.lower().strip()
        
        # Get cost rates per 1K tokens for the model
        model_cost = MODEL_COSTS.get(model_name, DEFAULT_MODEL_COST)
        
        # Calculate base costs in USD
        input_cost_usd = (token_usage.input_tokens / 1000) * model_cost["input"]
        output_cost_usd = (token_usage.output_tokens / 1000) * model_cost["output"]
        total_cost_usd = input_cost_usd + output_cost_usd
        
        # Apply markup
        marked_up_cost_usd = total_cost_usd * (1 + LLM_MARKUP_PERCENTAGE)
        
        # Convert to credits
        credit_cost = marked_up_cost_usd / CREDIT_TO_USD_RATIO
        
        return credit_cost
    
    def calculate_tools_cost(self, tool_usages: List[ToolUsage]) -> float:
        """Calculate cost of tool usage in credits"""
        total_tool_accesses = sum(tool.count for tool in tool_usages)
        return total_tool_accesses * TOOL_ACCESS_CREDITS
    
    def calculate_kb_cost(self, kb_usages: List[KBUsage]) -> float:
        """Calculate cost of knowledge base access in credits"""
        total_kb_accesses = sum(kb.count for kb in kb_usages)
        return total_kb_accesses * KB_ACCESS_CREDITS
    
    def track_run(
        self, 
        run_id: str, 
        token_usage: Optional[TokenUsage] = None,
        tool_usages: Optional[List[ToolUsage]] = None,
        kb_usages: Optional[List[KBUsage]] = None
    ) -> CreditCostBreakdown:
        """Track and calculate the cost of an AI agent run"""
        # Initialize with defaults if not provided
        token_usage = token_usage or TokenUsage(model_name="default")
        tool_usages = tool_usages or []
        kb_usages = kb_usages or []
        
        # Calculate individual costs
        llm_cost = self.calculate_llm_cost(token_usage) if token_usage else 0
        tools_cost = self.calculate_tools_cost(tool_usages)
        kb_cost = self.calculate_kb_cost(kb_usages)
        
        # Calculate total cost
        total_cost = FIXED_COST_CREDITS + llm_cost + tools_cost + kb_cost
        
        # Create cost breakdown
        cost_breakdown = CreditCostBreakdown(
            fixed_cost=FIXED_COST_CREDITS,
            llm_cost=llm_cost,
            tools_cost=tools_cost,
            kb_cost=kb_cost,
            total_cost=total_cost,
            token_usage=token_usage,
            tool_usages=tool_usages,
            kb_usages=kb_usages
        )
        
        # Store the cost record
        self.cost_records[run_id] = cost_breakdown
        
        # Log the cost breakdown
        print(f"Credit usage for run {run_id}: {total_cost:.2f} credits (${total_cost * CREDIT_TO_USD_RATIO:.6f})")
        print(f"Breakdown: Fixed={FIXED_COST_CREDITS} | LLM={llm_cost:.2f} | Tools={tools_cost:.2f} | KB={kb_cost:.2f}")
        
        # Log the details with loguru
        print(f"Credit usage for run {run_id}: {total_cost:.2f} credits (${total_cost * CREDIT_TO_USD_RATIO:.6f})")
        print(f"Credit breakdown: Fixed={FIXED_COST_CREDITS} | LLM={llm_cost:.2f} | Tools={tools_cost:.2f} | KB={kb_cost:.2f}")
        
        # Log token usage details if available
        if token_usage and (token_usage.input_tokens > 0 or token_usage.output_tokens > 0):
            print(f"Token usage: Model={token_usage.model_name} | Input={token_usage.input_tokens} | Output={token_usage.output_tokens}")
        
        # Log tool usage details if available
        if tool_usages:
            tools_str = ", ".join([f"{tool.tool_name}({tool.count})" for tool in tool_usages])
            print(f"Tool usage: {tools_str}")
            
        # Log KB usage details if available
        if kb_usages:
            kb_str = ", ".join([f"{kb.kb_name}({kb.count})" for kb in kb_usages])
            print(f"KB usage: {kb_str}")
        
        return cost_breakdown
    
    def get_cost_breakdown(self, run_id: str) -> Optional[CreditCostBreakdown]:
        """Get the cost breakdown for a specific run"""
        return self.cost_records.get(run_id)
    
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