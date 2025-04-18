import asyncio
import json
import os
import re
import warnings
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator
from urllib.parse import urlencode

import anyio
import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_pagination import add_pagination
from loguru import logger
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import PydanticDeprecatedSince20
from pydantic_core import PydanticSerializationError
from rich import print as rprint
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from langflow.api import health_check_router, log_router, router, router_v2
from langflow.initial_setup.setup import (
    create_or_update_starter_projects,
    initialize_super_user_if_needed,
    load_bundles_from_urls,
    load_flows_from_directory,
)
from langflow.interface.components import get_and_cache_all_types_dict
from langflow.interface.utils import setup_llm_caching
from langflow.logging.logger import configure
from langflow.middleware import ContentSizeLimitMiddleware
from langflow.services.deps import get_queue_service, get_settings_service, get_telemetry_service, get_db_service, get_session, session_scope
from langflow.services.email.service import get_email_service
from langflow.services.utils import initialize_services, teardown_services
from langflow.services.manager import service_manager
from langflow.services.schema import ServiceType

if TYPE_CHECKING:
    from tempfile import TemporaryDirectory

# Ignore Pydantic deprecation warnings from Langchain
warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)

_tasks: list[asyncio.Task] = []

MAX_PORT = 65535


class RequestCancelledMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        sentinel = object()

        async def cancel_handler():
            while True:
                if await request.is_disconnected():
                    return sentinel
                await asyncio.sleep(0.1)

        handler_task = asyncio.create_task(call_next(request))
        cancel_task = asyncio.create_task(cancel_handler())

        done, pending = await asyncio.wait([handler_task, cancel_task], return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()

        if cancel_task in done:
            return Response("Request was cancelled", status_code=499)
        return await handler_task


class JavaScriptMIMETypeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            response = await call_next(request)
        except Exception as exc:
            if isinstance(exc, PydanticSerializationError):
                message = (
                    "Something went wrong while serializing the response. "
                    "Please share this error on our GitHub repository."
                )
                error_messages = json.dumps([message, str(exc)])
                raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=error_messages) from exc
            raise
        if (
            "files/" not in request.url.path
            and request.url.path.endswith(".js")
            and response.status_code == HTTPStatus.OK
        ):
            response.headers["Content-Type"] = "text/javascript"
        return response


async def load_bundles_with_error_handling():
    try:
        return await load_bundles_from_urls()
    except (httpx.TimeoutException, httpx.HTTPError, httpx.RequestError) as exc:
        logger.error(f"Error loading bundles from URLs: {exc}")
        return [], []


