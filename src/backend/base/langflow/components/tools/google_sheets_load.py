import os
import json
from uuid import UUID
from typing import Optional

from sqlmodel import create_engine, Session, select, SQLModel
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from loguru import logger
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import StrInput
from langflow.schema import Data

# Import your IntegrationToken model.
from langflow.services.database.models.integration_token.model import IntegrationToken

# Define the scopes required by the Google Sheets API (read-only).
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

class GoogleSheetsDataLoaderSchema(BaseModel):
    spreadsheet_id: str = Field(..., description="Google Sheet ID")
    range: str = Field(..., description="A1 notation range, e.g., 'A1:D10'")
    user_id: str = Field(..., description="User UUID")
    filter_column: Optional[int] = Field(
        default=None,
        description="0-based index of the column to apply an exact filter match (optional)"
    )
    filter_value: Optional[str] = Field(
        default=None,
        description="Exact value to match in the specified column (optional)"
    )
    search_value: Optional[str] = Field(
        default=None,
        description="Substring to search for in all columns (optional)"
    )

class GoogleSheetsDataLoaderComponent(LCToolComponent):
    display_name = "Google Sheets Data Loader"
    description = "Load and filter data from a Google Sheet, returning a JSON response with the sheet values."
    icon = "GoogleSpreadSheets"
    name = "GoogleSheetsDataLoaderTool"

    inputs = [
        StrInput(
            name="spreadsheet_id",
            display_name="Spreadsheet ID",
            info="Google Sheet ID",
            value="",
            required=False
        ),
        StrInput(
            name="range",
            display_name="Range",
            info="A1 notation range (e.g., 'A1:D10')",
            value="",
            required=False
        ),
        StrInput(
            name="user_id",
            display_name="User ID",
            info="User UUID",
            value="",
            required=False
        ),
        StrInput(
            name="filter_column",
            display_name="Filter Column",
            info="0-based index of the column to filter on (optional)",
            value="",
            required=False
        ),
        StrInput(
            name="filter_value",
            display_name="Filter Value",
            info="Exact value to filter in the specified column (optional)",
            value="",
            required=False
        ),
        StrInput(
            name="search_value",
            display_name="Search Value",
            info="Substring to search for across all columns (optional)",
            value="",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        # Convert filter_column from string to int if provided
        filter_column = int(self.filter_column) if self.filter_column else None
        filter_value = self.filter_value if self.filter_value else None
        search_value = self.search_value if self.search_value else None

        return self._load_data(
            self.spreadsheet_id,
            self.range,
            self.user_id,
            filter_column,
            filter_value,
            search_value,
        )

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            name="google_sheets_data_loader",
            description=(
                "Fetch data from a Google Sheet with optional filtering by an exact column match "
                "and/or a substring search across all cells. Returns a JSON response with the sheet values."
            ),
            func=self._load_data,
            args_schema=GoogleSheetsDataLoaderSchema,
        )

    def _load_data(
        self,
        spreadsheet_id: str,
        range: str,
        user_id: str,
        filter_column: Optional[int] = None,
        filter_value: Optional[str] = None,
        search_value: Optional[str] = None,
    ) -> list[Data]:
        # Validate user_id
        try:
            user_uuid = UUID(self.user_id)
        except ValueError:
            error_message = json.dumps({"status": "error", "error": "Invalid user_id format."})
            logger.error(error_message)
            return [Data(text=error_message)]
    
        # Database connection
        engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
        SQLModel.metadata.create_all(engine)
    
        # Retrieve the correct Google Sheets token
        try:
            with Session(engine) as db:
                sheets_token = db.exec(
                    select(IntegrationToken)
                    .where(IntegrationToken.user_id == user_uuid)
                    .where(IntegrationToken.service_name == "gmail")  # Assuming service_name "gmail" for Sheets token
                ).first()
    
                if not sheets_token:
                    error_message = json.dumps({"status": "error", "error": "Google Sheets token not found."})
                    logger.error(error_message)
                    return [Data(text=error_message)]
    
                credentials = Credentials(
                    token=sheets_token.access_token,
                    refresh_token=sheets_token.refresh_token,
                    token_uri=sheets_token.token_uri,
                    client_id=sheets_token.client_id,
                    client_secret=sheets_token.client_secret,
                    scopes=SCOPES,
                )
                service = build("sheets", "v4", credentials=credentials)
        except Exception as e:
            error_message = json.dumps({"status": "error", "error": f"Token retrieval error: {str(e)}"})
            logger.error(error_message)
            return [Data(text=error_message)]
    
        # Fetch data from Google Sheets
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range
            ).execute()
            values = result.get("values", [])
        except HttpError as e:
            error_message = json.dumps({
                "status": "error",
                "error": f"Google Sheets API error: {e.resp.status} {e.content.decode('utf-8') if hasattr(e.content, 'decode') else e.content}"
            })
            logger.error(error_message)
            return [Data(text=error_message)]
        except Exception as e:
            error_message = json.dumps({"status": "error", "error": f"Unexpected error: {str(e)}"})
            logger.error(error_message)
            return [Data(text=error_message)]
    
        original_count = len(values)
    
        # Apply exact filtering on a specific column if provided
        if filter_column is not None and filter_value is not None:
            values = [
                row for row in values 
                if len(row) > filter_column and row[filter_column].strip().lower() == filter_value.strip().lower()
            ]
    
        # Apply substring search across all columns if provided
        if search_value is not None:
            search_value_lower = search_value.strip().lower()
            values = [
                row for row in values 
                if any(isinstance(cell, str) and search_value_lower in cell.lower() for cell in row)
            ]
    
        filtered_count = len(values)
    
        response = json.dumps({
            "status": "success",
            "original_row_count": original_count,
            "filtered_row_count": filtered_count,
            "data": values
        })
        return [Data(text=response)]
