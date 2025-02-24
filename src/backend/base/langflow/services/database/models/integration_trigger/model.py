from uuid import UUID, uuid4
from sqlmodel import Field, Relationship, SQLModel, Column, JSON
from typing import TYPE_CHECKING
from langflow.services.database.models.integration_token.model import IntegrationToken
from langflow.services.database.models.flow.model import Flow
if TYPE_CHECKING:
    from langflow.services.database.models.integration_token.model import IntegrationToken
    from langflow.services.database.models.flow.model import Flow

class IntegrationTrigger(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)


    integration_id: UUID = Field(foreign_key="integrationtoken.id", index=True)
    flow_id: UUID = Field(foreign_key="flow.id", index=True)
    # Optionally, you can add settings that influence how the flow is executed