import os
import html
import base64
from uuid import UUID
from email.mime.text import MIMEText

from sqlmodel import create_engine, Session, select, SQLModel
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from loguru import logger
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import StrInput
from langflow.schema import Data
from tenacity import retry, stop_after_attempt, wait_fixed
from google.auth.transport.requests import Request

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Define the scopes required by the Gmail API for sending emails.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose'
]

# Define the input schema for creating an email draft.
class GmailCreateDraftEmailSchema(BaseModel):
    to: str = Field(
        ...,
        description="Comma-separated list of recipient email addresses."
    )
    subject: str = Field(
        ...,
        description="The subject line of the email."
    )
    body: str = Field(
        ...,
        description="The body content of the email."
    )
    user_id: str = Field(
        ...,
        description="The current user's ID."
    )
    cc: str = Field(
        "",
        description="Optional comma-separated list of email addresses to CC."
    )
    bcc: str = Field(
        "",
        description="Optional comma-separated list of email addresses to BCC."
    )

class GmailEmailDraftCreatorComponent(LCToolComponent):
    display_name = "Gmail Email Draft Creator"
    description = (
        "Create a new Gmail email draft. "
        "Provide recipient(s), subject, email body, and optional CC/BCC addresses."
    )
    icon = "Gmail"
    name = "GmailEmailDraftCreatorTool"

    inputs = [
        StrInput(name="to", display_name="To", required=False),
        StrInput(name="subject", display_name="Subject", required=False),
        StrInput(name="body", display_name="Email Body", required=False),
        StrInput(name="user_id", display_name="User ID", required=False),
        StrInput(name="cc", display_name="CC", required=False),
        StrInput(name="bcc", display_name="BCC", required=False),
    ]

    def run_model(self) -> list[Data]:
        return self._gmail_create_draft(
            self.to, self.subject, self.body, self.user_id, self.cc, self.bcc
        )

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            name="gmail_create_draft",
            description=(
                "Create a new email draft using the Gmail API. "
                "Requires recipient(s), subject, email body, user_id, and optional CC/BCC addresses."
            ),
            func=self._gmail_create_draft,
            args_schema=GmailCreateDraftEmailSchema,
        )

    def _gmail_create_draft(self, to: str, subject: str, body: str, user_id: str, cc: str = "", bcc: str = "") -> list[Data]:
        try:
            user_uuid = UUID(self.user_id)
        except Exception as e:
            return [Data(text=f"Error: Invalid user_id provided. {str(e)}")]

        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)

        try:
            with Session(engine) as db:
                tokens = db.exec(select(IntegrationToken).where(IntegrationToken.user_id == user_uuid)).all()
                if not tokens:
                    return [Data(text="Error: No authentication token found for the user.")]
                gmail_token = next((token for token in tokens if token.service_name == "gmail"), None)
                if not gmail_token:
                    return [Data(text="Error: Gmail not connected or token not found.")]
                if not (gmail_token.refresh_token and gmail_token.token_uri and
                        gmail_token.client_id and gmail_token.client_secret):
                    return [Data(text="Error: The Gmail integration token is incomplete. Reauthenticate and try again.")]
                
                credentials = Credentials(
                    token=gmail_token.access_token,
                    refresh_token=gmail_token.refresh_token,
                    token_uri=gmail_token.token_uri,
                    client_id=gmail_token.client_id,
                    client_secret=gmail_token.client_secret,
                    scopes=SCOPES
                )

                @retry(stop=stop_after_attempt(1), wait=wait_fixed(2))
                def refresh_credentials(credentials):
                    credentials.refresh(Request())
                    return credentials

                if credentials.expired or not credentials.valid:
                    credentials = refresh_credentials(credentials)
                
                service = build("gmail", "v1", credentials=credentials, num_retries=1)

                # Create the MIME email message.
                mime_message = MIMEText(body)
                mime_message["to"] = to
                mime_message["from"] = "me"
                mime_message["subject"] = subject

                if cc:
                    mime_message["Cc"] = cc
                if bcc:
                    mime_message["Bcc"] = bcc

                raw_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
                message_body = {"raw": raw_message}

                # Create the draft.
                draft_body = {"message": message_body}
                result = service.users().drafts().create(userId="me", body=draft_body).execute()
                draft_id = result.get("id", "unknown")

                return [Data(text=f"Draft created successfully. Draft ID: {draft_id}")]
        except Exception as e:
            logger.error(f"Error creating email draft: {e}")
            return [Data(text=f"Error: {str(e)}")]
