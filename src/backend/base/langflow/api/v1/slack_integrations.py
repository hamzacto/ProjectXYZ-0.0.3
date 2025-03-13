from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.api.v1.schemas import SimplifiedAPIRequest
from langflow.services.database.models.user.model import User
from langflow.services.auth.utils import get_current_active_user
from langflow.services.database.models.flow import Flow, FlowCreate
from langflow.services.database.models.integration_token.model import IntegrationToken
from langflow.services.database.models.integration_trigger.model import IntegrationTrigger
from langflow.services.deps import get_session, get_session_service
from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.api.v1.endpoints import simple_run_flow
from langflow.services.auth.utils import get_current_active_user, oauth2_login, get_current_user_by_jwt
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request, Cookie
from langflow.api.v1.endpoints import simple_run_flow
import traceback
from langflow.services.database.models.user.crud import create_integration_token, get_integration_tokens,delete_integration_token, get_integration_token_by_id, update_integration_token, create_integration_trigger, update_slack_token
from langflow.services.database.models.integration_trigger.crud import get_integration_triggers_by_integration
from langflow.services.database.models.integration_token.crud import get_integration_by_email_address
from sqlmodel.ext.asyncio.session import AsyncSession
from langflow.services.deps import get_session
import base64
from sqlalchemy import select
from langflow.helpers.user import get_user_by_flow_id_or_endpoint_name
from redis import asyncio as aioredis
from langflow.api.v1.endpoints import simple_run_flow
from typing import TYPE_CHECKING, Dict, Optional
from dotenv import load_dotenv
router = APIRouter(tags=["Slack Integrations"])

# Slack API configuration
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")
SLACK_SCOPES = [
    "channels:history", 
    "channels:read",
    "chat:write", 
    "groups:history",
    "im:history",
    "im:read",
    "im:write",
    "users:read",
    "users.profile:read"
]
if TYPE_CHECKING:
    from langflow.services.settings.service import SettingsService

load_dotenv()

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
@router.post("/slack/events")
async def slack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session)
):
    """
    Handle incoming events from Slack.
    """
    try:
        # Get the raw request body
        body = await request.body()
        body_str = body.decode()
        
        # Parse the request body
        event_data = json.loads(body_str)
        print(f"Received Slack event: {event_data}")
        
        # Handle URL verification challenge
        if event_data.get("type") == "url_verification":
            return {"challenge": event_data.get("challenge")}
            
        # Get event type
        event_type = event_data.get("type")
        if event_type != "event_callback":
            print(f"Ignoring non-event callback: {event_type}")
            return {"ok": True}
            
        # Get the event details
        event = event_data.get("event", {})
        event_type = event.get("type")
        
        # Handle message events
        if event_type == "message":
            # Check if this is a bot message or a message changed event
            if event.get("subtype") in ["bot_message", "message_changed", "message_deleted"]:
                return {"ok": True}
                
            # Process the message
            await process_user_slack_message(event_data, db)
            
        return {"ok": True}
        
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error in slack_webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def process_user_slack_message(event_data: dict, db: AsyncSession):
    """
    Process a message event from Slack, checking if it matches any user-level event subscriptions.
    """
    async with db as session:
        try:
            # Get the team_id from the event data
            team_id = event_data.get("team_id")
            if not team_id:
                print("No team_id in event data")
                return
            
            # Get all Slack integrations
            statement = select(IntegrationToken).where(
                IntegrationToken.service_name == "slack"
            )
            results = await session.exec(statement)
            integrations = results.all()
            
            # Filter integrations by team_id in metadata and check for watch_user_events flag
            valid_integrations = []
            for integration_row in integrations:
                try:
                    # Convert SQLAlchemy Row to dictionary using __dict__ access
                    integration_dict = {
                        'id': integration_row.__dict__.get('id'),
                        'integration_metadata': integration_row.__dict__.get('integration_metadata', {}),
                        'service_name': integration_row.__dict__.get('service_name'),
                        'user_id': integration_row.__dict__.get('user_id'),
                        'access_token': integration_row.__dict__.get('access_token')
                    }
                    
                    # Get metadata and check flags
                    metadata = integration_dict['integration_metadata'] or {}
                    integration_id = integration_dict['id']
                    integration_team_id = metadata.get("team_id")
                    watch_user_events = metadata.get("watch_user_events", False)
                    
                    print(f"Integration {integration_id}:")
                    print(f"  Team ID (integration): {integration_team_id}")
                    print(f"  Team ID (event): {team_id}")
                    print(f"  Watch user events: {watch_user_events}")
                    
                    # Verify team ID with Slack API
                    try:
                        access_token = integration_dict['access_token']
                        if not access_token:
                            print(f"No access token for integration {integration_dict['id']}")
                            continue
                            
                        response = requests.get(
                            "https://slack.com/api/team.info",
                            headers={"Authorization": f"Bearer {access_token}"}
                        )
                        team_data = response.json()
                        if not team_data.get("ok"):
                            print(f"Error getting team info: {team_data.get('error')}")
                            continue
                            
                        verified_team_id = team_data.get("team", {}).get("id")
                        if not verified_team_id:
                            print("Could not get team ID from Slack API")
                            continue
                            
                        print(f"  Verified team ID: {verified_team_id}")
                        
                        if verified_team_id == team_id and watch_user_events:
                            valid_integrations.append((integration_row, integration_dict))
                            print(f"  Integration {integration_id} is valid for team {team_id}")
                    except Exception as e:
                        print(f"Error verifying team ID: {str(e)}")
                        continue
                        
                except Exception as e:
                    print(f"Error processing integration {integration_row.__dict__.get('id', 'unknown')}: {str(e)}")
                    continue
            
            if not valid_integrations:
                print(f"No matching integrations found for team {team_id}")
                return
            
            # Process the event for each valid integration
            for integration_row, integration_dict in valid_integrations:
                try:
                    await process_slack_message(team_id, event_data.get("event", {}))
                except Exception as e:
                    print(f"Error processing message for integration {integration_dict['id']}: {str(e)}")
                    continue
                    
        except Exception as e:
            print(f"Error in process_user_slack_message: {str(e)}")
            await session.rollback()
        finally:
            await session.close()

