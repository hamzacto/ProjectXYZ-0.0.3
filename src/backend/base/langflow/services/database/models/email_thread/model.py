from datetime import datetime
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, UniqueConstraint

class EmailThread(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    flow_id: UUID = Field(foreign_key="flow.id", index=True)
    thread_id: str = Field(index=True)
    session_id: str = Field(index=True)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (UniqueConstraint("flow_id", "thread_id", name="uix_flow_thread"),) 