import os
import json
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
            name="SlackMessageSender",
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
            user_id_uuid = UUID(self.user_id)
        except ValueError:
            return [Data(content=f"Invalid user ID: {user_id}")]
        
        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        # Create all tables if they do not exist.
        SQLModel.metadata.create_all(engine)
        
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
                
                if not token:
                    return [Data(content="No Slack integration token found. Please set up your Slack integration.")]
                
                # Get the encrypted token from the database
                encrypted_token = token.access_token
                logger.info(f"Token from DB ======   {encrypted_token}")
                
                # Properly decrypt the token using the get_token method from the model
                decrypted_token = token.get_token()
                
                # Fallback to manual decryption if the get_token method doesn't work
                if not decrypted_token or not (decrypted_token.startswith('xoxp-') or decrypted_token.startswith('xoxb-')):
                    try:
                        from langflow.services.database.models.integration_token.model import decrypt_token
                        decrypted_token = decrypt_token(encrypted_token)
                        logger.info("Token manually decrypted")
                    except Exception as e:
                        logger.error(f"Error decrypting token: {str(e)}")
                        # If all decryption methods fail, we'll use the original token
                        decrypted_token = encrypted_token
                
                logger.info(f"Decrypted token prefix: {decrypted_token[:10] if decrypted_token else 'None'}...")
                
                # Check token format to determine if it's a valid token
                is_user_token = decrypted_token.startswith('xoxp-') if decrypted_token else False
                is_bot_token = decrypted_token.startswith('xoxb-') if decrypted_token else False
                
                if not (is_user_token or is_bot_token):
                    logger.error("Token doesn't appear to be a valid Slack token format")
                    # Check for common token masking issues
                    if decrypted_token and ("***" in decrypted_token or "MASK" in decrypted_token):
                        return [Data(content="Failed to send Slack message: Your token appears to be masked or corrupted. Please reconnect your Slack account.")]
                    
                    # If token is still encrypted, it means decryption failed
                    if decrypted_token and decrypted_token.startswith('gAAAAA'):
                        return [Data(content="Failed to send Slack message: Could not decrypt your Slack token. This may be due to an encryption key mismatch. Please reconnect your Slack account or use the /api/v1/slack/fix-token endpoint to manually update your token.")]
                else:
                    logger.info(f"Token appears to be a {'user' if is_user_token else 'bot'} token")
                
                # Prepare the message payload
                payload = {
                    "channel": channel,
                    "text": message
                }
                
                # Add thread_ts if provided
                if thread_ts:
                    payload["thread_ts"] = thread_ts
                
                # For user tokens, we need to set as_user=True
                if is_user_token:
                    payload["as_user"] = True
                    
                try:
                    # Make the API call to Slack
                    response = requests.post(
                        "https://slack.com/api/chat.postMessage",
                        headers={"Authorization": f"Bearer {decrypted_token}"},
                        json=payload
                    )
                    
                    # Parse the response
                    result = response.json()
                    
                    # Check if the message was sent successfully
                    if result.get("ok"):
                        return [Data(content=f"Message sent to Slack channel {channel}")]
                    else:
                        error_message = result.get("error", "Unknown error")
                        logger.error(f"Slack API error: {error_message}")
                        
                        # Special handling for auth errors with user-specific guidance
                        if error_message == "invalid_auth":
                            advice = "Your Slack token appears to be invalid or expired."
                            if is_user_token:
                                advice += " You can fix this by reconnecting your Slack account."
                            return [Data(content=f"Failed to send Slack message: invalid_auth. {advice}")]
                            
                        # General error handling
                        return [Data(content=f"Failed to send Slack message: {error_message}")]
                        
                except Exception as e:
                    logger.error(f"Error sending Slack message: {str(e)}")
                    return [Data(content=f"Error sending Slack message: {str(e)}")]
                    
        except Exception as e:
            logger.error(f"Error in Slack message sender: {str(e)}")
            return [Data(content=f"Error in Slack message sender: {str(e)}")]