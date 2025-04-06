from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser, DbSession, parse_value
from langflow.api.v1.schemas import (
    ConfigResponse,
    CustomComponentRequest,
    CustomComponentResponse,
    InputValueRequest,
    RunResponse,
    SimplifiedAPIRequest,
    TaskStatusResponse,
    UpdateCustomComponentRequest,
    UploadFileResponse,
)
from langflow.custom.custom_component.component import Component
from langflow.custom.utils import build_custom_component_template, get_instance_name, update_component_build_config
from langflow.events.event_manager import create_stream_tokens_event_manager
from langflow.exceptions.api import APIException, InvalidChatInputError
from langflow.exceptions.serialization import SerializationError
from langflow.graph.graph.base import Graph
from langflow.graph.schema import RunOutputs
from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.helpers.user import get_user_by_flow_id_or_endpoint_name
from langflow.interface.initialize.loading import update_params_with_load_from_db_fields
from langflow.processing.process import process_tweaks, run_graph_internal
from langflow.schema.graph import Tweaks
from langflow.services.auth.utils import api_key_security, get_current_active_user
from langflow.services.cache.utils import save_uploaded_file
from langflow.services.database.models.flow import Flow
from langflow.services.database.models.flow.model import FlowRead
from langflow.services.database.models.flow.utils import get_all_webhook_components_in_flow
from langflow.services.database.models.user.model import User, UserRead
from langflow.services.deps import get_session_service, get_settings_service, get_telemetry_service
from langflow.services.settings.feature_flags import FEATURE_FLAGS
from langflow.services.telemetry.schema import RunPayload
from langflow.utils.version import get_version_info
from langflow.utils.validate import TokenUsageRegistry
if TYPE_CHECKING:
    from langflow.services.event_manager import EventManager
    from langflow.services.settings.service import SettingsService

router = APIRouter(tags=["Base"])


@router.get("/all", dependencies=[Depends(get_current_active_user)])
async def get_all():
    from langflow.interface.components import get_and_cache_all_types_dict

    try:
        return await get_and_cache_all_types_dict(settings_service=get_settings_service())

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def validate_input_and_tweaks(input_request: SimplifiedAPIRequest) -> None:
    # If the input_value is not None and the input_type is "chat"
    # then we need to check the tweaks if the ChatInput component is present
    # and if its input_value is not None
    # if so, we raise an error
    if not input_request.tweaks:
        return

    for key, value in input_request.tweaks.items():
        if not isinstance(value, dict):
            continue

        input_value = value.get("input_value")
        if input_value is None:
            continue

        request_has_input = input_request.input_value is not None

        if any(chat_key in key for chat_key in ("ChatInput", "Chat Input")):
            if request_has_input and input_request.input_type == "chat":
                msg = "If you pass an input_value to the chat input, you cannot pass a tweak with the same name."
                raise InvalidChatInputError(msg)

        elif (
            any(text_key in key for text_key in ("TextInput", "Text Input"))
            and request_has_input
            and input_request.input_type == "text"
        ):
            msg = "If you pass an input_value to the text input, you cannot pass a tweak with the same name."
            raise InvalidChatInputError(msg)


# HTTPX Stream interceptor for accurate token tracking
import httpx
import re
import json
from functools import wraps

# Store original method
original_aiter_bytes = httpx.Response.aiter_bytes

