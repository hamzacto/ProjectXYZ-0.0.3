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

# Keep this class for usage tracking - it will be populated by the HTTPX Stream implementation
class TokenUsageRegistry:
    """Global registry for storing token usage information from OpenAI calls."""
    
    _instance = None
    _usage_log = []
    _flow_context = {}
    _flow_tracking = {}  # Track cumulative usage per flow
    _kb_tools_invoked = {}  # Track KB tools that have been invoked
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of registry."""
        if cls._instance is None:
            cls._instance = TokenUsageRegistry()
        return cls._instance
    
    @classmethod
    def set_flow_context(cls, flow_id=None, component_id=None):
        """Set the current flow context for token tracking."""
        instance = cls.get_instance()
        instance._flow_context = {
            "flow_id": flow_id,
            "component_id": component_id
        }
        print(f"[Token Tracking] Set context: Flow {flow_id}, Component {component_id}")
        
        # If we see an invoking line in the logs right before this context is set, record it
        # This is a workaround for tools not being properly tracked through the callback
        if flow_id and component_id and "agent" in component_id.lower():
            # Check if there's evidence of KB tool invocation in the logs
            import builtins
            original_print = builtins.print
            
            def detect_kb_invocation(text, kb_name=None):
                """Detect KB tool invocations in logged text and record them."""
                if isinstance(text, str) and text.startswith("Inevoking: `") and "-" in text:
                    # Format is typically: Invoking: `Milvus-search_documents` with `{'search_query': '...'}`
                    try:
                        # Extract the tool name (e.g., "Milvus-search_documents")
                        tool_part = text.split("`")[1]
                        if "-" in tool_part:
                            kb_base = tool_part.split("-")[0].lower()
                            KNOWN_KB_COMPONENTS = {"milvus", "chroma", "qdrant", "pinecone", "vectorstore"}
                            
                            if kb_base in KNOWN_KB_COMPONENTS:
                                print(f"[TokenRegistry] Detected KB tool invocation: {tool_part} for flow {flow_id}")
                                # Record this KB invocation for this flow
                                if flow_id not in cls._kb_tools_invoked:
                                    cls._kb_tools_invoked[flow_id] = []
                                cls._kb_tools_invoked[flow_id].append(kb_base)
                    except Exception as e:
                        print(f"[TokenRegistry] Error parsing tool invocation: {e}")
            
            # Check recent logs for KB tool invocations
            if flow_id in cls._kb_tools_invoked:
                print(f"[TokenRegistry] KB tools already detected for flow {flow_id}: {cls._kb_tools_invoked[flow_id]}")
    
    @classmethod
    def get_flow_context(cls):
        """Get the current flow context."""
        return cls.get_instance()._flow_context
    
    @classmethod
    def clear_flow_context(cls):
        """Clear the current flow context."""
        cls.get_instance()._flow_context = {}
    
    @classmethod
    def register_kb_tool_invocation(cls, flow_id, kb_name):
        """Explicitly register a KB tool invocation."""
        instance = cls.get_instance()
        if flow_id not in instance._kb_tools_invoked:
            instance._kb_tools_invoked[flow_id] = []
        if kb_name not in instance._kb_tools_invoked[flow_id]:
            instance._kb_tools_invoked[flow_id].append(kb_name)
            print(f"[TokenRegistry] Registered KB tool invocation: {kb_name} for flow {flow_id}")
    
    @classmethod
    def reset_kb_tracking(cls, flow_id):
        """Reset KB tracking for a specific flow ID."""
        instance = cls.get_instance()
        if flow_id in instance._kb_tools_invoked:
            instance._kb_tools_invoked.pop(flow_id)
            print(f"[TokenRegistry] Reset KB tracking for flow: {flow_id}")
    
    @classmethod
    def summarize_flow_usage(cls, flow_id):
        """Get a summary of token usage for a specific flow."""
        instance = cls.get_instance()
        if flow_id not in instance._flow_tracking:
            return None
        
        return instance._flow_tracking[flow_id]
    
    def _update_flow_tracking(self, flow_id, model, prompt_tokens, completion_tokens, total_tokens):
        """Update cumulative token tracking for a flow."""
        if not flow_id:
            return  # Skip if no flow_id
            
        if flow_id not in self._flow_tracking:
            self._flow_tracking[flow_id] = {
                "llm_calls": 0,
                "models": set(),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "components": set()
            }
        
        # Update tracking
        self._flow_tracking[flow_id]["llm_calls"] += 1
        self._flow_tracking[flow_id]["models"].add(model)
        self._flow_tracking[flow_id]["prompt_tokens"] += prompt_tokens
        self._flow_tracking[flow_id]["completion_tokens"] += completion_tokens
        self._flow_tracking[flow_id]["total_tokens"] += total_tokens
        
        component_id = self._flow_context.get("component_id")
        if component_id:
            self._flow_tracking[flow_id]["components"].add(component_id)
    
    def record_usage(self, model, prompt_tokens, completion_tokens, total_tokens):
        """Record token usage from an API call and log it to CreditService."""
        import datetime

        # Get current flow context
        flow_context = self._flow_context
        flow_id = flow_context.get("flow_id")
        component_id = flow_context.get("component_id")

        # We still store the raw log entry locally if needed
        usage_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "flow_id": flow_id,
            "component_id": component_id
        }
        self._usage_log.append(usage_entry)

        # Update cumulative tracking per flow (can keep this for flow summary)
        self._update_flow_tracking(flow_id, model, prompt_tokens, completion_tokens, total_tokens)

        # Log token usage using the CreditService
        try:
            credit_service = service_manager.get(ServiceType.CREDIT_SERVICE)
            if credit_service:
                # Create TokenUsage object
                token_usage_data = TokenUsage(
                    model_name=model,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens
                )

                # Generate a unique run_id - HOW? Needs context.
                # This is a problem. The HTTPX patch doesn't know the overall 'run_id'.
                # We might need to pass the run_id via flow_context as well.
                # For now, let's use flow_id + component_id + timestamp as a temporary proxy,
                # but this needs alignment with the run_id used by callbacks.
                # --- START TEMPORARY RUN ID ---
                run_id = f"{flow_id}_{component_id}_{datetime.datetime.now().timestamp()}"
                # Store the base flow_id for KB usage logging
                base_run_id = flow_id
                if not flow_id or not component_id:
                    print("Cannot determine run_id for token logging due to missing flow/component context.")
                    # Decide fallback: maybe log globally without run_id, or skip? Skipping for now.
                    return
                # --- END TEMPORARY RUN ID ---

                # Log token usage to the service
                credit_service.log_token_usage(
                    run_id=run_id, # Pass the determined run_id
                    token_usage=token_usage_data,
                )
                
                # IMPORTANT: Also log to the base flow_id to ensure it gets consolidated properly
                if base_run_id and base_run_id != run_id:
                    credit_service.log_token_usage(
                        run_id=base_run_id,
                        token_usage=token_usage_data,
                    )
                    print(f"[TokenRegistry] Also logged token usage to base run_id: {base_run_id}")

                # Add back KB detection logic
                if component_id:
                    # Check if this is a KB component (case-insensitive)
                    component_base_name = component_id.split('-')[0].lower()
                    kb_method_pattern = r'([a-zA-Z]+)-search_documents'
                    KNOWN_KB_COMPONENTS = {"milvus", "chroma", "qdrant", "pinecone", "vectorstore"}
                    
                    # Direct KB component detection
                    if component_base_name in KNOWN_KB_COMPONENTS and credit_service:
                        from langflow.services.credit.service import KBUsage
                        kb_usage = KBUsage(kb_name=component_base_name, count=1)
                        # Use the base flow_id for KB tracking
                        credit_service.log_kb_usage(
                            run_id=base_run_id, # Use base flow_id for consistency with finalize_run_cost
                            kb_usage=kb_usage
                        )
                        print(f"[TokenRegistry] Logged KB usage for {component_base_name} with run_id {base_run_id}")
                    
                    # KB tool invocation detection (e.g., "Milvus-search_documents")
                    elif "-" in component_id:
                        # Add more debugging
                        print(f"[TokenRegistry DEBUG] Checking tool component: {component_id}")
                        
                        # Check for search_documents pattern
                        if "search_documents" in component_id.lower():
                            # This is likely a KB tool invocation
                            tool_base_name = component_id.split('-')[0].lower()
                            print(f"[TokenRegistry DEBUG] Found search_documents pattern, base name: {tool_base_name}")
                            
                            if tool_base_name in KNOWN_KB_COMPONENTS:
                                kb_usage = KBUsage(kb_name=tool_base_name, count=1)
                                credit_service.log_kb_usage(
                                    run_id=base_run_id, # Use base flow_id for consistency
                                    kb_usage=kb_usage
                                )
                                print(f"[TokenRegistry] Logged KB tool invocation for {tool_base_name} with run_id {base_run_id}")
                            else:
                                print(f"[TokenRegistry DEBUG] Base name {tool_base_name} not in known KB components: {KNOWN_KB_COMPONENTS}")
                        else:
                            # Let's also check for other common KB operation patterns
                            kb_operation_patterns = ["similarity_search", "get_", "query", "retrieve", "search", "vector_search"]
                            matched_pattern = next((pattern for pattern in kb_operation_patterns if pattern in component_id.lower()), None)
                            
                            if matched_pattern:
                                print(f"[TokenRegistry DEBUG] Found potential KB operation: {matched_pattern} in {component_id}")
                                # Extract the component name
                                tool_base_name = component_id.split('-')[0].lower()
                                if tool_base_name in KNOWN_KB_COMPONENTS:
                                    kb_usage = KBUsage(kb_name=tool_base_name, count=1)
                                    credit_service.log_kb_usage(
                                        run_id=base_run_id,
                                        kb_usage=kb_usage
                                    )
                                    print(f"[TokenRegistry] Logged KB tool invocation (alt pattern) for {tool_base_name} with run_id {base_run_id}")
                    
                    # Check if any KB tools were previously detected for this flow
                    if flow_id in self._kb_tools_invoked and self._kb_tools_invoked[flow_id]:
                        # If the component is the agent making LLM calls (usually after tool usage)
                        if "agent" in component_id.lower():
                            for kb_name in self._kb_tools_invoked[flow_id]:
                                kb_usage = KBUsage(kb_name=kb_name, count=1)
                                credit_service.log_kb_usage(
                                    run_id=base_run_id,
                                    kb_usage=kb_usage
                                )
                                print(f"[TokenRegistry] Logged previously detected KB usage for {kb_name} with run_id {base_run_id}")
                            # Clear the list after logging
                            self._kb_tools_invoked[flow_id] = []

            else:
                # Fallback logging if CreditService isn't available
                # This can remain as simple print statements
                cost_per_1k_input = 0.01
                cost_per_1k_output = 0.03
                input_cost = (prompt_tokens / 1000) * cost_per_1k_input
                completion_cost = (completion_tokens / 1000) * cost_per_1k_output
                total_cost = input_cost + completion_cost
                print(f"[Fallback LLM Cost] Flow: {flow_id or 'unknown'}, Comp: {component_id or 'unknown'}, Model: {model}")
                print(f"[Fallback LLM Cost] Tokens: P={prompt_tokens}(${input_cost:.6f}) C={completion_tokens}(${completion_cost:.6f}) Total Cost: ${total_cost:.6f}")

        except Exception as e:
            logger.error(f"[Token Tracking] Error logging token usage to CreditService: {e}")
            # Log basic info if we hit an error
            print(f"[Token Usage Fallback] Model: {model}, Input: {prompt_tokens}, Output: {completion_tokens}")
    
    def print_flow_summary(self, flow_id):
        """Print a summary of token usage for a flow."""
        if flow_id not in self._flow_tracking:
            print(f"[Flow Summary] No data available for flow {flow_id}")
            return
        
        data = self._flow_tracking[flow_id]
        total_prompt_tokens = data["prompt_tokens"]
        total_completion_tokens = data["completion_tokens"]
        total_tokens = data["total_tokens"]
        
        # Calculate cost (simplified version)
        # In production, would use model-specific costs from CreditService
        avg_prompt_cost = 0.01  # Average cost per 1K tokens
        avg_completion_cost = 0.03  # Average cost per 1K tokens
        prompt_cost = (total_prompt_tokens / 1000) * avg_prompt_cost
        completion_cost = (total_completion_tokens / 1000) * avg_completion_cost
        total_cost = prompt_cost + completion_cost
        
        print("\n" + "="*50)
        print(f"[FLOW SUMMARY] Flow ID: {flow_id}")
        print(f"[FLOW SUMMARY] Total LLM calls: {data['llm_calls']}")
        print(f"[FLOW SUMMARY] Models used: {', '.join(data['models'])}")
        print(f"[FLOW SUMMARY] Components with LLM calls: {', '.join(data['components'])}")
        print(f"[FLOW SUMMARY] Total prompt tokens: {total_prompt_tokens} (${prompt_cost:.6f})")
        print(f"[FLOW SUMMARY] Total completion tokens: {total_completion_tokens} (${completion_cost:.6f})")
        print(f"[FLOW SUMMARY] Total tokens: {total_tokens}")
        print(f"[FLOW SUMMARY] Estimated total cost: ${total_cost:.6f}")
        print("="*50 + "\n")
    
    def get_all_usage(self):
        """Get all recorded token usage."""
        return self._usage_log
    
    def get_total_usage(self):
        """Get total token usage across all calls."""
        total_prompt = sum(entry["prompt_tokens"] for entry in self._usage_log)
        total_completion = sum(entry["completion_tokens"] for entry in self._usage_log)
        total = sum(entry["total_tokens"] for entry in self._usage_log)
        return {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total
        }
        
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
