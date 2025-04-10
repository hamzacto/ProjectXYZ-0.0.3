from types import FunctionType
from typing import Optional, Union, Dict, List, Set, Any
from redis import asyncio as aioredis
import asyncio
import threading
from uuid import UUID
import time
import concurrent.futures

from langchain_core._api.deprecation import LangChainDeprecationWarning
from loguru import logger
from pydantic import ValidationError
from langflow.field_typing.constants import CUSTOM_COMPONENT_SUPPORTED_TYPES, DEFAULT_IMPORT_STRING
from langflow.services.manager import service_manager
from langflow.services.schema import ServiceType
from langflow.services.credit.service import TokenUsage

# Get Redis connection from the existing implementation
try:
    from langflow.api.v1.hubspot_integrations import redis as redis_connection
except ImportError:
    # Fallback if we can't import the existing Redis connection
    redis_connection = None

class TokenUsageRegistry:
    """Registry for tracking token usage across flows"""
    _instance = None
    _instance_lock = threading.Lock()  # Class-level lock for singleton access
    _thread_context = threading.local()  # Thread-local storage for flow context
    
    def __init__(self):
        self._flow_tracking_lock = threading.RLock()  # Reentrant lock for flow tracking operations
        self._kb_tools_lock = threading.RLock()       # Reentrant lock for KB tools operations
        self._context_lock = threading.RLock()        # Lock for flow context operations
        self._id_mapping_lock = threading.RLock()     # Lock for ID mapping operations
        
        self._flow_tracking: Dict[str, Dict[str, Union[int, Set[str]]]] = {}  # Format: {flow_id: {prompt_tokens, completion_tokens, total_tokens, models}}
        self._flow_user_mapping: Dict[str, UUID] = {}  # Format: {flow_id: user_id}
        self._kb_tools_invoked: Dict[str, List[str]] = {}  # Format: {flow_id: [kb_names]}
        self._credit_service = None
        self._original_session_ids = {}
        self._id_mapping = {}
        self._token_thread_loop = None
        self._kb_thread_loop = None
        self._redis = None
        self._redis_initialized = False
        self._redis_prefix = "langflow:billing:"
        
        # Initialize Redis connection
        self._init_redis()
    
    def _init_redis(self):
        """Initialize Redis connection"""
        global redis_connection
        try:
            if redis_connection is not None:
                self._redis = redis_connection
                self._redis_initialized = True
                print("[TokenRegistry] Redis connection initialized from existing connection")
            else:
                # Create new connection if we couldn't import the existing one
                self._redis_task = asyncio.create_task(self._connect_redis())
                print("[TokenRegistry] Created task to initialize Redis connection")
        except Exception as e:
            print(f"[TokenRegistry] Failed to initialize Redis: {e}")
            self._redis_initialized = False
    
    async def _connect_redis(self):
        """Connect to Redis asynchronously"""
        try:
            print("[TokenRegistry] Attempting to connect to Redis at localhost:6379...")
            self._redis = await aioredis.from_url("redis://localhost:6379")
            self._redis_initialized = True
            print("[TokenRegistry] Redis connection successfully initialized")
        except Exception as e:
            print(f"[TokenRegistry] Failed to connect to Redis: {e}")
            self._redis_initialized = False
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance with thread safety"""
        if cls._instance is None:
            with cls._instance_lock:  # Ensure only one thread creates the instance
                if cls._instance is None:  # Double-check pattern
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
    
    def _get_distributed_cache(self):
        """Get distributed cache connection"""
        cache = self._redis if self._redis_initialized else None
        if cache:
            print("[TokenRegistry] Using Redis as distributed cache")
        else:
            print("[TokenRegistry] Redis not available, using local memory cache only")
        return cache
    
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
        with instance._context_lock:
            return {
                "flow_id": TokenUsageRegistry._get_current_flow_id(),
                "component_id": TokenUsageRegistry._get_current_component_id()
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
    
    @staticmethod
    def set_flow_user(flow_id: str, user_id: UUID):
        """Set the user for a flow context"""
        instance = TokenUsageRegistry.get_instance()
        instance.set_user_for_flow(flow_id, user_id)
    
    # ==== IMPLEMENTATION METHODS (private) ====
    def _set_flow_context_impl(self, flow_id, component_id=None):
        """Implementation of set_flow_context"""
        with self._context_lock:
            self._set_current_flow_id(flow_id)
            self._set_current_component_id(component_id)
    
    def _clear_flow_context_impl(self):
        """Implementation of clear_flow_context"""
        with self._context_lock:
            self._set_current_flow_id(None)
            self._set_current_component_id(None)
    
    async def _redis_update_tokens(self, flow_id, model, prompt, completion, total):
        """Update token counts in Redis atomically"""
        print(f"[TokenRegistry] Attempting to update Redis token tracking for flow {flow_id}")
        try:
            pipe = self._redis.pipeline()
            key_base = f"{self._redis_prefix}flow:{flow_id}"
            
            print(f"[TokenRegistry] Redis pipeline: updating tokens - prompt: {prompt}, completion: {completion}, total: {total}")
            # Update token counts
            pipe.hincrby(f"{key_base}:tokens", "prompt", prompt)
            pipe.hincrby(f"{key_base}:tokens", "completion", completion)
            pipe.hincrby(f"{key_base}:tokens", "total", total)
            
            # Add model to set
            pipe.sadd(f"{key_base}:models", model)
            print(f"[TokenRegistry] Redis pipeline: adding model {model} to set")
            
            # Set expiration (7 days)
            pipe.expire(f"{key_base}:tokens", 7 * 24 * 60 * 60)
            pipe.expire(f"{key_base}:models", 7 * 24 * 60 * 60)
            
            print("[TokenRegistry] Executing Redis pipeline...")
            result = await pipe.execute()
            print(f"[TokenRegistry] Redis pipeline executed successfully: {result}")
            return True
        except Exception as e:
            print(f"[TokenRegistry] Redis token update error: {e}")
            logger.error(f"Redis token update error: {e}")
            return False
    
    def _record_usage_impl(self, model, prompt_tokens, completion_tokens, total_tokens):
        """Implementation of record_usage with thread safety"""
        with self._context_lock:
            current_flow_id = self._get_current_flow_id()
            current_component_id = self._get_current_component_id()
            
        if not current_flow_id:
            print("[TokenRegistry] No flow context set for token tracking")
            return
        
        print(f"[TokenRegistry] Recording token usage: model={model}, prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
        
        # Try to update in distributed cache first
        distributed_cache = self._get_distributed_cache()
        if distributed_cache:
            try:
                # Create a dedicated event loop for this operation if needed
                # This ensures we always have a valid event loop
                need_new_loop = False
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If we're in an async context, create a task
                        print("[TokenRegistry] In async context, creating task for Redis update")
                        # Create a fresh coroutine instance instead of reusing the method
                        async def _create_token_update_coroutine():
                            # Create a new coroutine to avoid event loop attachment issues
                            try:
                                pipe = self._redis.pipeline()
                                key_base = f"{self._redis_prefix}flow:{current_flow_id}"
                                
                                # Update token counts
                                pipe.hincrby(f"{key_base}:tokens", "prompt", prompt_tokens)
                                pipe.hincrby(f"{key_base}:tokens", "completion", completion_tokens)
                                pipe.hincrby(f"{key_base}:tokens", "total", total_tokens)
                                
                                # Add model to set
                                pipe.sadd(f"{key_base}:models", model)
                                
                                # Set expiration (7 days)
                                pipe.expire(f"{key_base}:tokens", 7 * 24 * 60 * 60)
                                pipe.expire(f"{key_base}:models", 7 * 24 * 60 * 60)
                                
                                result = await pipe.execute()
                                print(f"[TokenRegistry] Redis token update complete in async context: {result}")
                                return True
                            except Exception as e:
                                print(f"[TokenRegistry] Redis token update error in async context: {e}")
                                return False
                        
                        # Create a fresh task with the newly created coroutine
                        asyncio.create_task(_create_token_update_coroutine())
                    else:
                        need_new_loop = True
                except RuntimeError:
                    # No event loop in this thread
                    need_new_loop = True
                    
                if need_new_loop:
                    print("[TokenRegistry] Not in async context, using background thread for Redis update")
                    # Ensure we have a thread with an event loop
                    if not hasattr(self, "_token_thread_loop") or self._token_thread_loop is None:
                        print("[TokenRegistry] Creating new event loop for token thread")
                        self._token_thread_loop = asyncio.new_event_loop()
                        thread = threading.Thread(target=self._run_token_event_loop, daemon=True)
                        thread.start()
                        # Wait a tiny bit to ensure the loop is running before we try to use it
                        time.sleep(0.01)
                        print("[TokenRegistry] Token thread started")
                    
                    # Create a function that will produce a fresh coroutine when called
                    # This ensures the coroutine is created within the context of the target event loop
                    def get_token_coroutine():
                        async def _threaded_token_update():
                            try:
                                pipe = self._redis.pipeline()
                                key_base = f"{self._redis_prefix}flow:{current_flow_id}"
                                
                                # Update token counts
                                pipe.hincrby(f"{key_base}:tokens", "prompt", prompt_tokens)
                                pipe.hincrby(f"{key_base}:tokens", "completion", completion_tokens)
                                pipe.hincrby(f"{key_base}:tokens", "total", total_tokens)
                                
                                # Add model to set
                                pipe.sadd(f"{key_base}:models", model)
                                
                                # Set expiration (7 days)
                                pipe.expire(f"{key_base}:tokens", 7 * 24 * 60 * 60)
                                pipe.expire(f"{key_base}:models", 7 * 24 * 60 * 60)
                                
                                result = await pipe.execute()
                                print(f"[TokenRegistry] Redis token update complete in thread: {result}")
                                return True
                            except Exception as e:
                                print(f"[TokenRegistry] Redis token update error in thread: {e}")
                                return False
                        return _threaded_token_update()
                        
                    # Schedule the coroutine to run in the thread's event loop
                    print("[TokenRegistry] Scheduling Redis update in thread event loop")
                    try:
                        # Use get_token_coroutine() to get a fresh coroutine
                        future = asyncio.run_coroutine_threadsafe(
                            get_token_coroutine(),
                            self._token_thread_loop
                        )
                        # Optionally, can wait for a short time to ensure the task has started
                        try:
                            future.result(timeout=0.2)  # Small timeout to not block too long
                        except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                            # This is expected, we don't really need to wait for completion
                            pass
                        except Exception as e:
                            print(f"[TokenRegistry] Token update async operation error: {e}")
                    except Exception as e:
                        print(f"[TokenRegistry] Error scheduling token update: {e}")
                        import traceback
                        traceback.print_exc()
            except Exception as e:
                print(f"[TokenRegistry] Failed to update Redis token tracking: {e}")
                logger.error(f"Failed to update Redis token tracking: {e}")
                import traceback
                traceback.print_exc()
            
        # Still update local cache with proper locking
        with self._flow_tracking_lock:
            # Initialize or update flow tracking
            if current_flow_id not in self._flow_tracking:
                self._flow_tracking[current_flow_id] = {
                    "prompt_tokens": 0, 
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "models": set()
                }
            
            ft = self._flow_tracking[current_flow_id]
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
            self.credit_service.log_token_usage(run_id=current_flow_id, token_usage=token_usage)
            print(f"[TokenRegistry] Delegated {prompt_tokens} input, {completion_tokens} output tokens directly to CreditService")
            
            # Also log to component-specific run_id if component is set
            if current_component_id:
                component_run_id = f"{current_flow_id}_{current_component_id}"
                self.credit_service.log_token_usage(run_id=component_run_id, token_usage=token_usage)
                
        # Also log to BillingService if available
        try:
            from langflow.services.manager import service_manager
            from langflow.services.schema import ServiceType
            
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
                session_id = current_flow_id
                
                # Get the user ID for this flow
                user_id = self._get_user_id_for_flow(current_flow_id)
                if not user_id:
                    print(f"[TokenRegistry] WARNING: No user_id found for flow {current_flow_id}")
                    # Try to get user ID from any related flows
                    for related_id, mapped_id in self._id_mapping.items():
                        if related_id == current_flow_id or mapped_id == current_flow_id:
                            user_id = self._get_user_id_for_flow(related_id) or self._get_user_id_for_flow(mapped_id)
                            if user_id:
                                print(f"[TokenRegistry] Found user_id {user_id} from related flow {related_id if user_id == self._get_user_id_for_flow(related_id) else mapped_id}")
                                break
                
                # Try different strategies to get the correct session ID:
                with self._id_mapping_lock:
                    # 1. If we're dealing with a UUID, check if it's mapped in BillingService
                    if len(current_flow_id) == 36 and not current_flow_id.startswith("Session"):
                        # Check if BillingService has a mapping for this UUID
                        if hasattr(billing_service, "_uuid_to_session_mappings") and current_flow_id in billing_service._uuid_to_session_mappings:
                            original_session_id = billing_service._uuid_to_session_mappings[current_flow_id]
                            print(f"[TokenRegistry] Using mapped Session ID from BillingService: {original_session_id}")
                            session_id = original_session_id
                        elif current_flow_id in self._id_mapping:
                            # Try our own mapping as fallback
                            print(f"[TokenRegistry] Using internally mapped Session ID: {self._id_mapping[current_flow_id]}")
                            session_id = self._id_mapping[current_flow_id]
                        else:
                            # As a last resort, keep using UUID directly
                            print(f"[TokenRegistry] Using UUID directly: {current_flow_id}")
                
                # Similar approach to Redis updates - check for event loop and handle properly
                need_new_loop = False
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule the async operation as a background task
                        if user_id:
                            asyncio.create_task(billing_service.log_token_usage(run_id=session_id, token_usage=token_usage, user_id=user_id))
                            print(f"[TokenRegistry] Scheduled token usage logging to BillingService with ID: {session_id}, user_id: {user_id}")
                        else:
                            print(f"[TokenRegistry] SKIPPED token usage logging to BillingService - no user_id available")
                    else:
                        need_new_loop = True
                except RuntimeError:
                    # No event loop in this thread
                    need_new_loop = True
                
                if need_new_loop:
                    print(f"[TokenRegistry] Event loop not running, using thread event loop for BillingService")
                    # Use run_coroutine_threadsafe with a new event loop
                    if not hasattr(self, "_token_thread_loop") or self._token_thread_loop is None:
                        # Create a new event loop for this thread if none exists
                        self._token_thread_loop = asyncio.new_event_loop()
                        thread = threading.Thread(target=self._run_token_event_loop, daemon=True)
                        thread.start()
                        # Wait briefly to ensure the loop is running
                        time.sleep(0.01)
                    
                    # Schedule the coroutine to run in the thread's event loop
                    if user_id:
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                billing_service.log_token_usage(run_id=session_id, token_usage=token_usage, user_id=user_id),
                                self._token_thread_loop
                            )
                            print(f"[TokenRegistry] Scheduled token usage in threadsafe loop: {session_id}, user_id: {user_id}")
                            # Wait briefly for task to start
                            try:
                                future.result(timeout=0.2)
                            except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                                pass  # Expected, just making sure task started
                        except Exception as e:
                            print(f"[TokenRegistry] Error scheduling BillingService token task: {e}")
                    else:
                        print(f"[TokenRegistry] SKIPPED token usage in threadsafe loop - no user_id available")
                
        except Exception as e:
            print(f"[TokenRegistry] Error logging to BillingService: {e}")
            import traceback
            traceback.print_exc()
    
    async def _redis_update_kb_tools(self, flow_id, kb_name):
        """Add KB tool to Redis tracking set"""
        print(f"[TokenRegistry] Attempting to update Redis KB tracking for flow {flow_id}, kb {kb_name}")
        try:
            key = f"{self._redis_prefix}flow:{flow_id}:kb_tools"
            
            # Add KB name to set
            print(f"[TokenRegistry] Adding KB {kb_name} to Redis set {key}")
            result = await self._redis.sadd(key, kb_name)
            
            # Set expiration (7 days)
            expiry_result = await self._redis.expire(key, 7 * 24 * 60 * 60)
            print(f"[TokenRegistry] Redis KB update complete: add result={result}, expire result={expiry_result}")
            
            return True
        except Exception as e:
            print(f"[TokenRegistry] Redis KB tool update error: {e}")
            logger.error(f"Redis KB tool update error: {e}")
            return False
    
    def _track_kb_tool_invocation_impl(self, kb_name):
        """Implementation of track_kb_tool_invocation with thread safety"""
        with self._context_lock:
            current_flow_id = self._get_current_flow_id()
            
        if not current_flow_id:
            return
        
        # Try to update in distributed cache first
        distributed_cache = self._get_distributed_cache()
        if distributed_cache:
            try:
                # Create a dedicated event loop for this operation if needed
                # This ensures we always have a valid event loop
                need_new_loop = False
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If we're in an async context, create a task
                        print("[TokenRegistry] In async context, creating task for Redis KB update")
                        # Create a fresh coroutine instance instead of reusing the method
                        async def _create_kb_update_coroutine():
                            # Create a new coroutine to avoid event loop attachment issues
                            key = f"{self._redis_prefix}flow:{current_flow_id}:kb_tools"
                            try:
                                result = await self._redis.sadd(key, kb_name)
                                expiry_result = await self._redis.expire(key, 7 * 24 * 60 * 60)
                                print(f"[TokenRegistry] Redis KB update complete in async context: add={result}, expire={expiry_result}")
                                return True
                            except Exception as e:
                                print(f"[TokenRegistry] Redis KB update error in async context: {e}")
                                return False
                        
                        # Create a fresh task with the newly created coroutine
                        asyncio.create_task(_create_kb_update_coroutine())
                    else:
                        need_new_loop = True
                except RuntimeError:
                    # No event loop in this thread
                    need_new_loop = True
                    
                if need_new_loop:
                    print("[TokenRegistry] Not in async context, using background thread for Redis KB update")
                    # Ensure we have a thread with an event loop
                    if not hasattr(self, "_kb_thread_loop") or self._kb_thread_loop is None:
                        print("[TokenRegistry] Creating new event loop for KB thread")
                        self._kb_thread_loop = asyncio.new_event_loop()
                        thread = threading.Thread(target=self._run_kb_event_loop, daemon=True)
                        thread.start()
                        # Wait a tiny bit to ensure the loop is running before we try to use it
                        time.sleep(0.01)
                        print("[TokenRegistry] KB thread started")
                    
                    # Create a function that will produce a fresh coroutine when called
                    # This ensures the coroutine is created within the context of the target event loop
                    def get_kb_coroutine():
                        async def _threaded_kb_update():
                            key = f"{self._redis_prefix}flow:{current_flow_id}:kb_tools"
                            try:
                                # Use the Redis instance directly - it handles connection pooling
                                result = await self._redis.sadd(key, kb_name)
                                expiry_result = await self._redis.expire(key, 7 * 24 * 60 * 60)
                                print(f"[TokenRegistry] Redis KB update complete in thread: add={result}, expire={expiry_result}")
                                return True
                            except Exception as e:
                                print(f"[TokenRegistry] Redis KB update error in thread: {e}")
                                return False
                        return _threaded_kb_update()
                    
                    # Schedule the coroutine to run in the thread's event loop
                    print("[TokenRegistry] Scheduling Redis KB update in thread event loop")
                    try:
                        # Use get_kb_coroutine() to get a fresh coroutine
                        future = asyncio.run_coroutine_threadsafe(
                            get_kb_coroutine(),
                            self._kb_thread_loop
                        )
                        # Optionally, can wait for a short time to ensure the task has started
                        try:
                            future.result(timeout=0.2)  # Small timeout to not block too long
                        except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                            # This is expected, we don't really need to wait for completion
                            pass
                        except Exception as e:
                            print(f"[TokenRegistry] KB update async operation error: {e}")
                    except Exception as e:
                        print(f"[TokenRegistry] Error scheduling KB update: {e}")
                        import traceback
                        traceback.print_exc()
            except Exception as e:
                print(f"[TokenRegistry] Failed to update Redis KB tracking: {e}")
                logger.error(f"Failed to update Redis KB tracking: {e}")
                import traceback
                traceback.print_exc()
            
        # Still update local cache with proper locking
        with self._kb_tools_lock:
            if current_flow_id not in self._kb_tools_invoked:
                self._kb_tools_invoked[current_flow_id] = []
                
            if kb_name not in self._kb_tools_invoked[current_flow_id]:
                self._kb_tools_invoked[current_flow_id].append(kb_name)
            
        # Delegate to credit service
        if self.credit_service:
            from langflow.services.credit.service import KBUsage
            kb_usage = KBUsage(kb_name=kb_name, count=1)
            self.credit_service.log_kb_usage(run_id=current_flow_id, kb_usage=kb_usage)
            print(f"[TokenRegistry] Delegated KB usage for {kb_name} directly to CreditService")
            
            # Also log to BillingService if available
            try:
                from langflow.services.manager import service_manager
                from langflow.services.schema import ServiceType
                
                billing_service = service_manager.get(ServiceType.BILLING_SERVICE)
                if billing_service:
                    from langflow.services.credit.service import KBUsage
                    kb_usage = KBUsage(kb_name=kb_name, count=1)
                    
                    # IMPORTANT: Use the same approach as _record_usage_impl 
                    # to find consistent session ID
                    session_id = current_flow_id
                    
                    # Get the user ID for this flow
                    user_id = self._get_user_id_for_flow(current_flow_id)
                    if not user_id:
                        print(f"[TokenRegistry] WARNING: No user_id found for flow {current_flow_id}")
                        # Try to get user ID from any related flows
                        for related_id, mapped_id in self._id_mapping.items():
                            if related_id == current_flow_id or mapped_id == current_flow_id:
                                user_id = self._get_user_id_for_flow(related_id) or self._get_user_id_for_flow(mapped_id)
                                if user_id:
                                    print(f"[TokenRegistry] Found user_id {user_id} from related flow {related_id if user_id == self._get_user_id_for_flow(related_id) else mapped_id}")
                                    break
                    
                    # Try different strategies to get the correct session ID:
                    with self._id_mapping_lock:
                        # 1. If we're dealing with a UUID, check if it's mapped in BillingService
                        if len(current_flow_id) == 36 and not current_flow_id.startswith("Session"):
                            # Check if BillingService has a mapping for this UUID
                            if hasattr(billing_service, "_uuid_to_session_mappings") and current_flow_id in billing_service._uuid_to_session_mappings:
                                original_session_id = billing_service._uuid_to_session_mappings[current_flow_id]
                                print(f"[TokenRegistry] Using mapped Session ID from BillingService: {original_session_id}")
                                session_id = original_session_id
                            elif current_flow_id in self._id_mapping:
                                # Try our own mapping as fallback
                                print(f"[TokenRegistry] Using internally mapped Session ID: {self._id_mapping[current_flow_id]}")
                                session_id = self._id_mapping[current_flow_id]
                            else:
                                # As a last resort, keep using UUID directly
                                print(f"[TokenRegistry] Using UUID directly: {current_flow_id}")
                    
                    # Similar approach to Redis updates - check for event loop and handle properly
                    need_new_loop = False
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Schedule the async operation as a background task
                            if user_id:
                                asyncio.create_task(billing_service.log_kb_usage(run_id=session_id, kb_usage=kb_usage, user_id=user_id))
                                print(f"[TokenRegistry] Scheduled KB usage logging to BillingService with ID: {session_id}, user_id: {user_id}")
                            else:
                                print(f"[TokenRegistry] SKIPPED KB usage logging to BillingService - no user_id available")
                        else:
                            need_new_loop = True
                    except RuntimeError:
                        # No event loop in this thread
                        need_new_loop = True
                    
                    if need_new_loop:
                        print(f"[TokenRegistry] Event loop not running, using thread event loop for BillingService KB logging")
                        # Use run_coroutine_threadsafe with a new event loop
                        if not hasattr(self, "_kb_thread_loop") or self._kb_thread_loop is None:
                            # Create a new event loop for this thread if none exists
                            self._kb_thread_loop = asyncio.new_event_loop()
                            thread = threading.Thread(target=self._run_kb_event_loop, daemon=True)
                            thread.start()
                            # Wait briefly to ensure the loop is running
                            time.sleep(0.01)
                        
                        # Schedule the coroutine to run in the thread's event loop
                        if user_id:
                            try:
                                future = asyncio.run_coroutine_threadsafe(
                                    billing_service.log_kb_usage(run_id=session_id, kb_usage=kb_usage, user_id=user_id),
                                    self._kb_thread_loop
                                )
                                print(f"[TokenRegistry] Scheduled KB usage in threadsafe loop: {session_id}, user_id: {user_id}")
                                # Wait briefly for task to start
                                try:
                                    future.result(timeout=0.2)
                                except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                                    pass  # Expected, just making sure task started
                            except Exception as e:
                                print(f"[TokenRegistry] Error scheduling BillingService KB task: {e}")
                        else:
                            print(f"[TokenRegistry] SKIPPED KB usage in threadsafe loop - no user_id available")
                
            except Exception as e:
                print(f"[TokenRegistry] Error logging KB to BillingService: {e}")
                import traceback
                traceback.print_exc()
        
    def _sync_flow_ids_impl(self, source_id, target_id):
        """Sync tracking data from source_id to target_id with thread safety"""
        if source_id == target_id:
            return  # No need to sync if they're the same
        
        print(f"[TokenRegistry] Syncing IDs: source={source_id}, target={target_id}")
        
        # Also sync user_id if available
        with self._context_lock:
            source_user_id = self._flow_user_mapping.get(source_id)
            target_user_id = self._flow_user_mapping.get(target_id)
            
            # If target has no user_id but source does, copy it
            if source_user_id and not target_user_id:
                self._flow_user_mapping[target_id] = source_user_id
                print(f"[TokenRegistry] Copied user_id {source_user_id} from {source_id} to {target_id}")
            # If source has no user_id but target does, copy it the other way
            elif target_user_id and not source_user_id:
                self._flow_user_mapping[source_id] = target_user_id
                print(f"[TokenRegistry] Copied user_id {target_user_id} from {target_id} to {source_id}")
            
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
            with self._id_mapping_lock:
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
            
        # Sync token tracking in distributed cache if available
        distributed_cache = self._get_distributed_cache()
        if distributed_cache:
            # This would contain Redis logic to sync flow IDs
            # For example, copy all token usage data from source to target
            pass
            
        # Sync token tracking in local cache
        source_data = None
        with self._flow_tracking_lock:
            # Get source data
            if source_id in self._flow_tracking:
                source_data = self._flow_tracking[source_id].copy()
                
                # Initialize target if needed
                if target_id not in self._flow_tracking:
                    self._flow_tracking[target_id] = {
                        "prompt_tokens": 0, 
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "models": set()
                    }
                    
                # Add source tracking to target
                self._flow_tracking[target_id]["prompt_tokens"] += source_data["prompt_tokens"]
                self._flow_tracking[target_id]["completion_tokens"] += source_data["completion_tokens"] 
                self._flow_tracking[target_id]["total_tokens"] += source_data["total_tokens"]
                self._flow_tracking[target_id]["models"].update(source_data["models"])
                
                print(f"[TokenRegistry] Synced {source_data['total_tokens']} tokens from {source_id} to {target_id}")
            
        # Sync KB tracking in local cache
        source_kb_tools = None
        with self._kb_tools_lock:
            if source_id in self._kb_tools_invoked:
                source_kb_tools = self._kb_tools_invoked[source_id].copy()
                
                if target_id not in self._kb_tools_invoked:
                    self._kb_tools_invoked[target_id] = []
                    
                # Add source KB tools to target
                for kb in source_kb_tools:
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

    def _run_token_event_loop(self):
        """Run the event loop in a background thread for token usage async operations."""
        print("[TokenRegistry] Starting token event loop in background thread")
        asyncio.set_event_loop(self._token_thread_loop)
        try:
            self._token_thread_loop.run_forever()
            print("[TokenRegistry] Token event loop ended")
        except Exception as e:
            print(f"[TokenRegistry] Error in token event loop: {e}")
        
    def _run_kb_event_loop(self):
        """Run the event loop in a background thread for KB usage async operations."""
        print("[TokenRegistry] Starting KB event loop in background thread")
        asyncio.set_event_loop(self._kb_thread_loop)
        try:
            self._kb_thread_loop.run_forever()
            print("[TokenRegistry] KB event loop ended")
        except Exception as e:
            print(f"[TokenRegistry] Error in KB event loop: {e}")

    # Add method to get user ID for a flow
    def _get_user_id_for_flow(self, flow_id: str) -> Optional[UUID]:
        """Get the user ID associated with a flow ID"""
        with self._context_lock:
            return self._flow_user_mapping.get(flow_id)
    
    # Add method to set user ID for a flow
    def set_user_for_flow(self, flow_id: str, user_id: UUID):
        """Set the user ID associated with a flow ID"""
        with self._context_lock:
            self._flow_user_mapping[flow_id] = user_id
            print(f"[TokenRegistry] Set user ID {user_id} for flow {flow_id}")

    # === Thread-local context helpers ===
    @staticmethod
    def _get_current_flow_id():
        """Get current flow ID from thread-local storage"""
        return getattr(TokenUsageRegistry._thread_context, 'flow_id', None)
    
    @staticmethod
    def _set_current_flow_id(flow_id):
        """Set current flow ID in thread-local storage"""
        TokenUsageRegistry._thread_context.flow_id = flow_id
    
    @staticmethod
    def _get_current_component_id():
        """Get current component ID from thread-local storage"""
        return getattr(TokenUsageRegistry._thread_context, 'component_id', None)
    
    @staticmethod
    def _set_current_component_id(component_id):
        """Set current component ID in thread-local storage"""
        TokenUsageRegistry._thread_context.component_id = component_id

    def _reset_kb_tracking_impl(self, flow_id):
        """Implementation of reset_kb_tracking with thread safety"""
        # Try to reset in distributed cache first (placeholder for Redis)
        distributed_cache = self._get_distributed_cache()
        if distributed_cache:
            # This would contain Redis logic to delete KB tracking
            # For example:
            # distributed_cache.delete(f"flow:{flow_id}:kb_tools")
            pass
            
        # Still update local cache with proper locking
        with self._kb_tools_lock:
            if flow_id in self._kb_tools_invoked:
                self._kb_tools_invoked[flow_id] = []
            
    def _reset_flow_tracking_impl(self, flow_id):
        """Reset all tracking data for a specific flow with thread safety"""
        # Try to reset in distributed cache first (placeholder for Redis)
        distributed_cache = self._get_distributed_cache()
        if distributed_cache:
            # This would contain Redis logic to delete all flow tracking data
            # For example:
            # distributed_cache.delete(f"flow:{flow_id}:tokens")
            # distributed_cache.delete(f"flow:{flow_id}:models")
            # distributed_cache.delete(f"flow:{flow_id}:kb_tools")
            pass
            
        # Reset token tracking in local cache
        with self._flow_tracking_lock:
            if flow_id in self._flow_tracking:
                print(f"[TokenRegistry] Clearing token tracking for flow: {flow_id}")
                self._flow_tracking.pop(flow_id)
            
        # Reset KB tracking in local cache
        with self._kb_tools_lock:
            if flow_id in self._kb_tools_invoked:
                print(f"[TokenRegistry] Clearing KB tracking for flow: {flow_id}")
                self._kb_tools_invoked.pop(flow_id)
            
        # Clear all related flows (including component-specific ones)
        related_flows = []
        
        with self._flow_tracking_lock:
            related_flows.extend([k for k in self._flow_tracking.keys() 
                                 if k.startswith(flow_id) or (k.startswith("Session") and flow_id.startswith("Session"))])
            
        with self._kb_tools_lock:
            related_flows.extend([k for k in self._kb_tools_invoked.keys() 
                                 if k.startswith(flow_id) or (k.startswith("Session") and flow_id.startswith("Session"))])
        
        # Remove duplicates
        related_flows = list(set(related_flows))
        
        for related_id in related_flows:
            if related_id != flow_id:  # Already cleared above
                with self._flow_tracking_lock:
                    if related_id in self._flow_tracking:
                        self._flow_tracking.pop(related_id)
                        
                with self._kb_tools_lock:
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
        """Implementation of summarize_flow_usage with thread safety"""
        # Try to get from distributed cache first (placeholder for Redis)
        distributed_cache = self._get_distributed_cache()
        if distributed_cache:
            # This would contain Redis logic to get flow usage summary
            # For example:
            # prompt_tokens = int(distributed_cache.hget(f"flow:{flow_id}:tokens", "prompt") or 0)
            # completion_tokens = int(distributed_cache.hget(f"flow:{flow_id}:tokens", "completion") or 0)
            # total_tokens = int(distributed_cache.hget(f"flow:{flow_id}:tokens", "total") or 0)
            # models = distributed_cache.smembers(f"flow:{flow_id}:models")
            # return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, 
            #        "total_tokens": total_tokens, "models": models}
            pass
            
        # Fall back to local cache with proper locking
        with self._flow_tracking_lock:
            return self._flow_tracking.get(flow_id, {})
    
    def _print_flow_summary_impl(self, flow_id):
        """Implementation of print_flow_summary with thread safety"""
        summary = self._summarize_flow_usage_impl(flow_id)
        
        if not summary:
            print(f"No token usage tracked for flow: {flow_id}")
            return
            
        models_str = ", ".join(summary.get("models", []))
        print(f"\n===== TOKEN USAGE SUMMARY FOR FLOW {flow_id} =====")
        print(f"Models used: {models_str}")
        print(f"Prompt tokens: {summary.get('prompt_tokens', 0)}")
        print(f"Completion tokens: {summary.get('completion_tokens', 0)}")
        print(f"Total tokens: {summary.get('total_tokens', 0)}")
        
        # Show KB tool invocations if any
        with self._kb_tools_lock:
            if flow_id in self._kb_tools_invoked and self._kb_tools_invoked[flow_id]:
                kb_tools = ", ".join(self._kb_tools_invoked[flow_id])
                print(f"KB tools accessed: {kb_tools}")
        print("=============================================\n")
