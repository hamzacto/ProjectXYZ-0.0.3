# Path: src/backend/langflow/services/database/models/flow_wizard_metadata/utils.py

from uuid import UUID
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.flow_wizard_metadata.model import (
    FlowWizardMetadata,
    FlowWizardMetadataCreate,
    FlowWizardMetadataUpdate,
)

async def get_flow_wizard_metadata(session: AsyncSession, flow_id: UUID) -> FlowWizardMetadata | None:
    """Get the wizard metadata for a flow"""
    result = await session.exec(
        select(FlowWizardMetadata).where(FlowWizardMetadata.flow_id == flow_id)
    )
    return result.first()

async def create_flow_wizard_metadata(
    session: AsyncSession, metadata_create: FlowWizardMetadataCreate
) -> FlowWizardMetadata:
    """Create new wizard metadata for a flow"""
    metadata = FlowWizardMetadata(**metadata_create.model_dump())
    session.add(metadata)
    await session.commit()
    await session.refresh(metadata)
    return metadata

async def update_flow_wizard_metadata(
    session: AsyncSession, 
    flow_id: UUID, 
    metadata_update: FlowWizardMetadataUpdate
) -> FlowWizardMetadata | None:
    """Update wizard metadata for a flow"""
    metadata = await get_flow_wizard_metadata(session, flow_id)
    if not metadata:
        return None
    
    update_data = metadata_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(metadata, key, value)
    
    session.add(metadata)
    await session.commit()
    await session.refresh(metadata)
    return metadata

async def delete_flow_wizard_metadata(
    session: AsyncSession, flow_id: UUID
) -> bool:
    """Delete wizard metadata for a flow"""
    metadata = await get_flow_wizard_metadata(session, flow_id)
    if not metadata:
        return False
    
    await session.delete(metadata)
    await session.commit()
    return True
