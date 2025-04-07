import asyncio
import json
import time
import traceback
import uuid
import builtins
from collections.abc import AsyncIterator

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from sqlmodel import select

from langflow.api.disconnect import DisconnectHandlerStreamingResponse
from langflow.api.utils import (
    CurrentActiveUser,
    build_graph_from_data,
    build_graph_from_db,
    format_elapsed_time,
    format_exception_message,
    get_top_level_vertices,
    parse_exception,
)
from langflow.api.v1.schemas import (
    FlowDataRequest,
    InputValueRequest,
    ResultDataResponse,
    VertexBuildResponse,
)
from langflow.events.event_manager import EventManager
from langflow.exceptions.component import ComponentBuildError
from langflow.graph.graph.base import Graph
from langflow.graph.utils import log_vertex_build
from langflow.schema.message import ErrorMessage
from langflow.schema.schema import OutputValue
from langflow.services.database.models.flow import Flow
from langflow.services.deps import get_chat_service, get_telemetry_service, session_scope
from langflow.services.job_queue.service import JobQueueService
from langflow.services.telemetry.schema import ComponentPayload, PlaygroundPayload

# Store the original print function
original_print = builtins.print

# Create a set of known KB components (case-insensitive)
KNOWN_KB_COMPONENTS = {"milvus", "chroma", "qdrant", "pinecone", "vectorstore"} 

# Flag to control if interception is active
_interception_active = False
# Current flow ID for KB tracking
_current_flow_id = None

def kb_tracking_print_interceptor(*args, **kwargs):
    """Global print interceptor to detect KB tool invocations."""
    # Call the original print first
    original_print(*args, **kwargs)
    
    # Only process when interception is active
    if _interception_active and _current_flow_id:
        # Check if this is a tool invocation message
        if args and isinstance(args[0], str) and args[0].startswith("Inrvoking: `"):
            try:
                # Format typically: Invoking: `Milvus-search_documents` with `{...}`
                tool_part = args[0].split("`")[1]
                if "-" in tool_part:
                    kb_base = tool_part.split("-")[0].lower()
                    kb_method = tool_part.split("-")[1].lower() if len(tool_part.split("-")) > 1 else ""
                    
                    # Common KB detection patterns
                    kb_components = {"milvus", "chroma", "qdrant", "pinecone", "vectorstore"}
                    kb_operations = ["search", "query", "get", "retrieve", "similarity"]
                    
                    is_kb_tool = False
                    
                    # Check if the base name is a known KB component
                    if kb_base in kb_components:
                        is_kb_tool = True
                    # Check if the method looks like a KB operation
                    elif any(op in kb_method for op in kb_operations) and any(kb in tool_part.lower() for kb in kb_components):
                        is_kb_tool = True
                        
                    if is_kb_tool:
                        # Get the credit service and log KB usage
                        from langflow.services.manager import service_manager
                        from langflow.services.schema import ServiceType
                        from langflow.services.credit.service import KBUsage
                        
                        credit_service = service_manager.get(ServiceType.CREDIT_SERVICE)
                        if credit_service:
                            # Directly log the KB usage with the flow ID
                            kb_usage = KBUsage(kb_name=kb_base, count=1)
                            # Log to both the complete flow ID and base ID if different
                            credit_service.log_kb_usage(run_id=_current_flow_id, kb_usage=kb_usage)
                            original_print(f"[KB Interceptor] ✅ Logged KB usage for {kb_base} with flow_id {_current_flow_id}")
                            
                            # Also try with the OpenAIToolsAgent format if this fails
                            if "-" in _current_flow_id:
                                # Skip
                                pass
                            else:
                                # Look for the agent format in other logs
                                for prefix in ["OpenAIToolsAgent", "Agent"]:
                                    agent_run_id = f"{_current_flow_id}_{prefix}"
                                    credit_service.log_kb_usage(run_id=agent_run_id, kb_usage=kb_usage)
                                    original_print(f"[KB Interceptor] Also logged to potential agent ID: {agent_run_id}")
            except Exception as e:
                original_print(f"[KB Interceptor] Error intercepting KB tool: {e}")

