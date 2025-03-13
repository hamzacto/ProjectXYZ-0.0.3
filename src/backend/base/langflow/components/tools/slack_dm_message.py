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
        # Validate user_id format
        try:
            user_id_uuid = UUID(self.user_id)
        except ValueError:
            return [Data(content=f"Invalid user ID: {user_id}")]

        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)

        try:
            with Session(engine) as db:
                # Retrieve Slack token for the user
                tokens = db.exec(
                    select(IntegrationToken).where(IntegrationToken.user_id == user_id_uuid)
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
