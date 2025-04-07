from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.agents import AgentAction, AgentFinish

from langflow.services.manager import service_manager
from langflow.services.schema import ServiceType
from langflow.services.credit.service import CreditService, KBUsage, ToolUsage
from loguru import logger

# Define known KB component base names (case-insensitive check)
# These should match the 'name' attribute of the VectorStore components
KNOWN_KB_COMPONENTS = {"milvus", "chroma", "qdrant", "pinecone", "vectorstore"} # Add more as needed

# Global interceptor for tool invocations
# This is a class-level tracking mechanism to ensure we don't miss KB tool invocations
class ToolInvocationTracker:
    """Tracks tool invocations for credit calculation."""
    # Static dictionary to track KB tool invocations by run_id
    _kb_invocations = {}  # Format: {run_id: [kb_names]}
    
    @classmethod
    def register_invocation(cls, run_id: str, tool_name: str):
        """Register a tool invocation for tracking."""
        if not run_id or not tool_name:
            return
            
        # Check if it's a KB tool
        kb_base = None
        for kb in KNOWN_KB_COMPONENTS:
            if kb.lower() in tool_name.lower():
                kb_base = kb
                break
                
        if kb_base:
            # It's a KB tool, register it
            if run_id not in cls._kb_invocations:
                cls._kb_invocations[run_id] = []
            
            if kb_base not in cls._kb_invocations[run_id]:
                cls._kb_invocations[run_id].append(kb_base)
                print(f"[ToolTracker] Registered KB invocation: {kb_base} for run_id {run_id}")
                
                # Also try to log directly
                try:
                    credit_service = service_manager.get(ServiceType.CREDIT_SERVICE)
                    if credit_service:
                        # Log to the run_id directly
                        kb_usage = KBUsage(kb_name=kb_base, count=1)
                        credit_service.log_kb_usage(run_id=run_id, kb_usage=kb_usage)
                        
                        # Also log to base run_id if different
                        base_run_id = run_id.split('_')[0] if '_' in run_id else run_id
                        if base_run_id != run_id:
                            credit_service.log_kb_usage(run_id=base_run_id, kb_usage=kb_usage)
                            print(f"[ToolTracker] Also logged to base run_id: {base_run_id}")
                except Exception as e:
                    print(f"[ToolTracker] Error logging KB usage: {e}")

    @classmethod
    def reset_tracking(cls, run_id: str):
        """Reset tracking for a flow run."""
        if run_id in cls._kb_invocations:
            cls._kb_invocations.pop(run_id)
            print(f"[ToolTracker] Reset KB tracking for flow: {run_id}")