# Create patched version that intercepts OpenAI streaming responses
@wraps(original_aiter_bytes)
async def patched_aiter_bytes(self, *args, **kwargs):
    # Call original method to get async generator
    async_generator = original_aiter_bytes(self, *args, **kwargs)
    
    # Check if this is an OpenAI streaming response
    is_openai = False
    request_url = str(self.request.url) if hasattr(self, "request") else ""
    if "api.openai.com" in request_url and "chat/completions" in request_url:
        is_openai = True
        print(f"[HTTPX Intercept] Detected OpenAI streaming API call to {request_url}")
        # Extract model from request body if available
        model = "unknown"
        prompt_tokens = 0
        try:
            if hasattr(self.request, "content") and self.request.content:
                request_body = json.loads(self.request.content.decode("utf-8", errors="ignore"))
                model = request_body.get("model", "unknown")
                # Get the encoding for this model
                import tiktoken
                try:
                    encoding = tiktoken.encoding_for_model(model) if model != "unknown" else tiktoken.get_encoding("cl100k_base")
                    # Track this encoding for later use with output tokens
                    self._tiktoken_encoding = encoding
                    # Count input tokens accurately using tiktoken
                    for message in request_body.get("messages", []):
                        if isinstance(message, dict) and "content" in message:
                            prompt_tokens += len(encoding.encode(message["content"]))
                except Exception as e:
                    print(f"[HTTPX Intercept] Error counting input tokens: {e}")
        except Exception as e:
            print(f"[HTTPX Intercept] Error parsing request body: {e}")
        
        # Start with these values
        completion_tokens = 0
        buffer = b""
        
        # Store encoding for reuse with output tokens
        self._model = model
        try:
            import tiktoken
            self._tiktoken_encoding = tiktoken.encoding_for_model(model) if model != "unknown" else tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            print(f"[HTTPX Intercept] Error creating tiktoken encoding: {e}")
            self._tiktoken_encoding = None
    
    # If not an OpenAI call, just return original generator
    if not is_openai:
        async for chunk in async_generator:
            yield chunk
        return
    
    # For OpenAI calls, intercept chunks and count tokens
    buffer = b""
    
    # Process chunks
    try:
        async for chunk in async_generator:
            # Pass through chunk
            yield chunk
            
            # Add to buffer for processing
            buffer += chunk
            
            # Process any complete lines
            if b"\n\n" in buffer:
                lines = buffer.split(b"\n\n")
                buffer = lines.pop()  # Keep incomplete line
                
                for line in lines:
                    if line.startswith(b"data: "):
                        data_str = line[6:].decode("utf-8", errors="ignore")
                        if data_str.strip() == "[DONE]":
                            continue
                        
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                choice = data["choices"][0]
                                if "delta" in choice and "content" in choice["delta"]:
                                    content = choice["delta"]["content"]
                                    # Count output tokens accurately using tiktoken
                                    if hasattr(self, "_tiktoken_encoding") and self._tiktoken_encoding:
                                        tokens_in_chunk = len(self._tiktoken_encoding.encode(content))
                                        completion_tokens += tokens_in_chunk
                        except Exception as e:
                            print(f"[HTTPX Intercept] Error parsing chunk: {e}")
        
        # Process any remaining data in buffer
        if buffer and buffer.startswith(b"data: "):
            try:
                data_str = buffer[6:].decode("utf-8", errors="ignore")
                if data_str.strip() != "[DONE]":
                    data = json.loads(data_str)
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        if "delta" in choice and "content" in choice["delta"]:
                            content = choice["delta"]["content"]
                            # Count tokens accurately using tiktoken
                            if hasattr(self, "_tiktoken_encoding") and self._tiktoken_encoding:
                                tokens_in_chunk = len(self._tiktoken_encoding.encode(content))
                                completion_tokens += tokens_in_chunk
            except Exception as e:
                print(f"[HTTPX Intercept] Error processing buffer: {e}")
        
        # Log total token usage
        total_tokens = prompt_tokens + completion_tokens
        print(f"\n[HTTPX Stream] Model: {model}")
        print(f"[HTTPX Stream] Input tokens: {prompt_tokens}")
        print(f"[HTTPX Stream] Output tokens: {completion_tokens}")
        print(f"[HTTPX Stream] Total tokens: {total_tokens}\n")
        
        # Record in registry
        try:
            registry = TokenUsageRegistry.get_instance()
            registry.record_usage(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens
            )
        except Exception as e:
            print(f"[HTTPX Stream] Error recording usage: {e}")
            # Print the traceback for debugging
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"[HTTPX Stream] Error intercepting stream: {e}")
        # Ensure we yield remaining chunks if there's an error
        async for chunk in async_generator:
            yield chunk

# Apply patch
httpx.Response.aiter_bytes = patched_aiter_bytes
print("[INFO] Patched HTTPX.Response.aiter_bytes for streaming token tracking")