def get_lifespan(*, fix_migration=False, version=None):
    telemetry_service = get_telemetry_service()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        configure(async_file=True)

        # Startup message
        if version:
            rprint(f"[bold green]Starting Langflow v{version}...[/bold green]")
        else:
            rprint("[bold green]Starting Langflow...[/bold green]")

        temp_dirs: list[TemporaryDirectory] = []
        try:
            await initialize_services(fix_migration=fix_migration)
            
            # Initialize rate limiter
            from langflow.services.limiter.service import init_limiter
            await init_limiter()
            
            # Start billing cycle manager
            try:
                from langflow.services.billing.cycle_manager import get_billing_cycle_manager
                billing_cycle_manager = get_billing_cycle_manager()
                await billing_cycle_manager.start()
                logger.info("Started billing cycle manager")
            except Exception as exc:
                logger.error(f"Failed to start billing cycle manager: {exc}")
            
            setup_llm_caching()
            await initialize_super_user_if_needed()
            temp_dirs, bundles_components_paths = await load_bundles_with_error_handling()
            get_settings_service().settings.components_path.extend(bundles_components_paths)
            all_types_dict = await get_and_cache_all_types_dict(get_settings_service())
            await create_or_update_starter_projects(all_types_dict)
                
            telemetry_service.start()
            await load_flows_from_directory()
            
            # Create default subscription plans - moved here to ensure database is fully initialized
            try:
                from langflow.services.database.models.billing.utils import create_default_subscription_plans
                from asyncio import sleep
                from sqlmodel import text
                from langflow.services.deps import session_scope
                
                # Use a retry mechanism with exponential backoff
                max_retries = 3
                retry_delay = 1.0  # Start with 1 second delay
                last_exception = None
                
                for attempt in range(max_retries):
                    try:
                        async with session_scope() as session:
                            # First check if the table exists
                            try:
                                # Check if table exists
                                result = await session.exec(text("SELECT name FROM sqlite_master WHERE type='table' AND name='subscriptionplan'"))
                                table_exists = result.first() is not None
                                if not table_exists:
                                    logger.warning("subscriptionplan table doesn't exist yet, waiting...")
                                    if attempt < max_retries - 1:
                                        await sleep(retry_delay)
                                        retry_delay *= 2
                                        continue
                                    else:
                                        logger.error("subscriptionplan table not created after max retries")
                                        break
                            except Exception as table_check_exc:
                                logger.warning(f"Error checking for subscriptionplan table: {table_check_exc}")
                                # Continue anyway, the create_default_subscription_plans might handle it
                            
                            # Table exists or we couldn't check, try to create/update plans
                            plans = await create_default_subscription_plans(session)
                            logger.info(f"Created/updated {len(plans)} subscription plans")
                            break  # Success, exit the retry loop
                    except Exception as retry_exc:
                        last_exception = retry_exc
                        logger.warning(f"Attempt {attempt+1}/{max_retries} to create subscription plans failed: {retry_exc}")
                        if attempt < max_retries - 1:  # Don't sleep on the last attempt
                            await sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                else:  # This runs if no break occurred in the for loop
                    if last_exception:
                        logger.error(f"Failed to create default subscription plans after {max_retries} attempts: {last_exception}")
            except Exception as exc:
                logger.error(f"Failed to create default subscription plans: {exc}")
                
            # Load Stripe product IDs from environment variables
            try:
                from langflow.services.billing.utils import load_stripe_product_ids_from_env
                
                async with session_scope() as session:
                    result = await load_stripe_product_ids_from_env(session)
                    if result["updated"] > 0:
                        logger.info(f"Updated {result['updated']} subscription plans with Stripe IDs from environment variables")
            except Exception as exc:
                logger.error(f"Failed to load Stripe product IDs from environment variables: {exc}")
            
            queue_service = get_queue_service()
            if not queue_service.is_started():  # Start if not already started
                queue_service.start()
            await initialize_email_service()
            yield

        except Exception as exc:
            if "langflow migration --fix" not in str(exc):
                logger.exception(exc)
            raise
        finally:
            # Clean shutdown
            logger.info("Cleaning up resources...")
            
            # Stop billing cycle manager
            try:
                from langflow.services.billing.cycle_manager import get_billing_cycle_manager
                billing_cycle_manager = get_billing_cycle_manager()
                await billing_cycle_manager.stop()
                logger.info("Stopped billing cycle manager")
            except Exception as exc:
                logger.error(f"Failed to stop billing cycle manager: {exc}")
                
            await teardown_services()
            await logger.complete()
            temp_dir_cleanups = [asyncio.to_thread(temp_dir.cleanup) for temp_dir in temp_dirs]
            await asyncio.gather(*temp_dir_cleanups)
            # Final message
            rprint("[bold red]Langflow shutdown complete[/bold red]")

    return lifespan