class AgentCostTrackingCallbackHandler(BaseCallbackHandler):
    """Callback handler to track tool and KB usage during agent execution."""

    # Ensure that Langchain callbacks are serializable
    raise_error: bool = True

    def __init__(self, run_id: str):
        if not run_id:
            raise ValueError("run_id must be provided for cost tracking.")
        self.run_id = run_id
        self._credit_service = None # Lazily load service

    @property
    def credit_service(self) -> Optional[CreditService]:
        """Lazy load credit service to avoid issues during initialization or serialization."""
        if self._credit_service is None:
            try:
                service = service_manager.get(ServiceType.CREDIT_SERVICE)
                if not service:
                    print("[CostCallback] CreditService not found. Cost tracking for tools/KB will be skipped.")
                self._credit_service = service
            except Exception as e:
                logger.error(f"[CostCallback] Failed to get CreditService: {e}. Cost tracking will be skipped.")
                self._credit_service = None # Ensure it's None on error
        return self._credit_service


    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> Any:
        """Run when tool starts running."""
        # Check if service is available on each call
        credit_service = self.credit_service
        if not credit_service:
            logger.debug("[CostCallback] Skipping tool start logging - CreditService unavailable.")
            return

        # Add detailed debugging to see what's coming in
        print(f"[CostCallback] TOOL START RECEIVED: {serialized}")
        print(f"[CostCallback] INPUT STRING: {repr(input_str)}")
        if kwargs:
            print(f"[CostCallback] KWARGS: {kwargs}")

        # Tool name from LangChain is often the function/method name,
        # e.g., 'Milvus-search_documents' or just the tool's name attribute.
        tool_name = serialized.get("name", "unknown_tool")
        
        # Register tool invocation in the global tracker
        ToolInvocationTracker.register_invocation(self.run_id, tool_name)

        # Extract the base component name (assuming 'ComponentName-method' or just 'ComponentName')
        # Convert to lower for case-insensitive comparison
        component_base_name = tool_name.split('-')[0].lower() if '-' in tool_name else tool_name.lower()

        print(f"[CostCallback] Tool invoked: '{tool_name}', Base='{component_base_name}', RunID='{self.run_id}'")
        logger.debug(f"[CostCallback] Tool Start: Name='{tool_name}', Base='{component_base_name}', RunID='{self.run_id}'")

        # Detection of KB tools
        KNOWN_KB_COMPONENTS = {"milvus", "chroma", "qdrant", "pinecone", "vectorstore"}
        is_kb_tool = False
        kb_name = None

        # Checks for KB tool invocation:
        # 1. Direct match of base component name
        if component_base_name in KNOWN_KB_COMPONENTS:
            is_kb_tool = True
            kb_name = component_base_name
        # 2. Check for KB operation in the method part (e.g., search_documents)
        elif "-" in tool_name and any(kb in component_base_name for kb in KNOWN_KB_COMPONENTS):
            method_part = tool_name.split('-')[1].lower() if len(tool_name.split('-')) > 1 else ""
            kb_operations = ["search", "query", "get", "retrieve", "similarity"]
            if any(op in method_part for op in kb_operations):
                is_kb_tool = True
                kb_name = component_base_name
        # 3. Check for KB name in the full tool name
        elif any(kb in tool_name.lower() for kb in KNOWN_KB_COMPONENTS):
            for kb in KNOWN_KB_COMPONENTS:
                if kb in tool_name.lower():
                    is_kb_tool = True
                    kb_name = kb
                    break
        # 4. Check the input string for signs of KB tool usage
        if not is_kb_tool and isinstance(input_str, str):
            # Check if input is a search query for a KB component
            for kb in KNOWN_KB_COMPONENTS:
                if kb.lower() in input_str.lower() and any(term in input_str.lower() for term in ["search", "query", "retrieve", "find"]):
                    is_kb_tool = True
                    kb_name = kb
                    print(f"[CostCallback] Detected KB usage from input string: {kb}")
                    break

        try:
            if is_kb_tool and kb_name:
                # Log as KB usage
                kb_usage = KBUsage(kb_name=kb_name, count=1)
                credit_service.log_kb_usage(self.run_id, kb_usage)
                print(f"[CostCallback] ✅ Detected KB usage: {kb_name} for run_id: {self.run_id}")
                logger.info(f"[CostCallback] Logged KB Usage for Run {self.run_id}: {kb_name}")
                
                # Also log directly to the base run_id if different
                try:
                    base_run_id = self.run_id.split('_')[0] if '_' in self.run_id else self.run_id
                    if base_run_id != self.run_id:
                        kb_usage = KBUsage(kb_name=kb_name, count=1)
                        credit_service.log_kb_usage(base_run_id, kb_usage)
                        print(f"[CostCallback] Also logged KB usage to base run_id: {base_run_id}")
                except Exception as e:
                    print(f"[CostCallback] Error in additional KB logging: {e}")
            else:
                # Log as generic tool usage
                tool_usage = ToolUsage(tool_name=component_base_name, count=1)
                credit_service.log_tool_usage(self.run_id, tool_usage)
                print(f"[CostCallback] Logged Tool Usage: {component_base_name}")
                logger.info(f"[CostCallback] Logged Tool Usage for Run {self.run_id}: {component_base_name}")
        except Exception as e:
            logger.exception(f"[CostCallback] Error logging tool/KB usage for run {self.run_id}: {e}")
            print(f"[CostCallback] Error logging tool/KB usage for run {self.run_id}: {e}")
    
    # Manually add the tool end hook to capture tools that send messages directly
    def on_tool_end(
        self,
        output: str,
        **kwargs: Any,
    ) -> Any:
        """Run when agent tool ends running."""
        print(f"[CostCallback] TOOL END with output: {output[:100]}...")
    
    # Override on_agent_action to directly catch tool invocations at the source
    def on_agent_action(
        self, action: AgentAction, **kwargs: Any
    ) -> Any:
        """Run when agent takes an action."""
        tool = action.tool
        tool_input = action.tool_input
        print(f"[AGENT ACTION] Tool: {tool}, Input: {tool_input}")
        
        # Directly register the tool invocation
        ToolInvocationTracker.register_invocation(self.run_id, tool)

    # Optional: Implement other callback methods if needed later
    # def on_llm_start(...)
    # def on_agent_finish(...)
    # def on_tool_error(...)


