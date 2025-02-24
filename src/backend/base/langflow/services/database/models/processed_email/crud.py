from uuid import UUID
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from langflow.services.database.models.processed_email.model import ProcessedEmail


async def create_processed_email(
    session: AsyncSession,
    flow_id: UUID,
    message_id: str,
) -> ProcessedEmail:
    processed_email = ProcessedEmail(
        flow_id=flow_id,
        message_id=message_id,
    )
    session.add(processed_email)
    await session.commit()
    await session.refresh(processed_email)
    return processed_email


async def get_processed_email(
    session: AsyncSession,
    flow_id: UUID,
    message_id: str,
) -> ProcessedEmail | None:
    query = select(ProcessedEmail).where(
        ProcessedEmail.flow_id == flow_id,
        ProcessedEmail.message_id == message_id
    )
    result = await session.exec(query)
    return result.first()


async def delete_processed_email(
    session: AsyncSession,
    processed_email: ProcessedEmail,
) -> None:
    await session.delete(processed_email)
    await session.commit()