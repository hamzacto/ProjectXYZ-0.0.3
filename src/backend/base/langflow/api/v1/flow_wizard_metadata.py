from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.flow_wizard_metadata.model import (
    FlowWizardMetadataCreate,
    FlowWizardMetadataRead,
    FlowWizardMetadataUpdate,
)
from langflow.services.database.models.flow_wizard_metadata.utils import (
    create_flow_wizard_metadata,
    delete_flow_wizard_metadata,
    get_flow_wizard_metadata,
    update_flow_wizard_metadata,
)

# Build router
router = APIRouter(prefix="/flow-wizard-metadata", tags=["Flow Wizard Metadata"])


@router.post("/{flow_id}", response_model=FlowWizardMetadataRead, status_code=201)
async def create_metadata(
    *,
    session: DbSession,
    flow_id: UUID,
    metadata: FlowWizardMetadataUpdate,
    current_user: CurrentActiveUser,
):
    """Create or update wizard metadata for a flow."""
    try:
        # Check if flow exists and belongs to current user
        flow = await session.get(Flow, flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        if flow.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this flow")
        
        # Check if metadata already exists for this flow
        existing_metadata = await get_flow_wizard_metadata(session, flow_id)
        if existing_metadata:
            # Update the existing metadata
            updated_metadata = await update_flow_wizard_metadata(
                session, flow_id, metadata
            )
            return updated_metadata
        else:
            # Create new metadata
            metadata_create = FlowWizardMetadataCreate(
                flow_id=flow_id, 
                wizard_metadata=metadata.wizard_metadata or {}
            )
            db_metadata = await create_flow_wizard_metadata(session, metadata_create)
            return db_metadata
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{flow_id}", response_model=FlowWizardMetadataRead, status_code=200)
async def read_metadata(
    *,
    session: DbSession,
    flow_id: UUID,
    current_user: CurrentActiveUser,
):
    """Read wizard metadata for a flow."""
    try:
        # Check if flow exists and belongs to current user
        flow = await session.get(Flow, flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        if flow.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this flow")
        
        # Get the metadata
        metadata = await get_flow_wizard_metadata(session, flow_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Wizard metadata not found for this flow")
        
        return metadata
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{flow_id}", status_code=204)
async def delete_metadata(
    *,
    session: DbSession,
    flow_id: UUID,
    current_user: CurrentActiveUser,
):
    """Delete wizard metadata for a flow."""
    try:
        # Check if flow exists and belongs to current user
        flow = await session.get(Flow, flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        if flow.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this flow")
        
        # Delete the metadata
        success = await delete_flow_wizard_metadata(session, flow_id)
        if not success:
            raise HTTPException(status_code=404, detail="Wizard metadata not found for this flow")
        
        return None
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(e))
