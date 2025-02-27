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
SCOPES = ['https://www.googleapis.com/auth/calendar']

class GoogleCalendarEventModifierSchema(BaseModel):
    event_id: str = Field(..., description="The ID of the event to modify.")
    calendar_id: str = Field("primary", description="The ID of the calendar to modify (default is 'primary').")
    summary: str = Field("", description="Optional: New summary for the event. Leave blank to keep unchanged.")
    location: str = Field("", description="Optional: New location for the event. Leave blank to keep unchanged.")
    description: str = Field("", description="Optional: New description for the event. Leave blank to keep unchanged.")
    start_datetime: str = Field("", description="Optional: New start datetime in ISO format (e.g., 2025-03-01T09:00:00). Leave blank to keep unchanged.")
    end_datetime: str = Field("", description="Optional: New end datetime in ISO format (e.g., 2025-03-01T10:00:00). Leave blank to keep unchanged.")
    time_zone: str = Field("UTC", description="Time zone for the event (e.g., UTC, America/New_York).")
    attendees: str = Field("", description="Optional: Comma-separated list of new attendee email addresses. Leave blank to keep unchanged.")
    user_id: str = Field(..., description="The current user's ID.")

class GoogleCalendarEventModifierComponent(LCToolComponent):
    display_name = "Google Calendar Event Modifier"
    description = "Modify details of an existing event in Google Calendar using the Calendar API. All errors are passed to the AI Agent."
    icon = "GoogleCalendar"  # Update with your desired icon identifier.
    name = "GoogleCalendarEventModifierTool"

    inputs = [
        StrInput(
            name="event_id",
            display_name="Event ID",
            info="The ID of the event to modify.",
            value="",
            required=False
        ),
        StrInput(
            name="calendar_id",
            display_name="Calendar ID",
            info="The ID of the calendar containing the event (default is 'primary').",
            value="primary",
            required=False
        ),
        StrInput(
            name="summary",
            display_name="New Summary",
            info="Optional: New summary for the event. Leave blank if unchanged.",
            value="",
            required=False
        ),
        StrInput(
            name="location",
            display_name="New Location",
            info="Optional: New location for the event. Leave blank if unchanged.",
            value="",
            required=False
        ),
        StrInput(
            name="description",
            display_name="New Description",
            info="Optional: New description for the event. Leave blank if unchanged.",
            value="",
            required=False
        ),
        StrInput(
            name="start_datetime",
            display_name="New Start DateTime",
            info="Optional: New start datetime in ISO format (e.g., 2025-03-01T09:00:00). Leave blank if unchanged.",
            value="",
            required=False
        ),
        StrInput(
            name="end_datetime",
            display_name="New End DateTime",
            info="Optional: New end datetime in ISO format (e.g., 2025-03-01T10:00:00). Leave blank if unchanged.",
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
            display_name="New Attendees",
            info="Optional: Comma-separated list of new attendee email addresses. Leave blank if unchanged.",
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
        return self._modify_event(
            self.event_id,
            self.calendar_id,
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
            name="google_calendar_event_modifier",
            description=(
                "Modify an existing event in Google Calendar by providing updated details. "
                "If an error occurs, the error is passed to the AI Agent for decision-making."
            ),
            func=self._modify_event,
            args_schema=GoogleCalendarEventModifierSchema,
        )

    def _modify_event(
        self,
        event_id: str = "",
        calendar_id: str = "primary",
        summary: str = "",
        location: str = "",
        description: str = "",
        start_datetime: str = "",
        end_datetime: str = "",
        time_zone: str = "UTC",
        attendees: str = "",
        user_id: str = ""
    ) -> list[Data]:
        # Validate the provided user_id and catch errors without throwing them.
        try:
            user_uuid = UUID(self.user_id)
        except Exception as e:
            error_message = f"Invalid user_id provided: {e}"
            logger.error(error_message)
            return [Data(text=error_message)]
        
        # Create a database connection.
        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)

        try:
            with Session(engine) as db:
                tokens = db.exec(
                    select(IntegrationToken).where(IntegrationToken.user_id == user_uuid)
                ).all()
                
                if not tokens:
                    error_message = "No token was found."
                    logger.error(error_message)
                    return [Data(text=error_message)]
                
                # Retrieve the Google Calendar integration token.
                calendar_token = next(
                    (token for token in tokens if token.service_name == "gmail"),
                    None
                )
                if not calendar_token:
                    error_message = "Google Calendar not connected or token not found."
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
                
                # Build the Calendar API client.
                service = build("calendar", "v3", credentials=credentials)
        except Exception as e:
            error_message = f"Error during token retrieval or service setup: {e}"
            logger.error(error_message)
            return [Data(text=error_message)]
        
        # Build the payload for modifications based on provided fields.
        event_changes = {}
        if summary.strip():
            event_changes["summary"] = summary.strip()
        if location.strip():
            event_changes["location"] = location.strip()
        if description.strip():
            event_changes["description"] = description.strip()
        if start_datetime.strip():
            event_changes["start"] = {
                "dateTime": start_datetime.strip(),
                "timeZone": time_zone
            }
        if end_datetime.strip():
            event_changes["end"] = {
                "dateTime": end_datetime.strip(),
                "timeZone": time_zone
            }
        if attendees.strip():
            event_changes["attendees"] = [{"email": email.strip()} for email in attendees.split(",") if email.strip()]
        
        if not event_changes:
            error_message = "No changes provided to update the event."
            logger.error(error_message)
            return [Data(text=error_message)]
        
        try:
            # Update the event using the patch method.
            updated_event = service.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body=event_changes
            ).execute()
            updated_event_id = updated_event.get("id", "unknown")
            result_text = f"Event updated successfully. Event ID: {updated_event_id}"
            return [Data(text=result_text)]
        except Exception as e:
            error_message = f"Error updating event: {e}"
            logger.error(error_message)
            return [Data(text=error_message)]
