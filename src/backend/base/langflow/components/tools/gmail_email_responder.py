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
from langflow.inputs import StrInput
from langflow.schema import Data
from tenacity import retry, stop_after_attempt, wait_fixed
from google.auth.transport.requests import Request

from langflow.services.database.models.integration_token.model import IntegrationToken

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]

class GmailReplyEmailSchema(BaseModel):
    message_id: str = Field(..., description="The Gmail API message ID of the email you want to reply to.")
    reply_text: str = Field(..., description="The body content of your reply email.")
    user_id: str = Field(..., description="Set automatically")
    cc: str = Field("", description="Optional comma-separated list of email addresses to CC.")
    bcc: str = Field("", description="Optional comma-separated list of email addresses to BCC.")

class GmailEmailResponderComponent(LCToolComponent):
    display_name = "Gmail Email Responder"
    description = "Reply to an existing Gmail email with optional CC and BCC."
    icon = "Gmail"
    name = "GmailEmailResponderTool"

    inputs = [
        StrInput(name="message_id", display_name="Original Message ID", required=False),
        StrInput(name="reply_text", display_name="Reply Email Body", required=False),
        StrInput(name="user_id", display_name="User ID", required=False),
        StrInput(name="cc", display_name="CC", required=False),
        StrInput(name="bcc", display_name="BCC", required=False),
    ]

    def run_model(self) -> list[Data]:
        return self._gmail_email_responder(self.message_id, self.reply_text, self.user_id, self.cc, self.bcc)

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            name="gmail_email_responder",
            description="Reply to an email with optional CC and BCC.",
            func=self._gmail_email_responder,
            args_schema=GmailReplyEmailSchema,
        )

    def _gmail_email_responder(self, message_id: str, reply_text: str, user_id: str, cc: str = "", bcc: str = "") -> list[Data]:
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
                
                original_message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
                thread_id = original_message.get("threadId")
                headers = original_message.get("payload", {}).get("headers", [])
                
                orig_subject, orig_from, orig_message_id = None, None, None
                for header in headers:
                    header_name = header.get("name", "").lower()
                    if header_name == "subject":
                        orig_subject = header.get("value")
                    elif header_name == "from":
                        orig_from = header.get("value")
                    elif header_name == "message-id":
                        orig_message_id = header.get("value")
                
                if not orig_from or not orig_subject or not orig_message_id:
                    return [Data(text="Error: Could not retrieve necessary headers from the original email.")]
                
                reply_subject = f"Re: {orig_subject}" if not orig_subject.lower().startswith("re:") else orig_subject
                
                reply_message = MIMEText(reply_text)
                reply_message["to"] = orig_from
                reply_message["from"] = "me"
                reply_message["subject"] = reply_subject
                reply_message["In-Reply-To"] = orig_message_id
                reply_message["References"] = orig_message_id
                
                if cc:
                    reply_message["Cc"] = cc
                
                raw_message = base64.urlsafe_b64encode(reply_message.as_bytes()).decode()
                email_body = {
                    "raw": raw_message,
                    "threadId": thread_id,
                }
                
                if bcc:
                    email_body["bccAddress"] = bcc
                
                result = service.users().messages().send(userId="me", body=email_body).execute()
                sent_message_id = result.get("id", "unknown")
                return [Data(text=f"Reply sent successfully. Message ID: {sent_message_id}")]
                
        except Exception as e:
            logger.error(f"Error replying to email: {e}")
            return [Data(text=f"Error: {str(e)}")]
