from uuid import UUID
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from langflow.services.database.models.integration_token.model import IntegrationToken
from langflow.services.database.models.integration_trigger.model import IntegrationTrigger

async def create_integration_token(session: AsyncSession, token_data: dict, user_id: UUID):
    db_token = IntegrationToken(
        user_id=user_id,
        integration_name=token_data["integration_name"],
        token_value=token_data["token_value"]
    )
    session.add(db_token)
    await session.commit()
    await session.refresh(db_token)
    return db_token

async def get_user_integration_tokens(session: AsyncSession, user_id: UUID):
    statement = select(IntegrationToken).where(IntegrationToken.user_id == user_id)
    results = await session.exec(statement)
    return results.all()

async def delete_integration_token(session: AsyncSession, token_id: UUID):
    statement = select(IntegrationToken).where(IntegrationToken.id == token_id)
    result = await session.exec(statement)
    token = result.first()
    if token:
        await session.delete(token)
        await session.commit()
    return token

async def get_integration_triggers_by_integration(session: AsyncSession, integration_id: UUID):
    statement = select(IntegrationTrigger).where(IntegrationTrigger.integration_id == integration_id)
    results = await session.exec(statement)
    return results.all()


async def get_integration_by_email_address(db: AsyncSession, email_address: str):
    statement = select(IntegrationToken).where(IntegrationToken.email_address == email_address)
    results = await db.exec(statement)
    return results.first()