async def simple_run_flow(
    flow: Flow,
    input_request: SimplifiedAPIRequest,
    *,
    stream: bool = False,
    api_key_user: User | None = None,
    event_manager: EventManager | None = None,
):
    validate_input_and_tweaks(input_request)
    try:
        task_result: list[RunOutputs] = []
        user_id = api_key_user.id if api_key_user else None
        flow_id_str = str(flow.id)
        if flow.data is None:
            msg = f"Flow {flow_id_str} has no data"
            raise ValueError(msg)
        graph_data = flow.data.copy()
        graph_data = process_tweaks(graph_data, input_request.tweaks or {}, stream=stream)
        graph = Graph.from_payload(graph_data, flow_id=flow_id_str, user_id=str(user_id), flow_name=flow.name)
        inputs = None
        if input_request.input_value is not None:
            inputs = [
                InputValueRequest(
                    components=[],
                    input_value=input_request.input_value,
                    type=input_request.input_type,
                )
            ]
        if input_request.output_component:
            outputs = [input_request.output_component]
        else:
            outputs = [
                vertex.id
                for vertex in graph.vertices
                if input_request.output_type == "debug"
                or (
                    vertex.is_output
                    and (input_request.output_type == "any" or input_request.output_type in vertex.id.lower())  # type: ignore[operator]
                )
            ]
        task_result, session_id = await run_graph_internal(
            graph=graph,
            flow_id=flow_id_str,
            session_id=input_request.session_id,
            inputs=inputs,
            outputs=outputs,
            stream=stream,
            event_manager=event_manager,
        )

        return RunResponse(outputs=task_result, session_id=session_id)

    except sa.exc.StatementError as exc:
        raise ValueError(str(exc)) from exc


async def simple_run_flow_task(
    flow: Flow,
    input_request: SimplifiedAPIRequest,
    *,
    stream: bool = False,
    api_key_user: User | None = None,
    event_manager: EventManager | None = None,
):
    """Run a flow task as a BackgroundTask, therefore it should not throw exceptions."""
    try:
        return await simple_run_flow(
            flow=flow,
            input_request=input_request,
            stream=stream,
            api_key_user=api_key_user,
            event_manager=event_manager,
        )

    except Exception:  # noqa: BLE001
        logger.exception(f"Error running flow {flow.id} task")


async def consume_and_yield(queue: asyncio.Queue, client_consumed_queue: asyncio.Queue) -> AsyncGenerator:
    """Consumes events from a queue and yields them to the client while tracking timing metrics.

    This coroutine continuously pulls events from the input queue and yields them to the client.
    It tracks timing metrics for how long events spend in the queue and how long the client takes
    to process them.

    Args:
        queue (asyncio.Queue): The queue containing events to be consumed and yielded
        client_consumed_queue (asyncio.Queue): A queue for tracking when the client has consumed events

    Yields:
        The value from each event in the queue

    Notes:
        - Events are tuples of (event_id, value, put_time)
        - Breaks the loop when receiving a None value, signaling completion
        - Tracks and logs timing metrics for queue time and client processing time
        - Notifies client consumption via client_consumed_queue
    """
    while True:
        event_id, value, put_time = await queue.get()
        if value is None:
            break
        get_time = time.time()
        yield value
        get_time_yield = time.time()
        client_consumed_queue.put_nowait(event_id)
        logger.debug(
            f"consumed event {event_id} "
            f"(time in queue, {get_time - put_time:.4f}, "
            f"client {get_time_yield - get_time:.4f})"
        )


