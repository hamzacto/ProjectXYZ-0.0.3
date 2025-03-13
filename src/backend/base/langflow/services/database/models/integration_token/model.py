from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlmodel import Field, Relationship, SQLModel, Column, JSON
from typing import TYPE_CHECKING
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger
from sqlalchemy import String, DateTime

if TYPE_CHECKING:
    from langflow.services.database.models.user import User

# Encryption configuration
# Generate a key or use an environment variable
ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY", "")
if not ENCRYPTION_KEY:
    logger.warning("No TOKEN_ENCRYPTION_KEY set, generating a random one. Tokens will be lost on restart!")
    # Generate a key for development purposes (in production, this should be stable)
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    ENCRYPTION_KEY = base64.urlsafe_b64encode(kdf.derive(b"langflow-temp-key"))

# Initialize Fernet cipher
try:
    cipher_suite = Fernet(ENCRYPTION_KEY)
except Exception as e:
    logger.error(f"Error initializing encryption: {e}")
    # Fallback to a development key
    cipher_suite = None

def encrypt_token(token: str) -> str:
    """Encrypt a token before storing it in the database."""
    if not cipher_suite:
        logger.warning("Encryption not initialized, storing token as-is")
        return token
        
    try:
        if not token:
            return token
        return cipher_suite.encrypt(token.encode()).decode()
    except Exception as e:
        logger.error(f"Error encrypting token: {e}")
        return token

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a token retrieved from the database."""
    if not cipher_suite:
        logger.warning("Encryption not initialized, returning token as-is")
        return encrypted_token
        
    try:
        if not encrypted_token:
            return encrypted_token
        # Check if the token is already encrypted
        if encrypted_token.startswith('gAAAAA'):
            return cipher_suite.decrypt(encrypted_token.encode()).decode()
        # If not encrypted (e.g., legacy tokens or dev environment)
        return encrypted_token
    except Exception as e:
        logger.error(f"Error decrypting token, it may not be encrypted: {e}")
        return encrypted_token

class IntegrationToken(SQLModel, table=True):  # type: ignore[call-arg]
    id: UUID = Field(default_factory=uuid4, primary_key=True, unique=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)  # Link to User
    service_name: str = Field(index=True)  # e.g., "gmail", "slack"
    access_token: str = Field()  # Store securely in production
    refresh_token: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    token_uri: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    client_id: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    client_secret: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime, nullable=True))  # Token expiration time
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # New fields for Gmail watch:
    last_history_id: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    channel_id: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    # Optionally, a field to store the expiration of the watch subscription:
    watch_expiration: datetime | None = Field(default=None, sa_column=Column(DateTime, nullable=True))

    email_address: str | None = Field(default=None, sa_column=Column(String, nullable=True))

    # JSON field to store additional service-specific metadata
    integration_metadata: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    user: "User" = Relationship(back_populates="integrations")
    
    def get_token(self) -> str:
        """Get the decrypted access token."""
        return decrypt_token(self.access_token)
    
    def set_token(self, token: str) -> None:
        """Set and encrypt the access token."""
        self.access_token = encrypt_token(token)