from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from uuid import UUID, uuid4

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Cookie, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import base64
from langflow.api.v1.schemas import SimplifiedAPIRequest
from langflow.services.database.models.user.model import User
from langflow.services.auth.utils import get_current_active_user, oauth2_login, get_current_user_by_jwt
from langflow.services.database.models.flow import Flow
from langflow.services.database.models.integration_token.model import IntegrationToken, decrypt_token
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
from redis import asyncio as aioredis
from contextlib import asynccontextmanager

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

redis = aioredis.from_url("redis://localhost:6379")

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
        print(f"Current user ID: {current_user.id}")
        
        if not HUBSPOT_CLIENT_ID or not HUBSPOT_CLIENT_SECRET:
            logger.error("HubSpot client configuration missing")
            raise HTTPException(status_code=500, detail="HubSpot client configuration missing")

        # Exchange code for token
        print("Sending token request to HubSpot")
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
        
        print(f"HubSpot token response status code: {response.status_code}")
        
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

@router.post("/hubspot/events")
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
        import json
        from sqlalchemy import select
        body = await request.body()
        data = json.loads(body)
        
        print(f"Received HubSpot webhook: {data}")
        
        # Process the webhook based on the type
        # HubSpot webhooks can come as a list of events
        if isinstance(data, list) and len(data) > 0:
            # Use the first event in the list
            event = data[0]
            if "subscriptionType" not in event:
                print("Invalid HubSpot webhook format - missing subscriptionType in event")
                return {"status": "error", "message": "Invalid webhook format"}
            
            # Extract HubSpot portal ID from the webhook
            portal_id = event.get("portalId")
            if not portal_id:
                logger.error("No portal ID in webhook data")
                return {"status": "error", "message": "No portal ID provided"}
        elif isinstance(data, dict) and "subscriptionType" in data:
            # Single event format
            event = data
            portal_id = data.get("portalId")
            if not portal_id:
                logger.error("No portal ID in webhook data")
                return {"status": "error", "message": "No portal ID provided"}
        else:
            print("Invalid HubSpot webhook format - unexpected data structure")
            return {"status": "error", "message": "Invalid webhook format"}
        
        # Find integration based on portal ID in metadata
        # First try to find by portal ID in metadata
        stmt = select(IntegrationToken).where(
            IntegrationToken.service_name == "hubspot"
        )
        
        # Use exec() instead of execute() as recommended by SQLModel
        result = await db.exec(stmt)
        integrations = result.all()
        print(f"Found {len(integrations)} HubSpot integrations")
        # Debug the integrations
        for i, integ in enumerate(integrations):
            print(f"Integration #{i+1} details:")
            print(f"  - Type: {type(integ)}")
            print(f"  - Dir: {dir(integ)}")
            
            # Try multiple ways to extract the ID
            integ_id = None
            
            # Method 1: Direct attribute access (works for SQLModel objects)
            try:
                if hasattr(integ, "id"):
                    integ_id = integ.id
                    print(f"Got ID via direct access: {integ_id}")
            except Exception as e:
                print(f"Error with direct ID access: {str(e)}")
            
            # Method 2: If it's a tuple/list (common for SQLAlchemy results)
            if not integ_id and isinstance(integ, (tuple, list)) and len(integ) > 0:
                try:
                    # First element is often the model object
                    if hasattr(integ[0], "id"):
                        integ_id = integ[0].id
                        print(f"Got ID from tuple[0]: {integ_id}")
                except Exception as e:
                    print(f"Error getting ID from tuple: {str(e)}")
        
        # If no integrations found, return error
        if not integrations:
            logger.error(f"No HubSpot integrations found")
            return {"status": "error", "message": "No HubSpot integrations configured"}
            
        # Find the integration with matching portal_id in metadata
        integration = None
        integration_id = None
        portal_id_str = str(portal_id)
        print(f"Looking for HubSpot integration with portal ID: {portal_id_str}")
        
        # First pass: Look for exact match in metadata
        for integ in integrations:
            # Try multiple ways to extract the ID
            integ_id = None
            
            # Method 1: Direct attribute access (works for SQLModel objects)
            try:
                if hasattr(integ, "id"):
                    integ_id = integ.id
            except Exception:
                pass
            
            # Method 2: If it's a tuple/list (common for SQLAlchemy results)
            if not integ_id and isinstance(integ, (tuple, list)) and len(integ) > 0:
                try:
                    # First element is often the model object
                    if hasattr(integ[0], "id"):
                        integ_id = integ[0].id
                except Exception:
                    pass
            
            # Safely access metadata using getattr
            metadata_dict = None
            try:
                # Try direct access first
                if hasattr(integ, "metadata"):
                    metadata_dict = integ.metadata
                # If integ is a tuple, try the first element
                elif isinstance(integ, (tuple, list)) and len(integ) > 0 and hasattr(integ[0], "metadata"):
                    metadata_dict = integ[0].metadata
            except Exception:
                pass
            
            # Ensure metadata is a dict
            if metadata_dict is None:
                metadata_dict = {}
            elif not isinstance(metadata_dict, dict):
                try:
                    # Try to convert to dict if it's a string
                    if isinstance(metadata_dict, str):
                        import json
                        metadata_dict = json.loads(metadata_dict)
                    else:
                        metadata_dict = {}
                except:
                    metadata_dict = {}
            
            print(f"Integration ID: {integ_id}, metadata type: {type(metadata_dict)}")
            
            if isinstance(metadata_dict, dict):
                stored_portal_id = metadata_dict.get("portal_id")
                if stored_portal_id and (str(stored_portal_id) == portal_id_str):
                    integration = integ
                    integration_id = integ_id
                    print(f"Found exact matching integration by portal ID: {integ_id}")
                    break
        
        # If no integration found by exact match, use the first available HubSpot integration
        if not integration and integrations:
            integration = integrations[0]
            
            # Extract the integration ID properly from the SQLAlchemy Row
            if isinstance(integration, (tuple, list)):
                # If it's a tuple or list, the first element is the model
                if len(integration) > 0:
                    # Try accessing through item access first (t[0] for SQLAlchemy Row)
                    try:
                        integration_model = integration[0]
                        if hasattr(integration_model, "id"):
                            integration_id = integration_model.id
                            print(f"Got integration ID from tuple[0].id: {integration_id}")
                    except (IndexError, AttributeError) as e:
                        print(f"Error getting ID from tuple[0]: {str(e)}")
            
            # For SQLAlchemy Row objects, use item property access
            if not integration_id and hasattr(integration, "_mapping"):
                try:
                    # SQLAlchemy Row objects have a _mapping attribute
                    if "id" in integration._mapping:
                        integration_id = integration._mapping["id"]
                        print(f"Got integration ID from _mapping['id']: {integration_id}")
                except Exception as e:
                    print(f"Error getting ID from _mapping: {str(e)}")
                    
            # Try getattr with direct access
            if not integration_id:
                try:
                    integration_id = getattr(integration, "id", None)
                    if integration_id:
                        print(f"Got integration ID via getattr: {integration_id}")
                except Exception as e:
                    print(f"Error with getattr ID access: {str(e)}")
            
            # Direct item access for SQLAlchemy Row
            if not integration_id and hasattr(integration, "__getitem__"):
                try:
                    # Don't use direct dictionary-style access for SQLAlchemy Row objects
                    # integration_id = integration["id"]  # This causes the error
                    
                    # Instead, use the _mapping attribute or getattr for SQLAlchemy Row objects
                    if hasattr(integration, "_mapping"):
                        integration_id = integration._mapping.get("id")
                    elif hasattr(integration, "IntegrationToken"):
                        # For Row objects that have the model as a named attribute
                        integration_id = getattr(getattr(integration, "IntegrationToken", None), "id", None)
                    
                    if integration_id:
                        print(f"Got integration ID via safe item access: {integration_id}")
                except (KeyError, TypeError, IndexError) as e:
                    print(f"Error with item access: {str(e)}")
            
            # Try to inspect what fields are available in the integration object
            print(f"Integration object inspection:")
            
            # Check if it has _asdict method (named tuple/row interface)
            if hasattr(integration, "_asdict") and callable(getattr(integration, "_asdict")):
                try:
                    mapping = integration._asdict()
                    print(f"Integration _asdict keys: {list(mapping.keys())}")
                    if "id" in mapping:
                        integration_id = mapping["id"]
                        print(f"Got integration ID from _asdict: {integration_id}")
                except Exception as e:
                    print(f"Error with _asdict: {str(e)}")
                
            # If we still don't have an ID, try to extract from the first item
            if not integration_id:
                try:
                    # For Row objects, try the first item which might be the model
                    first_item = next(iter(integration))
                    if hasattr(first_item, "id"):
                        integration_id = first_item.id
                        print(f"Got integration ID from first iter item: {integration_id}")
                except Exception as e:
                    print(f"Error getting first item: {str(e)}")
                    
            # As last resort, extract UUIDs from string representation but avoid the user_id
            if not integration_id and hasattr(integration, "__str__"):
                try:
                    str_rep = str(integration)
                    print(f"Integration string representation: {str_rep}")
                    # Look for IDs but avoid user_id
                    import re
                    uuid_pattern = r'id=UUID\([\'"]([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})[\'"]\)'
                    matches = re.findall(uuid_pattern, str_rep)
                    
                    if matches:
                        for match in matches:
                            # Convert string to UUID object
                            from uuid import UUID
                            potential_id = UUID(match)
                            print(f"Found potential integration ID from string: {potential_id}")
                            integration_id = potential_id
                            break
                    else:
                        # Fallback to looking for any UUID but not after user_id=
                        uuid_pattern = r'(?<!user_id=)UUID\([\'"]([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})[\'"]\)'
                        matches = re.findall(uuid_pattern, str_rep)
                        if matches:
                            # Use the second UUID if available (first is often user_id)
                            if len(matches) > 1:
                                from uuid import UUID
                                integration_id = UUID(matches[1])
                                print(f"Using secondary UUID from string: {integration_id}")
                            else:
                                from uuid import UUID
                                integration_id = UUID(matches[0])
                                print(f"Using primary UUID from string: {integration_id}")
                except Exception as e:
                    print(f"Error extracting ID from string: {str(e)}")
                    traceback.print_exc()
            
            if integration_id:
                print(f"Using first available integration: {integration_id}")
                
                # Get existing metadata
                metadata_dict = None
                try:
                    # Try direct access first
                    if hasattr(integration, "metadata"):
                        metadata_dict = integration.metadata
                    # If integration is a tuple, try the first element
                    elif isinstance(integration, (tuple, list)) and len(integration) > 0 and hasattr(integration[0], "metadata"):
                        metadata_dict = integration[0].metadata
                except Exception:
                    pass
                
                # Ensure metadata is a dict
                if metadata_dict is None:
                    metadata_dict = {}
                elif not isinstance(metadata_dict, dict):
                    try:
                        # Try to convert to dict if it's a string
                        if isinstance(metadata_dict, str):
                            import json
                            metadata_dict = json.loads(metadata_dict)
                        else:
                            metadata_dict = {}
                    except:
                        metadata_dict = {}
                
                # Update metadata with portal ID
                metadata_dict["portal_id"] = portal_id_str
                
                # Update the integration record - use a different approach to avoid MetaData error
                try:
                    # Get the integration first to update its metadata
                    from sqlmodel import select
                    from sqlalchemy import update
                    
                    # First get the actual integration record
                    stmt = select(IntegrationToken).where(
                        IntegrationToken.id == integration_id
                    )
                    result = await db.exec(stmt)
                    actual_integration = result.first()
                    
                    if actual_integration:
                        # We can't set metadata directly as it's a ClassVar
                        # Instead, update the integration's metadata_json field
                        # First get the current metadata
                        current_metadata = getattr(actual_integration, "metadata_json", "{}")
                        
                        # Parse current metadata
                        try:
                            if isinstance(current_metadata, str):
                                current_metadata_dict = json.loads(current_metadata)
                            else:
                                current_metadata_dict = current_metadata or {}
                        except json.JSONDecodeError:
                            current_metadata_dict = {}
                            
                        # Update with the new metadata
                        current_metadata_dict.update(metadata_dict)
                        
                        # Save back to the integration
                        if hasattr(actual_integration, "integration_metadata"):
                            setattr(actual_integration, "integration_metadata", current_metadata_dict)
                        elif hasattr(actual_integration, "metadata_json"):
                            setattr(actual_integration, "metadata_json", json.dumps(current_metadata_dict))
                        elif hasattr(actual_integration, "_metadata"):
                            setattr(actual_integration, "_metadata", json.dumps(current_metadata_dict))
                        else:
                            # Try direct SQL update as a fallback
                            update_stmt = update(IntegrationToken).where(
                                IntegrationToken.id == integration_id
                            ).values(
                                integration_metadata=current_metadata_dict
                            )
                            await db.exec(update_stmt)
                            
                        # Commit the changes
                        await db.commit()
                        print(f"Updated integration {integration_id} with portal ID: {portal_id_str}")
                    else:
                        print(f"Could not find integration with ID {integration_id} for update")
                except Exception as e:
                    print(f"Error updating integration metadata: {str(e)}")
                    traceback.print_exc()
        
        if not integration_id:
            logger.error(f"No valid HubSpot integration found for portal ID: {portal_id}")
            return {"status": "error", "message": "No valid HubSpot integration found"}
        
        # Add to background tasks for async processing
        print(f"Adding webhook processing task for integration: {integration_id}")
        
        # Before passing the integration_id to the background task, ensure we have
        # a valid integration object we can look up
        try:
            # Verify that the integration exists by querying explicitly for the IntegrationToken object
            from sqlmodel import select
            from uuid import UUID
            
            # Ensure integration_id is a UUID
            if isinstance(integration_id, str):
                try:
                    integration_id = UUID(integration_id)
                except ValueError:
                    logger.error(f"Invalid UUID string format: {integration_id}")
                    return {"status": "error", "message": "Invalid integration ID format"}
            
            # Query using the ID without any additional filters
            # This ensures we're looking directly for the integration record
            stmt = select(IntegrationToken).where(IntegrationToken.id == integration_id)
            result = await db.exec(stmt)
            db_integration = result.first()
            
            if not db_integration:
                # Try one more approach - query all HubSpot integrations and check manually
                stmt = select(IntegrationToken).where(IntegrationToken.service_name == "hubspot")
                result = await db.exec(stmt)
                hubspot_integrations = result.all()
                
                # Log all available HubSpot integrations for debugging
                print(f"Available HubSpot integrations ({len(hubspot_integrations)}):")
                for i, integ in enumerate(hubspot_integrations):
                    # Try multiple ways to get the ID
                    try:
                        integ_id = getattr(integ, "id", None)
                        if not integ_id and hasattr(integ, "_mapping") and "id" in integ._mapping:
                            integ_id = integ._mapping["id"]
                        if not integ_id and hasattr(integ, "__getitem__"):
                            try:
                                integ_id = integ["id"]
                            except (KeyError, TypeError):
                                pass
                        
                        print(f"  #{i+1}: {integ_id}")
                    except Exception as e:
                        print(f"  #{i+1}: Error getting ID: {str(e)}")
                
                # If there are any HubSpot integrations, use the first one
                if hubspot_integrations:
                    first_integration = hubspot_integrations[0]
                    
                    # Try to get the ID from the integration
                    new_integration_id = None
                    try:
                        new_integration_id = getattr(first_integration, "id", None)
                        if not new_integration_id and hasattr(first_integration, "_mapping") and "id" in first_integration._mapping:
                            new_integration_id = first_integration._mapping["id"]
                        if not new_integration_id and hasattr(first_integration, "__getitem__"):
                            try:
                                new_integration_id = first_integration["id"]
                            except (KeyError, TypeError):
                                pass
                    except Exception as e:
                        print(f"Error getting ID from first integration: {str(e)}")
                    
                    if new_integration_id:
                        print(f"Using alternative HubSpot integration: {new_integration_id}")
                        integration_id = new_integration_id
                    else:
                        logger.error(f"Could not extract ID from alternative integration")
                        return {"status": "error", "message": "No valid HubSpot integration found"}
                else:
                    logger.error(f"No HubSpot integrations found in database")
                    return {"status": "error", "message": "No HubSpot integrations found"}
            else:
                # Successfully found the integration in the database
                print(f"Successfully verified integration exists in database: {integration_id}")
                # Get the actual ID from the database object to ensure we have the correct one
                integration_id = db_integration.id
                print(f"Using verified integration ID: {integration_id}")
        except Exception as e:
            logger.error(f"Error verifying integration ID: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": "Error verifying integration"}
            
        background_tasks.add_task(
            process_hubspot_webhook,
            data=data,
            integration_id=integration_id,
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
        print(f"Processing HubSpot webhook for integration: {integration_id}")
        
        # Ensure integration_id is a UUID object
        from uuid import UUID
        if isinstance(integration_id, str):
            try:
                integration_id = UUID(integration_id)
                print(f"Converted integration_id string to UUID: {integration_id}")
            except ValueError as e:
                logger.error(f"Invalid UUID string: {integration_id} - {str(e)}")
                return
        
        # Get the integration record
        # Use a direct SQL query to get the integration record to avoid lazy loading issues
        from sqlmodel import select
        stmt = select(IntegrationToken).where(
            IntegrationToken.id == integration_id
        )
        result = await db.exec(stmt)
        integration = result.first()
        
        if not integration:
            logger.error(f"Integration not found with ID: {integration_id}")
            return
        
        # Get all triggers associated with this integration
        from langflow.services.database.models.integration_trigger.crud import get_integration_triggers_by_integration
        triggers = await get_integration_triggers_by_integration(db, integration_id)
        
        if not triggers:
            print(f"No triggers configured for HubSpot integration: {integration_id}")
            return
            
        print(f"Found {len(triggers)} triggers for integration {integration_id}")
        
        # Get the decrypted token
        try:
            # Primary method to get decrypted token
            get_token_method = getattr(integration, "get_token", None)
            if get_token_method and callable(get_token_method):
                decrypted_token = get_token_method()
                print(f"Got token using get_token() method")
            else:
                # Fallback: manually decrypt the token
                access_token = getattr(integration, "access_token", "")
                from langflow.services.database.models.integration_token.model import decrypt_token
                decrypted_token = decrypt_token(access_token)
                print(f"Got token using manual decrypt_token()")
            
            # Validate the token format
            if not decrypted_token or not decrypted_token.strip():
                logger.error("Empty token after decryption")
                return
                
        except Exception as token_error:
            logger.error(f"Error decrypting token: {str(token_error)}")
            traceback.print_exc()
            return
        
        # Extract relevant information from the webhook
        try:
            if isinstance(data, list) and len(data) > 0:
                # Use the first event in the list
                event = data[0]
                event_type = event.get("subscriptionType", "")
                object_id = event.get("objectId", "")
                portal_id = event.get("portalId", "")
            else:
                # Single event format
                event_type = data.get("subscriptionType", "")
                object_id = data.get("objectId", "")
                portal_id = data.get("portalId", "")
            
            if not event_type or not object_id:
                logger.error("Missing event type or object ID in webhook data")
                return
        except Exception as e:
            logger.error(f"Error extracting webhook data: {str(e)}")
            traceback.print_exc()
            return
        
        print(f"Processing HubSpot event: {event_type} for object: {object_id}")
        
        # For deal.creation events, fetch the actual deal data
        deal_data = None
        if event_type == "deal.creation" and object_id:
            try:
                print(f"Fetching deal data for deal ID: {object_id}")
                
                # First, check if we need to refresh the token
                # We'll try to use the token and if it fails with a 401, we'll refresh it
                token_refreshed = False
                
                # Make API call to get deal data
                deal_url = f"https://api.hubapi.com/crm/v3/objects/deals/{object_id}"
                headers = {
                    "Authorization": f"Bearer {decrypted_token}",
                    "Content-Type": "application/json"
                }
                
                # Include associated objects and properties
                params = {
                    "properties": "amount,dealname,dealstage,pipeline,closedate,description,hubspot_owner_id",
                    "associations": "company,contact"
                }
                
                # First attempt with existing token
                deal_response = requests.get(deal_url, headers=headers, params=params)
                
                # Check if token is expired (401 Unauthorized)
                if deal_response.status_code == 401 and "expired" in deal_response.text.lower():
                    print(f"Token appears to be expired. Attempting to refresh token for integration: {integration.id}")
                    try:
                        # Refresh the token
                        new_token = await refresh_hubspot_token(db, integration)
                        if new_token:
                            # Update our local token variable
                            decrypted_token = new_token
                            # Update headers with new token
                            headers["Authorization"] = f"Bearer {new_token}"
                            token_refreshed = True
                            print("Token refreshed successfully. Retrying API call with new token.")
                            
                            # Retry the API call with the new token
                            deal_response = requests.get(deal_url, headers=headers, params=params)
                        else:
                            print("Failed to refresh token.")
                    except Exception as refresh_error:
                        logger.error(f"Error during token refresh: {str(refresh_error)}")
                        traceback.print_exc()
                
                # Check the response (either the first attempt or the retry after refresh)
                if deal_response.status_code == 200:
                    deal_data = deal_response.json()
                    import json as json_module
                    print(f"Successfully fetched deal data: {json_module.dumps(deal_data)[:100]}...")
                else:
                    error_msg = f"Failed to fetch deal data: {deal_response.status_code}"
                    if token_refreshed:
                        error_msg += " (even after token refresh)"
                    error_msg += f" - {deal_response.text}"
                    logger.error(error_msg)
            except Exception as deal_error:
                logger.error(f"Error fetching deal data: {str(deal_error)}")
                traceback.print_exc()
        
        # Process each trigger
        for trigger in triggers:
            try:
                # Get the flow associated with this trigger
                flow_id = getattr(trigger, "flow_id", None)
                trigger_id = getattr(trigger, "id", None)
                
                if not flow_id:
                    print(f"No flow ID found for trigger: {trigger_id}")
                    continue
                
                print(f"Processing trigger: {trigger_id} for flow: {flow_id}")
                
                # Get user associated with the flow
                try:
                    user = await get_user_by_flow_id_or_endpoint_name(str(flow_id))
                    if not user:
                        logger.error(f"No user found for flow: {flow_id}")
                        continue
                        
                    # Run the flow with the webhook data
                    flow = await get_flow_by_id_or_endpoint_name(flow_id_or_name=str(flow_id))
                    
                    if not flow:
                        logger.error(f"Flow not found: {flow_id}")
                        continue
                    
                    # Prepare simplified message for the flow
                    # If deal.creation event and we have deal data, pass simplified deal data
                    if event_type == "deal.creation" and deal_data:
                        # Extract only necessary information from deal_data
                        simplified_deal = {}
                        
                        # Include basic deal information
                        if "id" in deal_data:
                            simplified_deal["id"] = deal_data["id"]
                            
                        # Include essential properties
                        if "properties" in deal_data:
                            properties = deal_data["properties"]
                            simplified_deal["properties"] = {
                                "dealname": properties.get("dealname"),
                                "amount": properties.get("amount"),
                                "dealstage": properties.get("dealstage"),
                                "closedate": properties.get("closedate"),
                                "pipeline": properties.get("pipeline"),
                                "hubspot_owner_id": properties.get("hubspot_owner_id")
                            }
                            # Remove None values
                            simplified_deal["properties"] = {k: v for k, v in simplified_deal["properties"].items() if v is not None}
                        
                        # Include only IDs from associations
                        if "associations" in deal_data:
                            associations = deal_data["associations"]
                            simplified_associations = {}
                            
                            # Extract company IDs
                            if "companies" in associations and "results" in associations["companies"]:
                                simplified_associations["company_ids"] = [
                                    result["id"] for result in associations["companies"]["results"]
                                ]
                            
                            # Extract contact IDs
                            if "contacts" in associations and "results" in associations["contacts"]:
                                simplified_associations["contact_ids"] = [
                                    result["id"] for result in associations["contacts"]["results"]
                                ]
                                
                            if simplified_associations:
                                simplified_deal["associations"] = simplified_associations
                        
                        message = {
                            "event_type": event_type,
                            "object_id": object_id,
                            "deal": simplified_deal,
                            "timestamp": datetime.now().isoformat()
                        }
                    else:
                        # For other event types, use a simplified format
                        message = {
                            "event_type": event_type,
                            "object_id": object_id,
                            "timestamp": datetime.now().isoformat()
                        }
                    
                    # Create the request
                    from langflow.api.v1.schemas import SimplifiedAPIRequest
                    import json
                    from uuid import UUID
                    
                    # Convert message dictionary to JSON string
                    input_value_str = json.dumps(message, default=lambda o: str(o) if isinstance(o, UUID) else None)
                    
                    input_request = SimplifiedAPIRequest(
                        input_value=input_value_str,
                        input_type="chat",
                        output_type="chat"
                    )
                    
                    print(f"Executing flow {flow_id} with HubSpot webhook data")
                    
                    # Use Redis lock to prevent concurrent execution of the same flow
                    lock_key = f"flow_lock:{flow_id}"
                    try:
                        async with redis_lock(lock_key):
                            start_time = time.perf_counter()
                            try:
                                # Run the flow with the corrected function call
                                from langflow.api.v1.endpoints import simple_run_flow
                                response = await simple_run_flow(
                                    flow=flow,
                                    input_request=input_request,
                                    stream=False
                                )
                                print(f"Flow execution completed: {response}")
                                
                                # Log telemetry if available
                                try:
                                    from langflow.services.deps import get_telemetry_service
                                    telemetry_service = get_telemetry_service()
                                    from langflow.services.telemetry.schema import RunPayload
                                    await telemetry_service.log_package_run(
                                        RunPayload(
                                            run_is_webhook=True,
                                            run_seconds=int(time.perf_counter() - start_time),
                                            run_success=True,
                                            run_error_message=""
                                        )
                                    )
                                except Exception as telemetry_error:
                                    logger.error(f"Error logging telemetry: {str(telemetry_error)}")
                                    
                            except Exception as flow_error:
                                logger.error(f"Error running flow {flow_id}: {str(flow_error)}")
                                traceback.print_exc()
                                
                                # Log telemetry failure if available
                                try:
                                    from langflow.services.deps import get_telemetry_service
                                    telemetry_service = get_telemetry_service()
                                    from langflow.services.telemetry.schema import RunPayload
                                    await telemetry_service.log_package_run(
                                        RunPayload(
                                            run_is_webhook=True,
                                            run_seconds=int(time.perf_counter() - start_time),
                                            run_success=False,
                                            run_error_message=str(flow_error)
                                        )
                                    )
                                except Exception as telemetry_error:
                                    logger.error(f"Error logging telemetry: {str(telemetry_error)}")
                    except Exception as lock_error:
                        logger.error(f"Error acquiring lock for flow {flow_id}: {str(lock_error)}")
                        continue
                except Exception as user_flow_error:
                    logger.error(f"Error getting user or flow for trigger {trigger_id}: {str(user_flow_error)}")
                    traceback.print_exc()
                    continue
            except Exception as trigger_error:
                logger.error(f"Error processing trigger: {str(trigger_error)}")
                traceback.print_exc()
                continue
                
    except Exception as e:
        logger.error(f"Error processing HubSpot webhook: {str(e)}")
        traceback.print_exc()

@router.post("/hubspot/watch/{integration_id}")
async def watch_hubspot(
    integration_id: UUID,
    event_types: Optional[List[str]] = Body(None, description="List of event types to subscribe to"),
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
            get_token_method = getattr(integration, "get_token", None)
            if get_token_method and callable(get_token_method):
                decrypted_token = get_token_method()
            else:
                # Fallback: manually decrypt the token
                access_token = getattr(integration, "access_token", "")
                from langflow.services.database.models.integration_token.model import decrypt_token
                decrypted_token = decrypt_token(access_token)
            
            # Validate the token format
            if not decrypted_token or not decrypted_token.strip():
                logger.error("Empty token after decryption")
                raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        except Exception as token_error:
            logger.error(f"Error decrypting token: {str(token_error)}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        
        # Get the HubSpot app ID from metadata
        portal_id = getattr(integration.metadata, "get", lambda x: None)("portal_id")
        if not portal_id:
            # Try accessing metadata as a dictionary if it's stored that way
            metadata_dict = getattr(integration, "metadata", {})
            if isinstance(metadata_dict, dict):
                portal_id = metadata_dict.get("portal_id")
            
        if not portal_id:
            raise HTTPException(status_code=400, detail="Portal ID not found in integration metadata")
        
        # Create webhook subscription in HubSpot
        # URL where HubSpot will send webhooks
        webhook_url = f"{os.getenv('WEBHOOKS_BASE_URL', 'http://localhost:3000')}/api/v1/hubspot/events"
        
        # Register webhooks for each event type
        subscriptions = []
        
        if not event_types:
            event_types = ["deal.creation"]
            
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
                headers={"Authorization": f"Bearer {decrypted_token}",
                         "Content-Type": "application/json"},
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

@router.post("/hubspot/unwatch/{integration_id}")
async def unwatch_hubspot(
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
            get_token_method = getattr(integration, "get_token", None)
            if get_token_method and callable(get_token_method):
                decrypted_token = get_token_method()
            else:
                # Fallback: manually decrypt the token
                access_token = getattr(integration, "access_token", "")
                from langflow.services.database.models.integration_token.model import decrypt_token
                decrypted_token = decrypt_token(access_token)
            
            # Validate the token format
            if not decrypted_token or not decrypted_token.strip():
                logger.error("Empty token after decryption")
                raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        except Exception as token_error:
            logger.error(f"Error decrypting token: {str(token_error)}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail="Failed to decrypt access token")
        
        # Get the HubSpot app ID from metadata
        portal_id = getattr(integration.metadata, "get", lambda x: None)("portal_id")
        if not portal_id:
            # Try accessing metadata as a dictionary if it's stored that way
            metadata_dict = getattr(integration, "metadata", {})
            if isinstance(metadata_dict, dict):
                portal_id = metadata_dict.get("portal_id")
            
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
    event_types: Optional[List[str]] = Body(None, description="HubSpot event types to trigger on"),
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
        flow = await get_flow_by_id_or_endpoint_name(flow_id_or_name=str(flow_id))
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
            
        flow_user = await get_user_by_flow_id_or_endpoint_name(str(flow_id))
        if not flow_user or flow_user.id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this flow")
        
        # Create the trigger
        trigger_data = {
            "event_types": event_types or ["deal.creation"]
        }
        
        # Store the event types in the integration metadata instead
        # Update the integration's metadata to include the event types
        integration_metadata = getattr(integration, "metadata", {})
        if isinstance(integration_metadata, dict):
            integration_metadata["hubspot_event_types"] = event_types or ["deal.creation"]
        
        # Create the trigger without the trigger_data parameter
        trigger = await create_integration_trigger(
            db=db,
            integration_id=integration_id,
            flow_id=flow_id
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
        
        print(f"Refreshing HubSpot token for integration ID: {token_obj.id}")
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
            # Calculate expiration time (current time + expires_in seconds)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        # Update the token in the database
        stmt = update(IntegrationToken).where(
            IntegrationToken.id == token_obj.id
        ).values(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_at=expires_at
        )
        
        await db.exec(stmt)
        await db.commit()
        
        print(f"HubSpot token refreshed successfully. New expiration: {expires_at}")
        return new_access_token
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing HubSpot token: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error refreshing token: {str(e)}")