async def run_flow_generator(
    flow: Flow,
    input_request: SimplifiedAPIRequest,
    api_key_user: User | None,
    event_manager: EventManager,
    client_consumed_queue: asyncio.Queue,
) -> None:
    """Executes a flow asynchronously and manages event streaming to the client.

    This coroutine runs a flow with streaming enabled and handles the event lifecycle,
    including success completion and error scenarios.

    Args:
        flow (Flow): The flow to execute
        input_request (SimplifiedAPIRequest): The input parameters for the flow
        api_key_user (User | None): Optional authenticated user running the flow
        event_manager (EventManager): Manages the streaming of events to the client
        client_consumed_queue (asyncio.Queue): Tracks client consumption of events

    Events Generated:
        - "add_message": Sent when new messages are added during flow execution
        - "token": Sent for each token generated during streaming
        - "end": Sent when flow execution completes, includes final result
        - "error": Sent if an error occurs during execution

    Notes:
        - Runs the flow with streaming enabled via simple_run_flow()
        - On success, sends the final result via event_manager.on_end()
        - On error, logs the error and sends it via event_manager.on_error()
        - Always sends a final None event to signal completion
    """
    try:
        result = await simple_run_flow(
            flow=flow,
            input_request=input_request,
            stream=True,
            api_key_user=api_key_user,
            event_manager=event_manager,
        )
        event_manager.on_end(data={"result": result.model_dump()})
        await client_consumed_queue.get()
    except (ValueError, InvalidChatInputError, SerializationError) as e:
        logger.error(f"Error running flow: {e}")
        event_manager.on_error(data={"error": str(e)})
    finally:
        await event_manager.queue.put((None, None, time.time))


@router.post("/run/{flow_id_or_name}", response_model_exclude_none=True)  # noqa: RUF100, FAST003
async def simplified_run_flow(
    *,
    background_tasks: BackgroundTasks,
    flow: Annotated[FlowRead | None, Depends(get_flow_by_id_or_endpoint_name)],
    input_request: SimplifiedAPIRequest | None = None,
    stream: bool = False,
    api_key_user: Annotated[UserRead, Depends(api_key_security)],
):
    """Executes a specified flow by ID with support for streaming and telemetry.

    This endpoint executes a flow identified by ID or name, with options for streaming the response
    and tracking execution metrics. It handles both streaming and non-streaming execution modes.

    Args:
        background_tasks (BackgroundTasks): FastAPI background task manager
        flow (FlowRead | None): The flow to execute, loaded via dependency
        input_request (SimplifiedAPIRequest | None): Input parameters for the flow
        stream (bool): Whether to stream the response
        api_key_user (UserRead): Authenticated user from API key
        request (Request): The incoming HTTP request

    Returns:
        Union[StreamingResponse, RunResponse]: Either a streaming response for real-time results
        or a RunResponse with the complete execution results

    Raises:
        HTTPException: For flow not found (404) or invalid input (400)
        APIException: For internal execution errors (500)

    Notes:
        - Supports both streaming and non-streaming execution modes
        - Tracks execution time and success/failure via telemetry
        - Handles graceful client disconnection in streaming mode
        - Provides detailed error handling with appropriate HTTP status codes
        - In streaming mode, uses EventManager to handle events:
            - "add_message": New messages during execution
            - "token": Individual tokens during streaming
            - "end": Final execution result
    """
    telemetry_service = get_telemetry_service()
    input_request = input_request if input_request is not None else SimplifiedAPIRequest()
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found")
    start_time = time.perf_counter()

    if stream:
        asyncio_queue: asyncio.Queue = asyncio.Queue()
        asyncio_queue_client_consumed: asyncio.Queue = asyncio.Queue()
        event_manager = create_stream_tokens_event_manager(queue=asyncio_queue)
        main_task = asyncio.create_task(
            run_flow_generator(
                flow=flow,
                input_request=input_request,
                api_key_user=api_key_user,
                event_manager=event_manager,
                client_consumed_queue=asyncio_queue_client_consumed,
            )
        )

        async def on_disconnect() -> None:
            logger.debug("Client disconnected, closing tasks")
            main_task.cancel()

        return StreamingResponse(
            consume_and_yield(asyncio_queue, asyncio_queue_client_consumed),
            background=on_disconnect,
            media_type="text/event-stream",
        )

    try:
        result = await simple_run_flow(
            flow=flow,
            input_request=input_request,
            stream=stream,
            api_key_user=api_key_user,
        )
        end_time = time.perf_counter()
        background_tasks.add_task(
            telemetry_service.log_package_run,
            RunPayload(
                run_is_webhook=False,
                run_seconds=int(end_time - start_time),
                run_success=True,
                run_error_message="",
            ),
        )

    except ValueError as exc:
        background_tasks.add_task(
            telemetry_service.log_package_run,
            RunPayload(
                run_is_webhook=False,
                run_seconds=int(time.perf_counter() - start_time),
                run_success=False,
                run_error_message=str(exc),
            ),
        )
        if "badly formed hexadecimal UUID string" in str(exc):
            # This means the Flow ID is not a valid UUID which means it can't find the flow
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if "not found" in str(exc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, exception=exc, flow=flow) from exc
    except InvalidChatInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        background_tasks.add_task(
            telemetry_service.log_package_run,
            RunPayload(
                run_is_webhook=False,
                run_seconds=int(time.perf_counter() - start_time),
                run_success=False,
                run_error_message=str(exc),
            ),
        )
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, exception=exc, flow=flow) from exc

    return result


