from typing_extensions import override

from langflow.services.factory import ServiceFactory
from langflow.services.billing.service import BillingService


class BillingServiceFactory(ServiceFactory):
    def __init__(self):
        super().__init__(BillingService)

    @override
    def create(self):
        # BillingService doesn't require specific dependencies in its __init__
        return BillingService() 