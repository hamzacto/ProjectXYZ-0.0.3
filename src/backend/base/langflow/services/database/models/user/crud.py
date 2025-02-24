from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.user.model import User, UserUpdate

from langflow.services.database.models.integration_token.model import IntegrationToken

async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return (await db.exec(stmt)).first()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    stmt = select(User).where(User.id == user_id)
    return (await db.exec(stmt)).first()


async def update_user(user_db: User | None, user: UserUpdate, db: AsyncSession) -> User:
    if not user_db:
        raise HTTPException(status_code=404, detail="User not found")

    # user_db_by_username = get_user_by_username(db, user.username)
    # if user_db_by_username and user_db_by_username.id != user_id:
    #     raise HTTPException(status_code=409, detail="Username already exists")

    user_data = user.model_dump(exclude_unset=True)
    changed = False
    for attr, value in user_data.items():
        if hasattr(user_db, attr) and value is not None:
            setattr(user_db, attr, value)
            changed = True

    if not changed:
        raise HTTPException(status_code=status.HTTP_304_NOT_MODIFIED, detail="Nothing to update")

    user_db.updated_at = datetime.now(timezone.utc)
    flag_modified(user_db, "updated_at")

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e

    return user_db


async def update_user_last_login_at(user_id: UUID, db: AsyncSession):
    try:
        user_data = UserUpdate(last_login_at=datetime.now(timezone.utc))
        user = await get_user_by_id(db, user_id)
        return await update_user(user, user_data, db)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error updating user last login at: {e!s}")


# Integrations Token Management

async def create_integration_token(
    db: AsyncSession, 
    user_id: UUID, 
    service_name: str, 
    access_token: str, 
    refresh_token: str | None = None, 
    token_uri: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    expires_at: datetime | None = None,
    email_address: str | None = None
) -> IntegrationToken:
    token = IntegrationToken(
        user_id=user_id,
        service_name=service_name,
        access_token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        expires_at=expires_at,
        email_address=email_address
    )
    db.add(token)
    try:
        await db.commit()
        await db.refresh(token)
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
    
    return token


async def get_integration_tokens(db: AsyncSession, user_id: UUID):
    stmt = select(IntegrationToken).where(IntegrationToken.user_id == user_id)
    return (await db.exec(stmt)).all()

async def get_integration_token_by_id(db: AsyncSession, token_id: UUID):
    stmt = select(IntegrationToken).where(IntegrationToken.id == token_id)
    return (await db.exec(stmt)).first()

async def update_integration_token(db: AsyncSession, token_id: UUID, token: IntegrationToken):
    stmt = select(IntegrationToken).where(IntegrationToken.id == token_id)
    existing_token = (await db.exec(stmt)).first()
    if not existing_token:
        raise HTTPException(status_code=404, detail="Integration token not found")

    existing_token.last_history_id = token.last_history_id
    existing_token.channel_id = token.channel_id
    existing_token.watch_expiration = token.watch_expiration

    await db.commit()
    return existing_token

async def delete_integration_token(db: AsyncSession, token_id: UUID):
    token = await db.get(IntegrationToken, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Integration token not found")
    
    await db.delete(token)
    await db.commit()
    return {"message": "Token deleted successfully"}


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
    try:
        await db.commit()
        await db.refresh(integration_trigger)
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
    return integration_trigger