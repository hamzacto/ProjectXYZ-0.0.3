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


class SlackListChannelsUsersSchema(BaseModel):
    user_id: str = Field(..., description="The current user's ID.")


class SlackListChannelsUsersComponent(LCToolComponent):
    display_name = "Slack List Channels & Users"
    description = "Retrieve a list of available Slack channels and users."
    icon = "Slack"
    name = "SlackListChannelsUsersTool"

    inputs = [
        StrInput(
            name="user_id",
            display_name="User ID",
            info="The current user's ID (automatically filled by the system).",
            advanced=True,
        ),
    ]

    def run_model(self) -> list[Data]:
        params = {
            "user_id": self.user_id,
        }

        result = self._list_channels_users(**params)
        return result

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            func=self._list_channels_users,
            name="SlackListChannelsUsers",
            description="Retrieve a list of available Slack channels and users.",
            args_schema=SlackListChannelsUsersSchema,
            return_direct=False,
        )

    def _list_channels_users(self, user_id: str) -> list[Data]:
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
                    return [Data(content="Failed to retrieve Slack data: Invalid or missing token.")]

                # Fetch channels
                channels_response = requests.get(
                    "https://slack.com/api/conversations.list",
                    headers={"Authorization": f"Bearer {decrypted_token}"},
                )

                channels_data = channels_response.json()
                if not channels_data.get("ok"):
                    return [Data(content=f"Failed to retrieve channels: {channels_data.get('error', 'Unknown error')}")]

                channels = [
                    f"#{channel['name']} (ID: {channel['id']})"
                    for channel in channels_data.get("channels", [])
                ]

                # Fetch users
                users_response = requests.get(
                    "https://slack.com/api/users.list",
                    headers={"Authorization": f"Bearer {decrypted_token}"},
                )

                users_data = users_response.json()
                if not users_data.get("ok"):
                    return [Data(content=f"Failed to retrieve users: {users_data.get('error', 'Unknown error')}")]

                users = [
                    f"{user['real_name']} (ID: {user['id']})"
                    for user in users_data.get("members", [])
                    if not user.get("is_bot") and not user.get("deleted")
                ]

                return [Data(content=f"**Available Channels:**\n" + "\n".join(channels) + 
                                   f"\n\n**Available Users:**\n" + "\n".join(users))]

        except Exception as e:
            logger.error(f"Error retrieving Slack channels & users: {str(e)}")
            return [Data(content=f"Error retrieving Slack channels & users: {str(e)}")]
