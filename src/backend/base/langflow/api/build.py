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
        if args and isinstance(args[0], str) and args[0].startswith("Invoking: `"):
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
                        # Use TokenUsageRegistry to track KB usage - single source of truth
                        try:
                            from langflow.utils.validate import TokenUsageRegistry
                            registry = TokenUsageRegistry.get_instance()
                            # Set flow context (if not already set)
                            registry.set_flow_context(flow_id=_current_flow_id)
                            # Track KB tool invocation
                            registry.track_kb_tool_invocation(kb_name=kb_base)
                            original_print(f"[KB Interceptor] ✅ Tracked KB usage for {kb_base} with flow_id {_current_flow_id}")
                        except Exception as e:
                            original_print(f"[KB Interceptor] Error tracking KB tool via registry: {e}")
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
        from langflow.utils.validate import TokenUsageRegistry
        
        # Reset all tracking data for this flow before starting a new run
        # This ensures each run has isolated metrics
        TokenUsageRegistry.reset_flow_tracking(_current_flow_id)
        
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
        TokenUsageRegistry.reset_kb_tracking(_current_flow_id)
        
        # Create a usage record in BillingService
        billing_service = service_manager.get(ServiceType.BILLING_SERVICE)
        if billing_service and current_user and current_user.id:
            billing_service.set_user_context(current_user.id)
            session_id = inputs.session if inputs and hasattr(inputs, "session") else _current_flow_id
            usage_record = await billing_service.log_flow_run(
                flow_id=flow_id,
                session_id=session_id,
                user_id=current_user.id
            )
            if usage_record:
                original_print(f"[Billing] Created usage record for flow run: {session_id}")
                
                # IMPORTANT: Establish UUID to Session ID mapping immediately
                # This ensures token usage logging has access to the mapping from the start
                # Add to both BillingService and TokenUsageRegistry
                flow_id_str = str(flow_id)
                
                # 1. Store in BillingService mappings
                if hasattr(billing_service, "_uuid_to_session_mappings"):
                    billing_service._uuid_to_session_mappings[flow_id_str] = session_id
                    original_print(f"[Billing] Established early mapping: {flow_id_str} -> {session_id}")
                    
                    # Also add session prefix mapping for more robust lookups
                    if hasattr(billing_service, "_session_prefix_mappings") and session_id.startswith("Session "):
                        try:
                            day_prefix = session_id.split(",")[0]
                            if day_prefix and len(day_prefix) > 10:  # Reasonable min length for "Session Apr 08"
                                billing_service._session_prefix_mappings[day_prefix] = session_id
                                original_print(f"[Billing] Added early session prefix mapping: {day_prefix} -> {session_id}")
                        except Exception as e_prefix:
                            original_print(f"[Billing] Error adding prefix mapping: {e_prefix}")
                
                # 2. Also sync with TokenUsageRegistry to have consistent mappings
                registry = TokenUsageRegistry.get_instance()
                registry.sync_flow_ids(flow_id_str, session_id)
            else:
                original_print(f"[Billing] WARNING: Failed to create usage record for flow run {session_id}")
                
        # Also reset tracking in the TokenUsageRegistry 
        # TokenUsageRegistry.reset_kb_tracking(_current_flow_id) # This seems redundant or misplaced, commenting out
        
    except Exception as e:
        logger.error(f"Error during billing setup or KB tracking reset: {e}") # Adjusted error message

    
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

        # Finalize cost calculation for this run
        try:
            from langflow.services.manager import service_manager
            from langflow.services.schema import ServiceType
            from langflow.utils.validate import TokenUsageRegistry
            
            credit_service = service_manager.get(ServiceType.CREDIT_SERVICE)
            if credit_service and graph and graph.session_id:
                # Use a consistent run_id for all tracking
                run_id = graph.session_id  # Base run_id
                flow_id_str = str(flow_id)
                print(f"Finalizing costs for run_id: {run_id}")
                
                # Sync tracking between flow_id and session_id if they're different
                if flow_id_str != run_id:
                    print(f"[ID Sync] Flow ID {flow_id_str} differs from session ID {run_id}, synchronizing...")
                    
                    # First sync in TokenUsageRegistry (internal tracking)
                    registry = TokenUsageRegistry.get_instance()
                    registry.sync_flow_ids(flow_id_str, run_id)
                    
                    # Then ensure CreditService has the combined data
                    if flow_id_str in credit_service.pending_usage:
                        # Ensure the session_id has a pending usage entry
                        if run_id not in credit_service.pending_usage:
                            from langflow.services.credit.service import PendingUsage
                            credit_service.pending_usage[run_id] = PendingUsage()
                        
                        # Copy token usage from flow_id to session_id
                        flow_pending = credit_service.pending_usage.get(flow_id_str)
                        if flow_pending:
                            if flow_pending.tokens:
                                credit_service.pending_usage[run_id].tokens.extend(flow_pending.tokens)
                                print(f"[ID Sync] Transferred {len(flow_pending.tokens)} token usage entries")
                                
                            if flow_pending.tools:
                                credit_service.pending_usage[run_id].tools.extend(flow_pending.tools)
                                print(f"[ID Sync] Transferred {len(flow_pending.tools)} tool usage entries")
                                
                            if flow_pending.kbs:
                                credit_service.pending_usage[run_id].kbs.extend(flow_pending.kbs)
                                print(f"[ID Sync] Transferred {len(flow_pending.kbs)} KB usage entries")
                
                # Simply finalize the run cost with the main run_id
                # All token and KB usage should already be in CreditService
                # through the TokenUsageRegistry delegation
                result = await credit_service.finalize_run_cost(run_id=run_id)
                
                # After finalizing, make sure we clean up all tracking data to isolate each run
                # We've already calculated and displayed the costs, so this data isn't needed anymore
                TokenUsageRegistry.reset_flow_tracking(run_id)
                TokenUsageRegistry.reset_flow_tracking(flow_id_str)
                
                # Also clear any session-based tracking that might remain
                if run_id.startswith("Session"):
                    # Find and clear all Session-based tracking for this timestamp
                    session_time = run_id.split(" ")[1]  # Extract the timestamp part
                    for session_id in list(credit_service.pending_usage.keys()):
                        if isinstance(session_id, str) and session_id.startswith("Session") and session_time in session_id:
                            if session_id != run_id:  # Skip the one we just finalized
                                credit_service.pending_usage.pop(session_id, None)
                                print(f"[Final Cleanup] Removed related session tracking: {session_id}")
                
                if not result:
                    print(f"No usage data found for run_id: {run_id}")
                    
                    # Check for partial matches in run_id - needed for backward compatibility
                    if hasattr(credit_service, "pending_usage"):
                        patterns_to_check = [
                            f"{run_id}_",
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
                                        credit_service.pending_usage[run_id].tokens.extend(pending_data.tokens)
                                        print(f"[Merge] Transferred {len(pending_data.tokens)} token usage entries")
                                    
                                    if pending_data.tools:
                                        credit_service.pending_usage[run_id].tools.extend(pending_data.tools)
                                        print(f"[Merge] Transferred {len(pending_data.tools)} tool usage entries")
                                    
                                    if pending_data.kbs:
                                        credit_service.pending_usage[run_id].kbs.extend(pending_data.kbs)
                                        print(f"[Merge] Transferred {len(pending_data.kbs)} KB usage entries")
                                    
                                    # Remove the partial entry
                                    credit_service.pending_usage.pop(partial_id)
                            
                            # Now finalize with the merged data
                            await credit_service.finalize_run_cost(run_id=run_id)
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