import os
import requests
from uuid import UUID
from datetime import datetime, timezone, timedelta

from sqlmodel import create_engine, Session, select, SQLModel, update
from loguru import logger
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import StrInput, IntInput
from langflow.schema import Data
from dotenv import load_dotenv

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Load environment variables
load_dotenv()

# HubSpot API configuration
HUBSPOT_CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID")
HUBSPOT_CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET")


class HubSpotContactSchema(BaseModel):
    max_results: int = Field(
        10,
        description="Maximum number of contacts to retrieve (default is 10)."
    )
    user_id: str = Field(
        ...,
        description="The current user's ID."
    )
    query: str = Field(
        "",
        description="Optional query string to filter contacts by email or name."
    )


class HubSpotContactLoaderComponent(LCToolComponent):
    display_name = "HubSpot Contact Loader"
    description = (
        "Load contacts from a HubSpot account. Returns key contact details such as ID, properties, and more."
    )
    icon = "HubSpot"
    name = "HubSpotContactLoaderTool"

    inputs = [
        IntInput(
            name="max_results",
            display_name="Maximum Number of Contacts",
            info="The maximum number of contacts to fetch (default is 10).",
            value=10,
            required=False
        ),
        StrInput(
            name="user_id",
            display_name="User ID",
            info="The current user's ID. This is automatically filled by the system.",
            value="",
            required=False
        ),
        StrInput(
            name="query",
            display_name="Query Filter",
            info="Optional query string to filter contacts by email or name.",
            value="",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        return self._hubspot_contact_loader(
            self.max_results,
            self.user_id,
            self.query,
        )

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            func=self._hubspot_contact_loader,
            name="hubspot_contact_loader",
            description=(
                "Retrieve contacts from a HubSpot account by querying the HubSpot Contacts API. "
                "Optionally filter results by a query string. The tool also refreshes the OAuth token if needed."
            ),
            args_schema=HubSpotContactSchema,
            return_direct=False,
        )

    def _refresh_hubspot_token(self, token_obj: IntegrationToken) -> str | None:
        """
        Refreshes the HubSpot token using the refresh token.
        Updates the token in the database and returns the new access token.
        """
        refresh_url = "https://api.hubapi.com/oauth/v1/token"
        
        # Use environment variables for client credentials
        client_id = HUBSPOT_CLIENT_ID
        client_secret = HUBSPOT_CLIENT_SECRET
        
        if not client_id or not client_secret:
            logger.error("HubSpot client ID or client secret not configured in environment variables")
            return None
            
        # Get the refresh token using get_token method if possible
        refresh_token = None
        try:
            refresh_token = token_obj.refresh_token
            if not refresh_token:
                logger.error("No refresh token available")
                return None
        except Exception as e:
            logger.error(f"Error accessing refresh token: {str(e)}")
            return None
            
        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            logger.info("Attempting to refresh HubSpot token...")
            response = requests.post(refresh_url, data=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                new_access_token = data.get("access_token")
                new_refresh_token = data.get("refresh_token", refresh_token)
                expires_in = data.get("expires_in", 0)
                
                # Calculate new expiration time
                expires_at = None
                if expires_in:
                    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                
                logger.info(f"Token refreshed successfully. New expiration: {expires_at}")
                
                # Update the token object with the new values
                engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
                SQLModel.metadata.create_all(engine)
                
                with Session(engine) as db:
                    # Use update statement instead of directly modifying the object
                    stmt = update(IntegrationToken).where(
                        IntegrationToken.id == token_obj.id
                    ).values(
                        access_token=new_access_token,
                        refresh_token=new_refresh_token,
                        expires_at=expires_at
                    )
                    db.execute(stmt)
                    db.commit()
                    
                    # Fetch the updated token to return
                    updated_token = db.exec(
                        select(IntegrationToken).where(IntegrationToken.id == token_obj.id)
                    ).first()
                    
                    if updated_token:
                        logger.info("HubSpot token updated in database successfully")
                    else:
                        logger.warning("Token updated but couldn't verify the update")
                
                return new_access_token
            else:
                logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Exception during token refresh: {str(e)}")
            return None

    def _hubspot_contact_loader(
        self,
        max_results: int = 10,
        user_id: str = "",
        query: str = ""
    ) -> list[Data]:
        # First, try to use the user_id parameter if provided
        user_id_to_use = self.user_id
        
        # Initialize user_id_uuid as None
        user_id_uuid = None
        
        # Try to convert the user_id to UUID if it looks like a UUID
        if user_id_to_use:
            try:
                # Only try to convert to UUID if it looks like one
                if '-' in user_id_to_use and len(user_id_to_use) > 30:
                    user_id_uuid = UUID(user_id_to_use)
                    logger.info(f"Successfully converted user_id to UUID: {user_id_uuid}")
                else:
                    logger.warning(f"User ID doesn't appear to be in UUID format: {user_id_to_use}")
            except ValueError as e:
                logger.warning(f"Couldn't convert user_id to UUID: {user_id_to_use}, Error: {str(e)}")
                # Continue without a UUID - we'll handle this case below
        
        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)

        try:
            with Session(engine) as db:
                # Query for integration tokens with service_name 'hubspot'
                # If we have a valid UUID, filter by user_id, otherwise get all HubSpot tokens
                if user_id_uuid:
                    logger.info(f"Querying for HubSpot tokens with user_id: {user_id_uuid}")
                    tokens = db.exec(
                        select(IntegrationToken).where(
                            (IntegrationToken.user_id == user_id_uuid) & 
                            (IntegrationToken.service_name.like("%hubspot%"))
                        )
                    ).all()
                else:
                    # If we don't have a UUID, just get all HubSpot tokens
                    logger.info("Querying for all HubSpot tokens")
                    tokens = db.exec(
                        select(IntegrationToken).where(IntegrationToken.service_name.like("%hubspot%"))
                    ).all()

                if not tokens:
                    error_message = "No token was found."
                    logger.error(error_message)
                    return [Data(text=error_message)]

                hubspot_token = next(
                    (token for token in tokens if token.service_name.lower() == "hubspot"),
                    None
                )
                if not hubspot_token:
                    error_message = "HubSpot not connected or token not found."
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Check if token is expired before making the API call
                if hubspot_token.expires_at:
                    # Ensure we're comparing timezone-aware datetimes
                    now = datetime.now(timezone.utc)
                    
                    # Convert expires_at to timezone-aware if it's naive
                    token_expires_at = hubspot_token.expires_at
                    if token_expires_at.tzinfo is None:
                        # If the token's expires_at is naive, assume it's in UTC
                        token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)
                    
                    logger.info(f"Token expires at: {token_expires_at}, Current time: {now}")
                    
                    if token_expires_at <= now:
                        logger.info("Token has expired. Attempting to refresh before API call...")
                        new_token = self._refresh_hubspot_token(hubspot_token)
                        if not new_token:
                            return [Data(text="Failed to refresh expired HubSpot token.")]
                        access_token = new_token
                    else:
                        access_token = hubspot_token.get_token()
                else:
                    access_token = hubspot_token.get_token()
                
                if not access_token:
                    error_message = "Failed to retrieve a valid HubSpot access token."
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Build the HubSpot API endpoint URL.
                url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                # Prepare the request payload
                payload = {
                    "limit": max_results,
                    "properties": ["firstname", "lastname", "email"]
                }
                
                # Add search filters if query is provided
                if query:
                    logger.info(f"Filtering contacts with query: {query}")
                    
                    # Check if the query is a numeric ID
                    if query.isdigit():
                        logger.info(f"Query appears to be a contact ID: {query}")
                        # Use a direct GET request to fetch by ID instead of search
                        contact_id_url = f"https://api.hubapi.com/crm/v3/objects/contacts/{query}"
                        response = requests.get(contact_id_url, headers=headers)
                        
                        if response.status_code == 401:
                            logger.info("Access token expired or invalid. Attempting to refresh...")
                            new_token = self._refresh_hubspot_token(hubspot_token)
                            if not new_token:
                                return [Data(text="Failed to refresh HubSpot token after 401 error.")]
                            headers["Authorization"] = f"Bearer {new_token}"
                            response = requests.get(contact_id_url, headers=headers)
                            
                        if response.status_code == 200:
                            # Process single contact response
                            contact = response.json()
                            properties = contact.get("properties", {})
                            contact_id = contact.get("id", "Unknown ID")
                            firstname = properties.get("firstname", "N/A")
                            lastname = properties.get("lastname", "N/A")
                            email = properties.get("email", "N/A")
                            formatted = (
                                f"ID: {contact_id}\n"
                                f"Name: {firstname} {lastname}\n"
                                f"Email: {email}\n"
                            )
                            return [Data(text=formatted)]
                        elif response.status_code == 404:
                            return [Data(text=f"No contact found with ID: {query}")]
                        else:
                            error_message = f"Failed to retrieve contact by ID: {response.text}"
                            logger.error(error_message)
                            return [Data(text=error_message)]
                    
                    # If not a numeric ID, use the search endpoint with filters
                    payload["filterGroups"] = [
                        {
                            "filters": [
                                {
                                    "propertyName": "email",
                                    "operator": "CONTAINS_TOKEN",
                                    "value": query
                                }
                            ]
                        },
                        {
                            "filters": [
                                {
                                    "propertyName": "firstname",
                                    "operator": "CONTAINS_TOKEN",
                                    "value": query
                                }
                            ]
                        },
                        {
                            "filters": [
                                {
                                    "propertyName": "lastname",
                                    "operator": "CONTAINS_TOKEN",
                                    "value": query
                                }
                            ]
                        }
                    ]
                
                # Make the API request
                response = requests.post(url, headers=headers, json=payload)

                # If the token has expired, attempt to refresh it.
                if response.status_code == 401:
                    logger.info("Access token expired or invalid. Attempting to refresh...")
                    new_token = self._refresh_hubspot_token(hubspot_token)
                    if not new_token:
                        return [Data(text="Failed to refresh HubSpot token after 401 error.")]
                    headers["Authorization"] = f"Bearer {new_token}"
                    response = requests.post(url, headers=headers, json=payload)

                if response.status_code != 200:
                    error_message = f"Failed to retrieve contacts: {response.text}"
                    logger.error(error_message)
                    return [Data(text=error_message)]

                result = response.json()
                contacts = result.get("results", [])
                if not contacts:
                    return [Data(text="No contacts found.")]

                formatted_contacts = []
                for contact in contacts:
                    contact_id = contact.get("id", "Unknown ID")
                    properties = contact.get("properties", {})
                    firstname = properties.get("firstname", "N/A")
                    lastname = properties.get("lastname", "N/A")
                    email = properties.get("email", "N/A")
                    formatted = (
                        f"ID: {contact_id}\n"
                        f"Name: {firstname} {lastname}\n"
                        f"Email: {email}\n"
                    )
                    formatted_contacts.append(formatted)

                output = "\n".join(formatted_contacts)
                return [Data(text=output)]

        except Exception as e:
            logger.error(f"Error retrieving HubSpot contacts: {str(e)}")
            return [Data(text=f"Error retrieving HubSpot contacts: {str(e)}")]
