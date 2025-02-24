from langchain_core.tools import Tool
import os
import logging
from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.inputs import IntInput, MultilineInput, SecretStrInput
from langflow.schema import Data
from dotenv import load_dotenv

load_dotenv()

google_search_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
google_engine_cse_id = os.getenv("GOOGLE_ENGINE_CSE_ID")

logger = logging.getLogger(__name__)

class GoogleSearchAPIComponent(LCToolComponent):
    display_name = "Google Search"
    description = "Call Google Search API."
    name = "GoogleSearchAPI"
    icon = "Google"
    legacy = False
    inputs = [
        MultilineInput(
            name="input_value",
            display_name="Input",
            required=False,
        ),
        IntInput(name="k", display_name="Number of results", value=4, required=True),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._wrapper = None

    def _initialize_wrapper(self):
        if self._wrapper is None:
            try:
                from langchain_google_community import GoogleSearchAPIWrapper
            except ImportError as e:
                msg = "Please install langchain-google-community to use GoogleSearchAPIWrapper."
                raise ImportError(msg) from e
            if not google_search_api_key or not google_engine_cse_id:
                raise ValueError("Google API key or CSE ID not configured properly.")
            self._wrapper = GoogleSearchAPIWrapper(
                google_api_key=google_search_api_key, 
                google_cse_id=google_engine_cse_id, 
                k=self.k
            )
        return self._wrapper

    def run_model(self) -> Data | list[Data]:
        if not self.input_value:
            error_msg = "No input query provided."
            logger.error(error_msg)
            return [Data(data={"error": error_msg}, text=error_msg)]
        try:
            wrapper = self._initialize_wrapper()
            results = wrapper.results(query=self.input_value, num_results=self.k)
            data = [Data(data=result, text=result.get("snippet", "")) for result in results]
            self.status = data
            return data
        except Exception as e:
            error_msg = f"Error during Google Search API call: {e}"
            logger.error(error_msg)
            return [Data(data={"error": error_msg}, text=error_msg)]

    def build_tool(self) -> Tool:
        # The function used here could be a simple wrapper around run_model for consistency.
        def tool_func(query: str) -> list[Data]:
            self.input_value = query
            return self.run_model()
        return Tool(
            name="google_search",
            description="Search Google for recent results.",
            func=tool_func,
        )