async def process_slack_message(team_id: str, event: Dict):
    """
    Process a Slack message event and trigger appropriate flows.
    """
    async with get_session() as db:
        try:
            # Get the message details
            channel_id = event.get("channel")
            message_text = event.get("text", "")
            thread_ts = event.get("thread_ts")
            message_ts = event.get("ts")
            
            # Find any integration tokens that match this workspace
            statement = select(IntegrationToken).where(
                IntegrationToken.service_name == "slack"
            )
            results = await db.exec(statement)
            tokens = results.all()
            
            # We need to verify team_id to find the right integration
            matching_token = None
            
            for token_row in tokens:
                try:
                    # Convert SQLAlchemy Row to dictionary using __dict__ access
                    token_dict = {
                        'id': token_row.__dict__.get('id'),
                        'integration_metadata': token_row.__dict__.get('integration_metadata', {}),
                        'service_name': token_row.__dict__.get('service_name'),
                        'user_id': token_row.__dict__.get('user_id'),
                        'access_token': token_row.__dict__.get('access_token')
                    }
                    
                    # Get metadata and check flags
                    metadata = token_dict['integration_metadata'] or {}
                    integration_id = token_dict['id']
                    integration_team_id = metadata.get("team_id")
                    watch_user_events = metadata.get("watch_user_events", False)
                    
                    print(f"Integration {integration_id}:")
                    print(f"  Team ID (integration): {integration_team_id}")
                    print(f"  Team ID (event): {team_id}")
                    print(f"  Watch user events: {watch_user_events}")
                    
                    # Verify team using Slack API
                    try:
                        access_token = token_dict['access_token']
                        if not access_token:
                            print(f"No access token for integration {token_dict['id']}")
                            continue
                            
                        response = requests.get(
                            "https://slack.com/api/team.info",
                            headers={"Authorization": f"Bearer {access_token}"}
                        )
                        team_data = response.json()
                        if not team_data.get("ok"):
                            print(f"Error getting team info: {team_data.get('error')}")
                            continue
                            
                        verified_team_id = team_data.get("team", {}).get("id")
                        if not verified_team_id:
                            print("Could not get team ID from Slack API")
                            continue
                            
                        print(f"  Verified team ID: {verified_team_id}")
                        
                        if verified_team_id == team_id and watch_user_events:
                            matching_token = token_row
                            break
                    except Exception as e:
                        print(f"Error verifying team ID: {str(e)}")
                        continue
                        
                except Exception as e:
                    print(f"Error processing integration {token_row.__dict__.get('id', 'unknown')}: {str(e)}")
                    continue
            
            if not matching_token:
                print(f"No matching Slack integration found for team ID: {team_id}")
                return
            
            # Get triggers configured for this integration
            matching_token_dict = {
                'id': matching_token.__dict__.get('id'),
                'integration_metadata': matching_token.__dict__.get('integration_metadata', {}),
                'service_name': matching_token.__dict__.get('service_name'),
                'user_id': matching_token.__dict__.get('user_id'),
                'access_token': matching_token.__dict__.get('access_token')
            }
            triggers = await IntegrationTrigger.get_integration_triggers_by_integration(db, matching_token_dict['id'])
            
            if not triggers:
                print(f"No triggers configured for Slack integration {matching_token_dict['id']}")
                return
            
            # Process for each configured trigger
            for trigger_dict in triggers:
                try:
                    flow_id = trigger_dict['flow_id']
                    if not flow_id:
                        print(f"Trigger {trigger_dict['id']} has no flow_id")
                        continue
                    
                    # Check if flow exists
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
                    request_data = SimplifiedAPIRequest(
                        message=message_text,
                        flow_id=str(flow_id),
                        session_id=session_id,
                        from_slack=True
                    )
                    
                    # Run the flow
                    try:
                        response = await simple_run_flow(request_data)
                        reply = response.get("response", "No response from flow")
                        
                        # Prepare thread parameters if this is a reply to a thread
                        thread_params = {"thread_ts": thread_ts} if thread_ts else {}
                        
                        # Send the response back to Slack
                        try:
                            # Send message to Slack
                            slack_response = requests.post(
                                "https://slack.com/api/chat.postMessage",
                                headers={"Authorization": f"Bearer {matching_token_dict['access_token']}"},
                                json={
                                    "channel": channel_id,
                                    "text": reply,
                                    **thread_params
                                }
                            )
                            
                            if not slack_response.json().get("ok"):
                                print(f"Error sending message to Slack: {slack_response.json().get('error')}")
                                
                        except Exception as slack_error:
                            print(f"Error sending response to Slack: {str(slack_error)}")
                            
                    except Exception as flow_error:
                        print(f"Error running flow: {str(flow_error)}")
                        
                except Exception as e:
                    print(f"Error processing trigger {trigger_dict.get('id', 'unknown')}: {str(e)}")
                    continue
                    
        except Exception as e:
            print(f"Error in process_slack_message: {str(e)}")
            await db.rollback()
            raise
        finally:
            await db.close()

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
    async with db as session:
        try:
            # Convert token to dict for safe field access
            token_dict = {
                'id': token.__dict__.get('id'),
                'integration_metadata': token.__dict__.get('integration_metadata', {}),
                'service_name': token.__dict__.get('service_name'),
                'user_id': token.__dict__.get('user_id'),
                'access_token': token.__dict__.get('access_token')
            }
            
            # Get access token
            access_token = token_dict['access_token']
            
            # Prepare the request data
            request_data = SimplifiedAPIRequest(
                message=message,
                flow_id=str(flow_id),
                session_id=None,  # Let the system generate one
                from_slack=True
            )
            
            # Run the flow
            try:
                response = await simple_run_flow(request_data)
                reply = response.get("response", "No response from flow")
                
                # Prepare thread parameters if this is a reply to a thread
                thread_params = {"thread_ts": thread_ts} if thread_ts else {}
                
                # Send the response back to Slack
                try:
                    # Send message to Slack
                    slack_response = requests.post(
                        "https://slack.com/api/chat.postMessage",
                        headers={"Authorization": f"Bearer {access_token}"},
                        json={
                            "channel": channel_id,
                            "text": reply,
                            **thread_params
                        }
                    )
                    
                    if not slack_response.json().get("ok"):
                        print(f"Error sending message to Slack: {slack_response.json().get('error')}")
                        
                except Exception as slack_error:
                    print(f"Error sending response to Slack: {str(slack_error)}")
                    
            except Exception as flow_error:
                print(f"Error running flow: {str(flow_error)}")
                # Optionally send error message to Slack
                
        except Exception as e:
            print(f"Error in trigger_flow_for_slack: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()

class IntegrationTrigger:
    @staticmethod
    async def get_integration_triggers_by_integration(
        db: AsyncSession, integration_id: UUID
    ) -> List[Dict]:
        """Get all triggers for a given integration."""
        try:
            async with db as session:
                statement = select(IntegrationTrigger).where(
                    IntegrationTrigger.integration_id == integration_id
                )
                results = await session.exec(statement)
                triggers = results.all()
                
                # Convert SQLAlchemy rows to dictionaries using __dict__ access
                trigger_dicts = []
                for trigger in triggers:
                    trigger_dict = {
                        'id': trigger.__dict__.get('id'),
                        'flow_id': trigger.__dict__.get('flow_id'),
                        'integration_id': trigger.__dict__.get('integration_id'),
                        'trigger_type': trigger.__dict__.get('trigger_type'),
                        'trigger_metadata': trigger.__dict__.get('trigger_metadata', {})
                    }
                    trigger_dicts.append(trigger_dict)
                
                return trigger_dicts
                
        except SQLAlchemyError as e:
            print(f"Database error in get_integration_triggers_by_integration: {str(e)}")
            raise
        except Exception as e:
            print(f"Error in get_integration_triggers_by_integration: {str(e)}")
            raise

@router.post("/slack/watch/{integration_id}")
async def watch_slack(
    integration_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Enable watching user-level events for a Slack integration.
    """
    async with db as session:
        try:
            # Get the integration
            statement = select(IntegrationToken).where(
                IntegrationToken.id == integration_id,
                IntegrationToken.service_name == "slack"
            )
            result = await session.exec(statement)
            integration = result.first()
            
            if not integration:
                raise HTTPException(status_code=404, detail="Integration not found")
            
            # Convert to dict for safe field access
            integration_dict = {
                'id': integration.__dict__.get('id'),
                'integration_metadata': integration.__dict__.get('integration_metadata', {}),
                'service_name': integration.__dict__.get('service_name'),
                'user_id': integration.__dict__.get('user_id'),
                'access_token': integration.__dict__.get('access_token')
            }
            
            # Get access token
            access_token = integration_dict['access_token']
            if not access_token:
                raise HTTPException(status_code=500, detail="Invalid access token")
            
            # Get team info from Slack API
            try:
                response = requests.get(
                    "https://slack.com/api/team.info",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                team_data = response.json()
                if not team_data.get("ok"):
                    print(f"Error getting team info: {team_data.get('error')}")
                    raise HTTPException(status_code=500, detail="Error getting team info from Slack")
                
                team_id = team_data.get("team", {}).get("id")
                if not team_id:
                    raise HTTPException(status_code=500, detail="Could not get team ID from Slack")
                
                # Update metadata to enable user event watching
                metadata = integration_dict['integration_metadata'] or {}
                metadata.update({
                    "team_id": team_id,
                    "watch_user_events": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })
                
                # Update the integration
                integration.integration_metadata = metadata
                await session.commit()
                
                return {
                    "status": "success",
                    "message": "User event watching enabled",
                    "team_id": team_id
                }
                
            except requests.RequestException as e:
                print(f"Error making request to Slack API: {str(e)}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"Response status code: {e.response.status_code}")
                    print(f"Response content: {e.response.text}")
                
                raise HTTPException(status_code=500, detail="Error communicating with Slack")
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"Error in watch_slack: {str(e)}")
            await session.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")
        finally:
            await session.close()

@router.post("/slack/unwatch/{integration_id}")
async def unwatch_slack(
    integration_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Disable watching user-level events for a Slack integration.
    """
    async with db as session:
        try:
            # Get the integration
            statement = select(IntegrationToken).where(
                IntegrationToken.id == integration_id,
                IntegrationToken.service_name == "slack"
            )
            result = await session.exec(statement)
            integration = result.first()
            
            if not integration:
                raise HTTPException(status_code=404, detail="Integration not found")
            
            # Convert to dict for safe field access
            integration_dict = {
                'id': integration.__dict__.get('id'),
                'integration_metadata': integration.__dict__.get('integration_metadata', {}),
                'service_name': integration.__dict__.get('service_name'),
                'user_id': integration.__dict__.get('user_id'),
                'access_token': integration.__dict__.get('access_token')
            }
            
            # Update metadata to disable user event watching
            metadata = integration_dict['integration_metadata'] or {}
            metadata.update({
                "watch_user_events": False,
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            
            # Update the integration
            integration.integration_metadata = metadata
            await session.commit()
            
            return {
                "status": "success",
                "message": "User event watching disabled"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"Error in unwatch_slack: {str(e)}")
            await session.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")
        finally:
            await session.close()

@router.post("/slack/subscription/{integration_id}")
async def create_slack_subscription(
    integration_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Create or update a Slack subscription for the given integration.
    """
    async with db as session:
        try:
            # Get the integration
            statement = select(IntegrationToken).where(
                IntegrationToken.id == integration_id,
                IntegrationToken.service_name == "slack"
            )
            result = await session.exec(statement)
            integration = result.first()
            
            if not integration:
                raise HTTPException(status_code=404, detail="Integration not found")
            
            # Convert to dict for safe field access
            integration_dict = {
                'id': integration.__dict__.get('id'),
                'integration_metadata': integration.__dict__.get('integration_metadata', {}),
                'service_name': integration.__dict__.get('service_name'),
                'user_id': integration.__dict__.get('user_id'),
                'access_token': integration.__dict__.get('access_token')
            }
            
            # Get access token
            access_token = integration_dict['access_token']
            if not access_token:
                raise HTTPException(status_code=500, detail="Invalid access token")
            
            # Get team info from Slack API
            try:
                response = requests.get(
                    "https://slack.com/api/team.info",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                team_data = response.json()
                if not team_data.get("ok"):
                    print(f"Error getting team info: {team_data.get('error')}")
                    raise HTTPException(status_code=500, detail="Error getting team info from Slack")
                
                team_id = team_data.get("team", {}).get("id")
                if not team_id:
                    raise HTTPException(status_code=500, detail="Could not get team ID from Slack")
                
                # Update metadata with subscription info
                metadata = integration_dict['integration_metadata'] or {}
                metadata.update({
                    "team_id": team_id,
                    "subscription_active": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })
                
                # Update the integration
                integration.integration_metadata = metadata
                await session.commit()
                
                return {
                    "status": "success",
                    "message": "Subscription created/updated",
                    "team_id": team_id
                }
                
            except requests.RequestException as e:
                print(f"Error making request to Slack API: {str(e)}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"Response status code: {e.response.status_code}")
                    print(f"Response content: {e.response.text}")
                
                raise HTTPException(status_code=500, detail="Error communicating with Slack")
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"Error in create_slack_subscription: {str(e)}")
            await session.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")
        finally:
            await session.close()

@router.get("/slack/subscription/{integration_id}")
async def get_slack_subscription(
    integration_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Get the Slack subscription for the given integration.
    """
    async with db as session:
        try:
            # Get the integration
            statement = select(IntegrationToken).where(
                IntegrationToken.id == integration_id,
                IntegrationToken.service_name == "slack"
            )
            result = await session.exec(statement)
            integration = result.first()
            
            if not integration:
                raise HTTPException(status_code=404, detail="Integration not found")
            
            # Convert to dict for safe field access
            integration_dict = {
                'id': integration.__dict__.get('id'),
                'integration_metadata': integration.__dict__.get('integration_metadata', {}),
                'service_name': integration.__dict__.get('service_name'),
                'user_id': integration.__dict__.get('user_id'),
                'access_token': integration.__dict__.get('access_token')
            }
            
            # Get metadata
            metadata = integration_dict['integration_metadata'] or {}
            
            return {
                "status": "success",
                "subscription": {
                    "active": metadata.get("subscription_active", False),
                    "team_id": metadata.get("team_id"),
                    "team_name": metadata.get("team_name"),
                    "updated_at": metadata.get("updated_at")
                }
            }
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"Error in get_slack_subscription: {str(e)}")
            await session.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")
        finally:
            await session.close()

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