import ast
import contextlib
import importlib
import warnings
from types import FunctionType
from typing import Optional, Union

from langchain_core._api.deprecation import LangChainDeprecationWarning
from loguru import logger
from pydantic import ValidationError
from langflow.field_typing.constants import CUSTOM_COMPONENT_SUPPORTED_TYPES, DEFAULT_IMPORT_STRING
from langflow.services.manager import service_manager
from langflow.services.schema import ServiceType
from langflow.services.credit.service import TokenUsage

class TokenUsageRegistry:
    """Registry for tracking token usage across flows"""
    _instance = None
    
    def __init__(self):
        self._flow_tracking = {}  # Format: {flow_id: {prompt_tokens, completion_tokens, total_tokens, models}}
        self._current_flow_id = None
        self._current_component_id = None
        self._kb_tools_invoked = {}  # Format: {flow_id: [kb_names]}
        self._credit_service = None
        self._original_session_ids = {}
        self._id_mapping = {}
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance"""
        if cls._instance is None:
            cls._instance = TokenUsageRegistry()
        return cls._instance
    
    @property
    def credit_service(self):
        """Lazy load credit service to avoid circular imports"""
        if self._credit_service is None:
            try:
                from langflow.services.manager import service_manager
                from langflow.services.schema import ServiceType
                self._credit_service = service_manager.get(ServiceType.CREDIT_SERVICE)
            except Exception as e:
                print(f"Error getting credit service: {e}")
        return self._credit_service
    
    # ==== STATIC INTERFACE METHODS (for external calls) ====
    @staticmethod
    def set_flow_context(flow_id=None, component_id=None):
        """Set current flow context for token tracking"""
        instance = TokenUsageRegistry.get_instance()
        instance._set_flow_context_impl(flow_id, component_id)
    
    @staticmethod
    def clear_flow_context():
        """Clear current flow context"""
        instance = TokenUsageRegistry.get_instance()
        instance._clear_flow_context_impl()
    
    @staticmethod
    def get_flow_context():
        """Get the current flow context"""
        instance = TokenUsageRegistry.get_instance()
        return {
            "flow_id": instance._current_flow_id,
            "component_id": instance._current_component_id
        }
    
    @staticmethod
    def record_usage(model, prompt_tokens, completion_tokens, total_tokens):
        """Record token usage"""
        instance = TokenUsageRegistry.get_instance()
        instance._record_usage_impl(model, prompt_tokens, completion_tokens, total_tokens)
    
    @staticmethod
    def track_kb_tool_invocation(kb_name):
        """Track KB tool invocation"""
        instance = TokenUsageRegistry.get_instance()
        instance._track_kb_tool_invocation_impl(kb_name)
    
    @staticmethod
    def reset_kb_tracking(flow_id):
        """Reset KB tracking for a flow"""
        instance = TokenUsageRegistry.get_instance()
        instance._reset_kb_tracking_impl(flow_id)
        
    @staticmethod
    def reset_flow_tracking(flow_id):
        """Reset all tracking data for a specific flow"""
        instance = TokenUsageRegistry.get_instance()
        instance._reset_flow_tracking_impl(flow_id)
    
    @staticmethod
    def summarize_flow_usage(flow_id):
        """Get token usage summary for a flow"""
        instance = TokenUsageRegistry.get_instance()
        return instance._summarize_flow_usage_impl(flow_id)
    
    @staticmethod
    def print_flow_summary(flow_id):
        """Print token usage summary for a flow"""
        instance = TokenUsageRegistry.get_instance()
        instance._print_flow_summary_impl(flow_id)
        
    @staticmethod
    def sync_flow_ids(source_id, target_id):
        """Synchronize tracking between two IDs (for when flow_id and session_id differ)"""
        instance = TokenUsageRegistry.get_instance()
        instance._sync_flow_ids_impl(source_id, target_id)
    
    # ==== IMPLEMENTATION METHODS (private) ====
    def _set_flow_context_impl(self, flow_id, component_id=None):
        """Implementation of set_flow_context"""
        self._current_flow_id = flow_id
        self._current_component_id = component_id
    
    def _clear_flow_context_impl(self):
        """Implementation of clear_flow_context"""
        self._current_flow_id = None
        self._current_component_id = None
    
    def _record_usage_impl(self, model, prompt_tokens, completion_tokens, total_tokens):
        """Implementation of record_usage"""
        if not self._current_flow_id:
            print("No flow context set for token tracking")
            return
            
        # Initialize or update flow tracking
        if self._current_flow_id not in self._flow_tracking:
            self._flow_tracking[self._current_flow_id] = {
                "prompt_tokens": 0, 
                "completion_tokens": 0,
                "total_tokens": 0,
                "models": set()
            }
        
        ft = self._flow_tracking[self._current_flow_id]
        ft["prompt_tokens"] += prompt_tokens
        ft["completion_tokens"] += completion_tokens
        ft["total_tokens"] += total_tokens
        ft["models"].add(model)
        
        # Delegate to credit service
        if self.credit_service:
            from langflow.services.credit.service import TokenUsage
            token_usage = TokenUsage(
                model_name=model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens
            )
            self.credit_service.log_token_usage(run_id=self._current_flow_id, token_usage=token_usage)
            print(f"[TokenRegistry] Delegated {prompt_tokens} input, {completion_tokens} output tokens directly to CreditService")
            
            # Also log to component-specific run_id if component is set
            if self._current_component_id:
                component_run_id = f"{self._current_flow_id}_{self._current_component_id}"
                self.credit_service.log_token_usage(run_id=component_run_id, token_usage=token_usage)
                
        # Also log to BillingService if available
        try:
            from langflow.services.manager import service_manager
            from langflow.services.schema import ServiceType
            import asyncio
            
            billing_service = service_manager.get(ServiceType.BILLING_SERVICE)
            if billing_service:
                from langflow.services.credit.service import TokenUsage
                token_usage = TokenUsage(
                    model_name=model,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens
                )
                
                # IMPORTANT: Look for the original session ID stored in BillingService
                # instead of generating a new one with current timestamp
                # This ensures we're always using the same ID that was used to create the record
                session_id = self._current_flow_id
                
                # Try different strategies to get the correct session ID:
                
                # 1. If we're dealing with a UUID, check if it's mapped in BillingService
                if len(self._current_flow_id) == 36 and not self._current_flow_id.startswith("Session"):
                    # Check if BillingService has a mapping for this UUID
                    if hasattr(billing_service, "_uuid_to_session_mappings") and self._current_flow_id in billing_service._uuid_to_session_mappings:
                        original_session_id = billing_service._uuid_to_session_mappings[self._current_flow_id]
                        print(f"[TokenRegistry] Using mapped Session ID from BillingService: {original_session_id}")
                        session_id = original_session_id
                    elif self._current_flow_id in self._id_mapping:
                        # Try our own mapping as fallback
                        print(f"[TokenRegistry] Using internally mapped Session ID: {self._id_mapping[self._current_flow_id]}")
                        session_id = self._id_mapping[self._current_flow_id]
                    else:
                        # As a last resort, keep using UUID directly: {self._current_flow_id}")
                        print(f"[TokenRegistry] Using UUID directly: {self._current_flow_id}")
                
                # If we're currently using a Session ID, we want to stick with that
                # instead of generating a new one - BillingService._find_usage_record 
                # will handle prefix matching and other fallbacks
                
                # Check if we're in an event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule the async operation as a background task
                        asyncio.create_task(billing_service.log_token_usage(run_id=session_id, token_usage=token_usage))
                        print(f"[TokenRegistry] Scheduled token usage logging to BillingService with ID: {session_id}")
                    else:
                        print(f"[TokenRegistry] Event loop not running, cannot log to BillingService")
                except RuntimeError:
                    print(f"[TokenRegistry] No event loop available for async operations")
                
        except Exception as e:
            print(f"[TokenRegistry] Error logging to BillingService: {e}")
    
    def _track_kb_tool_invocation_impl(self, kb_name):
        """Implementation of track_kb_tool_invocation"""
        if not self._current_flow_id:
            return
            
        if self._current_flow_id not in self._kb_tools_invoked:
            self._kb_tools_invoked[self._current_flow_id] = []
            
        if kb_name not in self._kb_tools_invoked[self._current_flow_id]:
            self._kb_tools_invoked[self._current_flow_id].append(kb_name)
            
        # Delegate to credit service
        if self.credit_service:
            from langflow.services.credit.service import KBUsage
            kb_usage = KBUsage(kb_name=kb_name, count=1)
            self.credit_service.log_kb_usage(run_id=self._current_flow_id, kb_usage=kb_usage)
            print(f"[TokenRegistry] Delegated KB usage for {kb_name} directly to CreditService")
            
        # Also log to BillingService if available
        try:
            from langflow.services.manager import service_manager
            from langflow.services.schema import ServiceType
            import asyncio
            
            billing_service = service_manager.get(ServiceType.BILLING_SERVICE)
            if billing_service:
                from langflow.services.credit.service import KBUsage
                kb_usage = KBUsage(kb_name=kb_name, count=1)
                
                # IMPORTANT: Use the same approach as _record_usage_impl 
                # to find consistent session ID
                session_id = self._current_flow_id
                
                # Try different strategies to get the correct session ID:
                
                # 1. If we're dealing with a UUID, check if it's mapped in BillingService
                if len(self._current_flow_id) == 36 and not self._current_flow_id.startswith("Session"):
                    # Check if BillingService has a mapping for this UUID
                    if hasattr(billing_service, "_uuid_to_session_mappings") and self._current_flow_id in billing_service._uuid_to_session_mappings:
                        original_session_id = billing_service._uuid_to_session_mappings[self._current_flow_id]
                        print(f"[TokenRegistry] Using mapped Session ID from BillingService: {original_session_id}")
                        session_id = original_session_id
                    elif self._current_flow_id in self._id_mapping:
                        # Try our own mapping as fallback
                        print(f"[TokenRegistry] Using internally mapped Session ID: {self._id_mapping[self._current_flow_id]}")
                        session_id = self._id_mapping[self._current_flow_id]
                    else:
                        # As a last resort, keep using UUID directly - BillingService
                        # will try to resolve it via its enhanced fallback
                        print(f"[TokenRegistry] Using UUID directly: {self._current_flow_id}")
                
                # Check if we're in an event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule the async operation as a background task
                        asyncio.create_task(billing_service.log_kb_usage(run_id=session_id, kb_usage=kb_usage))
                        print(f"[TokenRegistry] Scheduled KB usage logging to BillingService with ID: {session_id}")
                    else:
                        print(f"[TokenRegistry] Event loop not running, cannot log to BillingService")
                except RuntimeError:
                    print(f"[TokenRegistry] No event loop available for async operations")
                
        except Exception as e:
            print(f"[TokenRegistry] Error logging KB to BillingService: {e}")
    
    def _reset_kb_tracking_impl(self, flow_id):
        """Implementation of reset_kb_tracking"""
        if flow_id in self._kb_tools_invoked:
            self._kb_tools_invoked[flow_id] = []
            
    def _reset_flow_tracking_impl(self, flow_id):
        """Reset all tracking data for a specific flow"""
        # Reset token tracking
        if flow_id in self._flow_tracking:
            print(f"[TokenRegistry] Clearing token tracking for flow: {flow_id}")
            self._flow_tracking.pop(flow_id)
            
        # Reset KB tracking
        if flow_id in self._kb_tools_invoked:
            print(f"[TokenRegistry] Clearing KB tracking for flow: {flow_id}")
            self._kb_tools_invoked.pop(flow_id)
            
        # Clear all related flows (including component-specific ones)
        related_flows = []
        if hasattr(self, "_flow_tracking"):
            related_flows.extend([k for k in self._flow_tracking.keys() 
                                 if k.startswith(flow_id) or (k.startswith("Session") and flow_id.startswith("Session"))])
            
        if hasattr(self, "_kb_tools_invoked"):
            related_flows.extend([k for k in self._kb_tools_invoked.keys() 
                                 if k.startswith(flow_id) or (k.startswith("Session") and flow_id.startswith("Session"))])
        
        for related_id in related_flows:
            if related_id != flow_id:  # Already cleared above
                if related_id in self._flow_tracking:
                    self._flow_tracking.pop(related_id)
                if related_id in self._kb_tools_invoked:
                    self._kb_tools_invoked.pop(related_id)
                print(f"[TokenRegistry] Cleared related tracking for: {related_id}")
                
        # Also reset in CreditService if available
        if self.credit_service and hasattr(self.credit_service, "pending_usage"):
            cs_pending = self.credit_service.pending_usage
            # Find all related run_ids in CreditService
            related_cs_ids = [run_id for run_id in cs_pending.keys() 
                             if run_id.startswith(flow_id) or 
                             (run_id.startswith("Session") and flow_id.startswith("Session"))]
            
            # Clear them all
            for run_id in related_cs_ids:
                if run_id in cs_pending:
                    cs_pending.pop(run_id)
                    print(f"[TokenRegistry] Cleared CreditService tracking for: {run_id}")
    
    def _summarize_flow_usage_impl(self, flow_id):
        """Implementation of summarize_flow_usage"""
        return self._flow_tracking.get(flow_id, {})
    
    def _print_flow_summary_impl(self, flow_id):
        """Implementation of print_flow_summary"""
        if flow_id not in self._flow_tracking:
            print(f"No token usage tracked for flow: {flow_id}")
            return
            
        ft = self._flow_tracking[flow_id]
        models_str = ", ".join(ft["models"])
        print(f"\n===== TOKEN USAGE SUMMARY FOR FLOW {flow_id} =====")
        print(f"Models used: {models_str}")
        print(f"Prompt tokens: {ft['prompt_tokens']}")
        print(f"Completion tokens: {ft['completion_tokens']}")
        print(f"Total tokens: {ft['total_tokens']}")
        
        # Show KB tool invocations if any
        if flow_id in self._kb_tools_invoked and self._kb_tools_invoked[flow_id]:
            kb_tools = ", ".join(self._kb_tools_invoked[flow_id])
            print(f"KB tools accessed: {kb_tools}")
        print("=============================================\n")
        
    def _sync_flow_ids_impl(self, source_id, target_id):
        """Sync tracking data from source_id to target_id"""
        if source_id == target_id:
            return  # No need to sync if they're the same
        
        print(f"[TokenRegistry] Syncing IDs: source={source_id}, target={target_id}")
        
        # Determine UUID and Session format IDs
        uuid_format_id = None
        session_format_id = None
        
        if len(source_id) == 36 and not source_id.startswith("Session"):
            uuid_format_id = source_id
        elif source_id.startswith("Session"):
            session_format_id = source_id
            
        if len(target_id) == 36 and not target_id.startswith("Session"):
            uuid_format_id = target_id
        elif target_id.startswith("Session"):
            session_format_id = target_id
            
        print(f"[TokenRegistry] Identified formats: UUID={uuid_format_id}, Session={session_format_id}")
        
        # Store the relationship for future reference
        if uuid_format_id and session_format_id:
            if not hasattr(self, "_id_mapping"):
                self._id_mapping = {}
            
            self._id_mapping[uuid_format_id] = session_format_id
            self._id_mapping[session_format_id] = uuid_format_id
            print(f"[TokenRegistry] Saved ID mapping: {uuid_format_id} ⟷ {session_format_id}")
            
            # Also propagate to BillingService to ensure consistency
            try:
                from langflow.services.manager import service_manager
                from langflow.services.schema import ServiceType
                billing_service = service_manager.get(ServiceType.BILLING_SERVICE)
                if billing_service and hasattr(billing_service, "_uuid_to_session_mappings"):
                    billing_service._uuid_to_session_mappings[uuid_format_id] = session_format_id
                    
                    # Also add the day prefix mapping for future lookups
                    if hasattr(billing_service, "_session_prefix_mappings"):
                        try:
                            day_prefix = session_format_id.split(",")[0]
                            if day_prefix and len(day_prefix) > 10:
                                billing_service._session_prefix_mappings[day_prefix] = session_format_id
                                print(f"[TokenRegistry] Added session prefix mapping to BillingService: {day_prefix} -> {session_format_id}")
                        except Exception:
                            pass
                            
                    print(f"[TokenRegistry] Added UUID->Session mapping to BillingService: {uuid_format_id} -> {session_format_id}")
            except Exception as e:
                print(f"[TokenRegistry] Error updating BillingService mappings: {e}")
            
        # Sync token tracking
        if source_id in self._flow_tracking:
            if target_id not in self._flow_tracking:
                self._flow_tracking[target_id] = {
                    "prompt_tokens": 0, 
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "models": set()
                }
                
            # Add source tracking to target
            source_data = self._flow_tracking[source_id]
            self._flow_tracking[target_id]["prompt_tokens"] += source_data["prompt_tokens"]
            self._flow_tracking[target_id]["completion_tokens"] += source_data["completion_tokens"] 
            self._flow_tracking[target_id]["total_tokens"] += source_data["total_tokens"]
            self._flow_tracking[target_id]["models"].update(source_data["models"])
            
            print(f"[TokenRegistry] Synced {source_data['total_tokens']} tokens from {source_id} to {target_id}")
            
        # Sync KB tracking
        if source_id in self._kb_tools_invoked:
            if target_id not in self._kb_tools_invoked:
                self._kb_tools_invoked[target_id] = []
                
            # Add source KB tools to target
            for kb in self._kb_tools_invoked[source_id]:
                if kb not in self._kb_tools_invoked[target_id]:
                    self._kb_tools_invoked[target_id].append(kb)
            
            print(f"[TokenRegistry] Synced KB tools from {source_id} to {target_id}")
            
        # Also sync in the credit service if available
        if self.credit_service and hasattr(self.credit_service, "pending_usage"):
            if source_id in self.credit_service.pending_usage:
                # Ensure target has an entry
                from langflow.services.credit.service import PendingUsage
                if target_id not in self.credit_service.pending_usage:
                    self.credit_service.pending_usage[target_id] = PendingUsage()
                    
                # Copy data from source to target
                source_pending = self.credit_service.pending_usage[source_id]
                
                # Fix for double-counting: Only transfer token usage from main flow ID
                # Skip any usage with component-specific IDs (containing underscore)
                if source_pending.tokens:
                    # Filter out component-specific token usages when transferring
                    if "_" not in source_id:
                        # Only transfer the parent flow tokens, not component-specific ones
                        self.credit_service.pending_usage[target_id].tokens.extend(source_pending.tokens)
                        print(f"[TokenRegistry] Synced {len(source_pending.tokens)} token usages in CreditService")
                    else:
                        print(f"[TokenRegistry] Skipping component-specific token usage from {source_id}")
                    
                if source_pending.tools:
                    self.credit_service.pending_usage[target_id].tools.extend(source_pending.tools)
                    print(f"[TokenRegistry] Synced {len(source_pending.tools)} tool usages in CreditService")
                    
                if source_pending.kbs:
                    self.credit_service.pending_usage[target_id].kbs.extend(source_pending.kbs)
                    print(f"[TokenRegistry] Synced {len(source_pending.kbs)} KB usages in CreditService")

def add_type_ignores() -> None:
    if not hasattr(ast, "TypeIgnore"):

        class TypeIgnore(ast.AST):
            _fields = ()

        ast.TypeIgnore = TypeIgnore  # type: ignore[assignment, misc]


def validate_code(code):
    # Initialize the errors dictionary
    errors = {"imports": {"errors": []}, "function": {"errors": []}}

    # Parse the code string into an abstract syntax tree (AST)
    try:
        tree = ast.parse(code)
    except Exception as e:  # noqa: BLE001
        if hasattr(logger, "opt"):
            logger.opt(exception=True).debug("Error parsing code")
        else:
            logger.debug("Error parsing code")
        errors["function"]["errors"].append(str(e))
        return errors

    # Add a dummy type_ignores field to the AST
    add_type_ignores()
    tree.type_ignores = []

    # Evaluate the import statements
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                try:
                    importlib.import_module(alias.name)
                except ModuleNotFoundError as e:
                    errors["imports"]["errors"].append(str(e))

    # Evaluate the function definition
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            code_obj = compile(ast.Module(body=[node], type_ignores=[]), "<string>", "exec")
            try:
                exec(code_obj)
            except Exception as e:  # noqa: BLE001
                logger.opt(exception=True).debug("Error executing function code")
                errors["function"]["errors"].append(str(e))

    # Return the errors dictionary
    return errors


def eval_function(function_string: str):
    # Create an empty dictionary to serve as a separate namespace
    namespace: dict = {}

    # Execute the code string in the new namespace
    exec(function_string, namespace)
    function_object = next(
        (
            obj
            for name, obj in namespace.items()
            if isinstance(obj, FunctionType) and obj.__code__.co_filename == "<string>"
        ),
        None,
    )
    if function_object is None:
        msg = "Function string does not contain a function"
        raise ValueError(msg)
    return function_object


def execute_function(code, function_name, *args, **kwargs):
    add_type_ignores()

    module = ast.parse(code)
    exec_globals = globals().copy()

    for node in module.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                try:
                    exec(
                        f"{alias.asname or alias.name} = importlib.import_module('{alias.name}')",
                        exec_globals,
                        locals(),
                    )
                    exec_globals[alias.asname or alias.name] = importlib.import_module(alias.name)
                except ModuleNotFoundError as e:
                    msg = f"Module {alias.name} not found. Please install it and try again."
                    raise ModuleNotFoundError(msg) from e

    function_code = next(
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    function_code.parent = None
    code_obj = compile(ast.Module(body=[function_code], type_ignores=[]), "<string>", "exec")
    try:
        exec(code_obj, exec_globals, locals())
    except Exception as exc:
        msg = "Function string does not contain a function"
        raise ValueError(msg) from exc

    # Add the function to the exec_globals dictionary
    exec_globals[function_name] = locals()[function_name]

    return exec_globals[function_name](*args, **kwargs)


def create_function(code, function_name):
    if not hasattr(ast, "TypeIgnore"):

        class TypeIgnore(ast.AST):
            _fields = ()

        ast.TypeIgnore = TypeIgnore

    module = ast.parse(code)
    exec_globals = globals().copy()

    for node in module.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                try:
                    if isinstance(node, ast.ImportFrom):
                        module_name = node.module
                        exec_globals[alias.asname or alias.name] = getattr(
                            importlib.import_module(module_name), alias.name
                        )
                    else:
                        module_name = alias.name
                        exec_globals[alias.asname or alias.name] = importlib.import_module(module_name)
                except ModuleNotFoundError as e:
                    msg = f"Module {alias.name} not found. Please install it and try again."
                    raise ModuleNotFoundError(msg) from e

    function_code = next(
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    function_code.parent = None
    code_obj = compile(ast.Module(body=[function_code], type_ignores=[]), "<string>", "exec")
    with contextlib.suppress(Exception):
        exec(code_obj, exec_globals, locals())
    exec_globals[function_name] = locals()[function_name]

    # Return a function that imports necessary modules and calls the target function
    def wrapped_function(*args, **kwargs):
        for module_name, module in exec_globals.items():
            if isinstance(module, type(importlib)):
                globals()[module_name] = module

        return exec_globals[function_name](*args, **kwargs)

    return wrapped_function


def create_class(code, class_name):
    """Dynamically create a class from a string of code and a specified class name.

    Args:
        code: String containing the Python code defining the class
        class_name: Name of the class to be created

    Returns:
         A function that, when called, returns an instance of the created class

    Raises:
        ValueError: If the code contains syntax errors or the class definition is invalid
    """
    if not hasattr(ast, "TypeIgnore"):
        ast.TypeIgnore = create_type_ignore_class()

    # Replace from langflow import CustomComponent with from langflow.custom import CustomComponent
    code = code.replace("from langflow import CustomComponent", "from langflow.custom import CustomComponent")
    code = code.replace(
        "from langflow.interface.custom.custom_component import CustomComponent",
        "from langflow.custom import CustomComponent",
    )
    # Add DEFAULT_IMPORT_STRING
    code = DEFAULT_IMPORT_STRING + "\n" + code
    module = ast.parse(code)
    exec_globals = prepare_global_scope(module)

    class_code = extract_class_code(module, class_name)
    compiled_class = compile_class_code(class_code)
    try:
        return build_class_constructor(compiled_class, exec_globals, class_name)
    except ValidationError as e:
        messages = [error["msg"].split(",", 1) for error in e.errors()]
        error_message = "\n".join([message[1] if len(message) > 1 else message[0] for message in messages])
        raise ValueError(error_message) from e


def create_type_ignore_class():
    """Create a TypeIgnore class for AST module if it doesn't exist.

    Returns:
        TypeIgnore class
    """

    class TypeIgnore(ast.AST):
        _fields = ()

    return TypeIgnore


def prepare_global_scope(module):
    """Prepares the global scope with necessary imports from the provided code module.

    Args:
        module: AST parsed module

    Returns:
        Dictionary representing the global scope with imported modules

    Raises:
        ModuleNotFoundError: If a module is not found in the code
    """
    exec_globals = globals().copy()
    for node in module.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                try:
                    exec_globals[alias.asname or alias.name] = importlib.import_module(alias.name)
                except ModuleNotFoundError as e:
                    msg = f"Module {alias.name} not found. Please install it and try again."
                    raise ModuleNotFoundError(msg) from e
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", LangChainDeprecationWarning)
                    imported_module = importlib.import_module(node.module)
                    for alias in node.names:
                        try:
                            # First try getting it as an attribute
                            exec_globals[alias.name] = getattr(imported_module, alias.name)
                        except AttributeError:
                            # If that fails, try importing the full module path
                            full_module_path = f"{node.module}.{alias.name}"
                            exec_globals[alias.name] = importlib.import_module(full_module_path)
            except ModuleNotFoundError as e:
                msg = f"Module {node.module} not found. Please install it and try again"
                raise ModuleNotFoundError(msg) from e
        elif isinstance(node, ast.ClassDef):
            # Compile and execute the class definition to properly create the class
            class_code = compile(ast.Module(body=[node], type_ignores=[]), "<string>", "exec")
            exec(class_code, exec_globals)
        elif isinstance(node, ast.FunctionDef):
            function_code = compile(ast.Module(body=[node], type_ignores=[]), "<string>", "exec")
            exec(function_code, exec_globals)
        elif isinstance(node, ast.Assign):
            assign_code = compile(ast.Module(body=[node], type_ignores=[]), "<string>", "exec")
            exec(assign_code, exec_globals)
    return exec_globals


def extract_class_code(module, class_name):
    """Extracts the AST node for the specified class from the module.

    Args:
        module: AST parsed module
        class_name: Name of the class to extract

    Returns:
        AST node of the specified class
    """
    class_code = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == class_name)

    class_code.parent = None
    return class_code


def compile_class_code(class_code):
    """Compiles the AST node of a class into a code object.

    Args:
        class_code: AST node of the class

    Returns:
        Compiled code object of the class
    """
    return compile(ast.Module(body=[class_code], type_ignores=[]), "<string>", "exec")


def build_class_constructor(compiled_class, exec_globals, class_name):
    """Builds a constructor function for the dynamically created class.

    Args:
        compiled_class: Compiled code object of the class
        exec_globals: Global scope with necessary imports
        class_name: Name of the class

    Returns:
         Constructor function for the class
    """
    exec(compiled_class, exec_globals, locals())
    exec_globals[class_name] = locals()[class_name]

    # Return a function that imports necessary modules and creates an instance of the target class
    def build_custom_class():
        for module_name, module in exec_globals.items():
            if isinstance(module, type(importlib)):
                globals()[module_name] = module

        return exec_globals[class_name]

    return build_custom_class()


# TODO: Remove this function
def get_default_imports(code_string):
    """Returns a dictionary of default imports for the dynamic class constructor."""
    default_imports = {
        "Optional": Optional,
        "List": list,
        "Dict": dict,
        "Union": Union,
    }
    langflow_imports = list(CUSTOM_COMPONENT_SUPPORTED_TYPES.keys())
    necessary_imports = find_names_in_code(code_string, langflow_imports)
    langflow_module = importlib.import_module("langflow.field_typing")
    default_imports.update({name: getattr(langflow_module, name) for name in necessary_imports})

    return default_imports


def find_names_in_code(code, names):
    """Finds if any of the specified names are present in the given code string.

    Args:
        code: The source code as a string.
        names: A list of names to check for in the code.

    Returns:
        A set of names that are found in the code.
    """
    return {name for name in names if name in code}


def extract_function_name(code):
    module = ast.parse(code)
    for node in module.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    msg = "No function definition found in the code string"
    raise ValueError(msg)


def extract_class_name(code: str) -> str:
    """Extract the name of the first Component subclass found in the code.

    Args:
        code (str): The source code to parse

    Returns:
        str: Name of the first Component subclass found

    Raises:
        TypeError: If no Component subclass is found in the code
    """
    try:
        module = ast.parse(code)
        for node in module.body:
            if not isinstance(node, ast.ClassDef):
                continue

            # Check bases for Component inheritance
            # TODO: Build a more robust check for Component inheritance
            for base in node.bases:
                if isinstance(base, ast.Name) and any(pattern in base.id for pattern in ["Component", "LC"]):
                    return node.name

        msg = f"No Component subclass found in the code string. Code snippet: {code[:100]}"
        raise TypeError(msg)
    except SyntaxError as e:
        msg = f"Invalid Python code: {e!s}"
        raise ValueError(msg) from e
