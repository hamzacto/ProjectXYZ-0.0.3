from uuid import UUID
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from .model import EmailThread
from datetime import datetime

async def create_email_thread(
    session: AsyncSession,
    flow_id: UUID,
    thread_id: str,
    session_id: str,
) -> EmailThread:
    email_thread = EmailThread(
        flow_id=flow_id,
        thread_id=thread_id,
        session_id=session_id,
    )
    session.add(email_thread)
    await session.commit()
    await session.refresh(email_thread)
    return email_thread

async def get_email_thread(
    session: AsyncSession,
    flow_id: UUID,
    thread_id: str,
) -> EmailThread | None:
    query = select(EmailThread).where(
        EmailThread.flow_id == flow_id,
        EmailThread.thread_id == thread_id
    )
    result = await session.exec(query)
    return result.first()

async def update_email_thread(
    session: AsyncSession,
    email_thread: EmailThread,
) -> EmailThread:
    email_thread.last_updated = datetime.utcnow()
    session.add(email_thread)
    await session.commit()
    await session.refresh(email_thread)
    return email_thread 