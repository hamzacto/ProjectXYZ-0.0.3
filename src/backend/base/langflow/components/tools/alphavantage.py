import os
import requests
import json
import pprint
from enum import Enum

from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.inputs import StrInput, DropdownInput
from langflow.schema import Data
from loguru import logger
from langflow.field_typing import Tool

os.load_dotenv()

# Define the available methods for Alpha Vantage.
class AlphaVantageMethod(str, Enum):
    OVERVIEW = "OVERVIEW"
    TIME_SERIES_DAILY = "TIME_SERIES_DAILY"
    TIME_SERIES_INTRADAY = "TIME_SERIES_INTRADAY"
    TIME_SERIES_WEEKLY = "TIME_SERIES_WEEKLY"
    TIME_SERIES_MONTHLY = "TIME_SERIES_MONTHLY"

# Define the input schema.
class AlphaVantageSchema(BaseModel):
    symbol: str = Field(..., description="The stock symbol to retrieve data for (e.g., AAPL, NVDA).")
    method: AlphaVantageMethod = Field(AlphaVantageMethod.OVERVIEW, description="The type of data to retrieve.")
    interval: str = Field("5min", description="Interval for intraday data (only applicable for TIME_SERIES_INTRADAY).")

class AlphaVantageComponent(LCToolComponent):
    display_name = "Alpha Vantage"
    description = "Fetch financial data from Alpha Vantage API."
    icon = "trending-up"
    name = "AlphaVantageTool"

    # Define the tool's input fields.
    inputs = [
        StrInput(
            name="symbol",
            display_name="Stock Symbol",
            info="The stock symbol to retrieve data for (e.g., AAPL, NVDA).",
            value="",
            required=False
        ),
        DropdownInput(
            name="method",
            display_name="Data Method",
            info="The type of data to retrieve.",
            options=[method.value for method in AlphaVantageMethod],
            value=AlphaVantageMethod.OVERVIEW.value,
            required=True
        ),
        StrInput(
            name="interval",
            display_name="Interval",
            info="Interval for intraday data (only used for TIME_SERIES_INTRADAY, e.g., 1min, 5min, 15min).",
            value="5min",
            required=False
        ),
    ]

    def run_model(self) -> list[Data]:
        """Synchronously run the Alpha Vantage tool."""
        return self._alpha_vantage_tool(self.symbol, self.method, self.interval)

    def build_tool(self) -> Tool:
        """Build a structured tool instance."""
        return StructuredTool.from_function(
            name="alpha_vantage",
            description="Fetch financial data from Alpha Vantage API based on the given method.",
            func=self._alpha_vantage_tool,
            args_schema=AlphaVantageSchema,
        )

    def _alpha_vantage_tool(self, symbol: str, method: str, interval: str = "5min") -> list[Data]:
        """Retrieve data from Alpha Vantage based on the selected method."""
        api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if not api_key:
            error_message = "Alpha Vantage API key not set in environment variable 'ALPHA_VANTAGE_API_KEY'."
            logger.error(error_message)
            raise Exception(e)

        base_url = "https://www.alphavantage.co/query"
        params = {"symbol": symbol, "apikey": api_key}

        try:
            method_enum = AlphaVantageMethod(method)
        except Exception as e:
            error_message = f"Invalid method: {method}"
            logger.error(error_message)
            raise Exception(e)

        # Build parameters based on the selected method.
        if method_enum == AlphaVantageMethod.OVERVIEW:
            params["function"] = "OVERVIEW"
        elif method_enum == AlphaVantageMethod.TIME_SERIES_DAILY:
            params["function"] = "TIME_SERIES_DAILY"
        elif method_enum == AlphaVantageMethod.TIME_SERIES_INTRADAY:
            params["function"] = "TIME_SERIES_INTRADAY"
            params["interval"] = interval
        elif method_enum == AlphaVantageMethod.TIME_SERIES_WEEKLY:
            params["function"] = "TIME_SERIES_WEEKLY"
        elif method_enum == AlphaVantageMethod.TIME_SERIES_MONTHLY:
            params["function"] = "TIME_SERIES_MONTHLY"
        else:
            error_message = f"Unsupported method: {method}"
            logger.error(error_message)
            raise Exception(e)

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            # Check for API rate limit or errors.
            if "Note" in data:
                error_message = f"Alpha Vantage API rate limit exceeded or note: {data['Note']}"
                logger.error(error_message)
                raise Exception(e)
            if "Error Message" in data:
                error_message = f"Alpha Vantage API error: {data['Error Message']}"
                logger.error(error_message)
                raise Exception(e)

            # Format the result for display.
            result_text = pprint.pformat(data)
        except Exception as e:
            error_message = f"Error fetching data from Alpha Vantage: {e}"
            logger.error(error_message)
            raise Exception(e)

        return [Data(text=result_text)]
