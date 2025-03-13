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
from langflow.inputs import StrInput, IntInput
from langflow.schema import Data

from langflow.services.database.models.integration_token.model import IntegrationToken


class SlackRetrieveMessagesSchema(BaseModel):
    channel: str = Field(..., description="Channel ID or channel name (e.g., #general) to retrieve messages from.")
    limit: int = Field(None, description="Number of messages to retrieve (default: 10 if not set).")
    user_id: str = Field(..., description="The current user's ID.")
    thread_ts: str | None = Field(None, description="Thread timestamp to retrieve threaded messages (optional).")
    user_filter: str | None = Field(None, description="Filter messages by a specific user ID (optional).")


class SlackRetrieveMessagesComponent(LCToolComponent):
    display_name = "Slack Retrieve Messages"
    description = "Retrieve messages from a Slack channel, with optional filtering by user and thread support."
    icon = "Slack"
    name = "SlackRetrieveMessagesTool"

    inputs = [
        StrInput(
            name="channel",
            display_name="Channel",
            is_list=False,
            placeholder="C123456789 or #general",
            info="Channel ID or channel name (e.g., #general) to retrieve messages from.",
        ),
        IntInput(
            name="limit",
            display_name="Limit",
            is_list=False,
            placeholder="10",
            info="Number of messages to retrieve (default: 10 if not set).",
        ),
        StrInput(
            name="user_id",
            display_name="User ID",
            info="The current user's ID (automatically filled by the system).",
            advanced=True,
        ),
        StrInput(
            name="thread_ts",
            display_name="Thread Timestamp",
            is_list=False,
            placeholder="1682345678.123456",
            info="Thread timestamp to retrieve messages in a thread (optional).",
            advanced=True,
        ),
        StrInput(
            name="user_filter",
            display_name="Filter by User",
            is_list=False,
            placeholder="U12345678",
            info="Filter messages by a specific user ID (optional).",
            advanced=True,
        ),
    ]

    def run_model(self) -> list[Data]:
        params = {
            "channel": self.channel,
            "limit": self.limit or 10,  # Default to 10 if limit is None
            "user_id": self.user_id,
            "thread_ts": self.thread_ts or None,  # Ensure None if missing
            "user_filter": self.user_filter or None,  # Ensure None if missing
        }

        result = self._retrieve_messages(**params)
        return result

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            func=self._retrieve_messages,
            name="SlackRetrieveMessages",
            description="Retrieve messages from a Slack channel, optionally filtering by user or retrieving a thread.",
            args_schema=SlackRetrieveMessagesSchema,
            return_direct=False,
        )

    def _retrieve_messages(
        self,
        channel: str,
        limit: int = 10,
        user_id: str = "",
        thread_ts: str | None = None,
        user_filter: str | None = None,
    ) -> list[Data]:
        # Ensure default values for limit, thread_ts, and user_filter
        limit = limit or 10
        thread_ts = thread_ts or None
        user_filter = user_filter or None

        # Convert user_id to UUID
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
                    return [Data(content="Failed to retrieve Slack messages: Invalid or missing token.")]

                # Resolve channel name to ID if necessary
                if channel.startswith("#"):
                    channel_id = self._resolve_channel_id(decrypted_token, channel)
                    if not channel_id:
                        return [Data(content=f"Failed to resolve channel name: {channel}")]
                else:
                    channel_id = channel  # Assume it's already an ID

                # Set up request parameters
                request_params = {
                    "channel": channel_id,
                    "limit": limit,
                }

                if thread_ts:
                    request_params["ts"] = thread_ts  # Fetch thread messages

                # Retrieve messages from Slack
                response = requests.get(
                    "https://slack.com/api/conversations.history" if not thread_ts else "https://slack.com/api/conversations.replies",
                    headers={"Authorization": f"Bearer {decrypted_token}"},
                    params=request_params,
                )

                result = response.json()
                if result.get("ok"):
                    messages = result.get("messages", [])

                    # Apply user filter if specified
                    if user_filter:
                        messages = [msg for msg in messages if msg.get("user") == user_filter]

                    formatted_messages = "\n".join(
                        [f"{msg.get('user', 'Unknown')}: {msg.get('text', '')}" for msg in messages]
                    )

                    return [Data(content=formatted_messages or "No messages found.")]
                else:
                    return [Data(content=f"Failed to retrieve messages: {result.get('error', 'Unknown error')}")]

        except Exception as e:
            logger.error(f"Error retrieving Slack messages: {str(e)}")
            return [Data(content=f"Error retrieving Slack messages: {str(e)}")]

    def _resolve_channel_id(self, token: str, channel_name: str) -> str | None:
        """Fetches channel ID using channel name."""
        response = requests.get(
            "https://slack.com/api/conversations.list",
            headers={"Authorization": f"Bearer {token}"},
        )

        result = response.json()
        if result.get("ok"):
            for channel in result.get("channels", []):
                if channel.get("name") == channel_name.strip("#"):
                    return channel.get("id")
        return None
