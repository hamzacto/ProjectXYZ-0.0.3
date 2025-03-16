import os
import html
import base64
from uuid import UUID
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sqlmodel import create_engine, Session, select, SQLModel
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from loguru import logger
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import StrInput, IntInput
from langflow.schema import Data

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Define the scopes required by the Gmail API for sending email.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.insert",
]

# Updated input schema without scheduler functionality.
class GmailSendEmailSchema(BaseModel):
    recipient: str = Field(..., description="Comma-separated list of recipient email addresses.")
    cc: str = Field("", description="Optional: Comma-separated CC email addresses.")
    bcc: str = Field("", description="Optional: Comma-separated BCC email addresses.")
    subject: str = Field(..., description="Subject of the email.")
    body_text: str = Field(..., description="Body content of the email.")
    labels: str = Field("", description="Optional: Comma-separated Gmail label IDs to add to the sent email.")
    thread_id: str = Field("", description="Optional: Gmail thread ID to which this email should belong.")
    user_id: str = Field(..., description="The current user's ID.")


class GmailEmailSenderComponent(LCToolComponent):
    display_name = "Gmail Email Sender"
    description = "Send an email via the Gmail API."
    icon = "Gmail"  # Update with your desired icon identifier.
    name = "GmailEmailSenderTool"

    # Updated inputs list without scheduling.
    inputs = [
        StrInput(
            name="recipient",
            display_name="Recipient Email(s)",
            info="Comma-separated list of recipient email addresses.",
            value="",
            required=False
        ),
        StrInput(
            name="cc",
            display_name="CC Email(s)",
            info="Optional: Comma-separated CC email addresses.",
            value="",
            required=False
        ),
        StrInput(
            name="bcc",
            display_name="BCC Email(s)",
            info="Optional: Comma-separated BCC email addresses.",
            value="",
            required=False
        ),
        StrInput(
            name="subject",
            display_name="Email Subject",
            info="The subject line of the email.",
            value="",
            required=False
        ),
        StrInput(
            name="body_text",
            display_name="Email Body",
            info="The main content of the email.",
            value="",
            required=False
        ),
        StrInput(
            name="labels",
            display_name="Gmail Label IDs",
            info="Optional: Comma-separated Gmail label IDs to add to the sent email.",
            value="",
            required=False
        ),
        StrInput(
            name="thread_id",
            display_name="Thread ID",
            info="Optional: Gmail thread ID to which this email should belong.",
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
        return self._gmail_email_sender(
            self.recipient,
            self.cc,
            self.bcc,
            self.subject,
            self.body_text,
            self.labels,
            self.thread_id,
            self.user_id
        )

    def build_tool(self) -> Tool:
        """Build a structured tool from the function."""
        return StructuredTool.from_function(
            name="gmail_email_sender",
            description=(
                "Send an email using the Gmail API by directly querying the database for "
                "the integration token. Supports multiple recipients (To, CC, BCC) and optional Gmail labels and threading."
            ),
            func=self._gmail_email_sender,
            args_schema=GmailSendEmailSchema,
        )

    def _gmail_email_sender(
        self,
        recipient: str = "",
        cc: str = "",
        bcc: str = "",
        subject: str = "",
        body_text: str = "",
        labels: str = "",
        thread_id: str = "",
        user_id: str = ""
    ) -> list[Data]:
        # First, try to use the user_id parameter if provided
        user_id_to_use = self.user_id
        
        # Initialize user_id_uuid as None
        user_id_uuid = None
        
        # Try to convert the user_id to UUID if it looks like a UUID
        if user_id_to_use:
            try:
                # Only try to convert to UUID if it looks like one
                if '-' in user_id_to_use and len(user_id_to_use) > 30:
                    user_id_uuid = UUID(user_id_to_use)
                    logger.info(f"Successfully converted user_id to UUID: {user_id_uuid}")
                else:
                    logger.warning(f"User ID doesn't appear to be in UUID format: {user_id_to_use}")
            except ValueError as e:
                logger.warning(f"Couldn't convert user_id to UUID: {user_id_to_use}, Error: {str(e)}")
                # Continue without a UUID - we'll handle this case below

        # Create a direct database connection.
        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)

        try:
            # Open a synchronous session.
            with Session(engine) as db:
                # Query for integration tokens with service_name 'gmail'
                # If we have a valid UUID, filter by user_id, otherwise get all Gmail tokens
                if user_id_uuid:
                    logger.info(f"Querying for Gmail tokens with user_id: {user_id_uuid}")
                    tokens = db.exec(
                        select(IntegrationToken).where(
                            (IntegrationToken.user_id == user_id_uuid) & 
                            (IntegrationToken.service_name == "gmail")
                        )
                    ).all()
                else:
                    # If we don't have a UUID, just get all Gmail tokens
                    logger.info("Querying for all Gmail tokens")
                    tokens = db.exec(
                        select(IntegrationToken).where(IntegrationToken.service_name == "gmail")
                    ).all()

                if not tokens:
                    error_message = "Error: No token was found."
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Retrieve the Gmail token.
                gmail_token = next(
                    (token for token in tokens if token.service_name == "gmail"),
                    None
                )
                if not gmail_token:
                    error_message = "Error: Gmail not connected or token not found."
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Ensure the token contains the fields needed for refreshing.
                if not (gmail_token.refresh_token and gmail_token.token_uri and
                        gmail_token.client_id and gmail_token.client_secret):
                    error_message = ("Error: The Gmail integration token is incomplete. "
                                     "Please reauthenticate to provide refresh_token, token_uri, client_id, and client_secret.")
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Build the Gmail API credentials.
                credentials = Credentials(
                    token=gmail_token.access_token,
                    refresh_token=gmail_token.refresh_token,
                    token_uri=gmail_token.token_uri,
                    client_id=gmail_token.client_id,
                    client_secret=gmail_token.client_secret,
                    scopes=SCOPES
                )

                # Build the Gmail API client.
                service = build("gmail", "v1", credentials=credentials)
        except Exception as e:
            error_message = f"Error during token retrieval or service setup: {e}"
            logger.error(error_message)
            return [Data(text=error_message)]

        def send_email() -> str:
            try:
                # Create a multipart MIME message.
                message = MIMEMultipart()
                message.attach(MIMEText(body_text, "plain"))

                # Set headers using comma-separated email addresses.
                message['to'] = recipient
                if cc.strip():
                    message['Cc'] = cc
                if bcc.strip():
                    message['Bcc'] = bcc
                message['from'] = "me"  # "me" tells Gmail to use the authenticated user.
                message['subject'] = subject

                # Encode the message.
                raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
                email_body = {"raw": raw_message}

                # Include thread ID if provided.
                if thread_id.strip():
                    email_body["threadId"] = thread_id.strip()

                # Send the email via the Gmail API.
                result = service.users().messages().send(userId="me", body=email_body).execute()
                message_id = result.get("id", "unknown")

                # Apply labels if provided.
                if labels.strip():
                    label_ids = [lab.strip() for lab in labels.split(",") if lab.strip()]
                    service.users().messages().modify(
                        userId="me", id=message_id, body={"addLabelIds": label_ids}
                    ).execute()
                return message_id
            except Exception as e:
                error_message = f"Error sending email: {e}"
                logger.error(error_message)
                return error_message

        # Send the email immediately.
        message_id = send_email()
        if message_id.startswith("Error"):
            return [Data(text=message_id)]
        else:
            result_text = f"Email sent successfully. Message ID: {message_id}"
            return [Data(text=result_text)]
