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
from langflow.inputs import StrInput, IntInput, FloatInput
from langflow.schema import Data
from dotenv import load_dotenv

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Load environment variables
load_dotenv()

# HubSpot API configuration
HUBSPOT_CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID")
HUBSPOT_CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET")


class HubSpotCreateDealSchema(BaseModel):
    user_id: str = Field(
        ...,
        description="The current user's ID."
    )
    dealname: str = Field(
        ...,
        description="The name of the deal."
    )
    amount: float = Field(
        0.0,
        description="The deal amount (optional)."
    )
    dealstage: str = Field(
        "",
        description="The stage of the deal (e.g., 'appointmentscheduled'). Optional but recommended."
    )
    pipeline: str = Field(
        "",
        description="The pipeline in which the deal will be created (optional)."
    )
    closedate: str = Field(
        "",
        description="The expected close date of the deal in ISO format (optional)."
    )
    company_id: str = Field(
        "",
        description="The ID of the company associated with the deal"
    )
    contact_id: str = Field(
        "",
        description="The ID of the contact associated with the deal"
    )
    # Add additional fields as needed


class HubSpotDealCreatorComponent(LCToolComponent):
    display_name = "HubSpot Deal Creator"
    description = (
        "Create a new deal in HubSpot. "
        "Requires a deal name, and optionally accepts amount, deal stage, pipeline, and close date."
    )
    icon = "HubSpot"
    name = "HubSpotDealCreatorTool"

    inputs = [
        StrInput(
            name="user_id",
            display_name="User ID",
            info="The current user's ID. This is automatically filled by the system.",
            value="",
            required=False
        ),
        StrInput(
            name="dealname",
            display_name="Deal Name",
            info="The name of the deal.",
            value="",
            required=False
        ),
        FloatInput(
            name="amount",
            display_name="Amount",
            info="The deal amount (optional).",
            value=0.0,
            required=False
        ),
        StrInput(
            name="dealstage",
            display_name="Deal Stage",
            info="The stage of the deal (e.g., 'appointmentscheduled').",
            value="",
            required=False
        ),
        StrInput(
            name="pipeline",
            display_name="Pipeline",
            info="The pipeline in which the deal will be created (optional).",
            value="",
            required=False
        ),
        StrInput(
            name="closedate",
            display_name="Close Date",
            info="The expected close date of the deal in ISO format (optional).",
            value="",
            required=False
        ),
        StrInput(
            name="company_id",
            display_name="Company ID",
            info="The ID of the company associated with the deal.",
            value="",
            required=False
        ),
        StrInput(
            name="contact_id",
            display_name="Contact ID",
            info="The ID of the contact associated with the deal.",
            value="",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        return self._create_hubspot_deal(
            self.user_id,
            self.dealname,
            self.amount,
            self.dealstage,
            self.pipeline,
            self.closedate,
            self.company_id,
            self.contact_id,
        )

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            func=self._create_hubspot_deal,
            name="hubspot_deal_creator",
            description=(
                "Create a new deal in HubSpot using the provided details (deal name, amount, deal stage, pipeline, and close date). "
                "Refreshes the OAuth token if needed."
            ),
            args_schema=HubSpotCreateDealSchema,
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
                expires_at = None
                if expires_in:
                    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                logger.info(f"Token refreshed successfully. New expiration: {expires_at}")

                engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
                SQLModel.metadata.create_all(engine)
                with Session(engine) as db:
                    stmt = update(IntegrationToken).where(
                        IntegrationToken.id == token_obj.id
                    ).values(
                        access_token=new_access_token,
                        refresh_token=new_refresh_token,
                        expires_at=expires_at
                    )
                    db.execute(stmt)
                    db.commit()
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

    def _create_hubspot_deal(
        self,
        user_id: str,
        dealname: str,
        amount: float = 0.0,
        dealstage: str = "",
        pipeline: str = "",
        closedate: str = "",
        company_id: str = "",
        contact_id: str = ""
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

                # Build the endpoint URL for creating a deal
                url = "https://api.hubapi.com/crm/v3/objects/deals"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                # Build the payload with provided deal properties under "properties" key.
                payload = {
                    "properties": {
                        "dealname": dealname,
                        "amount": str(amount),  # HubSpot expects amount as a string
                    }
                }
                # Optionally add dealstage, pipeline, and closedate if provided
                if dealstage:
                    payload["properties"]["dealstage"] = dealstage
                if pipeline:
                    payload["properties"]["pipeline"] = pipeline
                if closedate:
                    payload["properties"]["closedate"] = closedate
                
                # Create the deal first
                response = requests.post(url, json=payload, headers=headers)
                
                # Handle token refresh if needed
                if response.status_code == 401:
                    logger.info("Access token expired or invalid. Attempting to refresh...")
                    new_token = self._refresh_hubspot_token(hubspot_token)
                    if not new_token:
                        return [Data(text="Failed to refresh HubSpot token after 401 error.")]
                    headers["Authorization"] = f"Bearer {new_token}"
                    response = requests.post(url, json=payload, headers=headers)
                
                # Check if deal creation was successful
                if response.status_code not in (200, 201):
                    error_message = f"Failed to create deal: {response.text}"
                    logger.error(error_message)
                    return [Data(text=error_message)]
                
                # Deal was created successfully
                result = response.json()
                deal_id = result.get("id", "Unknown ID")
                logger.info(f"Deal created successfully with ID: {deal_id}")
                
                # Track associations for the final message
                associations_status = []
                
                # Handle company association if provided
                if company_id:
                    logger.info(f"Attempting to associate deal with company ID: {company_id}")
                    association_url = f"https://api.hubapi.com/crm/v3/associations/deal/company/batch/create"
                    association_payload = {
                        "inputs": [
                            {
                                "from": {"id": deal_id},
                                "to": {"id": company_id},
                                "type": "deal_to_company"
                            }
                        ]
                    }
                    
                    company_association_response = requests.post(
                        association_url, 
                        json=association_payload, 
                        headers=headers
                    )
                    
                    if company_association_response.status_code in (200, 201, 204):
                        logger.info(f"Successfully associated deal {deal_id} with company {company_id}")
                        associations_status.append(f"associated with company ID: {company_id}")
                    else:
                        error_msg = f"Failed to associate with company: {company_association_response.text}"
                        logger.error(error_msg)
                        associations_status.append(error_msg)
                
                # Handle contact association if provided
                if contact_id:
                    logger.info(f"Attempting to associate deal with contact ID: {contact_id}")
                    association_url = f"https://api.hubapi.com/crm/v3/associations/deal/contact/batch/create"
                    association_payload = {
                        "inputs": [
                            {
                                "from": {"id": deal_id},
                                "to": {"id": contact_id},
                                "type": "deal_to_contact"
                            }
                        ]
                    }
                    
                    contact_association_response = requests.post(
                        association_url, 
                        json=association_payload, 
                        headers=headers
                    )
                    
                    if contact_association_response.status_code in (200, 201, 204):
                        logger.info(f"Successfully associated deal {deal_id} with contact {contact_id}")
                        associations_status.append(f"associated with contact ID: {contact_id}")
                    else:
                        error_msg = f"Failed to associate with contact: {contact_association_response.text}"
                        logger.error(error_msg)
                        associations_status.append(error_msg)
                
                # Build the final output message
                output = f"Deal created successfully with ID: {deal_id}"
                if associations_status:
                    output += " and " + ", ".join(associations_status)
                
                return [Data(text=output)]

        except Exception as e:
            logger.error(f"Error creating HubSpot deal: {str(e)}")
            return [Data(text=f"Error creating HubSpot deal: {str(e)}")]