@router.post("/webhook/{flow_id_or_name}", response_model=dict, status_code=HTTPStatus.ACCEPTED)  # noqa: RUF100, FAST003
async def webhook_run_flow(
    flow: Annotated[Flow, Depends(get_flow_by_id_or_endpoint_name)],
    user: Annotated[User, Depends(get_user_by_flow_id_or_endpoint_name)],
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Run a flow using a webhook request.

    Args:
        flow (Flow, optional): The flow to be executed. Defaults to Depends(get_flow_by_id).
        user (User): The flow user.
        request (Request): The incoming HTTP request.
        background_tasks (BackgroundTasks): The background tasks manager.

    Returns:
        dict: A dictionary containing the status of the task.

    Raises:
        HTTPException: If the flow is not found or if there is an error processing the request.
    """
    telemetry_service = get_telemetry_service()
    start_time = time.perf_counter()
    logger.debug("Received webhook request")
    error_msg = ""
    try:
        try:
            data = await request.body()
        except Exception as exc:
            error_msg = str(exc)
            raise HTTPException(status_code=500, detail=error_msg) from exc

        if not data:
            error_msg = "Request body is empty. You should provide a JSON payload containing the flow ID."
            raise HTTPException(status_code=400, detail=error_msg)

        try:
            # get all webhook components in the flow
            webhook_components = get_all_webhook_components_in_flow(flow.data)
            tweaks = {}

            for component in webhook_components:
                tweaks[component["id"]] = {"data": data.decode() if isinstance(data, bytes) else data}
            input_request = SimplifiedAPIRequest(
                input_value="",
                input_type="chat",
                output_type="chat",
                tweaks=tweaks,
                session_id=None,
            )

            logger.debug("Starting background task")
            background_tasks.add_task(
                simple_run_flow_task,
                flow=flow,
                input_request=input_request,
                api_key_user=user,
            )
        except Exception as exc:
            error_msg = str(exc)
            raise HTTPException(status_code=500, detail=error_msg) from exc
    finally:
        background_tasks.add_task(
            telemetry_service.log_package_run,
            RunPayload(
                run_is_webhook=True,
                run_seconds=int(time.perf_counter() - start_time),
                run_success=not error_msg,
                run_error_message=error_msg,
            ),
        )

    return {"message": "Task started in the background", "status": "in progress"}


@router.post(
    "/run/advanced/{flow_id}",
    response_model=RunResponse,
    response_model_exclude_none=True,
)
async def experimental_run_flow(
    *,
    session: DbSession,
    flow_id: UUID,
    inputs: list[InputValueRequest] | None = None,
    outputs: list[str] | None = None,
    tweaks: Annotated[Tweaks | None, Body(embed=True)] = None,
    stream: Annotated[bool, Body(embed=True)] = False,
    session_id: Annotated[None | str, Body(embed=True)] = None,
    api_key_user: Annotated[UserRead, Depends(api_key_security)],
) -> RunResponse:
    """Executes a specified flow by ID with optional input values, output selection, tweaks, and streaming capability.

    This endpoint supports running flows with caching to enhance performance and efficiency.

    ### Parameters:
    - `flow_id` (str): The unique identifier of the flow to be executed.
    - `inputs` (List[InputValueRequest], optional): A list of inputs specifying the input values and components
      for the flow. Each input can target specific components and provide custom values.
    - `outputs` (List[str], optional): A list of output names to retrieve from the executed flow.
      If not provided, all outputs are returned.
    - `tweaks` (Optional[Tweaks], optional): A dictionary of tweaks to customize the flow execution.
      The tweaks can be used to modify the flow's parameters and components.
      Tweaks can be overridden by the input values.
    - `stream` (bool, optional): Specifies whether the results should be streamed. Defaults to False.
    - `session_id` (Union[None, str], optional): An optional session ID to utilize existing session data for the flow
      execution.
    - `api_key_user` (User): The user associated with the current API key. Automatically resolved from the API key.

    ### Returns:
    A `RunResponse` object containing the selected outputs (or all if not specified) of the executed flow
    and the session ID.
    The structure of the response accommodates multiple inputs, providing a nested list of outputs for each input.

    ### Raises:
    HTTPException: Indicates issues with finding the specified flow, invalid input formats, or internal errors during
    flow execution.

    ### Example usage:
    ```json
    POST /run/{flow_id}
    x-api-key: YOUR_API_KEY
    Payload:
    {
        "inputs": [
            {"components": ["component1"], "input_value": "value1"},
            {"components": ["component3"], "input_value": "value2"}
        ],
        "outputs": ["Component Name", "component_id"],
        "tweaks": {"parameter_name": "value", "Component Name": {"parameter_name": "value"}, "component_id": {"parameter_name": "value"}}
        "stream": false
    }
    ```

    This endpoint facilitates complex flow executions with customized inputs, outputs, and configurations,
    catering to diverse application requirements.
    """  # noqa: E501
    session_service = get_session_service()
    flow_id_str = str(flow_id)
    if outputs is None:
        outputs = []
    if inputs is None:
        inputs = [InputValueRequest(components=[], input_value="")]

    if session_id:
        try:
            session_data = await session_service.load_session(session_id, flow_id=flow_id_str)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
        graph, _artifacts = session_data or (None, None)
        if graph is None:
            msg = f"Session {session_id} not found"
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    else:
        try:
            # Get the flow that matches the flow_id and belongs to the user
            # flow = session.query(Flow).filter(Flow.id == flow_id).filter(Flow.user_id == api_key_user.id).first()
            stmt = select(Flow).where(Flow.id == flow_id_str).where(Flow.user_id == api_key_user.id)
            flow = (await session.exec(stmt)).first()
        except sa.exc.StatementError as exc:
            # StatementError('(builtins.ValueError) badly formed hexadecimal UUID string')
            if "badly formed hexadecimal UUID string" in str(exc):
                logger.error(f"Flow ID {flow_id_str} is not a valid UUID")
                # This means the Flow ID is not a valid UUID which means it can't find the flow
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

        if flow is None:
            msg = f"Flow {flow_id_str} not found"
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)

        if flow.data is None:
            msg = f"Flow {flow_id_str} has no data"
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        try:
            graph_data = flow.data
            graph_data = process_tweaks(graph_data, tweaks or {})
            graph = Graph.from_payload(graph_data, flow_id=flow_id_str)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    try:
        task_result, session_id = await run_graph_internal(
            graph=graph,
            flow_id=flow_id_str,
            session_id=session_id,
            inputs=inputs,
            outputs=outputs,
            stream=stream,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return RunResponse(outputs=task_result, session_id=session_id)


@router.post(
    "/predict/{flow_id}",
    dependencies=[Depends(api_key_security)],
)
@router.post(
    "/process/{flow_id}",
    dependencies=[Depends(api_key_security)],
)
async def process() -> None:
    """Endpoint to process an input with a given flow_id."""
    # Raise a depreciation warning
    logger.warning(
        "The /process endpoint is deprecated and will be removed in a future version. Please use /run instead."
    )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The /process endpoint is deprecated and will be removed in a future version. Please use /run instead.",
    )


@router.get("/task/{_task_id}", deprecated=True)
async def get_task_status(_task_id: str) -> TaskStatusResponse:
    """Get the status of a task by ID (Deprecated).

    This endpoint is deprecated and will be removed in a future version.
    """
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The /task endpoint is deprecated and will be removed in a future version. Please use /run instead.",
    )


@router.post(
    "/upload/{flow_id}",
    status_code=HTTPStatus.CREATED,
    deprecated=True,
)
async def create_upload_file(
    file: UploadFile,
    flow_id: UUID,
) -> UploadFileResponse:
    """Upload a file for a specific flow (Deprecated).

    This endpoint is deprecated and will be removed in a future version.
    """
    try:
        flow_id_str = str(flow_id)
        file_path = await asyncio.to_thread(save_uploaded_file, file, folder_name=flow_id_str)

        return UploadFileResponse(
            flow_id=flow_id_str,
            file_path=file_path,
        )
    except Exception as exc:
        logger.exception("Error saving file")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# get endpoint to return version of langflow
@router.get("/version")
async def get_version():
    return get_version_info()


@router.post("/custom_component", status_code=HTTPStatus.OK)
async def custom_component(
    raw_code: CustomComponentRequest,
    user: CurrentActiveUser,
) -> CustomComponentResponse:
    component = Component(_code=raw_code.code)

    built_frontend_node, component_instance = build_custom_component_template(component, user_id=user.id)
    if raw_code.frontend_node is not None:
        built_frontend_node = await component_instance.update_frontend_node(built_frontend_node, raw_code.frontend_node)

    tool_mode: bool = built_frontend_node.get("tool_mode", False)
    if isinstance(component_instance, Component):
        await component_instance.run_and_validate_update_outputs(
            frontend_node=built_frontend_node,
            field_name="tool_mode",
            field_value=tool_mode,
        )
    type_ = get_instance_name(component_instance)
    return CustomComponentResponse(data=built_frontend_node, type=type_)


@router.post("/custom_component/update", status_code=HTTPStatus.OK)
async def custom_component_update(
    code_request: UpdateCustomComponentRequest,
    user: CurrentActiveUser,
):
    """Update a custom component with the provided code request.

    This endpoint generates the CustomComponentFrontendNode normally but then runs the `update_build_config` method
    on the latest version of the template.
    This ensures that every time it runs, it has the latest version of the template.

    Args:
        code_request (CustomComponentRequest): The code request containing the updated code for the custom component.
        user (User, optional): The user making the request. Defaults to the current active user.

    Returns:
        dict: The updated custom component node.

    Raises:
        HTTPException: If there's an error building or updating the component
        SerializationError: If there's an error serializing the component to JSON
    """
    try:
        component = Component(_code=code_request.code)
        component_node, cc_instance = build_custom_component_template(
            component,
            user_id=user.id,
        )

        component_node["tool_mode"] = code_request.tool_mode

        if hasattr(cc_instance, "set_attributes"):
            template = code_request.get_template()
            params = {}

            for key, value_dict in template.items():
                if isinstance(value_dict, dict):
                    value = value_dict.get("value")
                    input_type = str(value_dict.get("_input_type"))
                    params[key] = parse_value(value, input_type)

            load_from_db_fields = [
                field_name
                for field_name, field_dict in template.items()
                if isinstance(field_dict, dict) and field_dict.get("load_from_db") and field_dict.get("value")
            ]
            params = await update_params_with_load_from_db_fields(cc_instance, params, load_from_db_fields)
            cc_instance.set_attributes(params)
        updated_build_config = code_request.get_template()
        await update_component_build_config(
            cc_instance,
            build_config=updated_build_config,
            field_value=code_request.field_value,
            field_name=code_request.field,
        )
        component_node["template"] = updated_build_config

        if isinstance(cc_instance, Component):
            await cc_instance.run_and_validate_update_outputs(
                frontend_node=component_node,
                field_name=code_request.field,
                field_value=code_request.field_value,
            )

    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return jsonable_encoder(component_node)
    except Exception as exc:
        raise SerializationError.from_exception(exc, data=component_node) from exc


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    try:
        from langflow.services.deps import get_settings_service

        settings_service: SettingsService = get_settings_service()

        return {
            "feature_flags": FEATURE_FLAGS,
            **settings_service.settings.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
