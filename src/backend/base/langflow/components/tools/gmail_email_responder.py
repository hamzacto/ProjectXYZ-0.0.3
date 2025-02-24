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
from langchain_core.tools import ToolException
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import StrInput, IntInput
from langflow.schema import Data
from tenacity import retry, stop_after_attempt, wait_fixed
from google.auth.transport.requests import Request  # NEW IMPORT

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Define the scopes required by the Gmail API for sending emails.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]


# Define the input schema for replying to an email.
class GmailReplyEmailSchema(BaseModel):
    message_id: str = Field(
        ...,
        description="The Gmail API message ID of the email you want to reply to."
    )
    reply_text: str = Field(
        ...,
        description="The body content of your reply email."
    )
    user_id: str = Field(
        ...,
        description="Set automatically"
    )


class GmailEmailResponderComponent(LCToolComponent):
    display_name = "Gmail Email Responder"
    description = "Reply to an existing Gmail email using your authenticated account. if the message_id is not provided in the user request look in the history of the conversation"
    icon = "Gmail"  # Update with your desired icon identifier.
    name = "GmailEmailResponderTool"

    # Define the tool's input fields.
    inputs = [
        StrInput(
            name="message_id",
            display_name="Original Message ID",
            info="The Gmail API message ID of the email to reply to.",
            value="",
            required=False
        ),
        StrInput(
            name="reply_text",
            display_name="Reply Email Body",
            info="The content of your reply email.",
            value="",
            required=False
        ),
        StrInput(
            name="user_id",
            display_name="User ID",
            info="The current user's ID.",
            value="",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        """Run the tool using the provided inputs."""
        return self._gmail_email_responder(
            self.message_id, self.reply_text, self.user_id
        )

    def build_tool(self) -> Tool:
        """Build a structured tool from the function."""
        return StructuredTool.from_function(
            name="gmail_email_responder",
            description=(
                "Reply to an existing email using the Gmail API by retrieving the original "
                "email's details (sender, subject, thread) and sending a reply. "
                "Requires the original message's ID, reply text, and the user_id."
            ),
            func=self._gmail_email_responder,
            args_schema=GmailReplyEmailSchema,
        )

    def _gmail_email_responder(self, message_id: str, reply_text: str, user_id: str) -> list[Data]:
        # Validate and convert the provided user_id into a UUID.
        
        try:
            user_uuid = UUID(self.user_id)
        except Exception as e:
            error_message = f"Invalid user_id provided: {e}"
            logger.error(error_message)
            raise ToolException(error_message) from e

        # Create a direct database connection using the environment variable or a default.
        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)

        try:
            # Open a synchronous session.
            with Session(engine) as db:
                tokens = db.exec(
                    select(IntegrationToken).where(IntegrationToken.user_id == user_uuid)
                ).all()

                if not tokens:
                    raise ToolException("No token was found.")

                # Retrieve the Gmail token.
                gmail_token = next(
                    (token for token in tokens if token.service_name == "gmail"),
                    None
                )
                if not gmail_token:
                    raise ToolException("Gmail not connected or token not found.")

                # Ensure that the stored token contains the fields needed for refreshing.
                if not (gmail_token.refresh_token and gmail_token.token_uri and
                        gmail_token.client_id and gmail_token.client_secret):
                    raise ToolException(
                        "The Gmail integration token is incomplete. Please reauthenticate to provide "
                        "refresh_token, token_uri, client_id, and client_secret."
                    )

                # Build the Gmail API credentials.
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

                # Build the Gmail API client.

                # Build the Gmail API client.
                service = build(
                    "gmail", 
                    "v1", 
                    credentials=credentials,
                    num_retries=1  # Set max retries to 1
                )

                # Retrieve the original email message to obtain the thread and header details.
                original_message = service.users().messages().get(
                    userId="me", id=message_id, format="full"
                ).execute()
                thread_id = original_message.get("threadId")
                headers = original_message.get("payload", {}).get("headers", [])

                # Extract the original email's subject, sender, and Message-ID.
                orig_subject = None
                orig_from = None
                orig_message_id = None
                for header in headers:
                    header_name = header.get("name", "").lower()
                    if header_name == "subject":
                        orig_subject = header.get("value")
                    elif header_name == "from":
                        orig_from = header.get("value")
                    elif header_name == "message-id":
                        orig_message_id = header.get("value")

                if not orig_from or not orig_subject or not orig_message_id:
                    raise ToolException("Could not retrieve necessary headers from the original email.")

                # Prepend "Re:" to the subject if not already present.
                if not orig_subject.lower().startswith("re:"):
                    reply_subject = f"Re: {orig_subject}"
                else:
                    reply_subject = orig_subject

                # Create the reply email message.
                reply_message = MIMEText(reply_text)
                reply_message["to"] = orig_from
                reply_message["from"] = "me"  # "me" tells Gmail to use the authenticated user.
                reply_message["subject"] = reply_subject
                reply_message["In-Reply-To"] = orig_message_id
                reply_message["References"] = orig_message_id

                # Encode the MIME message.
                raw_message = base64.urlsafe_b64encode(reply_message.as_bytes()).decode()
                email_body = {
                    "raw": raw_message,
                    "threadId": thread_id,
                }

                # Send the reply via the Gmail API.
                result = service.users().messages().send(userId="me", body=email_body).execute()
                sent_message_id = result.get("id", "unknown")

        except Exception as e:
            error_message = f"Error replying to email: {e}"
            logger.error(error_message)
            raise ToolException(error_message) from e

        result_text = f"Reply sent successfully. Message ID: {sent_message_id}"
        return [Data(text=result_text)]