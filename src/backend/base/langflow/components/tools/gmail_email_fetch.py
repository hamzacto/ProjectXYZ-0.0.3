import os
import html
from uuid import UUID

from sqlmodel import create_engine, Session, select, SQLModel
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from loguru import logger
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langchain_core.tools import ToolException
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import IntInput, StrInput
from langflow.schema import Data

# Import your IntegrationToken model.
# Adjust the import path to match your project structure.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Define the scopes required by the Gmail API.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


# Define the input schema.
class GmailEmailSchema(BaseModel):
    max_results: int = Field(
        5,
        description="Maximum number of emails to retrieve from the inbox."
    )
    user_id: str = Field(
        ...,
        description="The current user's ID."
    )


class GmailEmailLoaderComponent(LCToolComponent):
    display_name = "Gmail Email Loader"
    description = (
        "Load emails from a Gmail account by directly connecting to the database to retrieve "
        "the stored integration token. Returns email details such as subject, sender, date, and snippet."
    )
    icon = "Gmail"  # Update with your desired icon identifier.
    name = "GmailEmailLoaderTool"

    # Define the tool's input fields.
    inputs = [
        IntInput(
            name="max_results",
            display_name="Maximum Number of Emails",
            info="The maximum number of emails to fetch from the inbox.",
            value=5,
            required=False
        ),
        StrInput(
            name="user_id",
            display_name="User ID",
            info="The current user's ID. DO NOT SET",
            value="",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        """Synchronously run the tool using a direct database connection."""
        return self._gmail_email_loader_sync(self.max_results, self.user_id)

    def build_tool(self) -> Tool:
        """Build the structured tool instance."""
        return StructuredTool.from_function(
            name="gmail_email_loader",
            description=(
                "Fetch email details (subject, sender, date, snippet) from a Gmail account "
                "by directly querying the database for the integration token."
            ),
            func=self._gmail_email_loader_sync,
            args_schema=GmailEmailSchema,
        )

    def _gmail_email_loader_sync(self, max_results: int, user_id: str) -> list[Data]:
        # Validate and convert the provided user_id into a UUID.
        try:
            user_uuid = UUID(self.user_id)
        except Exception as e:
            error_message = f"Invalid user_id provided: {e}"
            logger.error(error_message)
            raise ToolException(error_message) from e

        # Create a direct database connection using an environment variable or a default value.
        database_url = os.getenv("LANGFLOW_DATABASE_URL", "sqlite:///langflow.db")
        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")

        # Create all tables if they do not exist.
        SQLModel.metadata.create_all(engine)

        try:
            # Open a synchronous session.
            with Session(engine) as db:
                # Pass the UUID object directly to the query.
                tokens = db.exec(
                    select(IntegrationToken).where(IntegrationToken.user_id == user_uuid)
                ).all()
                
                print(tokens)
                
                if not tokens:
                    raise ToolException("No token was found.")

                # Retrieve the Gmail token.
                gmail_token = next(
                    (token for token in tokens if token.service_name == "gmail"),
                    None
                )
                if not gmail_token:
                    raise ToolException("Gmail not connected or token not found.")

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

                # Retrieve the list of message IDs from the INBOX.
                results = service.users().messages().list(
                    userId="me", maxResults=max_results, labelIds=["INBOX"]
                ).execute()

                messages = results.get("messages", [])
                emails = []

                # Fetch details for each email.
                for msg in messages:
                    msg_data = service.users().messages().get(
                        userId="me", id=msg["id"], format="full"
                    ).execute()

                    snippet = msg_data.get("snippet", "")
                    headers = msg_data.get("payload", {}).get("headers", [])
                    subject = next(
                        (header["value"] for header in headers if header["name"].lower() == "subject"),
                        ""
                    )
                    sender = next(
                        (header["value"] for header in headers if header["name"].lower() == "from"),
                        ""
                    )
                    date = next(
                        (header["value"] for header in headers if header["name"].lower() == "date"),
                        ""
                    )

                    emails.append({
                        "snippet": snippet,
                        "subject": subject,
                        "sender": sender,
                        "date": date
                    })
        except Exception as e:
            error_message = f"Error fetching emails: {e}"
            logger.error(error_message)
            raise ToolException(error_message) from e

        # Process and format the emails into a list of Data objects.
        data_list = []
        for email in emails:
            snippet = html.unescape(email.get("snippet", ""))
            subject = html.unescape(email.get("subject", ""))
            sender = html.unescape(email.get("sender", ""))
            date = html.unescape(email.get("date", ""))

            email_details = (
                f"Subject: {subject}\n"
                f"Sender: {sender}\n"
                f"Date: {date}\n"
                f"Snippet: {snippet}"
            )
            data_list.append(Data(text=email_details))

        return data_list