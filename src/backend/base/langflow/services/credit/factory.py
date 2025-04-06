from typing_extensions import override

from langflow.services.factory import ServiceFactory
from langflow.services.credit.service import CreditService


class CreditServiceFactory(ServiceFactory):
    def __init__(self) -> None:
        super().__init__(CreditService)

    @override
    def create(self):
        """Create a new instance of the CreditService."""
        return CreditService() 