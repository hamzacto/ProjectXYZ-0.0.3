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

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Define the scopes required by the Gmail API for sending email.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']


# Define the input schema.
class GmailSendEmailSchema(BaseModel):
    recipient: str = Field(..., description="The recipient's email address.")
    subject: str = Field(..., description="Subject of the email.")
    body_text: str = Field(..., description="Body content of the email.")
    user_id: str = Field(..., description="The current user's ID.")


class GmailEmailSenderComponent(LCToolComponent):
    display_name = "Gmail Email Sender"
    description = "Send an email via the Gmail API using your authenticated account."
    icon = "Gmail"  # Update with your desired icon identifier.
    name = "GmailEmailSenderTool"

    # Define the tool's input fields.
    inputs = [
        StrInput(
            name="recipient",
            display_name="Recipient Email",
            info="The email address of the recipient.",
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
            self.recipient, self.subject, self.body_text, self.user_id
        )

    def build_tool(self) -> Tool:
        """Build a structured tool from the function."""
        return StructuredTool.from_function(
            name="gmail_email_sender",
            description=(
                "Send an email using the Gmail API by directly querying the database for "
                "the integration token. Requires recipient, subject, body text, and user_id."
            ),
            func=self._gmail_email_sender,
            args_schema=GmailSendEmailSchema,
        )

    def _gmail_email_sender(self, recipient: str, subject: str, body_text: str, user_id: str) -> list[Data]:
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

                # Build the Gmail API client.
                service = build("gmail", "v1", credentials=credentials)

                # Create the MIME message.
                message = MIMEText(body_text)
                message['to'] = recipient
                message['from'] = "me"  # "me" is a special value that tells Gmail to use the authenticated user.
                message['subject'] = subject
                raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

                # Prepare the payload for sending.
                email_body = {"raw": raw_message}

                # Send the email via the Gmail API.
                result = service.users().messages().send(userId="me", body=email_body).execute()
                message_id = result.get("id", "unknown")
        except Exception as e:
            error_message = f"Error sending email: {e}"
            logger.error(error_message)
            raise ToolException(error_message) from e

        result_text = f"Email sent successfully. Message ID: {message_id}"
        return [Data(text=result_text)]