from __future__ import annotations

import os
import base64
from email.mime.text import MIMEText
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow as GoogleFlow
from googleapiclient.discovery import build
from fastapi.security import OAuth2PasswordBearer

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from fastapi import APIRouter, HTTPException, Depends

import asyncio
import base64
import os
import time
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Dict, List, Optional
from uuid import UUID, uuid4
from sqlalchemy import select

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

from langflow.api.v1.schemas import (
    SimplifiedAPIRequest,
)
from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.helpers.user import get_user_by_flow_id_or_endpoint_name
from langflow.services.auth.utils import get_current_active_user, oauth2_login, get_current_user_by_jwt
from langflow.services.database.models.flow import Flow
from langflow.services.database.models.user.model import User
from langflow.services.database.models.integration_token.model import IntegrationToken
from langflow.services.deps import get_session_service, get_telemetry_service
from langflow.services.telemetry.schema import RunPayload
from dotenv import load_dotenv

from langflow.services.database.models.user.crud import create_integration_token, get_integration_tokens, delete_integration_token, get_integration_token_by_id, update_integration_token, create_integration_trigger, update_slack_token
from langflow.services.database.models.integration_trigger.crud import get_integration_triggers_by_integration
from langflow.services.database.models.integration_token.crud import get_integration_by_email_address
from langflow.services.database.models.email_thread.crud import (
    create_email_thread,
    get_email_thread,
    update_email_thread,
)
from datetime import datetime, timezone
from sqlmodel.ext.asyncio.session import AsyncSession
from langflow.services.deps import get_session
import base64
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from langflow.services.database.models.processed_email.crud import (
    create_processed_email,
    get_processed_email,
)
from langflow.helpers.user import get_user_by_flow_id_or_endpoint_name
from fastapi.concurrency import run_in_threadpool
from redis import asyncio as aioredis
from contextlib import asynccontextmanager
import json
from langflow.api.v1.endpoints import simple_run_flow
from google.auth import jwt
from google.auth.transport import requests as google_requests
import traceback

redis = aioredis.from_url("redis://localhost:6379")

if TYPE_CHECKING:
    from langflow.services.settings.service import SettingsService

async_engine = create_async_engine(
    "sqlite+aiosqlite:///database.db",
    echo=False,
    future=True
)

load_dotenv()

OLLAMA_API_URL = os.getenv('OLLAMA_API_URL')
MILVUS_HOST = os.getenv('MILVUS_HOST')
MILVUS_PORT = os.getenv('MILVUS_PORT')
MILVUS_USER = os.getenv('MILVUS_USER')
MILVUS_PASSWORD = os.getenv('MILVUS_PASSWORD')
MILVUS_DATABASE = os.getenv('MILVUS_DATABASE')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_FILE = os.path.join(BASE_DIR, "../../../../../../config/client_secret.json")
PUBSUB_TOPIC_NAME = "projects/langflow-449814/topics/gmail-notifications"

# Include the send scope if needed.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.file"
]
REDIRECT_URI = "http://localhost:3000/api/v1/auth/callback"

# Token storage (for demonstration only - use a secure storage method in production)
TOKEN_STORAGE_PATH = os.path.join(BASE_DIR, "token.pkl")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
router = APIRouter(tags=["Gmail"])

# Slack API configuration
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")
SLACK_SCOPES = [
    "channels:history", 
    "channels:read",
    "chat:write", 
    "im:history",
    "im:read",
    "im:write",
    "users:read",
    "users.profile:read"
]

async def get_gmail_profile(email_service):
    profile = email_service.users().getProfile(userId="me").execute()
    print("profile email", profile.get("emailAddress"))
    return profile.get("emailAddress")

@router.get("/auth/login")
async def login(
    current_user: User = Depends(oauth2_login),
    db: AsyncSession = Depends(get_session)
):
    flow = GoogleFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    flow.redirect_uri = REDIRECT_URI
    auth_url, state = flow.authorization_url(
        access_type="offline", 
        include_granted_scopes="true"
    )
    return RedirectResponse(auth_url)

