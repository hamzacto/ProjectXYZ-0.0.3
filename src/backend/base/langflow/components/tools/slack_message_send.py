import os
import requests
from uuid import UUID

from sqlmodel import create_engine, Session, select, SQLModel
from google.oauth2.credentials import Credentials

from loguru import logger
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import StrInput, IntInput
from langflow.schema import Data

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

class SlackMessageSchema(BaseModel):
    channel: str = Field(..., description="Channel ID, user ID, or channel name to send message to.")
    message: str = Field(..., description="The message text to send.")
    thread_ts: str = Field("", description="Optional: Thread timestamp to reply to a thread.")
    user_id: str = Field(..., description="The current user's ID.")

class SlackMessageSenderComponent(LCToolComponent):
    display_name = "Slack Message Sender"
    description = "Send a message via the Slack API."
    icon = "Slack"
    name = "SlackMessageSenderTool"

    inputs = [
        StrInput(
            name="channel",
            display_name="Channel",
            is_list=False,
            placeholder="C123456789 or #general",
            info="Channel ID, user ID, or channel name to send message to.",
        ),
        StrInput(
            name="message",
            display_name="Message",
            is_list=False,
            placeholder="Hello from your AI assistant!",
            info="The message text to send.",
        ),
        StrInput(
            name="thread_ts",
            display_name="Thread Timestamp",
            is_list=False,
            placeholder="1234567890.123456",
            info="Optional: Thread timestamp to reply to a thread.",
            advanced=True,
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
            "channel": self.channel,
            "message": self.message,
            "thread_ts": self.thread_ts,
            "user_id": self.user_id,
        }
        
        result = self._slack_message_sender(**params)
        return result
        
    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            func=self._slack_message_sender,
            name="Slack Message Sender",
            description="Send a message to a Slack channel or user.",
            args_schema=SlackMessageSchema,
            return_direct=False,
        )
        
    def _slack_message_sender(
        self,
        channel: str = "",
        message: str = "",
        thread_ts: str = "",
        user_id: str = ""
    ) -> list[Data]:
        # Validate and convert the provided user_id into a UUID.
        try:
            user_id_uuid = UUID(user_id)
        except ValueError:
            return [Data(content=f"Invalid user ID: {user_id}")]
        
        # Set up the database connection
        db_path = os.environ.get("LANGFLOW_DATABASE_URL", "sqlite:///database.db")
        engine = create_engine(db_path)
        
        try:
            with Session(engine) as db:
                # Query for integration tokens with service_name 'slack' for this user
                tokens = db.exec(
                    select(IntegrationToken).where(IntegrationToken.user_id == user_id_uuid)
                ).all()

                if not tokens:
                    error_message = "No token was found."
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Retrieve the Slack token.
                token = next(
                    (token for token in tokens if token.service_name == "slack"),
                    None
                )
                
                # Prepare the message payload
                payload = {
                    "channel": channel,
                    "text": message
                }
                
                # Add thread_ts if provided
                if thread_ts:
                    payload["thread_ts"] = thread_ts
                    
                try:
                    # Make the API call to Slack
                    response = requests.post(
                        "https://slack.com/api/chat.postMessage",
                        headers={"Authorization": f"Bearer {token.access_token}"},
                        json=payload
                    )
                    
                    # Parse the response
                    result = response.json()
                    
                    # Check if the message was sent successfully
                    if not result.get("ok"):
                        error_message = result.get("error", "Unknown error")
                        
                        # Provide more helpful error messages for common errors
                        if error_message == "not_in_channel":
                            return [Data(content=f"Failed to send message: The bot is not a member of the channel. Invite the bot to '{channel}' using the /invite @BotName command in Slack.")]
                        elif error_message == "channel_not_found":
                            return [Data(content=f"Failed to send message: Channel '{channel}' not found. Check if the channel name or ID is correct.")]
                        elif error_message == "not_authed":
                            return [Data(content=f"Failed to send message: Authentication failed. Please reconnect your Slack account in the Integrations section.")]
                        else:
                            return [Data(content=f"Failed to send Slack message: {error_message}")]
                    
                    # Success! Return message info
                    message_ts = result.get("ts")
                    channel_id = result.get("channel")
                    return [Data(content=f"Message sent successfully to Slack. Timestamp: {message_ts}, Channel: {channel_id}")]
                    
                except Exception as e:
                    logger.error(f"Error sending Slack message: {str(e)}")
                    return [Data(content=f"Error sending Slack message: {str(e)}")]
        except Exception as e:
            if "no such table: integrationtoken" in str(e):
                return [Data(content="Slack integration is not properly set up. The integrationtoken table doesn't exist in your database. Please run database migrations or contact your administrator.")]
            logger.error(f"Database error: {str(e)}")
            return [Data(content=f"Error accessing integration data: {str(e)}")] 