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


class HubSpotCreateCompanySchema(BaseModel):
    user_id: str = Field(
        ...,
        description="The current user's ID."
    )
    company_name: str = Field(
        ...,
        description="The name of the company."
    )
    domain: str = Field(
        "",
        description="The company domain (optional)."
    )
    industry: str = Field(
        "",
        description="Industry of the company (optional)."
    )
    numberofemployees: str = Field(
        "",
        description="Number of employees (e.g., '100-250') (optional)."
    )
    city: str = Field(
        "",
        description="City where the company is located (optional)."
    )
    state: str = Field(
        "",
        description="State where the company is located (optional)."
    )
    country: str = Field(
        "",
        description="Country code (e.g., 'US') where the company is located (optional)."
    )
    phone: str = Field(
        "",
        description="Phone number of the company (optional)."
    )


class HubSpotCompanyCreatorComponent(LCToolComponent):
    display_name = "HubSpot Company Creator"
    description = (
        "Create a new company in HubSpot with details such as company name, domain, industry, "
        "number of employees, city, state, country, and phone."
    )
    icon = "HubSpot"
    name = "HubSpotCompanyCreatorTool"

    inputs = [
        StrInput(
            name="user_id",
            display_name="User ID",
            info="The current user's ID. This is automatically filled by the system.",
            value="",
            required=False
        ),
        StrInput(
            name="company_name",
            display_name="Company Name",
            info="The name of the company.",
            value="",
            required=False
        ),
        StrInput(
            name="domain",
            display_name="Domain",
            info="The company domain (optional).",
            value="",
            required=False
        ),
        StrInput(
            name="industry",
            display_name="Industry",
            info="Industry of the company (optional).",
            value="",
            required=False
        ),
        StrInput(
            name="numberofemployees",
            display_name="Number of Employees",
            info="Number of employees (e.g., '100-250') (optional).",
            value="",
            required=False
        ),
        StrInput(
            name="city",
            display_name="City",
            info="City where the company is located (optional).",
            value="",
            required=False
        ),
        StrInput(
            name="state",
            display_name="State",
            info="State where the company is located (optional).",
            value="",
            required=False
        ),
        StrInput(
            name="country",
            display_name="Country",
            info="Country code (e.g., 'US') where the company is located (optional).",
            value="",
            required=False
        ),
        StrInput(
            name="phone",
            display_name="Phone",
            info="Phone number of the company (optional).",
            value="",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        return self._create_hubspot_company(
            self.user_id,
            self.company_name,
            self.domain,
            self.industry,
            self.numberofemployees,
            self.city,
            self.state,
            self.country,
            self.phone,
        )

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            func=self._create_hubspot_company,
            name="hubspot_company_creator",
            description=(
                "Create a new company in HubSpot with details: company name, domain, industry, "
                "number of employees, city, state, country, and phone. "
                "Refreshes the OAuth token if needed."
            ),
            args_schema=HubSpotCreateCompanySchema,
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

    def _create_hubspot_company(
        self,
        user_id: str,
        company_name: str,
        domain: str = "",
        industry: str = "",
        numberofemployees: str = "",
        city: str = "",
        state: str = "",
        country: str = "",
        phone: str = ""
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
                
                # Check token expiration and refresh if needed
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
                
                # Build the endpoint URL for creating a company
                url = "https://api.hubapi.com/crm/v3/objects/companies"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                # Build the payload with provided company properties under "properties" key.
                payload = {
                    "properties": {
                        "name": company_name,
                        "domain": domain,
                        "industry": industry,
                        "numberofemployees": numberofemployees,
                        "city": city,
                        "state": state,
                        "country": country,
                        "phone": phone,
                    }
                }
                
                response = requests.post(url, json=payload, headers=headers)
                
                # If the token is expired or invalid, try to refresh once.
                if response.status_code == 401:
                    logger.info("Access token expired or invalid. Attempting to refresh...")
                    new_token = self._refresh_hubspot_token(hubspot_token)
                    if not new_token:
                        return [Data(text="Failed to refresh HubSpot token after 401 error.")]
                    headers["Authorization"] = f"Bearer {new_token}"
                    response = requests.post(url, json=payload, headers=headers)
                
                if response.status_code not in (200, 201):
                    error_message = f"Failed to create company: {response.text}"
                    logger.error(error_message)
                    return [Data(text=error_message)]
                
                result = response.json()
                company_id = result.get("id", "Unknown ID")
                logger.info(f"Company created successfully with ID: {company_id}")
                output = f"Company created successfully with ID: {company_id}"
                return [Data(text=output)]
        
        except Exception as e:
            logger.error(f"Error creating HubSpot company: {str(e)}")
            return [Data(text=f"Error creating HubSpot company: {str(e)}")]
