"""Factory class for the download service."""
from langflow.services.download.service import DownloadService
from langflow.services.factory import ServiceFactory


class DownloadServiceFactory(ServiceFactory):
    """Factory class for creating a download service."""
    
    def __init__(self) -> None:
        """Initialize the factory with the DownloadService class."""
        super().__init__(DownloadService)
    
    def create(self):
        """Create a new instance of the DownloadService."""
        return DownloadService() 