from typing import TYPE_CHECKING

from typing_extensions import override

from langflow.services.factory import ServiceFactory
from langflow.services.email.service import EmailService

if TYPE_CHECKING:
    from langflow.services.settings.service import SettingsService


class EmailServiceFactory(ServiceFactory):
    def __init__(self):
        super().__init__(EmailService)

    @override
    def create(self, settings_service: "SettingsService"):
        return EmailService(settings_service=settings_service) 