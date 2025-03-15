from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from uuid import UUID, uuid4

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

import base64
from langflow.api.v1.schemas import SimplifiedAPIRequest
from langflow.services.database.models.user.model import User
from langflow.services.auth.utils import get_current_active_user, oauth2_login, get_current_user_by_jwt
from langflow.services.database.models.flow import Flow
from langflow.services.database.models.integration_token.model import IntegrationToken
from langflow.services.database.models.integration_trigger.model import IntegrationTrigger
from langflow.services.deps import get_session, get_telemetry_service
from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.api.v1.endpoints import simple_run_flow
from langflow.services.database.models.user.crud import (
    create_integration_token,
    get_integration_tokens,
    delete_integration_token,
    get_integration_token_by_id,
    update_integration_token,
    create_integration_trigger
)
from langflow.services.database.models.integration_trigger.crud import get_integration_triggers_by_integration
from langflow.helpers.user import get_user_by_flow_id_or_endpoint_name
from fastapi import BackgroundTasks, Body
from langflow.services.telemetry.schema import RunPayload
from dotenv import load_dotenv
import traceback
import time

router = APIRouter(tags=["HubSpot Integrations"])

# HubSpot API configuration
HUBSPOT_CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID")
HUBSPOT_CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET")
HUBSPOT_REDIRECT_URI = os.getenv("HUBSPOT_REDIRECT_URI", "http://localhost:3000/api/v1/auth/hubspot/callback")

# HubSpot API scopes
# Reference: https://developers.hubspot.com/docs/api/oauth-scopes
HUBSPOT_SCOPES = [
    "oauth",
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.companies.read",
    "crm.objects.companies.write",
    "crm.objects.deals.read",
    "crm.objects.deals.write",
    "crm.schemas.contacts.read",
    "crm.schemas.companies.read",
    "crm.schemas.deals.read",
    "settings.users.read"
]

load_dotenv()

@router.get("/auth/hubspot/login")
async def hubspot_login(
    current_user: User = Depends(oauth2_login),
    db: AsyncSession = Depends(get_session)
):
    """
    Initiates the HubSpot OAuth flow.
    """
    if not HUBSPOT_CLIENT_ID:
        raise HTTPException(status_code=500, detail="HubSpot client ID not configured")
    
    # Generate a state parameter to prevent CSRF
    state = str(uuid4())
    
    # Create the HubSpot OAuth URL
    auth_url = (
        f"https://app.hubspot.com/oauth/authorize"
        f"?client_id={HUBSPOT_CLIENT_ID}"
        f"&scope={'+'.join(HUBSPOT_SCOPES)}"
        f"&redirect_uri={HUBSPOT_REDIRECT_URI}"
        f"&state={state}"
    )
    
    return RedirectResponse(auth_url)

