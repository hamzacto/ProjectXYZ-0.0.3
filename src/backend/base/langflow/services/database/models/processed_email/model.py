from datetime import datetime
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Relationship, UniqueConstraint
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langflow.services.database.models.flow.model import Flow

class ProcessedEmail(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    flow_id: UUID = Field(foreign_key="flow.id", index=True)
    message_id: str = Field(index=True)
    processed_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (UniqueConstraint("flow_id", "message_id", name="uix_flow_message"),)
    # Relationship to Flow
    #flow: "Flow" = Relationship(back_populates="processed_emails") 