# Only replace the global print if not already replaced
if builtins.print is original_print:
    builtins.print = kb_tracking_print_interceptor

async def start_flow_build(
    *,
    flow_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    inputs: InputValueRequest | None,
    data: FlowDataRequest | None,
    files: list[str] | None,
    stop_component_id: str | None,
    start_component_id: str | None,
    log_builds: bool,
    current_user: CurrentActiveUser,
    queue_service: JobQueueService,
) -> str:
    """Start the flow build process by setting up the queue and starting the build task.

    Returns:
        the job_id.
    """
    job_id = str(uuid.uuid4())
    try:
        _, event_manager = queue_service.create_queue(job_id)
        task_coro = generate_flow_events(
            flow_id=flow_id,
            background_tasks=background_tasks,
            event_manager=event_manager,
            inputs=inputs,
            data=data,
            files=files,
            stop_component_id=stop_component_id,
            start_component_id=start_component_id,
            log_builds=log_builds,
            current_user=current_user,
        )
        queue_service.start_job(job_id, task_coro)
    except Exception as e:
        logger.exception("Failed to create queue and start task")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return job_id


async def get_flow_events_response(
    *,
    job_id: str,
    queue_service: JobQueueService,
    stream: bool = True,
):
    """Get events for a specific build job, either as a stream or single event."""
    try:
        main_queue, event_manager, event_task = queue_service.get_queue_data(job_id)
        if stream:
            if event_task is None:
                raise HTTPException(status_code=404, detail="No event task found for job")
            return await create_flow_response(
                queue=main_queue,
                event_manager=event_manager,
                event_task=event_task,
            )

        # Polling mode - get exactly one event
        _, value, _ = await main_queue.get()
        if value is None:
            # End of stream, trigger end event
            if event_task is not None:
                event_task.cancel()
            event_manager.on_end(data={})

        return JSONResponse({"event": value.decode("utf-8") if value else None})

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def create_flow_response(
    queue: asyncio.Queue,
    event_manager: EventManager,
    event_task: asyncio.Task,
) -> DisconnectHandlerStreamingResponse:
    """Create a streaming response for the flow build process."""

    async def consume_and_yield() -> AsyncIterator[str]:
        while True:
            try:
                event_id, value, put_time = await queue.get()
                if value is None:
                    break
                get_time = time.time()
                yield value.decode("utf-8")
                logger.debug(f"Event {event_id} consumed in {get_time - put_time:.4f}s")
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"Error consuming event: {exc}")
                break

    def on_disconnect() -> None:
        logger.debug("Client disconnected, closing tasks")
        event_task.cancel()
        event_manager.on_end(data={})

    return DisconnectHandlerStreamingResponse(
        consume_and_yield(),
        media_type="application/x-ndjson",
        on_disconnect=on_disconnect,
    )


