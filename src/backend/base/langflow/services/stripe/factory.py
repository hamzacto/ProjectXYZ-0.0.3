"""Factory class for creating instances of the StripeService."""

from langflow.services.factory import ServiceFactory
from langflow.services.schema import ServiceType
from langflow.services.base import Service
from langflow.services.stripe.service import StripeService


class StripeServiceFactory(ServiceFactory):
    """Factory for creating StripeService instances."""

    name = ServiceType.STRIPE_SERVICE
    dependencies = []
    
    def __init__(self) -> None:
        super().__init__(StripeService)
    # The Stripe service doesn't directly depend on other services
    # It gets settings via get_settings_service() as needed 

    def create(self, **kwargs) -> Service:
        """Create a new StripeService instance."""
        return StripeService() 