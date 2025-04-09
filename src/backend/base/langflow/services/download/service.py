"""Download service for Langflow."""
import os
from pathlib import Path
from typing import Optional

from loguru import logger

from langflow.services.base import Service
from langflow.services.schema import ServiceType


class DownloadService(Service):
    """Service to handle file downloads."""
    name = ServiceType.DOWNLOAD_SERVICE

    def __init__(self):
        """Initialize the download service."""
        super().__init__()
        self.downloads_dir = Path(os.environ.get("DOWNLOADS_DIR", "downloads"))
        os.makedirs(self.downloads_dir, exist_ok=True)
        logger.info(f"Download service initialized with downloads directory: {self.downloads_dir}")

    def save_file(self, file_content: bytes, filename: str, subdirectory: Optional[str] = None) -> Path:
        """Save a file to the downloads directory."""
        if subdirectory:
            target_dir = self.downloads_dir / subdirectory
            os.makedirs(target_dir, exist_ok=True)
        else:
            target_dir = self.downloads_dir

        filepath = target_dir / filename
        with open(filepath, "wb") as f:
            f.write(file_content)
        
        logger.info(f"File saved: {filepath}")
        return filepath

    def get_file_path(self, filename: str, subdirectory: Optional[str] = None) -> Path:
        """Get the path to a file in the downloads directory."""
        if subdirectory:
            return self.downloads_dir / subdirectory / filename
        return self.downloads_dir / filename 