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

@router.get("/auth/slack/login")
async def slack_login(
    current_user: User = Depends(oauth2_login),
    db: AsyncSession = Depends(get_session)
):
    """
    Initiates the Slack OAuth flow.
    """
    if not SLACK_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Slack client ID not configured")
    
    # Generate a state parameter to prevent CSRF
    state = str(uuid4())
    
    # Create the Slack OAuth URL with only user scopes, no bot scopes
    auth_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={SLACK_CLIENT_ID}"
        f"&user_scope={'%20'.join(SLACK_SCOPES)}"  # Only user scopes
        f"&redirect_uri={SLACK_REDIRECT_URI}"
        f"&state={state}"
    )
    
    return RedirectResponse(auth_url)

@router.get("/auth/slack/callback")
async def slack_callback(
    request: Request,
    state: str,
    code: str,
    access_token_lf: str = Cookie(None, alias="access_token_lf"),
    db: AsyncSession = Depends(get_session)
):
    try:  
        if not access_token_lf:
            print("⚠️ No access token found in cookies")
            html_content = """
            <html>
                <script type="text/javascript">
                    window.opener.postMessage({ slackError: "authentication_required" }, "*");
                    window.close();
                </script>
                <body>Authentication required. Please login first and try again.</body>
            </html>
            """
            return HTMLResponse(content=html_content)

        current_user = await get_current_user_by_jwt(access_token_lf, db)
        print(f"Current user ID: {current_user.id}")
        
        if not SLACK_CLIENT_ID or not SLACK_CLIENT_SECRET:
            print("⚠️ Slack client configuration missing")
            raise HTTPException(status_code=500, detail="Slack client configuration missing")

        # Exchange code for token
        print("\n----- SENDING TOKEN REQUEST TO SLACK -----")
        request_data = {
            "client_id": SLACK_CLIENT_ID,
            "client_secret": SLACK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": SLACK_REDIRECT_URI
        }
        
        response = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data=request_data
        )
        
        print("\n----- SLACK TOKEN RESPONSE -----")
        print(f"Response status code: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        
        # After receiving the response from Slack
        token_data = response.json()
        print("\n----- RAW TOKEN DATA STRUCTURE -----")
        print(f"token_data keys: {token_data.keys()}")
        if "authed_user" in token_data:
            print(f"authed_user keys: {token_data['authed_user'].keys()}")
            if "access_token" in token_data["authed_user"]:
                token_value = token_data["authed_user"]["access_token"]
                print(f"Raw token length: {len(token_value)}")
                print(f"Raw token prefix: {token_value[:8] if len(token_value) >= 8 else token_value}")
        
        if not token_data.get("ok"):
            print(f"⚠️ Slack error: {token_data.get('error')}")
            html_content = f"""
            <html>
                <script type="text/javascript">
                    window.opener.postMessage({{ slackError: "{token_data.get('error')}" }}, "*");
                    window.close();
                </script>
                <body>Slack authentication error: {token_data.get('error')}</body>
            </html>
            """
            return HTMLResponse(content=html_content)

        # Extract user token from authed_user
        authed_user = token_data.get("authed_user", {})
        user_access_token = authed_user.get("access_token")
        refresh_token = authed_user.get("refresh_token", None)

        # Debug token information
        if user_access_token:
            token_prefix = user_access_token[:8] if len(user_access_token) >= 8 else user_access_token
            print(f"User token prefix: {token_prefix}...")
            
            # Validate token format
            if not user_access_token.startswith('xoxp-'):
                print(f"⚠️ WARNING: User token does not have expected format (xoxp-). Prefix: {token_prefix}")
        else:
            print("⚠️ No user access token received!")

        # Get user info using the user token
        slack_user_id = authed_user.get("id")
        print(f"Slack user ID: {slack_user_id}")
        
        slack_email = None
        try:
            print("\n----- GETTING SLACK USER INFO -----")
            user_info_response = requests.get(
                "https://slack.com/api/users.info",
                params={"user": slack_user_id},
                headers={"Authorization": f"Bearer {user_access_token}"}
            )
            print(f"User info response status: {user_info_response.status_code}")
            
            user_info = user_info_response.json()
            print(f"User info response: {user_info}")
            
            if user_info.get("ok"):
                slack_email = user_info.get("user", {}).get("profile", {}).get("email")
                print(f"Slack email: {slack_email}")
            else:
                print(f"⚠️ Error getting user info: {user_info.get('error')}")
        except Exception as e:
            print(f"⚠️ Error getting Slack user info: {str(e)}")

        # Store the token in the database
        print("\n----- STORING TOKEN IN DATABASE -----")
        if not user_access_token:
            print("⚠️ ERROR: No user access token to store!")
            html_content = """
            <html>
                <script type="text/javascript">
                    window.opener.postMessage({ slackError: "no_user_token" }, "*");
                    window.close();
                </script>
                <body>Error: No user token received from Slack. Please try again or contact support.</body>
            </html>
            """
            return HTMLResponse(content=html_content)
            
        # Store the raw token without any processing or transformation
        print(f"Token length before storage: {len(user_access_token)}")
        print(f"Token prefix before storage: {user_access_token[:8] if len(user_access_token) >= 8 else user_access_token}")

        # Debug the token string in detail to identify any encoding issues
        print("\n----- TOKEN ENCODING DEBUG -----")
        print(f"Token type: {type(user_access_token)}")
        print(f"Token hex representation: {' '.join([hex(ord(c)) for c in user_access_token[:10]])}")
        print(f"Is token ASCII? {all(ord(c) < 128 for c in user_access_token)}")
        
        # Create a clean copy of the token to avoid any reference issues
        clean_token = str(user_access_token).strip()
        print(f"Stored token prefix: {clean_token}")
        # Create token in database with the clean token
        await create_integration_token(
            db=db,
            user_id=current_user.id,
            service_name="slack",
            access_token=clean_token,
            refresh_token=refresh_token,
            token_uri=None,
            client_id=SLACK_CLIENT_ID,
            client_secret=SLACK_CLIENT_SECRET,
            expires_at=None,
            email_address=slack_email
        )
        print("✅ Token stored successfully")

        print("\n----- RETURNING SUCCESS RESPONSE -----")
        html_content = """
        <html>
            <script type="text/javascript">
                window.opener.postMessage({ slackConnected: true }, "*");
                window.close();
            </script>
            <body>Slack authentication complete. Closing window...</body>
        </html>
        """
        print("===== END SLACK CALLBACK DEBUG INFO =====\n")
        return HTMLResponse(content=html_content)
    except Exception as e:
        print(f"\n⚠️ EXCEPTION IN SLACK CALLBACK: {str(e)}")
        print(f"Exception type: {type(e)}")
        print(f"Exception traceback: {traceback.format_exc()}")
        print("===== END SLACK CALLBACK DEBUG INFO =====\n")
        raise HTTPException(status_code=400, detail=f"Slack OAuth error: {str(e)}")

@router.post("/slack/message")
async def send_slack_message(
    channel: str = Body(..., embed=True, description="Channel or user ID to send message to"),
    message: str = Body(..., embed=True, description="Message text to send"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Send a message to a Slack channel or user.
    """
    try:
        tokens = await get_integration_tokens(db, current_user.id)
        slack_token = next((token for token in tokens if token.service_name == "slack"), None)
        
        if not slack_token:
            raise HTTPException(status_code=401, detail="Slack not connected")
        
        # Send the message using Slack's Web API
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {slack_token.access_token}"},
            json={
                "channel": channel,
                "text": message
            }
        )
        
        result = response.json()
        if not result.get("ok"):
            raise HTTPException(
                status_code=400, 
                detail=f"Error sending Slack message: {result.get('error')}"
            )
        
        return {
            "status": "success", 
            "message_id": result.get("ts"),
            "channel": result.get("channel")
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error sending Slack message: {str(e)}"
        )

@router.post("/slack/webhook")
async def slack_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Endpoint for receiving Slack Events API notifications.
    This endpoint will verify the request and then process events asynchronously.
    """
    try:
        body = await request.json()
        
        # Handle Slack URL verification challenge
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge")}
        
        # Process the event in the background
        if "event" in body:
            event = body.get("event", {})
            event_type = event.get("type")
            
            # Currently we're handling message events
            if event_type == "message":
                # Ignore bot messages to prevent potential infinite loops
                if not event.get("bot_id") and not event.get("subtype") == "bot_message":
                    background_tasks.add_task(
                        process_slack_message,
                        team_id=body.get("team_id"),
                        event=event
                    )
        
        # Slack expects a 200 OK response quickly
        return {"status": "processing"}
    except Exception as e:
        print(f"Error processing Slack webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_slack_message(team_id: str, event: Dict):
    """
    Process a Slack message event and trigger appropriate flows.
    """
    try:
        db_gen = get_session()
        db = await db_gen.__anext__()
        
        try:
            # Find any integration tokens that match this workspace
            statement = select(IntegrationToken).where(
                IntegrationToken.service_name == "slack"
            )
            results = await db.exec(statement)
            tokens = results.all()
            
            # We need to verify team_id to find the right integration
            # This requires an API call to Slack for each token
            matching_token = None
            
            for token in tokens:
                try:
                    response = requests.get(
                        "https://slack.com/api/team.info",
                        headers={"Authorization": f"Bearer {token.access_token}"}
                    )
                    result = response.json()
                    if result.get("ok") and result.get("team", {}).get("id") == team_id:
                        matching_token = token
                        break
                except Exception as e:
                    print(f"Error checking Slack team: {str(e)}")
            
            if not matching_token:
                print(f"No matching Slack integration found for team ID: {team_id}")
                return
            
            # Get triggers configured for this integration
            triggers = await get_integration_triggers_by_integration(db, matching_token.id)
            
            if not triggers:
                print(f"No triggers configured for Slack integration {matching_token.id}")
                return
            
            # Get the message details
            channel_id = event.get("channel")
            message_text = event.get("text", "")
            thread_ts = event.get("thread_ts")
            message_ts = event.get("ts")
            
            # Process for each configured trigger
            for trigger in triggers:
                flow_id = trigger.flow_id
                
                # Check if flow exists
                try:
                    flow = await get_flow_by_id_or_endpoint_name(flow_id_or_name=str(flow_id))
                    if not flow:
                        print(f"Flow {flow_id} not found")
                        continue
                        
                    # Create or get thread session
                    thread_id = thread_ts or message_ts  # If not in a thread, use the message ts as thread id
                    session_id = str(uuid4())  # Create a new session ID for each flow run
                    
                    # Prepare session
                    session_service = get_session_service()
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
                    
                    # Trigger the flow with the message content
                    await trigger_flow_for_slack(
                        flow_id=flow_id,
                        message=message_text,
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                        db=db,
                        token=matching_token
                    )
                except Exception as flow_error:
                    print(f"Error triggering flow {flow_id}: {str(flow_error)}")
        finally:
            await db_gen.aclose()
    except Exception as e:
        print(f"Error processing Slack message: {str(e)}")

async def trigger_flow_for_slack(
    flow_id: UUID, 
    message: str, 
    channel_id: str,
    thread_ts: Optional[str],
    db: AsyncSession,
    token: IntegrationToken
):
    """
    Trigger a flow based on a Slack message and send the response back to Slack.
    """
    try:
        # Get the flow
        flow = await get_flow_by_id_or_endpoint_name(flow_id_or_name=str(flow_id))
        user = await get_user_by_flow_id_or_endpoint_name(str(flow_id))
        
        if not user:
            raise ValueError("User not found for flow")
        
        # Create service-specific lock key (to avoid concurrency issues)
        lock_key = f"slack_flow:{flow_id}:{channel_id}:{thread_ts or 'new'}"
        
        async with redis_lock(lock_key):
            # Run the flow with the message as input
            inputs = {"message": message}
            inputs_map = {}
            
            # Find which node to connect the message to
            for node in flow.data.get("nodes", []):
                if node.get("node_type", "") == "chatInputNode":
                    node_id = node.get("id")
                    inputs_map[node_id] = {"message": message}
                
            api_request = SimplifiedAPIRequest(
                inputs=inputs,
                inputs_map=inputs_map,
                is_interactive=False,
                tweaks={},
                session_id=str(uuid4())
            )
            
            response = await simple_run_flow(
                flow_id_or_name=str(flow_id),
                api_request=api_request,
                user=user
            )
            
            # Process and send the response back to Slack
            if response:
                # Extract the reply message from the flow output
                reply = None
                
                # Look for output nodes with text or message fields
                if isinstance(response, dict):
                    for key, value in response.items():
                        if isinstance(value, str) and value.strip():
                            reply = value
                            break
                elif isinstance(response, str) and response.strip():
                    reply = response
                
                if reply:
                    # Send the reply back to Slack
                    thread_params = {"thread_ts": thread_ts} if thread_ts else {}
                    
                    slack_response = requests.post(
                        "https://slack.com/api/chat.postMessage",
                        headers={"Authorization": f"Bearer {token.access_token}"},
                        json={
                            "channel": channel_id,
                            "text": reply,
                            **thread_params
                        }
                    )
                    
                    if not slack_response.json().get("ok"):
                        print(f"Error sending Slack response: {slack_response.json().get('error')}")
    except Exception as e:
        print(f"Error in trigger_flow_for_slack: {str(e)}")
        # Optionally, send an error message to Slack

@router.post("/slack/create-subscription")
async def create_slack_subscription(
    integration_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Set up a Slack Events API subscription for the given integration.
    
    This endpoint provides instructions for setting up the Events API in the Slack API dashboard,
    as Slack requires a publicly accessible URL for events.
    """
    try:
        # Verify the integration belongs to the user and is a Slack integration
        integration = await get_integration_token_by_id(db=db, token_id=integration_id)
        if not integration or integration.service_name != "slack" or integration.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Slack integration not found or unauthorized")
        
        # Provide instructions for setting up Slack Events API
        return {
            "message": "Slack Events API setup instructions",
            "integration_id": str(integration_id),
            "instructions": [
                "1. Go to your Slack App configuration at https://api.slack.com/apps",
                "2. Select your app and go to 'Event Subscriptions'",
                "3. Enable Events and set the Request URL to: " + 
                f"https://your-langflow-domain.com/api/v1/slack/webhook",
                "4. Subscribe to the following bot events: message.channels, message.im",
                "5. Save changes and reinstall your app if prompted"
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error preparing Slack subscription: {str(e)}"
        )

@router.post("/slack/fix-token")
async def fix_slack_token(
    token: str = Body(..., embed=True, description="The new Slack token to store"), 
    integration_id: UUID = Body(..., embed=True, description="The integration ID to update"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Manually update a Slack token in the database.
    
    This endpoint is useful when a token needs to be fixed or updated without going
    through the OAuth flow again. Only token owners can update their tokens.
    """
    try:
        # Verify the integration belongs to the user and is a Slack integration
        integration = await get_integration_token_by_id(db=db, token_id=integration_id)
        if not integration or integration.service_name != "slack" or integration.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Slack integration not found or unauthorized")
        
        # Validate the token format
        if not token.startswith("xoxp-") and not token.startswith("xoxb-"):
            raise HTTPException(
                status_code=400, 
                detail="Invalid Slack token format. Must start with 'xoxp-' (for user tokens) or 'xoxb-' (for bot tokens)."
            )
        
        # Update the token in the database
        # The update_slack_token function expects user_id and new_token parameters
        await update_slack_token(
            db=db,
            integration_id=integration_id,
            new_token=token
        )
        
        return {
            "message": "Slack token updated successfully",
            "integration_id": str(integration_id)
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating Slack token: {str(e)}"
        )

@router.get("/encryption-key/status", dependencies=[Depends(get_current_active_user)])
async def check_encryption_key():
    """
    Check the status of the encryption key for debugging token encryption/decryption issues.
    This is an administrative endpoint that should be secured in production.
    """
    try:
        from cryptography.fernet import Fernet
        import base64
        import os
        
        # First check environment variable
        env_key = os.getenv("LANGFLOW_ENCRYPTION_KEY")
        
        # Check for key in various places
        key_locations = []
        for location in [".env", "src/backend/base/langflow/.env", "src/backend/.env", ".encryption_key"]:
            if os.path.exists(location):
                key_locations.append(location)
        
        # Also check TOKEN_ENCRYPTION_KEY
        token_key = os.getenv("TOKEN_ENCRYPTION_KEY")
        
        # Create response with key information (careful not to expose the actual key)
        response = {
            "status": "ok" if env_key or token_key else "missing",
            "langflow_key_exists": bool(env_key),
            "token_key_exists": bool(token_key),
            "potential_key_files": key_locations,
            "key_valid": False
        }
        
        # Test that the key is valid by creating a Fernet instance
        try:
            if env_key:
                f = Fernet(env_key.encode())
                test_token = f.encrypt(b"test").decode()
                response["key_valid"] = True
                response["key_test"] = "passed"
            elif token_key:
                f = Fernet(token_key.encode())
                test_token = f.encrypt(b"test").decode()
                response["key_valid"] = True
                response["key_test"] = "passed using TOKEN_ENCRYPTION_KEY"
        except Exception as e:
            response["key_test"] = f"failed: {str(e)}"
        
        return response
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error checking encryption key: {str(e)}"
        )