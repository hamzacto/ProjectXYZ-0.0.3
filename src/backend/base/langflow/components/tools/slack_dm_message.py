import os
import json
import requests
from uuid import UUID

from sqlmodel import create_engine, Session, select, SQLModel
from loguru import logger
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import StrInput
from langflow.schema import Data

from langflow.services.database.models.integration_token.model import IntegrationToken


class SlackDMMessageSchema(BaseModel):
    user: str = Field(..., description="Slack User ID to send a direct message to.")
    message: str = Field(..., description="The message text to send.")
    user_id: str = Field(..., description="The current user's ID.")


class SlackDMSenderComponent(LCToolComponent):
    display_name = "Slack DM Sender"
    description = "Send a direct message (DM) to a Slack user."
    icon = "Slack"
    name = "SlackDMSenderTool"

    inputs = [
        StrInput(
            name="user",
            display_name="User",
            is_list=False,
            placeholder="U12345678",
            info="Slack User ID to send a direct message to.",
        ),
        StrInput(
            name="message",
            display_name="Message",
            is_list=False,
            placeholder="Hello, this is a private message!",
            info="The message text to send.",
        ),
        StrInput(
            name="user_id",
            display_name="User ID",
            info="The current user's ID (automatically filled by the system).",
            advanced=True,
        ),
    ]

    def run_model(self) -> list[Data]:
        params = {
            "user": self.user,
            "message": self.message,
            "user_id": self.user_id,
        }
        
        result = self._slack_dm_sender(**params)
        return result
        
    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            func=self._slack_dm_sender,
            name="SlackDMSender",
            description="Send a direct message (DM) to a Slack user.",
            args_schema=SlackDMMessageSchema,
            return_direct=False,
        )

    def _slack_dm_sender(
        self,
        user: str = "",
        message: str = "",
        user_id: str = ""
    ) -> list[Data]:
        # First, try to use the user_id parameter if provided
        user_id_to_use = user_id or self.user_id
        
        # Initialize user_id_uuid as None
        user_id_uuid = None
        
        # Try to convert the user_id to UUID if it looks like a UUID
        if user_id_to_use:
            try:
                # Only try to convert to UUID if it looks like one
                if '-' in user_id_to_use and len(user_id_to_use) > 30:
                    user_id_uuid = UUID(user_id_to_use)
                    logger.info(f"Successfully converted user_id to UUID: {user_id_uuid}")
            except ValueError:
                logger.warning(f"Couldn't convert user_id to UUID: {user_id_to_use}")
                # Continue without a UUID - we'll handle this case below

        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)

        try:
            with Session(engine) as db:
                # Query for integration tokens with service_name 'slack'
                # If we have a valid UUID, filter by user_id, otherwise get all Slack tokens
                if user_id_uuid:
                    logger.info(f"Querying for Slack tokens with user_id: {user_id_uuid}")
                    tokens = db.exec(
                        select(IntegrationToken).where(
                            (IntegrationToken.user_id == user_id_uuid) & 
                            (IntegrationToken.service_name == "slack")
                        )
                    ).all()
                else:
                    # If we don't have a UUID, just get all Slack tokens
                    logger.info("Querying for all Slack tokens")
                    tokens = db.exec(
                        select(IntegrationToken).where(IntegrationToken.service_name == "slack")
                    ).all()

                if not tokens:
                    return [Data(content="No token found for this user.")]

                token = next(
                    (token for token in tokens if token.service_name == "slack"),
                    None
                )

                if not token:
                    return [Data(content="No Slack integration token found. Please set up your Slack integration.")]

                decrypted_token = token.get_token()

                if not decrypted_token or not (decrypted_token.startswith('xoxp-') or decrypted_token.startswith('xoxb-')):
                    return [Data(content="Failed to send Slack DM: Invalid or missing token.")]

                # Step 1: Open a DM conversation with the user
                open_dm_response = requests.post(
                    "https://slack.com/api/conversations.open",
                    headers={"Authorization": f"Bearer {decrypted_token}"},
                    json={"users": user}
                )

                open_dm_result = open_dm_response.json()
                
                if not open_dm_result.get("ok"):
                    error_message = open_dm_result.get("error", "Unknown error opening DM")
                    logger.error(f"Slack API error (open DM): {error_message}")
                    return [Data(content=f"Failed to open DM: {error_message}")]

                dm_channel_id = open_dm_result["channel"]["id"]

                # Step 2: Send the message
                send_message_response = requests.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {decrypted_token}"},
                    json={"channel": dm_channel_id, "text": message}
                )

                send_message_result = send_message_response.json()

                if send_message_result.get("ok"):
                    return [Data(content=f"DM sent to user {user} successfully.")]
                else:
                    error_message = send_message_result.get("error", "Unknown error sending DM")
                    logger.error(f"Slack API error (send DM): {error_message}")
                    return [Data(content=f"Failed to send DM: {error_message}")]

        except Exception as e:
            logger.error(f"Error sending Slack DM: {str(e)}")
            return [Data(content=f"Error sending Slack DM: {str(e)}")]
