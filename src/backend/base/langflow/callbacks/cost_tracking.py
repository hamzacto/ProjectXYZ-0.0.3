from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.agents import AgentAction, AgentFinish
import asyncio
import threading

from langflow.services.manager import service_manager
from langflow.services.schema import ServiceType
from langflow.services.credit.service import CreditService, KBUsage, ToolUsage
from loguru import logger

# Define known KB component base names (case-insensitive check)
# These should match the 'name' attribute of the VectorStore components
KNOWN_KB_COMPONENTS = {"milvus", "chroma", "qdrant", "pinecone", "vectorstore"} # Add more as needed

# Define premium tools with their credit costs
PREMIUM_TOOLS = {
    "alpha_vantage": 5,  # 5 credits per use
    "google_search": 2,  # 2 credits per use
    # Add other premium tools here
}

# Global interceptor for tool invocations
# This is a class-level tracking mechanism to ensure we don't miss KB tool invocations
class ToolInvocationTracker:
    """Tracks tool invocations for credit calculation."""
    # Static dictionary to track KB tool invocations by run_id - deprecated
    # We'll use TokenUsageRegistry instead
    _kb_invocations = {}  # Format: {run_id: [kb_names]}
    
    # Thread safety locks
    _kb_invocations_lock = threading.RLock()
    
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
            # It's a KB tool, register it using TokenUsageRegistry
            try:
                from langflow.utils.token_usage_registry import TokenUsageRegistry
                # Use static methods directly
                TokenUsageRegistry.set_flow_context(flow_id=run_id)
                TokenUsageRegistry.track_kb_tool_invocation(kb_name=kb_base)
                print(f"[ToolTracker] Registered KB invocation: {kb_base} for run_id {run_id}")
                
                # Also add to internal tracking to preserve any existing code that depends on it
                with cls._kb_invocations_lock:
                    if run_id not in cls._kb_invocations:
                        cls._kb_invocations[run_id] = []
                    
                    if kb_base not in cls._kb_invocations[run_id]:
                        cls._kb_invocations[run_id].append(kb_base)
                
            except Exception as e:
                print(f"[ToolTracker] Error registering KB usage with TokenUsageRegistry: {e}")
        
        # Check if it's a premium tool
        elif tool_name in PREMIUM_TOOLS:
            tool_usage = ToolUsage(tool_name=tool_name, count=1)
            # Log to Credit Service ONLY
            try:
                credit_service = service_manager.get(ServiceType.CREDIT_SERVICE)
                if credit_service:
                    credit_service.log_tool_usage(run_id, tool_usage)
                    print(f"[ToolTracker] Registered premium tool usage with CreditService: {tool_name} for run_id {run_id}")
            except Exception as e:
                print(f"[ToolTracker] Error registering premium tool usage with CreditService: {e}")
                
            # Removed the attempt to log to Billing Service from here

    @classmethod
    def reset_tracking(cls, run_id: str):
        """Reset tracking for a flow run."""
        # Clear internal tracking
        with cls._kb_invocations_lock:
            if run_id in cls._kb_invocations:
                cls._kb_invocations.pop(run_id)
                print(f"[ToolTracker] Reset KB tracking for flow: {run_id}")
        
        # Also reset in TokenUsageRegistry
        try:
            from langflow.utils.token_usage_registry import TokenUsageRegistry
            TokenUsageRegistry.reset_kb_tracking(run_id)
        except Exception as e:
            print(f"[ToolTracker] Error resetting KB tracking in registry: {e}")