@router.get("/auth/hubspot/callback")
async def hubspot_callback(
    code: str,
    state: str,
    access_token_lf: str = Cookie(None, alias="access_token_lf"),
    db: AsyncSession = Depends(get_session)
):
    """
    Handles the callback from HubSpot OAuth flow.
    """
    try:
        if not access_token_lf:
            logger.error("No access token found in cookies")
            html_content = """
            <html>
                <script type="text/javascript">
                    window.opener.postMessage({ hubspotError: "authentication_required" }, "*");
                    window.close();
                </script>
                <body>Authentication required. Please login first and try again.</body>
            </html>
            """
            return HTMLResponse(content=html_content)

        current_user = await get_current_user_by_jwt(access_token_lf, db)
        logger.info(f"Current user ID: {current_user.id}")
        
        if not HUBSPOT_CLIENT_ID or not HUBSPOT_CLIENT_SECRET:
            logger.error("HubSpot client configuration missing")
            raise HTTPException(status_code=500, detail="HubSpot client configuration missing")

        # Exchange code for token
        logger.info("Sending token request to HubSpot")
        token_url = "https://api.hubapi.com/oauth/v1/token"
        request_data = {
            "grant_type": "authorization_code",
            "client_id": HUBSPOT_CLIENT_ID,
            "client_secret": HUBSPOT_CLIENT_SECRET,
            "code": code,
            "redirect_uri": HUBSPOT_REDIRECT_URI
        }
        
        response = requests.post(
            token_url,
            data=request_data
        )
        
        logger.info(f"HubSpot token response status code: {response.status_code}")
        
        # Process the response from HubSpot
        token_data = response.json()
        
        if "error" in token_data:
            logger.error(f"HubSpot error: {token_data.get('error')}")
            html_content = f"""
            <html>
                <script type="text/javascript">
                    window.opener.postMessage({{ hubspotError: "{token_data.get('error')}" }}, "*");
                    window.close();
                </script>
                <body>HubSpot authentication error: {token_data.get('error')}</body>
            </html>
            """
            return HTMLResponse(content=html_content)

        # Extract token data
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        
        if not access_token:
            logger.error("No access token received from HubSpot")
            raise HTTPException(status_code=400, detail="Failed to retrieve access token")

        # Get HubSpot account info to use as identifier
        hubspot_response = requests.get(
            "https://api.hubapi.com/settings/v3/users",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        hubspot_account_data = hubspot_response.json()
        print(f"HubSpot account data: {hubspot_account_data}")
        
        # Extract user data from the results array
        user_data = {}
        if "results" in hubspot_account_data and hubspot_account_data["results"]:
            user_data = hubspot_account_data["results"][0]
        
        # Extract user information
        email_address = user_data.get("email", "")
        first_name = user_data.get("firstName", "")
        last_name = user_data.get("lastName", "")
        user_id = user_data.get("id", "")
        
        # Get additional account information
        account_info_response = requests.get(
            "https://api.hubapi.com/integrations/v1/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        account_info = {}
        if account_info_response.status_code == 200:
            account_info = account_info_response.json()
            print(f"HubSpot account info: {account_info}")
        
        # Extract account information
        hub_domain = account_info.get("hub_domain", "")
        hub_id = account_info.get("hub_id", "")
        account_type = account_info.get("account_type", "")
        portal_id = account_info.get("portal_id", "")
        
        # Calculate token expiration time
        expires_at = None
        if expires_in:
            # Calculate expiration time (current time + expires_in seconds)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        # Initialize metadata dictionary
        integration_metadata = {
            "hub_domain": hub_domain,
            "hub_id": hub_id,
            "account_type": account_type,
            "portal_id": portal_id,
            "first_name": first_name,
            "last_name": last_name,
            "user_id": user_id
        }
        
        # Save the integration token
        try:
            await create_integration_token(
                db=db,
                user_id=current_user.id,
                service_name="hubspot",
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                email_address=email_address,  # Use email as identifier
                metadata=integration_metadata
            )
            
            # Return success HTML that closes the popup and posts a message to the parent window
            html_content = """
            <html>
                <script type="text/javascript">
                    window.opener.postMessage({ hubspotConnected: true }, "*");
                    window.close();
                </script>
                <body>Authentication complete. You can close this window.</body>
            </html>
            """
            return HTMLResponse(content=html_content)
            
        except Exception as e:
            logger.error(f"Error saving HubSpot integration: {str(e)}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Error saving integration: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in HubSpot callback: {str(e)}")
        traceback.print_exc()
        html_content = f"""
        <html>
            <script type="text/javascript">
                window.opener.postMessage({{ hubspotError: "unexpected_error" }}, "*");
                window.close();
            </script>
            <body>An unexpected error occurred: {str(e)}</body>
        </html>
        """
        return HTMLResponse(content=html_content)

@router.post("/hubspot/webhook")
async def hubspot_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session)
):
    """
    Handle incoming HubSpot webhook events.
    """
    try:
        # Extract the raw body content
        body = await request.body()
        data = json.loads(body)
        
        logger.info(f"Received HubSpot webhook: {data}")
        
        # Process the webhook based on the type
        if "subscriptionType" not in data:
            logger.warning("Invalid HubSpot webhook format")
            return {"status": "error", "message": "Invalid webhook format"}
        
        # Extract HubSpot portal ID from the webhook
        portal_id = data.get("portalId")
        if not portal_id:
            logger.error("No portal ID in webhook data")
            return {"status": "error", "message": "No portal ID provided"}
        
        # Find integration based on portal ID in metadata
        stmt = select(IntegrationToken).where(
            IntegrationToken.service_name == "hubspot",
            IntegrationToken.metadata.contains({"portal_id": str(portal_id)})
        )
        
        result = await db.execute(stmt)
        integration = result.scalars().first()
        
        if not integration:
            logger.error(f"No matching HubSpot integration found for portal ID: {portal_id}")
            return {"status": "error", "message": "No matching integration found"}
        
        # Add to background tasks for async processing
        background_tasks.add_task(
            process_hubspot_webhook,
            data=data,
            integration_id=integration.id,
            db=db
        )
        
        return {"status": "success", "message": "Webhook received and processing"}
    
    except Exception as e:
        logger.error(f"Error processing HubSpot webhook: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

async def process_hubspot_webhook(data: Dict, integration_id: UUID, db: AsyncSession):
    """
    Process a HubSpot webhook event and trigger any associated flows.
    """
    try:
        # Get the integration record
        integration = await get_integration_token_by_id(db, integration_id)
        
        if not integration:
            logger.error(f"Integration not found with ID: {integration_id}")
            return
        
        # Get all triggers associated with this integration
        triggers = await get_integration_triggers_by_integration(db, integration_id)
        
        if not triggers:
            logger.info(f"No triggers configured for HubSpot integration: {integration_id}")
            return
        
        # Get the decrypted token
        try:
            # Primary method to get decrypted token
            decrypted_token = integration.get_token()
            
            # Validate the token format
            if not decrypted_token or not decrypted_token.strip():
                logger.error("Empty token after decryption")
                return
                
        except Exception as token_error:
            logger.error(f"Error decrypting token: {str(token_error)}")
            traceback.print_exc()
            return
        
        # Extract relevant information from the webhook
        event_type = data.get("subscriptionType", "")
        object_id = data.get("objectId", "")
        
        if not event_type or not object_id:
            logger.error("Missing event type or object ID in webhook data")
            return
        
        # Process each trigger
        for trigger in triggers:
            # Get the flow associated with this trigger
            flow_id = getattr(trigger, "flow_id", None)
            
            if not flow_id:
                logger.warning(f"No flow ID found for trigger: {trigger.id}")
                continue
            
            # Get user associated with the flow
            try:
                user = await get_user_by_flow_id_or_endpoint_name(flow_id, None, db)
                if not user:
                    logger.error(f"No user found for flow: {flow_id}")
                    continue
                    
                # Run the flow with the webhook data
                flow = await get_flow_by_id_or_endpoint_name(flow_id, None, db)
                
                if not flow:
                    logger.error(f"Flow not found: {flow_id}")
                    continue
                
                # Construct the message to send to the flow
                message = {
                    "event_type": event_type,
                    "object_id": object_id,
                    "portal_id": data.get("portalId", ""),
                    "event_data": data,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Run the flow
                logger.info(f"Triggering flow {flow_id} for HubSpot event {event_type}")
                telemetry_service = get_telemetry_service()
                
                # Create run payload for telemetry
                if telemetry_service:
                    payload = RunPayload(
                        flow_id=str(flow_id),
                        user_id=str(user.id),
                        client_type="hubspot_trigger"
                    )
                    telemetry_service.register_payload(payload, datetime.now())
                
                # Execute the flow
                api_data = SimplifiedAPIRequest(
                    input=json.dumps(message),
                    user_id=str(user.id)
                )
                await simple_run_flow(api_data, flow_id, db)
                logger.info(f"Successfully executed flow {flow_id} for HubSpot event")
                
            except Exception as flow_error:
                logger.error(f"Error running flow for HubSpot event: {str(flow_error)}")
                traceback.print_exc()
                continue
    
    except Exception as e:
        logger.error(f"Error processing HubSpot webhook: {str(e)}")
        traceback.print_exc()

@router.post("/hubspot/register-webhook")
async def register_hubspot_webhook(
    integration_id: UUID,
    event_types: List[str] = Body(..., description="List of event types to subscribe to"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Register a HubSpot webhook subscription for specific event types.
    """
    try:
        # Verify the integration belongs to the current user
        integration = await get_integration_token_by_id(db, integration_id)
        
        if not integration:
            raise HTTPException(status_code=404, detail="Integration not found")
            
        if integration.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this integration")
            
        if integration.service_name != "hubspot":
            raise HTTPException(status_code=400, detail="Not a HubSpot integration")
        
        # Get the decrypted token
        try:
            # Primary method to get decrypted token
            decrypted_token = integration.get_token()
            
            # Validate the token format
            if not decrypted_token or not decrypted_token.strip():
                logger.error("Empty token after decryption")
                raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        except Exception as token_error:
            logger.error(f"Error decrypting token: {str(token_error)}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        
        # Get the HubSpot app ID from metadata
        portal_id = integration.metadata.get("portal_id")
        if not portal_id:
            raise HTTPException(status_code=400, detail="Portal ID not found in integration metadata")
        
        # Create webhook subscription in HubSpot
        # URL where HubSpot will send webhooks
        webhook_url = f"{os.getenv('WEBHOOKS_BASE_URL', 'http://localhost:3000')}/api/v1/hubspot/webhook"
        
        # Register webhooks for each event type
        subscriptions = []
        
        for event_type in event_types:
            # Make API call to register subscription
            subscription_data = {
                "eventType": event_type,
                "propertyName": "all",  # Subscribe to all property changes
                "active": True,
                "webhookUrl": webhook_url
            }
            
            response = requests.post(
                f"https://api.hubapi.com/webhooks/v1/{portal_id}/subscriptions",
                headers={
                    "Authorization": f"Bearer {decrypted_token}",
                    "Content-Type": "application/json"
                },
                json=subscription_data
            )
            
            if response.status_code >= 400:
                logger.error(f"Error registering HubSpot webhook: {response.text}")
                continue
                
            subscription = response.json()
            subscriptions.append(subscription)
        
        # Update integration metadata with subscription IDs
        new_metadata = integration.metadata or {}
        new_metadata["webhook_subscriptions"] = [s.get("id") for s in subscriptions]
        
        await update_integration_token(
            db=db,
            integration_id=integration_id,
            metadata=new_metadata
        )
        
        return {
            "status": "success",
            "subscriptions": subscriptions
        }
    
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error registering HubSpot webhook: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error registering webhook: {str(e)}")

@router.post("/hubspot/unregister-webhook")
async def unregister_hubspot_webhook(
    integration_id: UUID,
    subscription_ids: List[str] = Body(None, description="List of subscription IDs to unregister"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Unregister HubSpot webhook subscriptions.
    """
    try:
        # Verify the integration belongs to the current user
        integration = await get_integration_token_by_id(db, integration_id)
        
        if not integration:
            raise HTTPException(status_code=404, detail="Integration not found")
            
        if integration.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this integration")
            
        if integration.service_name != "hubspot":
            raise HTTPException(status_code=400, detail="Not a HubSpot integration")
        
        # Get the decrypted token
        try:
            # Primary method to get decrypted token
            decrypted_token = integration.get_token()
            
            # Validate the token format
            if not decrypted_token or not decrypted_token.strip():
                logger.error("Empty token after decryption")
                raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        except Exception as token_error:
            logger.error(f"Error decrypting token: {str(token_error)}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        
        # Get the HubSpot portal ID from metadata
        portal_id = integration.metadata.get("portal_id")
        if not portal_id:
            raise HTTPException(status_code=400, detail="Portal ID not found in integration metadata")
        
        # If no specific subscriptions provided, get all from metadata
        if not subscription_ids and integration.metadata and "webhook_subscriptions" in integration.metadata:
            subscription_ids = integration.metadata["webhook_subscriptions"]
        
        if not subscription_ids:
            return {"status": "success", "message": "No subscriptions to delete"}
        
        # Delete each subscription
        results = []
        for subscription_id in subscription_ids:
            response = requests.delete(
                f"https://api.hubapi.com/webhooks/v1/{portal_id}/subscriptions/{subscription_id}",
                headers={"Authorization": f"Bearer {decrypted_token}"}
            )
            
            results.append({
                "subscription_id": subscription_id,
                "success": response.status_code < 400,
                "status_code": response.status_code
            })
        
        # Update integration metadata
        if integration.metadata and "webhook_subscriptions" in integration.metadata:
            new_metadata = integration.metadata.copy()
            new_metadata["webhook_subscriptions"] = []
            
            await update_integration_token(
                db=db,
                integration_id=integration_id,
                metadata=new_metadata
            )
        
        return {
            "status": "success",
            "results": results
        }
    
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error unregistering HubSpot webhook: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error unregistering webhook: {str(e)}")

@router.post("/create-integration-trigger/hubspot")
async def create_hubspot_integration_trigger(
    integration_id: UUID,
    flow_id: UUID,
    event_types: List[str] = Body(..., description="HubSpot event types to trigger on"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Create a new integration trigger linking a flow to a HubSpot integration.
    """
    try:
        # Verify the integration belongs to the current user
        integration = await get_integration_token_by_id(db, integration_id)
        if not integration:
            raise HTTPException(status_code=404, detail="Integration not found")
            
        if integration.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this integration")
            
        if integration.service_name != "hubspot":
            raise HTTPException(status_code=400, detail="Not a HubSpot integration")
        
        # Verify the flow exists and belongs to the user
        flow = await get_flow_by_id_or_endpoint_name(flow_id, None, db)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
            
        flow_user = await get_user_by_flow_id_or_endpoint_name(flow_id, None, db)
        if not flow_user or flow_user.id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this flow")
        
        # Create the trigger
        trigger_data = {
            "event_types": event_types
        }
        
        trigger = await create_integration_trigger(
            db=db,
            integration_id=integration_id,
            flow_id=flow_id,
            trigger_data=trigger_data
        )
        
        # Register webhooks if needed - you might want to automatically register webhooks
        # or let this be a separate step
        
        return {
            "status": "success",
            "trigger_id": trigger.id,
            "message": "Integration trigger created successfully"
        }
    
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error creating HubSpot integration trigger: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating integration trigger: {str(e)}")

async def refresh_hubspot_token(db: AsyncSession, token_obj: IntegrationToken) -> str:
    """
    Refreshes the HubSpot OAuth token using the refresh token.
    Returns the new access token if successful, or raises an HTTPException if it fails.
    """
    if not HUBSPOT_CLIENT_ID or not HUBSPOT_CLIENT_SECRET:
        logger.error("HubSpot client configuration missing")
        raise HTTPException(status_code=500, detail="HubSpot client configuration missing")
    
    try:
        refresh_token = token_obj.refresh_token
        if not refresh_token:
            logger.error("No refresh token available for HubSpot integration")
            raise HTTPException(status_code=500, detail="No refresh token available")
        
        # Prepare the token refresh request
        token_url = "https://api.hubapi.com/oauth/v1/token"
        request_data = {
            "grant_type": "refresh_token",
            "client_id": HUBSPOT_CLIENT_ID,
            "client_secret": HUBSPOT_CLIENT_SECRET,
            "refresh_token": refresh_token
        }
        
        logger.info(f"Refreshing HubSpot token for integration ID: {token_obj.id}")
        response = requests.post(
            token_url,
            data=request_data
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to refresh HubSpot token: {response.text}")
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"Failed to refresh HubSpot token: {response.text}"
            )
        
        # Process the response
        token_data = response.json()
        new_access_token = token_data.get("access_token")
        new_refresh_token = token_data.get("refresh_token", refresh_token)
        expires_in = token_data.get("expires_in")
        
        if not new_access_token:
            logger.error("No access token received from HubSpot refresh")
            raise HTTPException(status_code=500, detail="Failed to retrieve new access token")
        
        # Calculate new expiration time
        expires_at = None
        if expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        # Update the token in the database
        stmt = update(IntegrationToken).where(
            IntegrationToken.id == token_obj.id
        ).values(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_at=expires_at
        )
        
        await db.execute(stmt)
        await db.commit()
        
        logger.info(f"HubSpot token refreshed successfully. New expiration: {expires_at}")
        return new_access_token
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing HubSpot token: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error refreshing token: {str(e)}")

@router.get("/hubspot/contacts")
async def get_hubspot_contacts(
    limit: int = 10,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Get contacts from HubSpot for the authenticated user.
    """
    try:
        # Get HubSpot integrations for the user
        tokens = await get_integration_tokens(db, current_user.id)
        hubspot_token = next((token for token in tokens if token.service_name == "hubspot"), None)
        
        if not hubspot_token:
            raise HTTPException(status_code=401, detail="HubSpot not connected")
        
        # Check if token is expired before making the API call
        should_refresh = False
        if hubspot_token.expires_at:
            now = datetime.now(timezone.utc)
            
            # Convert expires_at to timezone-aware if it's naive
            token_expires_at = hubspot_token.expires_at
            if token_expires_at.tzinfo is None:
                # If the token's expires_at is naive, assume it's in UTC
                token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)
            
            logger.info(f"Token expires at: {token_expires_at}, Current time: {now}")
            
            if token_expires_at <= now:
                logger.info(f"HubSpot token expired at {token_expires_at}. Current time: {now}")
                should_refresh = True
        
        # Get the decrypted token
        try:
            if should_refresh:
                logger.info("Refreshing expired HubSpot token before API call")
                decrypted_token = await refresh_hubspot_token(db, hubspot_token)
            else:
                decrypted_token = hubspot_token.get_token()
            
            if not decrypted_token:
                raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error decrypting token: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        
        # Query HubSpot API for contacts
        response = requests.get(
            f"https://api.hubapi.com/crm/v3/objects/contacts?limit={limit}&after={offset}",
            headers={
                "Authorization": f"Bearer {decrypted_token}",
                "Content-Type": "application/json"
            }
        )
        
        # Handle token expiration
        if response.status_code == 401:
            try:
                # Error response might indicate token expiration
                error_data = response.json()
                error_message = error_data.get("message", "")
                
                if "expired" in error_message.lower() or error_data.get("category") == "EXPIRED_AUTHENTICATION":
                    logger.info("Token expired according to HubSpot API. Refreshing token and retrying.")
                    new_token = await refresh_hubspot_token(db, hubspot_token)
                    
                    # Retry the request with the new token
                    response = requests.get(
                        f"https://api.hubapi.com/crm/v3/objects/contacts?limit={limit}&after={offset}",
                        headers={
                            "Authorization": f"Bearer {new_token}",
                            "Content-Type": "application/json"
                        }
                    )
            except Exception as refresh_error:
                logger.error(f"Error during token refresh after 401: {str(refresh_error)}")
        
        if response.status_code >= 400:
            logger.error(f"Error fetching HubSpot contacts: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"HubSpot API error: {response.text}")
            
        return response.json()
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error fetching HubSpot contacts: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching contacts: {str(e)}")

@router.get("/hubspot/deals")
async def get_hubspot_deals(
    limit: int = 10,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Get deals from HubSpot for the authenticated user.
    """
    try:
        # Get HubSpot integrations for the user
        tokens = await get_integration_tokens(db, current_user.id)
        hubspot_token = next((token for token in tokens if token.service_name == "hubspot"), None)
        
        if not hubspot_token:
            raise HTTPException(status_code=401, detail="HubSpot not connected")
        
        # Check if token is expired before making the API call
        should_refresh = False
        if hubspot_token.expires_at:
            now = datetime.now(timezone.utc)
            
            # Convert expires_at to timezone-aware if it's naive
            token_expires_at = hubspot_token.expires_at
            if token_expires_at.tzinfo is None:
                # If the token's expires_at is naive, assume it's in UTC
                token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)
            
            logger.info(f"Token expires at: {token_expires_at}, Current time: {now}")
            
            if token_expires_at <= now:
                logger.info(f"HubSpot token expired at {token_expires_at}. Current time: {now}")
                should_refresh = True
        
        # Get the decrypted token
        try:
            if should_refresh:
                logger.info("Refreshing expired HubSpot token before API call")
                decrypted_token = await refresh_hubspot_token(db, hubspot_token)
            else:
                decrypted_token = hubspot_token.get_token()
            
            if not decrypted_token:
                raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error decrypting token: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        
        # Query HubSpot API for deals
        response = requests.get(
            f"https://api.hubapi.com/crm/v3/objects/deals?limit={limit}&after={offset}",
            headers={
                "Authorization": f"Bearer {decrypted_token}",
                "Content-Type": "application/json"
            }
        )
        
        # Handle token expiration
        if response.status_code == 401:
            try:
                # Error response might indicate token expiration
                error_data = response.json()
                error_message = error_data.get("message", "")
                
                if "expired" in error_message.lower() or error_data.get("category") == "EXPIRED_AUTHENTICATION":
                    logger.info("Token expired according to HubSpot API. Refreshing token and retrying.")
                    new_token = await refresh_hubspot_token(db, hubspot_token)
                    
                    # Retry the request with the new token
                    response = requests.get(
                        f"https://api.hubapi.com/crm/v3/objects/deals?limit={limit}&after={offset}",
                        headers={
                            "Authorization": f"Bearer {new_token}",
                            "Content-Type": "application/json"
                        }
                    )
            except Exception as refresh_error:
                logger.error(f"Error during token refresh after 401: {str(refresh_error)}")
        
        if response.status_code >= 400:
            logger.error(f"Error fetching HubSpot deals: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"HubSpot API error: {response.text}")
            
        return response.json()
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error fetching HubSpot deals: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching deals: {str(e)}")
