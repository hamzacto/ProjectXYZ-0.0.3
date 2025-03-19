# Path: src/backend/langflow/services/database/models/flow_wizard_metadata/model.py

from typing import TYPE_CHECKING, Dict, Any, Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, Relationship, Column
from sqlalchemy import JSON
from pydantic import BaseModel

if TYPE_CHECKING:
    from langflow.services.database.models.flow import Flow

class FlowWizardMetadataBase(SQLModel):
    """Base model for flow wizard metadata"""
    # Use explicit typing with Optional for nullable fields
    wizard_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Metadata from the guided wizard process"
    )


class FlowWizardMetadata(FlowWizardMetadataBase, table=True):
    """Database model for flow wizard metadata"""
    __tablename__ = "flow_wizard_metadata"

    id: UUID = Field(default_factory=uuid4, primary_key=True, unique=True)
    flow_id: UUID = Field(foreign_key="flow.id", index=True)
    # Removing back_populates to avoid needing a relationship in the Flow model
    flow: "Flow" = Relationship()


class FlowWizardMetadataCreate(FlowWizardMetadataBase):
    """Create model for flow wizard metadata"""
    flow_id: UUID


class FlowWizardMetadataRead(FlowWizardMetadataBase):
    """Read model for flow wizard metadata"""
    id: UUID
    flow_id: UUID


class FlowWizardMetadataUpdate(BaseModel):
    """Update model for flow wizard metadata"""
    wizard_metadata: Optional[Dict[str, Any]] = None
