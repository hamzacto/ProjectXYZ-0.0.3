import os
import json
from uuid import UUID
from typing import List, Optional

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

# Define the scopes required by the Google Sheets API (read/write).
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

class GoogleSheetsAdvancedDataModifierSchema(BaseModel):
    spreadsheet_id: str = Field(..., description="Google Sheet ID")
    user_id: str = Field(..., description="User UUID")
    update_mode: str = Field(..., description="Update mode: 'line' for a specific row, 'range' for a specified range")
    range: Optional[str] = Field(
        None,
        description="A1 notation range to modify (e.g., 'A1:C3'); required if update_mode is 'range'"
    )
    row_number: Optional[int] = Field(
        None,
        description="Row number to modify (1-indexed); required if update_mode is 'line'"
    )
    start_column: Optional[str] = Field(
        None,
        description="Start column letter for modification (e.g., 'A'); required if update_mode is 'line'"
    )
    end_column: Optional[str] = Field(
        None,
        description="End column letter for modification (e.g., 'C'); required if update_mode is 'line'"
    )
    new_data: str = Field(..., description=(
        "New data to write. For 'line' mode, provide a JSON list of strings (e.g., ['A1','B1']); "
        "for 'range' mode, provide a JSON string of lists (e.g., '[[\"A1\",\"B1\"], [\"A2\",\"B2\"]]') without wrapping the entire list in an additional string."
    ))