def create_app():
    """Create the FastAPI app and include the router."""
    from langflow.utils.version import get_version_info

    __version__ = get_version_info()["version"]

    configure()
    lifespan = get_lifespan(version=__version__)
    app = FastAPI(lifespan=lifespan, title="Langflow", version=__version__)
    app.add_middleware(
        ContentSizeLimitMiddleware,
    )

    setup_sentry(app)
    origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(JavaScriptMIMETypeMiddleware)

    @app.middleware("http")
    async def check_boundary(request: Request, call_next):
        if "/api/v1/files/upload" in request.url.path:
            content_type = request.headers.get("Content-Type")

            if not content_type or "multipart/form-data" not in content_type or "boundary=" not in content_type:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={"detail": "Content-Type header must be 'multipart/form-data' with a boundary parameter."},
                )

            boundary = content_type.split("boundary=")[-1].strip()

            if not re.match(r"^[\w\-]{1,70}$", boundary):
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={"detail": "Invalid boundary format"},
                )

            body = await request.body()

            boundary_start = f"--{boundary}".encode()
            # The multipart/form-data spec doesn't require a newline after the boundary, however many clients do
            # implement it that way
            boundary_end = f"--{boundary}--\r\n".encode()
            boundary_end_no_newline = f"--{boundary}--".encode()

            if not body.startswith(boundary_start) or not body.endswith((boundary_end, boundary_end_no_newline)):
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={"detail": "Invalid multipart formatting"},
                )

        return await call_next(request)

    @app.middleware("http")
    async def flatten_query_string_lists(request: Request, call_next):
        flattened: list[tuple[str, str]] = []
        for key, value in request.query_params.multi_items():
            flattened.extend((key, entry) for entry in value.split(","))

        request.scope["query_string"] = urlencode(flattened, doseq=True).encode("utf-8")

        return await call_next(request)

    settings = get_settings_service().settings
    if prome_port_str := os.environ.get("LANGFLOW_PROMETHEUS_PORT"):
        # set here for create_app() entry point
        prome_port = int(prome_port_str)
        if prome_port > 0 or prome_port < MAX_PORT:
            rprint(f"[bold green]Starting Prometheus server on port {prome_port}...[/bold green]")
            settings.prometheus_enabled = True
            settings.prometheus_port = prome_port
        else:
            msg = f"Invalid port number {prome_port_str}"
            raise ValueError(msg)

    if settings.prometheus_enabled:
        from prometheus_client import start_http_server

        start_http_server(settings.prometheus_port)

    if settings.mcp_server_enabled:
        from langflow.api.v1 import mcp_router

        router.include_router(mcp_router)

    app.include_router(router)
    app.include_router(router_v2)
    app.include_router(health_check_router)
    app.include_router(log_router)

    @app.exception_handler(Exception)
    async def exception_handler(_request: Request, exc: Exception):
        if isinstance(exc, HTTPException):
            logger.error(f"HTTPException: {exc}", exc_info=exc)
            return JSONResponse(
                status_code=exc.status_code,
                content={"message": str(exc.detail)},
            )
        logger.error(f"unhandled error: {exc}", exc_info=exc)
        return JSONResponse(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            content={"message": str(exc)},
        )

    FastAPIInstrumentor.instrument_app(app)

    add_pagination(app)
    return app


def setup_sentry(app: FastAPI) -> None:
    settings = get_settings_service().settings
    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            profiles_sample_rate=settings.sentry_profiles_sample_rate,
        )
        app.add_middleware(SentryAsgiMiddleware)


def setup_static_files(app: FastAPI, static_files_dir: Path) -> None:
    """Setup the static files directory.

    Args:
        app (FastAPI): FastAPI app.
        static_files_dir (str): Path to the static files directory.
    """
    app.mount(
        "/",
        StaticFiles(directory=static_files_dir, html=True),
        name="static",
    )

    @app.exception_handler(404)
    async def custom_404_handler(_request, _exc):
        path = anyio.Path(static_files_dir) / "index.html"

        if not await path.exists():
            msg = f"File at path {path} does not exist."
            raise RuntimeError(msg)
        return FileResponse(path)


def get_static_files_dir():
    """Get the static files directory relative to Langflow's main.py file."""
    frontend_path = Path(__file__).parent
    return frontend_path / "frontend"


def setup_app(static_files_dir: Path | None = None, *, backend_only: bool = False) -> FastAPI:
    """Setup the FastAPI app."""
    # get the directory of the current file
    logger.info(f"Setting up app with static files directory {static_files_dir}")
    if not static_files_dir:
        static_files_dir = get_static_files_dir()

    if not backend_only and (not static_files_dir or not static_files_dir.exists()):
        msg = f"Static files directory {static_files_dir} does not exist."
        raise RuntimeError(msg)
    app = create_app()
    if not backend_only and static_files_dir is not None:
        setup_static_files(app, static_files_dir)
    return app


async def initialize_email_service():
    try:
        email_service = get_email_service()
        logger.info("Email service initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing email service: {e}")


if __name__ == "__main__":
    import uvicorn

    from langflow.__main__ import get_number_of_workers

    configure()
    uvicorn.run(
        "langflow.main:create_app",
        host="127.0.0.1",
        port=7860,
        workers=get_number_of_workers(),
        log_level="error",
        reload=True,
        loop="asyncio",
    )
