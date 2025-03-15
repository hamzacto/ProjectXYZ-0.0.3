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


class HubSpotDealLoaderSchema(BaseModel):
    max_results: int = Field(
        10,
        description="Maximum number of deals to retrieve (default is 10)."
    )
    user_id: str = Field(
        ...,
        description="The current user's ID."
    )
    query: str = Field(
        "",
        description="Optional query string to filter deals by name or properties."
    )


class HubSpotDealLoaderComponent(LCToolComponent):
    display_name = "HubSpot Deal Loader"
    description = (
        "Load deals from a HubSpot account. Returns detailed deal information including "
        "deal name, amount, stage, pipeline, close date, and associated company and contact IDs."
    )
    icon = "HubSpot"
    name = "HubSpotDealLoaderTool"

    inputs = [
        IntInput(
            name="max_results",
            display_name="Maximum Number of Deals",
            info="The maximum number of deals to fetch (default is 10).",
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
            info="Optional query string to filter deals by name or properties.",
            value="",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        return self._hubspot_deal_loader(
            self.max_results,
            self.user_id,
            self.query,
        )

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            func=self._hubspot_deal_loader,
            name="hubspot_deal_loader",
            description=(
                "Retrieve deals from a HubSpot account by querying the HubSpot Deals API. "
                "Returns details such as deal name, amount, stage, pipeline, close date, "
                "and associated company and contact IDs. Refreshes the OAuth token if needed."
            ),
            args_schema=HubSpotDealLoaderSchema,
            return_direct=False,
        )

    def _refresh_hubspot_token(self, token_obj: IntegrationToken) -> str | None:
        """
        Refresh the HubSpot token using the refresh token.
        Updates the token in the database and returns the new access token.
        """
        refresh_url = "https://api.hubapi.com/oauth/v1/token"
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

    def _hubspot_deal_loader(
        self,
        max_results: int = 10,
        user_id: str = "",
        query: str = ""
    ) -> list[Data]:
        # Validate and convert user_id into UUID if possible.
        try:
            user_uuid = UUID(self.user_id)
        except Exception as e:
            error_message = f"Invalid user_id provided: {e}"
            logger.error(error_message)
            return [Data(text=error_message)]

        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)

        try:
            with Session(engine) as db:
                tokens = db.exec(
                    select(IntegrationToken).where(IntegrationToken.user_id == user_uuid)
                ).all()

                if not tokens:
                    error_message = "No token was found for this user."
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
                    now = datetime.now(timezone.utc)
                    token_expires_at = hubspot_token.expires_at
                    if token_expires_at.tzinfo is None:
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

                # Build the API endpoint URL for deals
                url = "https://api.hubapi.com/crm/v3/objects/deals"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                # Specify desired deal properties
                params = {
                    "limit": max_results,
                    "properties": "dealname,amount,dealstage,pipeline,closedate,hubspot_owner_id,createdate,hs_lastmodifieddate"
                }
                if query:
                    params["q"] = query

                # Add associations to fetch related company and contact IDs
                params["associations"] = "company,contact"

                response = requests.get(url, headers=headers, params=params)

                # If token expired/invalid, attempt a refresh and retry
                if response.status_code == 401:
                    logger.info("Access token expired or invalid. Attempting to refresh...")
                    new_token = self._refresh_hubspot_token(hubspot_token)
                    if not new_token:
                        return [Data(text="Failed to refresh HubSpot token after 401 error.")]
                    headers["Authorization"] = f"Bearer {new_token}"
                    response = requests.get(url, headers=headers, params=params)

                if response.status_code != 200:
                    error_message = f"Failed to retrieve deals: {response.text}"
                    logger.error(error_message)
                    return [Data(text=error_message)]

                result = response.json()
                deals = result.get("results", [])
                if not deals:
                    return [Data(text="No deals found.")]

                formatted_deals = []
                for deal in deals:
                    deal_id = deal.get("id", "Unknown ID")
                    props = deal.get("properties", {})
                    dealname = props.get("dealname", "N/A")
                    amount = props.get("amount", "N/A")
                    dealstage = props.get("dealstage", "N/A")
                    pipeline = props.get("pipeline", "N/A")
                    closedate = props.get("closedate", "N/A")
                    hubspot_owner_id = props.get("hubspot_owner_id", "N/A")
                    createdate = props.get("createdate", "N/A")
                    lastmodifieddate = props.get("hs_lastmodifieddate", "N/A")
                    
                    # Get associated companies and contacts
                    associations = deal.get("associations", {})
                    company_ids = []
                    contact_ids = []
                    
                    companies = associations.get("companies", {}).get("results", [])
                    contacts = associations.get("contacts", {}).get("results", [])
                    
                    for company in companies:
                        company_ids.append(company.get("id", ""))
                    
                    for contact in contacts:
                        contact_ids.append(contact.get("id", ""))
                    
                    formatted = (
                        f"ID: {deal_id}\n"
                        f"Name: {dealname}\n"
                        f"Amount: {amount}\n"
                        f"Stage: {dealstage}\n"
                        f"Pipeline: {pipeline}\n"
                        f"Close Date: {closedate}\n"
                        f"Owner ID: {hubspot_owner_id}\n"
                        f"Created Date: {createdate}\n"
                        f"Last Modified Date: {lastmodifieddate}\n"
                    )
                    
                    if company_ids:
                        formatted += f"Associated Company IDs: {', '.join(company_ids)}\n"
                    
                    if contact_ids:
                        formatted += f"Associated Contact IDs: {', '.join(contact_ids)}\n"
                    
                    formatted_deals.append(formatted)

                output = "\n\n".join(formatted_deals)
                return [Data(text=output)]

        except Exception as e:
            logger.error(f"Error retrieving HubSpot deals: {str(e)}")
            return [Data(text=f"Error retrieving HubSpot deals: {str(e)}")]