class GoogleSheetsDataModifierComponent(LCToolComponent):
    display_name = "Google Sheets Data Modifier"
    description = (
        "Advanced tool to modify data in a Google Sheet. "
        "Supports 'line' mode to update a specific row and 'range' mode to update a custom range."
    )
    icon = "GoogleSpreadSheets"
    name = "GoogleSheetsDataModifierTool"

    inputs = [
        StrInput(
            name="spreadsheet_id",
            display_name="Spreadsheet ID",
            info="Google Sheet ID",
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
            name="update_mode",
            display_name="Update Mode",
            info="Update mode: 'line' for a specific row, 'range' for a specified range",
            value="",
            required=False
        ),
        StrInput(
            name="range",
            display_name="Range",
            info="A1 notation range to modify (e.g., 'A1:C3'); required if update_mode is 'range'",
            value="",
            required=False
        ),
        StrInput(
            name="row_number",
            display_name="Row Number",
            info="Row number to modify (1-indexed); required if update_mode is 'line'",
            value="",
            required=False
        ),
        StrInput(
            name="start_column",
            display_name="Start Column",
            info="Start column letter for modification (e.g., 'A'); required if update_mode is 'line'",
            value="",
            required=False
        ),
        StrInput(
            name="end_column",
            display_name="End Column",
            info="End column letter for modification (e.g., 'C'); required if update_mode is 'line'",
            value="",
            required=False
        ),
        StrInput(
            name="new_data",
            display_name="New Data",
            info=(
                "New data to write. For 'line' mode, provide a JSON list of strings (e.g., ['A1','B1']); "
                "for 'range' mode, provide a JSON string of lists (e.g., '[[\"A1\",\"B1\"], [\"A2\",\"B2\"]]') without wrapping the entire list in an additional string."
            ),
            value="",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        try:
            return self.modify_data(
                spreadsheet_id=self.spreadsheet_id,
                user_id=self.user_id,
                update_mode=self.update_mode,
                range=self.range,
                row_number=self.row_number,
                start_column=self.start_column,
                end_column=self.end_column,
                new_data=self.new_data,
            )
        except Exception as e:
            error_message = json.dumps({"status": "error", "error": f"Unhandled exception in run_model: {str(e)}"})
            logger.error(error_message)
            return [Data(text=error_message)]

    def build_tool(self) -> Tool:
        return StructuredTool.from_function(
            name="google_sheets_advanced_data_modifier",
            description=(
                "Advanced tool to modify data in a Google Sheet. "
                "Supports 'line' mode to update a specific row and 'range' mode to update a custom range."
            ),
            func=self.modify_data,
            args_schema=GoogleSheetsAdvancedDataModifierSchema,
        )

    def modify_data(
        self,
        spreadsheet_id: str,
        user_id: str,
        update_mode: str,
        new_data: str,
        range: Optional[str] = None,
        row_number: Optional[int] = None,
        start_column: Optional[str] = None,
        end_column: Optional[str] = None,
    ) -> list[Data]:
        try:
            update_mode = update_mode.strip().lower() if update_mode else ""
            # Parse the new_data parameter from JSON
            try:
                parsed_new_data = json.loads(new_data)
            except Exception as e:
                error_message = json.dumps({"status": "error", "error": f"Invalid new_data format: {str(e)}"})
                logger.error(error_message)
                return [Data(text=error_message)]
            
            if update_mode == "line":
                # Validate required parameters for line mode
                if row_number is None or not start_column or not end_column:
                    error_message = json.dumps({
                        "status": "error", 
                        "error": "For 'line' mode, row_number, start_column, and end_column are required."
                    })
                    logger.error(error_message)
                    return [Data(text=error_message)]
                try:
                    row_number_int = int(row_number)
                except ValueError:
                    error_message = json.dumps({"status": "error", "error": "row_number must be an integer."})
                    logger.error(error_message)
                    return [Data(text=error_message)]
                # Construct A1 notation range for the specific row (including sheet name)
                computed_range = f"{start_column.upper()}{row_number_int}:{end_column.upper()}{row_number_int}"
                # new_data for 'line' mode should be a JSON list of strings; wrap it in a list for the API
                if not isinstance(parsed_new_data, list) or (parsed_new_data and isinstance(parsed_new_data[0], list)):
                    error_message = json.dumps({
                        "status": "error", 
                        "error": "For 'line' mode, new_data must be a JSON list of strings."
                    })
                    logger.error(error_message)
                    return [Data(text=error_message)]
                new_data_to_use = [parsed_new_data]
            elif update_mode == "range":
                if not range:
                    error_message = json.dumps({"status": "error", "error": "For 'range' mode, the range parameter is required."})
                    logger.error(error_message)
                    return [Data(text=error_message)]
                computed_range = range.strip()
                # new_data for 'range' mode should be a JSON list of lists
                if not isinstance(parsed_new_data, list) or not parsed_new_data or not isinstance(parsed_new_data[0], list):
                    error_message = json.dumps({
                        "status": "error", 
                        "error": "For 'range' mode, new_data must be a JSON list of lists."
                    })
                    logger.error(error_message)
                    return [Data(text=error_message)]
                new_data_to_use = parsed_new_data
            else:
                error_message = json.dumps({"status": "error", "error": "Invalid update_mode. Must be 'line' or 'range'."})
                logger.error(error_message)
                return [Data(text=error_message)]
            
            return self._modify_data(spreadsheet_id, computed_range, user_id, new_data_to_use)
        except Exception as e:
            error_message = json.dumps({"status": "error", "error": f"Unhandled exception in modify_data: {str(e)}"})
            logger.error(error_message)
            return [Data(text=error_message)]

    def _modify_data(self, spreadsheet_id: str, computed_range: str, user_id: str, new_data: List[List[str]]) -> list[Data]:
        try:
            # Validate the user_id format
            try:
                user_uuid = UUID(self.user_id)
            except ValueError:
                error_message = json.dumps({"status": "error", "error": "Invalid user_id format."})
                logger.error(error_message)
                return [Data(text=error_message)]

            # Establish the database connection
            engine = create_engine("sqlite:///src/backend/base/langflow/langflow.db")
            SQLModel.metadata.create_all(engine)

            # Retrieve the correct Google Sheets token from the database
            try:
                with Session(engine) as db:
                    sheets_token = db.exec(
                        select(IntegrationToken)
                        .where(IntegrationToken.user_id == user_uuid)
                        .where(IntegrationToken.service_name == "gmail")  # Assuming the token is stored under "gmail"
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

            # Modify the data in the specified range of the spreadsheet
            try:
                body = {"values": new_data}
                result = service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=computed_range,
                    valueInputOption="USER_ENTERED",
                    body=body
                ).execute()
                response = json.dumps({"status": "success", "result": result})
                return [Data(text=response)]
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
        except Exception as e:
            error_message = json.dumps({"status": "error", "error": f"Unhandled exception in _modify_data: {str(e)}"})
            logger.error(error_message)
            return [Data(text=error_message)]
