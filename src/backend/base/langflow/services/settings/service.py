from __future__ import annotations

from langflow.services.base import Service
from langflow.services.settings.auth import AuthSettings
from langflow.services.settings.base import Settings
from langflow.services.settings.security import SecuritySettings
import os


class EmailSettings:
    def __init__(self):
        self.SMTP_SERVER = os.getenv("SMTP_SERVER", "")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
        self.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
        self.EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Langflow")
        self.EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", "noreply@langflow.com")
        self.VERIFICATION_TOKEN_EXPIRE_MINUTES = int(os.getenv("VERIFICATION_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
        self.EMAIL_TEMPLATES_DIR = os.getenv("EMAIL_TEMPLATES_DIR", "langflow/emails/templates")
        self.FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


class SettingsService(Service):
    name = "settings_service"

    def __init__(self, settings: Settings, auth_settings: AuthSettings):
        super().__init__()
        self.settings: Settings = settings
        self.auth_settings: AuthSettings = auth_settings
        self.email_settings = EmailSettings()
        self.security_settings = SecuritySettings()

    @classmethod
    def initialize(cls) -> SettingsService:
        # Check if a string is a valid path or a file name

        settings = Settings()
        if not settings.config_dir:
            msg = "CONFIG_DIR must be set in settings"
            raise ValueError(msg)

        auth_settings = AuthSettings(
            CONFIG_DIR=settings.config_dir,
        )
        return cls(settings, auth_settings)

    def set(self, key, value):
        setattr(self.settings, key, value)
        return self.settings