@router.get("/auth/callback")
async def callback(
    state: str, 
    code: str,
    access_token: str = Cookie(None, alias="access_token_lf"),
    db: AsyncSession = Depends(get_session)
):
    try:
        if not access_token:
            raise HTTPException(status_code=401, detail="No access token provided")
        
        current_user = await get_current_user_by_jwt(access_token, db)
        
        flow = GoogleFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES, state=state)
        flow.redirect_uri = REDIRECT_URI
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        expires_at = None
        if credentials.expiry:
            expires_at = credentials.expiry.replace(tzinfo=timezone.utc)
        
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        gmail_email = await get_gmail_profile(service)  # This should return the watched account's email address
        print("gmail_email", gmail_email, "expires_at", expires_at)

        await create_integration_token(
            db=db,
            user_id=current_user.id,
            service_name="gmail",
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_uri=credentials.token_uri,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            expires_at=expires_at,
            email_address=gmail_email
        )

        html_content = """
        <html>
            <script type="text/javascript">
                window.opener.postMessage({ gmailConnected: true }, "*");
                window.close();
            </script>
            <body>Authentication complete. Closing window...</body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")

@router.get("/emails")
async def get_emails(
    maxResults: int = Query(5, description="Maximum number of emails to fetch"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    try:
        tokens = await get_integration_tokens(db, current_user.id)
        gmail_token = next((token for token in tokens if token.service_name == "gmail"), None)
        
        if not gmail_token:
            raise HTTPException(status_code=401, detail="Gmail not connected")

        credentials = Credentials(
            token=gmail_token.access_token,
            refresh_token=gmail_token.refresh_token,
            token_uri=gmail_token.token_uri,
            client_id=gmail_token.client_id,
            client_secret=gmail_token.client_secret,
            scopes=SCOPES
        )

        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        results = service.users().messages().list(
            userId="me", maxResults=maxResults, labelIds=["CATEGORY_PERSONAL"]
        ).execute()

        messages = results.get("messages", [])
        emails = []

        for msg in messages:
            msg_data = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
            snippet = msg_data.get("snippet", "")
            headers = msg_data.get("payload", {}).get("headers", [])
            subject = next((header["value"] for header in headers if header["name"].lower() == "subject"), "")
            sender = next((header["value"] for header in headers if header["name"].lower() == "from"), "")
            date = next((header["value"] for header in headers if header["name"].lower() == "date"), "")

            emails.append({
                "snippet": snippet,
                "subject": subject,
                "sender": sender,
                "date": date
            })
            
        return {"emails": emails}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching emails: {str(e)}")

@router.post("/send_email")
async def send_email(
    recipient: str = Body(..., embed=True, description="The recipient's email address"),
    subject: str = Body(..., embed=True, description="Subject of the email"),
    body_text: str = Body(..., embed=True, description="Body content of the email"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Send an email using Gmail API.
    """
    try:
        tokens = await get_integration_tokens(db, current_user.id)
        gmail_token = next((token for token in tokens if token.service_name == "gmail"), None)
        
        if not gmail_token:
            raise HTTPException(status_code=401, detail="Gmail not connected")

        credentials = Credentials(
            token=gmail_token.access_token,
            refresh_token=gmail_token.refresh_token,
            token_uri=gmail_token.token_uri,
            client_id=gmail_token.client_id,
            client_secret=gmail_token.client_secret,
            scopes=SCOPES
        )

        # Create a MIMEText email message
        message = MIMEText(body_text)
        message["to"] = recipient
        message["subject"] = subject
        
        # Encode the message to base64 URL-safe string
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        sent_message = service.users().messages().send(
            userId="me", 
            body={"raw": encoded_message}
        ).execute()
        
        return {"status": "success", "message_id": sent_message.get("id")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending email: {str(e)}")


 # e.g., { "user1": { "gmail": credentials } }

def get_current_user(token: str = Depends(oauth2_scheme)):
    # Decode your JWT or session token to retrieve the user ID.
    # For simplicity, assume the token is the user_id.
    user_id = token  
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user")
    return user_id

@router.get("/integration/status")
async def integration_status(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Returns detailed integration status information for the current user.
    """
    try:
        tokens = await get_integration_tokens(db, current_user.id)
        integrations_info = []
        
        for token in tokens:
            # Build integration details
            integration_details = {
                "id": token.id,
                "service_name": token.service_name,
                "connected": True,
                "created_at": token.created_at.isoformat(),
                "updated_at": token.updated_at.isoformat(),
                "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                "permissions": [],  # Will be populated based on service
                "email": None  # Will be populated for supported services
            }

            # Add service-specific details
            if token.service_name == "gmail":
                try:
                    credentials = Credentials(
                        token=token.access_token,
                        refresh_token=token.refresh_token,
                        token_uri=token.token_uri,
                        client_id=token.client_id,
                        client_secret=token.client_secret,
                        scopes=SCOPES
                    )
                    
                    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
                    profile = service.users().getProfile(userId="me").execute()
                    
                    integration_details.update({
                        "email": profile.get("emailAddress"),
                        "permissions": [
                            "read_emails",
                            "send_emails",
                            "create_drafts"
                        ],
                        "status": "active" if credentials.valid else "expired"
                    })
                except Exception as e:
                    integration_details.update({
                        "status": "error",
                        "error_message": str(e)
                    })
            elif token.service_name == "slack":
                # Add Slack-specific details
                try:
                    # Include the integration metadata for Slack
                    integration_details.update({
                        "integration_metadata": token.integration_metadata,
                        "permissions": [
                            "send_messages",
                            "read_messages",
                            "manage_channels"
                        ],
                        "status": "active"
                    })
                except Exception as e:
                    integration_details.update({
                        "status": "error",
                        "error_message": str(e)
                    })
            
            integrations_info.append(integration_details)
        
        return {
            "integrations": integrations_info,
            "total_integrations": len(integrations_info)
        }
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Error getting integration status: {str(e)}"
        )
    


@router.delete("/integration/{service_name}")
async def delete_integration(
    service_name: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Delete an integration token by service name for the current user.
    """
    try:
        # Get all tokens for the user
        tokens = await get_integration_tokens(db, current_user.id)
        
        # Find the token for the specified service
        token = next((token for token in tokens if token.service_name == service_name), None)
        
        if not token:
            raise HTTPException(
                status_code=404, 
                detail=f"No integration found for service: {service_name}"
            )
        
        # Delete the token
        await delete_integration_token(db, token.id)
        
        return {"message": f"{service_name} integration deleted successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error deleting {service_name} integration: {str(e)}"
        )


@router.post("/integrations/trigger")
async def create_integration_trigger_endpoint(
    integration_id: UUID,
    flow_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """Create a new integration trigger linking a flow to an integration."""
    try:
        print("\n\n/integrations/trigger \n\n")
        # Verify the integration token exists and belongs to the user
        integration = await get_integration_token_by_id(db, integration_id)
        print("\n\nintegration from DB", integration)
        if not integration or integration.user_id != current_user.id:
            raise HTTPException(
                status_code=404,
                detail="Integration not found or does not belong to current user"
            )

        # Create the trigger record
        trigger = await create_integration_trigger(
            db=db,
            integration_id=integration_id,
            flow_id=flow_id
        )
        print("\n\ncreated trigger", trigger)

        return {
            "message": "Integration trigger created successfully",
            "trigger_id": trigger.id
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print("\n\nerror in /integrations/trigger", e)
        raise HTTPException(
            status_code=500,
            detail=f"Error creating integration trigger: {str(e)}"
        )

@router.post("/gmail/watch/{integration_id}")
async def watch_gmail(
    integration_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    For a given integration record (user's Gmail integration), register a watch and update the DB with subscription details.
    This endpoint now verifies that the integration belongs to the current user.
    """
    # Fetch integration token from DB and ensure it belongs to the authenticated user.
    integration = await get_integration_token_by_id(db=db, token_id=integration_id)
    if not integration or integration.service_name != "gmail" or integration.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Gmail integration not found or unauthorized")

    creds = Credentials(
        token=integration.access_token,
        refresh_token=integration.refresh_token,
        token_uri=integration.token_uri,
        client_id=integration.client_id,
        client_secret=integration.client_secret,
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send"
        ],
    )
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    
    request_body = {
        "labelIds": ["CATEGORY_PERSONAL"],
        "topicName": "projects/langflow-449814/topics/gmail-notifications",
        "payload": "application/json",
        "clientToken": str(integration.id),
        "params": {
            "integration_id": str(integration.id)
        }
    }
    
    # Offload the blocking call to stop any previous watch.
    try:
        await run_in_threadpool(lambda: service.users().stop(userId="me").execute())
    except Exception as e:
        print("No existing watch to stop:", str(e))
    
    # Offload the blocking call to create a new watch.
    response = await run_in_threadpool(lambda: service.users().watch(userId="me", body=request_body).execute())
    print("🔔 Watch Response:", response)
    
    integration.last_history_id = response.get("historyId")
    integration.channel_id = response.get("channelId")  # if provided
    expiration_timestamp = int(response.get("expiration", 0)) / 1000.0
    integration.watch_expiration = datetime.fromtimestamp(expiration_timestamp, timezone.utc)
    await update_integration_token(db=db, token_id=integration_id, token=integration)
    
    return {"message": "Gmail watch registered successfully", "historyId": integration.last_history_id}

@router.post("/pubsub/gmail")
async def receive_pubsub_message(request: Request, background_tasks: BackgroundTasks):
    try:
        print("\n🔔 === New Pub/Sub Request ===")
        print("📍 URL:", str(request.url))
        print("📝 Method:", request.method)
        print("📋 Headers:", dict(request.headers))
        
        # Get raw body for debugging
        raw_body = await request.body()
        print("📦 Raw body:", raw_body.decode())
        
        # Verify the token (now with more lenient verification)
        await verify_pubsub_token(request)
        
        body = await request.json()
        print("🔍 Parsed body:", json.dumps(body, indent=2))
        
        message = body.get("message", {})
        message_data = message.get("data")
        
        # Try to obtain integration_id and new_history_id from the message attributes or data payload.
        integration_id = message.get("attributes", {}).get("clientToken")
        new_history_id = message.get("attributes", {}).get("historyId")
        
        if not integration_id and message_data:
            decoded = base64.b64decode(message_data).decode()
            pubsub_payload = json.loads(decoded)
            integration_id = pubsub_payload.get("integration_id")
            new_history_id = pubsub_payload.get("historyId")
            
        # 3. Final fallback: lookup via email address if provided
        if not integration_id:
            email = None
            if 'pubsub_payload' in locals():
                email = pubsub_payload.get("emailAddress")
            if email:
                db_gen = get_session()
                db = await db_gen.__anext__()
                try:
                    integration = await get_integration_by_email_address(db, email_address=email)
                    integration_id = str(integration.id) if integration else None
                finally:
                    await db_gen.aclose()
                print("Integration ID retrieved via email lookup:", integration_id)

        if not integration_id:
            print("❌ Missing integration ID")
            return {"status": "missing integration id"}
        
        # Pass only integration_id and new_history_id to the background task.
        background_tasks.add_task(process_gmail_notification, integration_id, new_history_id)
        return {"status": "processing"}
    
    except HTTPException as he:
        print(f"Authentication error: {he.detail}")
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_gmail_notification(integration_id: str, new_history_id: str):
    db_gen = get_session()
    db = await db_gen.__anext__()
    try:
        integration = await get_integration_token_by_id(db, UUID(integration_id))
        if not integration:
            print("Integration record not found")
            return

        creds = Credentials(
            token=integration.access_token,
            refresh_token=integration.refresh_token,
            token_uri=integration.token_uri,
            client_id=integration.client_id,
            client_secret=integration.client_secret,
            scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"],
        )

        # Refresh the credentials if they're expired
        if not creds.valid:
            creds.refresh(google_requests.Request())
            # Update the token in the database
            integration.access_token = creds.token
            await update_integration_token(db, integration.id, integration)

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        # Offload the blocking history API call.
        response = await run_in_threadpool(
            lambda: service.users().history().list(
                userId="me", startHistoryId=integration.last_history_id
            ).execute()
        )
        history_events = response.get("history", [])
        print(f"Found {len(history_events)} history events")

        integration_email = integration.email_address
        if not integration_email:
            print("Warning: Integration email address not found")
            return

        unique_message_ids = set()
        for event in history_events:
            for msg in event.get("messages", []):
                unique_message_ids.add(msg["id"])

        print(f"Fetching {len(unique_message_ids)} messages concurrently")

        # Helper function to retrieve a message by its ID.
        async def fetch_message(message_id: str):
            try:
                service = build(
                    "gmail",
                    "v1",
                    credentials=creds,
                    cache_discovery=False
                )
                return await run_in_threadpool(
                    lambda: service.users().messages().get(
                        userId="me",
                        id=message_id,
                        format="full"
                    ).execute()
                )
            except Exception as e:
                print(f"Error fetching message {message_id}: {str(e)}")
                return None

        # Retrieve messages concurrently.
        message_tasks = [fetch_message(mid) for mid in unique_message_ids]
        full_messages = await asyncio.gather(*message_tasks, return_exceptions=True)

        # Process all retrieved messages.
        for full_message in full_messages:
            if full_message is None or isinstance(full_message, Exception):
                continue

            # Check for promotional and social labels.
            label_ids = full_message.get("labelIds", [])
            if "CATEGORY_PROMOTIONS" in label_ids or "CATEGORY_SOCIAL" in label_ids:
                print(f"Skipping promotional/social email with id {full_message.get('id')}")
                continue

            payload = full_message.get("payload", {})
            headers = payload.get("headers", [])
            subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
            sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
            date = next((h["value"] for h in headers if h["name"].lower() == "date"), "Unknown Date")
            snippet = full_message.get("snippet", "No preview available")
            sender_email = sender.split("<")[-1].rstrip(">")

            if sender_email.lower() == integration_email.lower():
                print(f"Skipping email from self ({sender_email})")
                continue
            auto_submitted = next((h["value"] for h in headers if h["name"].lower() == "auto-submitted"), None)
            if auto_submitted and auto_submitted.lower() != "no":
                print(f"Skipping auto-generated email for message {full_message.get('id')}")
                continue

            body_text = ""
            if "body" in payload and "data" in payload["body"]:
                body_text = base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="replace")
            elif "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                        body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode(errors="replace")
                        break

            message_content = (
                f"Email Details:\n"
                f"Message ID: {full_message.get('id', 'Unknown')}\n"
                f"Date: {date}\n"
                f"From: {sender}\n"
                f"Subject: {subject}\n"
                f"Preview: {snippet}\n\n"
                f"Body:\n{body_text}\n\n"
                f"Thread ID: {full_message.get('threadId', 'Unknown')}"
            )

            triggers = await get_integration_triggers_by_integration(db, integration.id)
            print("\n\ntriggers", triggers)
            for trigger in triggers:
                try:
                    await trigger_flow(trigger.flow_id, message_content, full_message.get("id"), full_message.get("threadId"), db)
                except Exception as e:
                    print(f"Error triggering flow for flow_id {trigger.flow_id}: {e}. Skipping.")

        if new_history_id:
            integration.last_history_id = new_history_id
            await update_integration_token(db, integration.id, integration)

    except Exception as e:
        print(f"Error processing Gmail notification: {str(e)}")
    finally:
        await db_gen.aclose()

@asynccontextmanager
async def redis_lock(lock_key: str, timeout: int = 300):
    # Use the nx flag to set the key only if it doesn't exist.
    is_locked = await redis.set(lock_key, "locked", ex=timeout, nx=True)
    if not is_locked:
        raise Exception("Lock already acquired")
    try:
        yield
    finally:
        await redis.delete(lock_key)


async def trigger_flow(flow_id: UUID, message: str, message_id: str, thread_id: str, db: AsyncSession):
    lock_key = f"flow_lock:{flow_id}"
    async with redis_lock(lock_key):
        start_time = time.perf_counter()
        try:
            telemetry_service = get_telemetry_service()
            session_service = get_session_service()
            
            # Check if email was already processed
            processed = await get_processed_email(db, flow_id, message_id)
            if processed:
                print(f"Skipping already processed message {message_id}")
                return
            
            # Get or create thread session
            email_thread = await get_email_thread(db, flow_id, thread_id)
            session_id = None
            
            if email_thread:
                # Use existing session for this thread
                session_id = email_thread.session_id
                await update_email_thread(db, email_thread)
            else:
                # Create a new session ID
                session_id = str(uuid4())
                # Try using the session service method, if available
                if hasattr(session_service, "set_session"):
                    await session_service.set_session(
                        session_id=session_id,
                        chat_data={
                            "flow_id": str(flow_id),
                            "messages": [],
                            "chat_history": []
                        }
                    )
                else:
                    # Fallback: initialize a sessions dictionary if it doesn't exist
                    if not hasattr(session_service, "sessions"):
                        session_service.sessions = {}
                    session_service.sessions[session_id] = {
                        "flow_id": str(flow_id),
                        "messages": [],
                        "chat_history": []
                    }
            
            # Create processed email record
            processed_email = await create_processed_email(db, flow_id, message_id)
            
            flow = await get_flow_by_id_or_endpoint_name(flow_id_or_name=str(flow_id))
            user = await get_user_by_flow_id_or_endpoint_name(str(flow_id))
            if not user:
                raise ValueError("User not found for flow")
            
            input_request = SimplifiedAPIRequest(
                input_value="New email received. Here is the email content:\n\n" + message,
                input_type="chat",
                output_type="chat",
                session_id=session_id
            )
            
            result = await simple_run_flow(flow=flow, input_request=input_request, api_key_user=user)
            
            # If this is a new thread, create a thread record with the new session ID
            if not email_thread:
                await create_email_thread(db, flow_id, thread_id, session_id)
            
            end_time = time.perf_counter()
            await telemetry_service.log_package_run(
                RunPayload(
                    run_is_webhook=True,
                    run_seconds=int(end_time - start_time),
                    run_success=True,
                    run_error_message=""
                )
            )
            return result
        except Exception as e:
            await telemetry_service.log_package_run(
                RunPayload(
                    run_is_webhook=True,
                    run_seconds=int(time.perf_counter() - start_time),
                    run_success=False,
                    run_error_message=str(e)
                )
            )
            raise

async def verify_pubsub_token(request: Request):
    print("🔍 Starting token verification")
    print("📝 Request headers:", dict(request.headers))
    
    # Get the authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        print("❌ No Authorization header found")
        # For testing, temporarily disable auth check
        return True
        # raise HTTPException(status_code=403, detail="Missing authorization header")
    
    if not auth_header.startswith('Bearer '):
        print("❌ Authorization header doesn't start with 'Bearer'")
        # For testing, temporarily disable auth check
        return True
        # raise HTTPException(status_code=403, detail="Invalid authorization header format")
    
    token = auth_header.split('Bearer ')[1]
    print("🔑 Extracted token:", token[:20] + "..." if token else "None")
    
    try:
        # For testing purposes, accept any token temporarily
        print("✅ Token verification bypassed for testing")
        return True
        
        # Original verification code (commented out for testing)
        # audience = f"https://{request.base_url.hostname}/api/v1/pubsub/gmail"
        # claims = jwt.decode(token, requests.Request(), audience=audience)
        # if claims['iss'] != 'https://accounts.google.com':
        #     raise HTTPException(status_code=403, detail="Invalid token issuer")
        # return claims
        
    except Exception as e:
        print(f"❌ Token verification failed: {str(e)}")
        # For testing, don't raise the exception
        return True
        # raise HTTPException(status_code=403, detail=f"Token verification failed: {str(e)}")
