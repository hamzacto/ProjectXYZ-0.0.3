from uuid import UUID
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.integration_trigger.model import IntegrationTrigger


async def create_integration_trigger(
    db: AsyncSession,
    integration_id: UUID,
    flow_id: UUID
) -> IntegrationTrigger:
    """Create a new integration trigger record."""
    integration_trigger = IntegrationTrigger(
        integration_id=integration_id,
        flow_id=flow_id,
    )
    db.add(integration_trigger)
    await db.commit()
    await db.refresh(integration_trigger)
    return integration_trigger

async def get_integration_triggers_by_integration(
    db: AsyncSession,
    integration_id: UUID
) -> list[IntegrationTrigger]:
    """Get all integration triggers by integration ID."""
    query = select(IntegrationTrigger).where(IntegrationTrigger.integration_id == integration_id)
    results = await db.exec(query)
    return results.all()

async def delete_integration_trigger_by_integration_and_flow(
    db: AsyncSession,
    integration_id: UUID,
    flow_id: UUID
) -> None:
    """Delete all integration triggers by integration ID and flow ID."""
    query = select(IntegrationTrigger).where(IntegrationTrigger.integration_id == integration_id, IntegrationTrigger.flow_id == flow_id)
    results = await db.exec(query)
    for trigger in results.all():
        await db.delete(trigger)
    await db.commit()