class AgentCostTrackingCallbackHandler(BaseCallbackHandler):
    """Callback handler to track tool and KB usage during agent execution."""

    # Ensure that Langchain callbacks are serializable
    raise_error: bool = True

    def __init__(self, run_id: str):
        if not run_id:
            raise ValueError("run_id must be provided for cost tracking.")
        self.run_id = run_id
        self._credit_service = None # Lazily load service
        self._billing_service = None # Lazily load service
        self._background_loop = None
        self._background_thread = None
        self._lock = threading.RLock()  # Add lock for thread safety

    def _ensure_background_loop(self):
        """Ensure a background event loop exists for async operations."""
        with self._lock:
            if self._background_loop is None:
                import threading
                self._background_loop = asyncio.new_event_loop()
                
                def run_event_loop():
                    asyncio.set_event_loop(self._background_loop)
                    self._background_loop.run_forever()
                    
                self._background_thread = threading.Thread(target=run_event_loop, daemon=True)
                self._background_thread.start()
                print(f"[CostCallback] Started background event loop thread for {self.run_id}")

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
        
    @property
    def billing_service(self):
        """Lazy load billing service."""
        if self._billing_service is None:
            try:
                service = service_manager.get(ServiceType.BILLING_SERVICE)
                self._billing_service = service
            except Exception as e:
                logger.error(f"[CostCallback] Failed to get BillingService: {e}")
                self._billing_service = None
        return self._billing_service

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> Any:
        """Run when tool starts running."""
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

        # Check for premium tools
        if tool_name in PREMIUM_TOOLS:
            credit_service = self.credit_service
            if credit_service:
                tool_usage = ToolUsage(tool_name=tool_name, count=1)
                credit_service.log_tool_usage(self.run_id, tool_usage)
                print(f"[CostCallback] Logged Premium Tool Usage: {tool_name} (Cost: {PREMIUM_TOOLS[tool_name]} credits)")
                
            # Also log to billing service - REMOVED
            # billing_service = self.billing_service
            # if billing_service:
            #     tool_usage = ToolUsage(tool_name=tool_name, count=1)
            #     asyncio.create_task(billing_service.log_tool_usage(self.run_id, tool_usage))
            #     print(f"[CostCallback] Scheduled Premium Tool Usage logging to BillingService: {tool_name}")

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
                # Log KB usage via TokenUsageRegistry
                from langflow.utils.token_usage_registry import TokenUsageRegistry
                TokenUsageRegistry.set_flow_context(flow_id=self.run_id)
                TokenUsageRegistry.track_kb_tool_invocation(kb_name=kb_name)
                print(f"[CostCallback] ✅ Detected KB usage: {kb_name} for run_id: {self.run_id}")
                logger.info(f"[CostCallback] Logged KB Usage for Run {self.run_id}: {kb_name}")
                
                # Also log directly to billing service
                billing_service = self.billing_service
                if billing_service:
                    kb_usage = KBUsage(kb_name=kb_name, count=1)
                    # Use safe async execution pattern
                    try:
                        # If we're in an async context, we can use create_task
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(billing_service.log_kb_usage(self.run_id, kb_usage))
                                print(f"[CostCallback] Scheduled KB Usage in BillingService via create_task: {kb_name}")
                            else:
                                # Start a new background thread with its own event loop
                                with self._lock:
                                    self._ensure_background_loop()
                                asyncio.run_coroutine_threadsafe(
                                    billing_service.log_kb_usage(self.run_id, kb_usage),
                                    self._background_loop
                                )
                                print(f"[CostCallback] Scheduled KB Usage in BillingService via threadsafe: {kb_name}")
                        except RuntimeError:
                            # If we're not in an async context, use a background thread
                            with self._lock:
                                self._ensure_background_loop()
                            asyncio.run_coroutine_threadsafe(
                                billing_service.log_kb_usage(self.run_id, kb_usage),
                                self._background_loop
                            )
                            print(f"[CostCallback] Scheduled KB Usage in BillingService via threadsafe: {kb_name}")
                    except Exception as e:
                        logger.error(f"[CostCallback] Error scheduling async KB usage: {e}")
                        print(f"[CostCallback] Error scheduling async KB usage: {e}")
                    print(f"[CostCallback] Logged KB Usage in BillingService: {kb_name}")
            else:
                # For non-KB tools, still track with CreditService directly
                credit_service = self.credit_service
                if credit_service:
                    tool_usage = ToolUsage(tool_name=component_base_name, count=1)
                    credit_service.log_tool_usage(self.run_id, tool_usage)
                    print(f"[CostCallback] Logged Tool Usage with CreditService: {component_base_name}")
                    logger.info(f"[CostCallback] Logged Tool Usage with CreditService for Run {self.run_id}: {component_base_name}")
                    
                # Removed tracking with BillingService from here
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
    
    def cleanup(self):
        """Clean up resources like background event loops."""
        with self._lock:
            if self._background_loop is not None:
                try:
                    # Schedule the event loop to stop
                    self._background_loop.call_soon_threadsafe(self._background_loop.stop)
                    print(f"[CostCallback] Stopped background event loop for {self.run_id}")
                    self._background_loop = None
                    self._background_thread = None
                except Exception as e:
                    print(f"[CostCallback] Error cleaning up background loop: {e}")
                
    def __del__(self):
        """Destructor to ensure cleanup when the object is garbage collected."""
        self.cleanup()


