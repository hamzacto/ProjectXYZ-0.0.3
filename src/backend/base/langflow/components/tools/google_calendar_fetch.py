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
from langflow.inputs import StrInput, IntInput
from langflow.schema import Data

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Define the scopes required by the Google Calendar API for reading events.
SCOPES = ['https://www.googleapis.com/auth/calendar']

class GoogleCalendarEventLoaderSchema(BaseModel):
    max_results: int = Field(
        10,
        description="Maximum number of events to retrieve."
    )
    calendar_id: str = Field(
        "primary",
        description="The ID of the calendar to load events from (default is 'primary')."
    )
    time_min: str = Field(
        "",
        description="Optional: The minimum datetime (ISO format, e.g., 2025-03-01T00:00:00Z) for events."
    )
    time_max: str = Field(
        "",
        description="Optional: The maximum datetime (ISO format, e.g., 2025-03-31T23:59:59Z) for events."
    )
    query: str = Field(
        "",
        description="Optional: Text query to filter events by summary or description."
    )
    user_id: str = Field(
        ...,
        description="The current user's ID."
    )

class GoogleCalendarEventLoaderComponent(LCToolComponent):
    display_name = "Google Calendar Event Loader"
    description = "Load events from Google Calendar using the Calendar API."
    icon = "GoogleCalendar"
    name = "GoogleCalendarEventLoaderTool"

    inputs = [
        IntInput(
            name="max_results",
            display_name="Maximum Number of Events",
            info="The maximum number of events to retrieve from the calendar.",
            value=10,
            required=False
        ),
        StrInput(
            name="calendar_id",
            display_name="Calendar ID",
            info="The ID of the calendar to load events from (default is 'primary').",
            value="primary",
            required=False
        ),
        StrInput(
            name="time_min",
            display_name="Time Min",
            info="Optional: Minimum datetime (ISO format, e.g., 2025-03-01T00:00:00Z) for events.",
            value="",
            required=False
        ),
        StrInput(
            name="time_max",
            display_name="Time Max",
            info="Optional: Maximum datetime (ISO format, e.g., 2025-03-31T23:59:59Z) for events.",
            value="",
            required=False
        ),
        StrInput(
            name="query",
            display_name="Query",
            info="Optional: Text query to filter events by summary or description.",
            value="",
            required=False
        ),
        StrInput(
            name="user_id",
            display_name="User ID",
            info="Optional: The current user's ID.",
            value="",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        return self._load_events(
            self.max_results,
            self.calendar_id,
            self.time_min,
            self.time_max,
            self.query,
            self.user_id
        )

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            name="google_calendar_event_loader",
            description=(
                "Fetch events from a Google Calendar by directly querying the database for the integration token "
                "and applying optional filters such as time range or text query."
            ),
            func=self._load_events,
            args_schema=GoogleCalendarEventLoaderSchema,
        )

    def _load_events(
        self,
        max_results: int = 10,
        calendar_id: str = "primary",
        time_min: str = "",
        time_max: str = "",
        query: str = "",
        user_id: str = ""
    ) -> list[Data]:
        # Validate the user_id.
        try:
            user_uuid = UUID(self.user_id)
        except Exception as e:
            error_message = f"Invalid user_id provided: {e}"
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
                    error_message = "No token was found."
                    logger.error(error_message)
                    return [Data(text=error_message)]

                # Retrieve the Google Calendar token.
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
        
        # Prepare query parameters for the events list.
        params = {
            "calendarId": calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime"
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if query:
            params["q"] = query
        
        try:
            events_result = service.events().list(**params).execute()
            events = events_result.get("items", [])
        except Exception as e:
            error_message = f"Error fetching events: {e}"
            logger.error(error_message)
            return [Data(text=error_message)]
        
        # Process and format events into readable details.
        event_list = []
        for event in events:
            event_id = event.get("id", "unknown")
            summary = event.get("summary", "No Title")
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
            end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date", ""))
            description = event.get("description", "")
            location = event.get("location", "")
            
            event_details = (
                f"ID: {event_id}\n"
                f"Summary: {summary}\n"
                f"Start: {start}\n"
                f"End: {end}\n"
                f"Location: {location}\n"
                f"Description: {description}"
            )
            event_list.append(Data(text=event_details))
        
        if not event_list:
            event_list.append(Data(text="No events found for the specified criteria."))
        
        return event_list
