import os
from uuid import UUID

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

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Define the scopes required by the Google Calendar API.
SCOPES = ['https://www.googleapis.com/auth/calendar',"https://www.googleapis.com/auth/calendar.events"]

class GoogleCalendarEventCreatorSchema(BaseModel):
    summary: str = Field(..., description="Summary or title of the event.")
    location: str = Field("", description="Optional: Location of the event.")
    description: str = Field("", description="Optional: Description of the event.")
    start_datetime: str = Field(
        ...,
        description="Start datetime in ISO format (e.g., 2025-03-01T09:00:00)."
    )
    end_datetime: str = Field(
        ...,
        description="End datetime in ISO format (e.g., 2025-03-01T10:00:00)."
    )
    time_zone: str = Field("UTC", description="Time zone for the event (e.g., UTC, America/New_York).")
    attendees: str = Field(
        "",
        description="Optional: Comma-separated list of attendee email addresses."
    )
    user_id: str = Field(..., description="The current user's ID.")

class GoogleCalendarEventCreatorComponent(LCToolComponent):
    display_name = "Google Calendar Event Creator"
    description = "Create a new event in Google Calendar using the Calendar API."
    icon = "GoogleCalendar"  # Update with your desired icon identifier.
    name = "GoogleCalendarEventCreatorTool"

    inputs = [
        StrInput(
            name="summary",
            display_name="Event Summary",
            info="Title or summary of the event.",
            value="",
            required=False
        ),
        StrInput(
            name="location",
            display_name="Location",
            info="Optional: Location of the event.",
            value="",
            required=False
        ),
        StrInput(
            name="description",
            display_name="Description",
            info="Optional: Description of the event.",
            value="",
            required=False
        ),
        StrInput(
            name="start_datetime",
            display_name="Start DateTime",
            info="Start datetime in ISO format (e.g., 2025-03-01T09:00:00).",
            value="",
            required=False
        ),
        StrInput(
            name="end_datetime",
            display_name="End DateTime",
            info="End datetime in ISO format (e.g., 2025-03-01T10:00:00).",
            value="",
            required=False
        ),
        StrInput(
            name="time_zone",
            display_name="Time Zone",
            info="Time zone for the event (e.g., UTC, America/New_York).",
            value="UTC",
            required=False
        ),
        StrInput(
            name="attendees",
            display_name="Attendees",
            info="Optional: Comma-separated list of attendee email addresses.",
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
        return self._create_event(
            self.summary,
            self.location,
            self.description,
            self.start_datetime,
            self.end_datetime,
            self.time_zone,
            self.attendees,
            self.user_id
        )

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            name="google_calendar_event_creator",
            description=(
                "Create a new event in Google Calendar using provided details. "
                "Fetches the Google Calendar integration token from the database and creates the event."
            ),
            func=self._create_event,
            args_schema=GoogleCalendarEventCreatorSchema,
        )

    def _create_event(
        self,
        summary: str = "",
        location: str = "",
        description: str = "",
        start_datetime: str = "",
        end_datetime: str = "",
        time_zone: str = "UTC",
        attendees: str = "",
        user_id: str = ""
    ) -> list[Data]:
        # Validate and convert the provided user_id into a UUID.
        try:
            user_uuid = UUID(self.user_id)
        except Exception as e:
            error_message = f"Error: Invalid user_id provided: {e}"
            logger.error(error_message)
            return [Data(text=error_message)]
        
        # Create a direct database connection.
        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)

        try:
            with Session(engine) as db:
                tokens = db.exec(
                    select(IntegrationToken).where(IntegrationToken.user_id == user_uuid)
                ).all()

                if not tokens:
                    error_message = "Error: No token was found."
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Retrieve the Google Calendar token.
                calendar_token = next(
                    (token for token in tokens if token.service_name == "gmail"),
                    None
                )
                if not calendar_token:
                    error_message = "Error: Google Calendar not connected or token not found."
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Ensure the token has the necessary credentials.
                if not (calendar_token.refresh_token and calendar_token.token_uri and
                        calendar_token.client_id and calendar_token.client_secret):
                    error_message = ("Error: The Google Calendar integration token is incomplete. "
                                     "Please reauthenticate to provide the necessary credentials.")
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Build the Google Calendar API credentials.
                credentials = Credentials(
                    token=calendar_token.access_token,
                    refresh_token=calendar_token.refresh_token,
                    token_uri=calendar_token.token_uri,
                    client_id=calendar_token.client_id,
                    client_secret=calendar_token.client_secret,
                    scopes=SCOPES
                )

                # Build the Google Calendar API client.
                service = build("calendar", "v3", credentials=credentials)
        except Exception as e:
            error_message = f"Error during token retrieval or service setup: {e}"
            logger.error(error_message)
            return [Data(text=error_message)]

        # Build the event details.
        event = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": {
                "dateTime": start_datetime,
                "timeZone": time_zone
            },
            "end": {
                "dateTime": end_datetime,
                "timeZone": time_zone
            },
        }
        if attendees.strip():
            event["attendees"] = [{"email": email.strip()} for email in attendees.split(",") if email.strip()]

        try:
            # Insert the event into the user's primary calendar.
            created_event = service.events().insert(calendarId="primary", body=event).execute()
            event_id = created_event.get("id", "unknown")
            result_text = f"Event created successfully. Event ID: {event_id}"
            return [Data(text=result_text)]
        except Exception as e:
            error_message = f"Error creating event: {e}"
            logger.error(error_message)
            return [Data(text=error_message)]
