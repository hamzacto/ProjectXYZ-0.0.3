from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlmodel import Field, Relationship, SQLModel, Column, JSON
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langflow.services.database.models.user import User

class IntegrationToken(SQLModel, table=True):  # type: ignore[call-arg]
    id: UUID = Field(default_factory=uuid4, primary_key=True, unique=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)  # Link to User
    service_name: str = Field(index=True)  # e.g., "gmail", "slack"
    access_token: str = Field()  # Store securely in production
    refresh_token: str | None = Field(default=None, nullable=True)
    token_uri: str | None = Field(default=None, nullable=True)
    client_id: str | None = Field(default=None, nullable=True)
    client_secret: str | None = Field(default=None, nullable=True)
    expires_at: datetime | None = Field(default=None, nullable=True)  # Token expiration time
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # New fields for Gmail watch:
    last_history_id: str | None = Field(default=None, nullable=True)
    channel_id: str | None = Field(default=None, nullable=True)
    # Optionally, a field to store the expiration of the watch subscription:
    watch_expiration: datetime | None = Field(default=None, nullable=True)

    email_address: str | None = Field(default=None, nullable=True)

    user: "User" = Relationship(back_populates="integrations")