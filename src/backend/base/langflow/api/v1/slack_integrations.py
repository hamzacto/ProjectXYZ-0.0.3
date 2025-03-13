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
from sqlalchemy import update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import base64
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
from langflow.services.deps import get_session, get_telemetry_service
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
    "users.profile:read",
    "team:read"
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
async def slack_webhook(request: Request, db: AsyncSession = Depends(get_session)):
    """
    Handle incoming Slack webhook events.
    """
    try:
        # Get the raw body
        body = await request.body()
        raw_body = body.decode('utf-8')
        
        print("\n===== RECEIVED SLACK WEBHOOK =====")
        print(f"Raw body: {raw_body}")
        
        # Parse the JSON data
        try:
            data = json.loads(raw_body)
            print(f"Parsed webhook data: {json.dumps(data, indent=2)}")
        except json.JSONDecodeError:
            print("Error decoding JSON")
            return {"status": "error", "message": "Invalid JSON"}
        
        # Handle URL verification challenge
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            print(f"Received URL verification challenge: {challenge}")
            return {"challenge": challenge}
        
        # Handle event callbacks
        if data.get("type") == "event_callback":
            print("\n===== PROCESSING EVENT CALLBACK =====")
            event = data.get("event", {})
            event_type = event.get("type")
            print(f"Event type: {event_type}")
            print(f"Event details: {json.dumps(event, indent=2)}")
            
            # Handle message events
            if event_type == "message" and "bot_id" not in event:
                print("\n===== PROCESSING USER MESSAGE =====")
                # Process the message asynchronously
                import asyncio
                asyncio.create_task(process_user_slack_message(data, db))
            
        # Always return a 200 OK to acknowledge receipt
        return {"status": "ok"}
        
    except Exception as e:
        print(f"Error in slack_webhook: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

async def process_user_slack_message(data, db=None):
    """
    Process a user message from Slack.
    """
    try:
        print("\n===== PROCESSING USER SLACK MESSAGE =====")
        team_id = data.get("team_id")
        print(f"Processing message for team_id: {team_id}")
        
        # Create a new database session instead of reusing the one from the webhook handler
        from langflow.services.deps import get_db_service
        async with get_db_service().with_session() as new_db:
            # Get all Slack integrations
            from sqlalchemy import select
            
            statement = select(IntegrationToken).where(IntegrationToken.service_name == "slack")
            results = await new_db.execute(statement)
            integrations = results.scalars().all()
            
            print(f"Found {len(integrations)} Slack integrations")
            
            valid_integrations = []
            for integration in integrations:
                try:
                    # Safely access integration fields using getattr
                    integration_id = getattr(integration, "id", None)
                    metadata = getattr(integration, "integration_metadata", {}) or {}
                    service_name = getattr(integration, "service_name", None)
                    user_id = getattr(integration, "user_id", None)
                    access_token = getattr(integration, "access_token", None)
                    
                    print(f"Integration ID: {integration_id}")
                    print(f"Integration metadata: {metadata}")
                    print(f"Service name: {service_name}")
                    print(f"User ID: {user_id}")
                    print(f"Has access token: {access_token is not None}")
                    
                    # Check if the integration has the required metadata
                    integration_team_id = metadata.get("team_id")
                    watch_user_events = metadata.get("watch_user_events", False)
                    
                    print(f"Integration team_id: {integration_team_id}")
                    print(f"Watch user events: {watch_user_events}")
                    
                    # Check if this integration is for the team that sent the message and is watching user events
                    if integration_team_id == team_id and watch_user_events:
                        print(f"Found valid integration: {integration_id}")
                        valid_integrations.append(integration)
                except Exception as e:
                    print(f"Error processing integration: {str(e)}")
                    traceback.print_exc()
            
            print(f"Found {len(valid_integrations)} valid integrations for team_id {team_id}")
            
            # Process each valid integration
            for integration in valid_integrations:
                try:
                    # Get the decrypted access token
                    try:
                        # Try to get the token using the get_token method
                        decrypted_token = integration.get_token()
                        print(f"Successfully decrypted token using get_token()")
                    except Exception as e:
                        print(f"Error using get_token(): {str(e)}")
                        # Fall back to manual decryption
                        from langflow.services.database.models.integration_token.model import decrypt_token
                        decrypted_token = decrypt_token(integration.access_token)
                        print(f"Successfully decrypted token using decrypt_token()")
                    
                    # Validate the token format
                    if decrypted_token and (decrypted_token.startswith("xoxp-") or decrypted_token.startswith("xoxb-")):
                        print(f"Token validation passed")
                        # Process the message with the valid integration
                        event = data.get("event", {})
                        await process_slack_message(event, integration, decrypted_token, new_db)
                    else:
                        print(f"Invalid token format: {decrypted_token[:5]}... (token doesn't start with xoxp- or xoxb-)")
                except Exception as e:
                    print(f"Error processing integration {getattr(integration, 'id', 'unknown')}: {str(e)}")
                    traceback.print_exc()
    except Exception as e:
        print(f"Error in process_user_slack_message: {str(e)}")
        traceback.print_exc()

async def process_slack_message(
    event: Dict,
    integration: IntegrationToken,
    decrypted_token: str,
    db: AsyncSession
):
    """
    Process a Slack message and trigger any associated flows.
    """
    try:
        print("\n===== PROCESSING SLACK MESSAGE =====")
        
        # Extract message details
        channel = event.get("channel")
        text = event.get("text", "")
        user = event.get("user")
        
        print(f"Channel: {channel}")
        print(f"Text: {text}")
        print(f"User: {user}")
        
        # Get the integration ID
        integration_id = getattr(integration, "id", None)
        if not integration_id:
            print("No integration ID found")
            return
        
        print(f"Processing for integration ID: {integration_id}")
        
        # Get triggers for this integration
        from langflow.services.database.models.integration_trigger.model import IntegrationTrigger
        from sqlalchemy import select
        
        statement = select(IntegrationTrigger).where(
            IntegrationTrigger.integration_id == integration_id
        )
        results = await db.execute(statement)
        triggers = results.scalars().all()
        
        print(f"Found {len(triggers)} triggers for integration {integration_id}")
        
        # Process each trigger
        for trigger in triggers:
            try:
                trigger_id = getattr(trigger, "id", None)
                flow_id = getattr(trigger, "flow_id", None)
                
                print(f"Processing trigger: {trigger_id} for flow: {flow_id}")
                
                # Get the flow from the database
                from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
                from langflow.api.v1.schemas import SimplifiedAPIRequest
                
                # Get the flow by ID
                flow = await get_flow_by_id_or_endpoint_name(flow_id_or_name=str(flow_id))
                if not flow:
                    print(f"Flow {flow_id} not found")
                    continue
                
                # Create a simplified API request with the message text as input
                input_request = SimplifiedAPIRequest(
                    input_value="New Slack message received. Here is the message content:\n\n" + text,
                    input_type="chat",
                    output_type="chat"
                )
                
                # Execute the flow
                print(f"Executing flow {flow_id} with input: {text}")
                try:
                    # Use the simple_run_flow function to execute the flow
                    from langflow.api.v1.endpoints import simple_run_flow
                    response = await simple_run_flow(
                        flow=flow,
                        input_request=input_request,
                        stream=False
                    )
                    
                    print(f"Flow execution completed: {response}")
                    
                    # Extract the response from the flow execution
                    flow_response = None
                    if response and response.outputs and len(response.outputs) > 0:
                        # Get the first output
                        first_output = response.outputs[0]
                        # If there's a value, use it as the response
                        if first_output and len(first_output) > 0 and "value" in first_output[0]:
                            flow_response = first_output[0]["value"]
                    
                    # Send the response back to Slack
                    if flow_response:
                        print(f"Sending response to Slack: {flow_response}")
                        
                        # Use the Slack API to send a message back to the channel
                        import requests
                        slack_response = requests.post(
                            "https://slack.com/api/chat.postMessage",
                            headers={"Authorization": f"Bearer {decrypted_token}"},
                            json={
                                "channel": channel,
                                "text": str(flow_response),
                                "thread_ts": event.get("thread_ts") or event.get("ts")
                            }
                        )
                        
                        print(f"Slack API response: {slack_response.status_code} {slack_response.text}")
                    else:
                        print("No response to send back to Slack")
                
                except Exception as e:
                    print(f"Error executing flow {flow_id}: {str(e)}")
                    traceback.print_exc()
            
            except Exception as e:
                print(f"Error processing trigger {trigger_id}: {str(e)}")
                traceback.print_exc()
                
    except Exception as e:
        print(f"Error in process_slack_message: {str(e)}")
        traceback.print_exc()

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
            telemetry_service = get_telemetry_service()
            # Convert token to dict for safe field access
            token_dict = {
                'id': token.id,
                'integration_metadata': token.integration_metadata,
                'service_name': token.service_name,
                'user_id': token.user_id,
                'access_token': token.access_token
            }
            
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

                end_time = time.perf_counter()  
                await telemetry_service.log_package_run(    
                    RunPayload(
                        run_is_webhook=True,
                        run_seconds=int(end_time - start_time),
                        run_success=True,
                        run_error_message=""
                    )
                )

                return response
            except Exception as flow_error:
                await telemetry_service.log_package_run(
                RunPayload(
                    run_is_webhook=True,
                    run_seconds=int(time.perf_counter() - start_time),
                    run_success=False,
                    run_error_message=str(e)
                )
            )
            raise
                
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
                
                # Convert SQLAlchemy rows to dictionaries using getattr
                trigger_dicts = []
                for trigger in triggers:
                    trigger_dict = {
                        'id': getattr(trigger, 'id', None),
                        'flow_id': getattr(trigger, 'flow_id', None),
                        'integration_id': getattr(trigger, 'integration_id', None),
                        'trigger_type': getattr(trigger, 'trigger_type', None),
                        'trigger_metadata': getattr(trigger, 'trigger_metadata', {})
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
    # Fetch integration token from DB and ensure it belongs to the authenticated user
    integration = await get_integration_token_by_id(db=db, token_id=integration_id)
    if not integration or integration.service_name != "slack" or integration.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Slack integration not found or unauthorized")
    
    try:
        # Get access token directly from the integration object and decrypt it
        encrypted_token = integration.access_token
        if not encrypted_token:
            raise HTTPException(status_code=500, detail="Invalid access token")
        
        # Decrypt the token using the get_token method from the model
        decrypted_token = integration.get_token()
        
        # Fallback to manual decryption if the get_token method doesn't work
        if not decrypted_token or not (decrypted_token.startswith('xoxp-') or decrypted_token.startswith('xoxb-')):
            try:
                from langflow.services.database.models.integration_token.model import decrypt_token
                decrypted_token = decrypt_token(encrypted_token)
                print("Token manually decrypted")
            except Exception as e:
                print(f"Error decrypting token: {str(e)}")
                # If all decryption methods fail, we'll use the original token
                decrypted_token = encrypted_token
        
        # Get team info from Slack API
        response = requests.get(
            "https://slack.com/api/team.info",
            headers={"Authorization": f"Bearer {decrypted_token}"}
        )
        team_data = response.json()
        if not team_data.get("ok"):
            print(f"Error getting team info: {team_data.get('error')}")
            raise HTTPException(status_code=500, detail="Error getting team info from Slack")
        
        team_id = team_data.get("team", {}).get("id")
        if not team_id:
            raise HTTPException(status_code=500, detail="Could not get team ID from Slack")
        
        # Get current metadata
        current_metadata = integration.integration_metadata or {}
        if not isinstance(current_metadata, dict):
            current_metadata = {}
        
        # Update with new values
        current_metadata.update({
            "team_id": team_id,
            "watch_user_events": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })

        print("Current metadata:", current_metadata)        

        # Update the integration directly
        integration.integration_metadata = current_metadata
        integration.updated_at = datetime.now(timezone.utc)
        await update_integration_token(db=db, token_id=integration_id, token=integration)
        
        return {
            "status": "success",
            "message": "User event watching enabled",
            "team_id": team_id,
            "metadata": current_metadata
        }
    
    except requests.RequestException as e:
        print(f"Error making request to Slack API: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response content: {e.response.text}")
        raise HTTPException(status_code=500, detail="Error communicating with Slack")
    except Exception as e:
        print(f"Error in watch_slack: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating integration: " + str(e))

@router.post("/slack/unwatch/{integration_id}")
async def unwatch_slack(
    integration_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Disable watching user-level events for a Slack integration.
    """
    # Fetch integration token from DB and ensure it belongs to the authenticated user
    integration = await get_integration_token_by_id(db=db, token_id=integration_id)
    if not integration or integration.service_name != "slack" or integration.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Slack integration not found or unauthorized")
    
    try:
        # Update metadata to disable user event watching
        metadata = integration.integration_metadata or {}
        metadata.update({
            "watch_user_events": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Update the integration directly
        integration.integration_metadata = metadata
        integration.updated_at = datetime.now(timezone.utc)
        await update_integration_token(db=db, token_id=integration_id, token=integration)
        
        return {
            "status": "success",
            "message": "User event watching disabled"
        }
    except Exception as e:
        print(f"Error in unwatch_slack: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating integration: " + str(e))

@router.post("/slack/subscription/{integration_id}")
async def create_slack_subscription(
    integration_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a subscription for a Slack integration.
    """
    # Fetch integration token from DB and ensure it belongs to the authenticated user
    integration = await get_integration_token_by_id(db=db, token_id=integration_id)
    if not integration or integration.service_name != "slack" or integration.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Slack integration not found or unauthorized")
    
    try:
        # Get access token directly from the integration object and decrypt it
        encrypted_token = integration.access_token
        if not encrypted_token:
            raise HTTPException(status_code=500, detail="Invalid access token")
        
        # Decrypt the token using the get_token method from the model
        decrypted_token = integration.get_token()
        
        # Fallback to manual decryption if the get_token method doesn't work
        if not decrypted_token or not (decrypted_token.startswith('xoxp-') or decrypted_token.startswith('xoxb-')):
            try:
                from langflow.services.database.models.integration_token.model import decrypt_token
                decrypted_token = decrypt_token(encrypted_token)
                print("Token manually decrypted")
            except Exception as e:
                print(f"Error decrypting token: {str(e)}")
                # If all decryption methods fail, we'll use the original token
                decrypted_token = encrypted_token
        
        # Get team info from Slack API
        response = requests.get(
            "https://slack.com/api/team.info",
            headers={"Authorization": f"Bearer {decrypted_token}"}
        )
        team_data = response.json()
        if not team_data.get("ok"):
            print(f"Error getting team info: {team_data.get('error')}")
            raise HTTPException(status_code=500, detail="Error getting team info from Slack")
        
        team_id = team_data.get("team", {}).get("id")
        if not team_id:
            raise HTTPException(status_code=500, detail="Could not get team ID from Slack")
        
        # Update metadata with subscription info
        metadata = integration.integration_metadata or {}
        metadata.update({
            "team_id": team_id,
            "subscription_active": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Update the integration directly
        integration.integration_metadata = metadata
        integration.updated_at = datetime.now(timezone.utc)
        await update_integration_token(db=db, token_id=integration_id, token=integration)
        
        return {
            "status": "success",
            "message": "Subscription created",
            "team_id": team_id
        }
        
    except requests.RequestException as e:
        print(f"Error making request to Slack API: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response content: {e.response.text}")
        raise HTTPException(status_code=500, detail="Error communicating with Slack")
    except Exception as e:
        print(f"Error in create_slack_subscription: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating integration: " + str(e))

@router.get("/slack/subscription/{integration_id}")
async def get_slack_subscription(
    integration_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get subscription status for a Slack integration.
    """
    # Fetch integration token from DB and ensure it belongs to the authenticated user
    integration = await get_integration_token_by_id(db=db, token_id=integration_id)
    if not integration or integration.service_name != "slack" or integration.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Slack integration not found or unauthorized")
    
    try:
        # Get metadata
        metadata = integration.integration_metadata or {}
        
        return {
            "status": "success",
            "subscription_active": metadata.get("subscription_active", False),
            "team_id": metadata.get("team_id", ""),
            "metadata": metadata
        }
    except Exception as e:
        print(f"Error in get_slack_subscription: {str(e)}")
        raise HTTPException(status_code=500, detail="Error getting subscription: " + str(e))

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