async def generate_flow_events(
    *,
    flow_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    event_manager: EventManager,
    inputs: InputValueRequest | None,
    data: FlowDataRequest | None,
    files: list[str] | None,
    stop_component_id: str | None,
    start_component_id: str | None,
    log_builds: bool,
    current_user: CurrentActiveUser,
) -> None:
    """Generate events for flow building process.

    This function handles the core flow building logic and generates appropriate events:
    - Building and validating the graph
    - Processing vertices
    - Handling errors and cleanup
    """
    # Activate global tracking
    _interception_active = True
    _current_flow_id = str(flow_id)
    original_print(f"[KB Interceptor] Activated for flow: {_current_flow_id}")
    
    # Reset KB tracking for this flow in CreditService
    try:
        from langflow.services.manager import service_manager
        from langflow.services.schema import ServiceType
        
        credit_service = service_manager.get(ServiceType.CREDIT_SERVICE)
        if credit_service and hasattr(credit_service, "_logged_kbs"):
            # Reset KB tracking for this flow_id to ensure fresh tracking
            if _current_flow_id in credit_service._logged_kbs:
                credit_service._logged_kbs.pop(_current_flow_id)
                original_print(f"[KB Tracking] Reset KB tracking for new flow run: {_current_flow_id}")
                
        # Also reset tracking in the ToolInvocationTracker
        from langflow.callbacks.cost_tracking import ToolInvocationTracker
        ToolInvocationTracker.reset_tracking(_current_flow_id)
        
        # Reset in the TokenUsageRegistry
        from langflow.utils.validate import TokenUsageRegistry
        TokenUsageRegistry.reset_kb_tracking(_current_flow_id)
        
    except Exception as e:
        logger.error(f"Error resetting KB tracking: {e}")

    
    try:
        chat_service = get_chat_service()
        telemetry_service = get_telemetry_service()
        if not inputs:
            inputs = InputValueRequest(session=str(flow_id))

        async def build_graph_and_get_order() -> tuple[list[str], list[str], Graph]:
            start_time = time.perf_counter()
            components_count = 0
            graph = None
            try:
                flow_id_str = str(flow_id)
                # Create a fresh session for database operations
                async with session_scope() as fresh_session:
                    graph = await create_graph(fresh_session, flow_id_str)

                graph.validate_stream()
                first_layer = sort_vertices(graph)

                if inputs is not None and getattr(inputs, "session", None) is not None:
                    graph.session_id = inputs.session

                for vertex_id in first_layer:
                    graph.run_manager.add_to_vertices_being_run(vertex_id)

                # Now vertices is a list of lists
                # We need to get the id of each vertex
                # and return the same structure but only with the ids
                components_count = len(graph.vertices)
                vertices_to_run = list(graph.vertices_to_run.union(get_top_level_vertices(graph, graph.vertices_to_run)))

                await chat_service.set_cache(flow_id_str, graph)
                await log_telemetry(start_time, components_count, success=True)

            except Exception as exc:
                await log_telemetry(start_time, components_count, success=False, error_message=str(exc))

                if "stream or streaming set to True" in str(exc):
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                logger.exception("Error checking build status")
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            return first_layer, vertices_to_run, graph

        async def log_telemetry(
            start_time: float, components_count: int, *, success: bool, error_message: str | None = None
        ):
            background_tasks.add_task(
                telemetry_service.log_package_playground,
                PlaygroundPayload(
                    playground_seconds=int(time.perf_counter() - start_time),
                    playground_component_count=components_count,
                    playground_success=success,
                    playground_error_message=str(error_message) if error_message else "",
                ),
            )

        async def create_graph(fresh_session, flow_id_str: str) -> Graph:
            if not data:
                return await build_graph_from_db(flow_id=flow_id, session=fresh_session, chat_service=chat_service)

            result = await fresh_session.exec(select(Flow.name).where(Flow.id == flow_id))
            flow_name = result.first()

            return await build_graph_from_data(
                flow_id=flow_id_str,
                payload=data.model_dump(),
                user_id=str(current_user.id),
                flow_name=flow_name,
            )

        def sort_vertices(graph: Graph) -> list[str]:
            try:
                return graph.sort_vertices(stop_component_id, start_component_id)
            except Exception:  # noqa: BLE001
                logger.exception("Error sorting vertices")
                return graph.sort_vertices()

        async def _build_vertex(vertex_id: str, graph: Graph, event_manager: EventManager) -> VertexBuildResponse:
            flow_id_str = str(flow_id)
            next_runnable_vertices = []
            top_level_vertices = []
            start_time = time.perf_counter()
            error_message = None
            
            # Set flow context for token tracking
            try:
                from langflow.utils.validate import TokenUsageRegistry
                TokenUsageRegistry.set_flow_context(flow_id=flow_id_str, component_id=vertex_id)
            except Exception as e:
                logger.warning(f"Failed to set token tracking context: {e}")
            
            try:
                vertex = graph.get_vertex(vertex_id)
                try:
                    lock = chat_service.async_cache_locks[flow_id_str]
                    vertex_build_result = await graph.build_vertex(
                        vertex_id=vertex_id,
                        user_id=str(current_user.id),
                        inputs_dict=inputs.model_dump() if inputs else {},
                        files=files,
                        get_cache=chat_service.get_cache,
                        set_cache=chat_service.set_cache,
                        event_manager=event_manager,
                    )
                    result_dict = vertex_build_result.result_dict
                    params = vertex_build_result.params
                    valid = vertex_build_result.valid
                    artifacts = vertex_build_result.artifacts
                    next_runnable_vertices = await graph.get_next_runnable_vertices(lock, vertex=vertex, cache=False)
                    top_level_vertices = graph.get_top_level_vertices(next_runnable_vertices)

                    result_data_response = ResultDataResponse.model_validate(result_dict, from_attributes=True)
                except Exception as exc:  # noqa: BLE001
                    if isinstance(exc, ComponentBuildError):
                        params = exc.message
                        tb = exc.formatted_traceback
                    else:
                        tb = traceback.format_exc()
                        logger.exception("Error building Component")
                        params = format_exception_message(exc)
                    message = {"errorMessage": params, "stackTrace": tb}
                    valid = False
                    error_message = params
                    output_label = vertex.outputs[0]["name"] if vertex.outputs else "output"
                    outputs = {output_label: OutputValue(message=message, type="error")}
                    result_data_response = ResultDataResponse(results={}, outputs=outputs)
                    artifacts = {}
                    background_tasks.add_task(graph.end_all_traces, error=exc)

                result_data_response.message = artifacts

                # Log the vertex build
                if not vertex.will_stream and log_builds:
                    background_tasks.add_task(
                        log_vertex_build,
                        flow_id=flow_id_str,
                        vertex_id=vertex_id,
                        valid=valid,
                        params=params,
                        data=result_data_response,
                        artifacts=artifacts,
                    )
                else:
                    await chat_service.set_cache(flow_id_str, graph)

                timedelta = time.perf_counter() - start_time
                duration = format_elapsed_time(timedelta)
                result_data_response.duration = duration
                result_data_response.timedelta = timedelta
                vertex.add_build_time(timedelta)
                inactivated_vertices = list(graph.inactivated_vertices)
                graph.reset_inactivated_vertices()
                graph.reset_activated_vertices()
                # graph.stop_vertex tells us if the user asked
                # to stop the build of the graph at a certain vertex
                # if it is in next_vertices_ids, we need to remove other
                # vertices from next_vertices_ids
                if graph.stop_vertex and graph.stop_vertex in next_runnable_vertices:
                    next_runnable_vertices = [graph.stop_vertex]

                if not graph.run_manager.vertices_being_run and not next_runnable_vertices:
                    background_tasks.add_task(graph.end_all_traces)

                build_response = VertexBuildResponse(
                    inactivated_vertices=list(set(inactivated_vertices)),
                    next_vertices_ids=list(set(next_runnable_vertices)),
                    top_level_vertices=list(set(top_level_vertices)),
                    valid=valid,
                    params=params,
                    id=vertex.id,
                    data=result_data_response,
                )
                background_tasks.add_task(
                    telemetry_service.log_package_component,
                    ComponentPayload(
                        component_name=vertex_id.split("-")[0],
                        component_seconds=int(time.perf_counter() - start_time),
                        component_success=valid,
                        component_error_message=error_message,
                    ),
                )
            except Exception as exc:
                background_tasks.add_task(
                    telemetry_service.log_package_component,
                    ComponentPayload(
                        component_name=vertex_id.split("-")[0],
                        component_seconds=int(time.perf_counter() - start_time),
                        component_success=False,
                        component_error_message=str(exc),
                    ),
                )
                logger.exception("Error building Component")
                message = parse_exception(exc)
                raise HTTPException(status_code=500, detail=message) from exc

            finally:
                # Clear token tracking context when done
                try:
                    from langflow.utils.validate import TokenUsageRegistry
                    TokenUsageRegistry.clear_flow_context()
                except Exception as e:
                    logger.warning(f"Failed to clear token tracking context: {e}")
            
            return build_response

        async def build_vertices(
            vertex_id: str,
            graph: Graph,
            event_manager: EventManager,
        ) -> None:
            """Build vertices and handle their events.

            Args:
                vertex_id: The ID of the vertex to build
                graph: The graph instance
                event_manager: Manager for handling events
            """
            try:
                vertex_build_response: VertexBuildResponse = await _build_vertex(vertex_id, graph, event_manager)
            except asyncio.CancelledError as exc:
                logger.exception(exc)
                raise

            # send built event or error event
            try:
                vertex_build_response_json = vertex_build_response.model_dump_json()
                build_data = json.loads(vertex_build_response_json)
            except Exception as exc:
                msg = f"Error serializing vertex build response: {exc}"
                raise ValueError(msg) from exc

            event_manager.on_end_vertex(data={"build_data": build_data})

            if vertex_build_response.valid and vertex_build_response.next_vertices_ids:
                tasks = []
                for next_vertex_id in vertex_build_response.next_vertices_ids:
                    task = asyncio.create_task(
                        build_vertices(
                            next_vertex_id,
                            graph,
                            event_manager,
                        )
                    )
                    tasks.append(task)
                await asyncio.gather(*tasks)

        try:
            ids, vertices_to_run, graph = await build_graph_and_get_order()
        except Exception as e:
            error_message = ErrorMessage(
                flow_id=flow_id,
                exception=e,
            )
            event_manager.on_error(data=error_message.data)
            raise

        event_manager.on_vertices_sorted(data={"ids": ids, "to_run": vertices_to_run})

        tasks = []
        for vertex_id in ids:
            task = asyncio.create_task(build_vertices(vertex_id, graph, event_manager))
            tasks.append(task)
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            background_tasks.add_task(graph.end_all_traces)
            raise
        except Exception as e:
            logger.error(f"Error building vertices: {e}")
            custom_component = graph.get_vertex(vertex_id).custom_component
            trace_name = getattr(custom_component, "trace_name", None)
            error_message = ErrorMessage(
                flow_id=flow_id,
                exception=e,
                session_id=graph.session_id,
                trace_name=trace_name,
            )
            event_manager.on_error(data=error_message.data)
            raise
        # Print flow summary after all vertices are processed
        try:
            from langflow.utils.validate import TokenUsageRegistry
            flow_id_str = str(flow_id)
            registry = TokenUsageRegistry.get_instance()
            registry.print_flow_summary(flow_id_str)
        except Exception as e:
            logger.error(f"Error printing flow summary: {e}")

        # Capture token usage from flow summary and ensure it's included in the credit service
        # This is a final safety check in case tokens were tracked in registry but not in credit service
        try:
            from langflow.services.credit.service import TokenUsage
            from langflow.services.manager import service_manager
            from langflow.services.schema import ServiceType
            
            flow_summary = registry.summarize_flow_usage(flow_id_str)
            if flow_summary and flow_summary.get("total_tokens", 0) > 0:
                credit_service = service_manager.get(ServiceType.CREDIT_SERVICE)
                if credit_service:
                    # Check if token usage was already recorded
                    already_recorded = False
                    if flow_id_str in credit_service.pending_usage:
                        already_recorded = len(credit_service.pending_usage[flow_id_str].tokens) > 0
                    elif flow_id_str in credit_service.finalized_costs:
                        already_recorded = len(credit_service.finalized_costs[flow_id_str].token_usages) > 0
                        
                    # If not already recorded, add it
                    if not already_recorded and flow_summary["models"]:
                        model_name = next(iter(flow_summary["models"]))
                        token_usage = TokenUsage(
                            model_name=model_name,
                            input_tokens=flow_summary["prompt_tokens"],
                            output_tokens=flow_summary["completion_tokens"]
                        )
                        # Log directly to credit service
                        credit_service.log_token_usage(run_id=flow_id_str, token_usage=token_usage)
                        print(f"[Final Token Check] Added missing token usage: {flow_summary['prompt_tokens']} input, {flow_summary['completion_tokens']} output tokens")
        except Exception as e:
            logger.error(f"Error capturing token usage from flow summary: {e}")

        # Finalize cost calculation for this run
        try:
            from langflow.services.manager import service_manager
            from langflow.services.schema import ServiceType
            from langflow.utils.validate import TokenUsageRegistry
            
            credit_service = service_manager.get(ServiceType.CREDIT_SERVICE)
            if credit_service and graph and graph.session_id:
                run_id = graph.session_id # Base run_id
                print(f"Finalizing costs for run_id: {run_id}")
                
                # Check for any pending KB tool invocations in the registry
                registry = TokenUsageRegistry.get_instance()
                if hasattr(registry, "_kb_tools_invoked") and run_id in registry._kb_tools_invoked:
                    kb_tools = registry._kb_tools_invoked[run_id]
                    if kb_tools:
                        from langflow.services.credit.service import KBUsage
                        print(f"[Final KB Check] Found {len(kb_tools)} KB tool invocations to log: {kb_tools}")
                        for kb_name in kb_tools:
                            kb_usage = KBUsage(kb_name=kb_name, count=1)
                            credit_service.log_kb_usage(run_id=run_id, kb_usage=kb_usage)
                            print(f"[Final KB Check] Logged final KB usage for {kb_name}")
                        # Clear the tracked invocations
                        registry._kb_tools_invoked[run_id] = []
                
                # ALSO check the tool invocation tracker
                try:
                    from langflow.callbacks.cost_tracking import ToolInvocationTracker
                    
                    if hasattr(ToolInvocationTracker, "_kb_invocations"):
                        if run_id in ToolInvocationTracker._kb_invocations:
                            kb_tools = ToolInvocationTracker._kb_invocations[run_id]
                            if kb_tools:
                                from langflow.services.credit.service import KBUsage
                                print(f"[Final KB Check] Found {len(kb_tools)} KB tool invocations in ToolTracker: {kb_tools}")
                                for kb_name in kb_tools:
                                    kb_usage = KBUsage(kb_name=kb_name, count=1)
                                    credit_service.log_kb_usage(run_id=run_id, kb_usage=kb_usage)
                                    print(f"[Final KB Check] Logged final KB usage from ToolTracker for {kb_name}")
                                # Clear the tracked invocations
                                ToolInvocationTracker._kb_invocations[run_id] = []
                except Exception as e:
                    print(f"[Final KB Check] Error checking ToolTracker: {e}")
                
                # First try with the simple run_id
                result = credit_service.finalize_run_cost(run_id=run_id)
                
                # If no data found, look for any pending usage with this run_id as a prefix
                if not result and hasattr(credit_service, "pending_usage"):
                    # Check for token usage in the registry that might not have been captured
                    registry = TokenUsageRegistry.get_instance()
                    if hasattr(registry, "_flow_tracking") and run_id in registry._flow_tracking:
                        flow_usage = registry._flow_tracking[run_id]
                        # If we have token usage in the registry but not in credit service, log it
                        print(f"[Token Check] Found token usage in registry for {run_id}: {flow_usage['prompt_tokens']} input, {flow_usage['completion_tokens']} output tokens")
                        
                        # Check if any token usage exists for this run_id in credit service
                        has_token_usage = False
                        for pending_id in credit_service.pending_usage:
                            if pending_id == run_id or pending_id.startswith(f"{run_id}_"):
                                if credit_service.pending_usage[pending_id].tokens:
                                    has_token_usage = True
                                    break
                        
                        # Only log if no token usage exists yet
                        if not has_token_usage and flow_usage["models"]:
                            model_name = next(iter(flow_usage["models"]))
                            from langflow.services.credit.service import TokenUsage
                            # Log the token usage directly from our registry
                            token_usage = TokenUsage(
                                model_name=model_name,
                                input_tokens=flow_usage["prompt_tokens"],
                                output_tokens=flow_usage["completion_tokens"]
                            )
                            credit_service.log_token_usage(run_id=run_id, token_usage=token_usage)
                            print(f"[Token Check] Logged token usage from registry to credit service for {run_id}")
                    
                    # Check for various run_id patterns
                    patterns_to_check = [
                        # 1. Base flow ID with components
                        f"{run_id}_",
                        # 2. Common agent patterns
                        f"{run_id}_OpenAIToolsAgent", 
                        f"{run_id}_Agent",
                    ]
                    
                    all_partial_matches = []
                    for pattern in patterns_to_check:
                        partial_matches = [
                            pending_id for pending_id in credit_service.pending_usage.keys() 
                            if pattern in pending_id
                        ]
                        all_partial_matches.extend(partial_matches)
                    
                    if all_partial_matches:
                        print(f"Found {len(all_partial_matches)} partial run_id matches. Transferring to primary run_id.")
                        print(f"Matched run_ids: {all_partial_matches}")
                        
                        # Get or create tracking set for merged KBs
                        if not hasattr(credit_service, "_logged_kbs"):
                            credit_service._logged_kbs = {}
                        if run_id not in credit_service._logged_kbs:
                            credit_service._logged_kbs[run_id] = set()
                            
                        # Track which KBs have been merged to prevent double-counting
                        merged_kbs = set()
                        
                        # Consolidate usage data from partial matches to the main run_id
                        for partial_id in all_partial_matches:
                            if partial_id in credit_service.pending_usage:
                                pending_data = credit_service.pending_usage[partial_id]
                                
                                # Create or get the main pending usage entry
                                if run_id not in credit_service.pending_usage:
                                    from langflow.services.credit.service import PendingUsage
                                    credit_service.pending_usage[run_id] = PendingUsage()
                                
                                # Transfer the data
                                if pending_data.tokens:
                                    original_token_count = len(credit_service.pending_usage[run_id].tokens)
                                    credit_service.pending_usage[run_id].tokens.extend(pending_data.tokens)
                                    print(f"[Merge] Transferred {len(pending_data.tokens)} token usage entries from {partial_id}")
                                    print(f"[Merge] Total token entries for {run_id}: {len(credit_service.pending_usage[run_id].tokens)} (was {original_token_count})")
                                
                                if pending_data.tools:
                                    credit_service.pending_usage[run_id].tools.extend(pending_data.tools)
                                    print(f"[Merge] Transferred {len(pending_data.tools)} tool usage entries from {partial_id}")
                                
                                # Transfer KB data without duplicates
                                for kb_usage in pending_data.kbs:
                                    if kb_usage.kb_name not in merged_kbs:
                                        credit_service.pending_usage[run_id].kbs.append(kb_usage)
                                        merged_kbs.add(kb_usage.kb_name)
                                        print(f"[Merge] Added KB {kb_usage.kb_name} from {partial_id}")
                                    else:
                                        print(f"[Merge] Skipped duplicate KB {kb_usage.kb_name} from {partial_id}")
                                
                                # Remove the partial entry
                                credit_service.pending_usage.pop(partial_id)
                        
                        # Now finalize with the merged data
                        credit_service.finalize_run_cost(run_id=run_id)
            elif not credit_service:
                print("CreditService not available, skipping cost finalization.")
            elif not graph or not graph.session_id:
                 print("Graph or session_id not available, cannot determine run_id for cost finalization.")

        except Exception as e:
            logger.error(f"Error finalizing run cost: {e}")
        event_manager.on_end(data={})
        await event_manager.queue.put((None, None, time.time()))

    finally:
        # Deactivate KB tracking when done
        _interception_active = False
        _current_flow_id = None
        original_print("[KB Interceptor] Deactivated")