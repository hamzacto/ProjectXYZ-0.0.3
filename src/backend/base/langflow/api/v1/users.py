from typing import Annotated
from uuid import UUID
import re
from email_validator import validate_email, EmailNotValidError
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select, Field, SQLModel
from sqlmodel.sql.expression import SelectOfScalar

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.api.v1.schemas import UsersResponse
from langflow.initial_setup.setup import get_or_create_default_folder
from langflow.services.auth.utils import (
    get_current_active_superuser,
    get_password_hash,
    verify_password,
)
from langflow.services.database.models.user import User, UserCreate, UserRead, UserUpdate
from langflow.services.database.models.user.crud import get_user_by_id, update_user
from langflow.services.deps import get_settings_service
from langflow.services.email.service import get_email_service
from jose import JWTError, jwt
from langflow.services.limiter.service import password_reset_limiter, email_verification_limiter, registration_limiter
from langflow.services.database.models.billing.utils import create_default_subscription_plans
from langflow.services.database.models.billing import SubscriptionPlan
from loguru import logger

router = APIRouter(tags=["Users"], prefix="/users")

# Add PasswordResetRequest model
class PasswordResetRequest(SQLModel):
    token: str
    new_password: str


@router.post("/", response_model=UserRead, status_code=201)
async def add_user(
    request: Request,
    user: UserCreate,
    session: DbSession,
    _: None = Depends(registration_limiter),
) -> User:
    """Add a new user to the database."""
    
    # Validate email format
    try:
        # Validates and normalizes the email
        valid_email = validate_email(user.email)
        normalized_email = valid_email.normalized
    except EmailNotValidError:
        raise HTTPException(status_code=400, detail="Invalid email format")

    try:
        # Get or create default subscription plans asynchronously
        plans = await create_default_subscription_plans(session)
        free_plan = plans.get("free")
        if not free_plan:
            raise HTTPException(status_code=500, detail="Default 'free' subscription plan not found.")

        # Prepare user data dictionary including defaults
        user_data = user.model_dump()
        user_data["email"] = normalized_email
        user_data["password"] = get_password_hash(user.password)
        user_data["is_active"] = False
        user_data["is_verified"] = False
        user_data["subscription_plan_id"] = free_plan.id
        user_data["subscription_status"] = "active"  # Start as active on free plan
        user_data["subscription_start_date"] = datetime.now(timezone.utc)
        user_data["credits_balance"] = free_plan.monthly_quota_credits # Assign initial credits from plan

        # Validate the complete user data dictionary
        new_user = User.model_validate(user_data)

        # Add user to session and commit
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        
        # Create default folder for the user
        folder = await get_or_create_default_folder(session, new_user.id)
        if not folder:
            raise HTTPException(status_code=500, detail="Error creating default folder")
        
        # Create initial billing period for the user
        try:
            from langflow.services.billing.cycle_manager import get_billing_cycle_manager
            from langflow.services.database.models.billing.models import BillingPeriod
            
            now = datetime.now(timezone.utc)
            end_date = now + timedelta(days=30)  # Standard 30-day period
            
            # Create the billing period record
            billing_period = BillingPeriod(
                user_id=new_user.id,
                start_date=now,
                end_date=end_date,
                subscription_plan_id=free_plan.id,
                status="active",
                quota_used=0.0,
                quota_remaining=free_plan.monthly_quota_credits,
                overage_credits=0.0,
                overage_cost=0.0,
                is_plan_change=False,
                previous_plan_id=None,
                invoiced=False
            )
            
            session.add(billing_period)
            await session.commit()
            logger.info(f"Created initial billing period for new user {new_user.id}")
            
            # Additional statistics logging for the new user
            logger.info(f"New user registered: {new_user.username}, Plan: {free_plan.name}, " 
                        f"Initial Credits: {free_plan.monthly_quota_credits}")
            
        except Exception as billing_error:
            logger.error(f"Error creating initial billing period: {billing_error}")
            # Continue with registration even if billing period creation fails
            # This ensures the user can still be created, and billing will be set up later
        
        # Send verification email using JWT token
        email_service = get_email_service()
        await email_service.send_verification_email(new_user, session)
        
    except IntegrityError as e:
        await session.rollback()
        if "unique constraint" in str(e).lower():
            if "username" in str(e).lower():
                raise HTTPException(status_code=400, detail="This username is already registered")
            elif "email" in str(e).lower():
                raise HTTPException(status_code=400, detail="This email is already registered")
        raise HTTPException(status_code=400, detail="Registration failed. Please try again.") from e
    except Exception as e:
        await session.rollback()
        logger.error(f"An unexpected error occurred during user registration: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred during registration.") from e

    return new_user


@router.get("/verify", status_code=200)
async def verify_email(
    request: Request,
    token: str,
    session: DbSession,
    _: None = Depends(email_verification_limiter),
):
    """Verify a user's email using the token sent via email"""
    from loguru import logger
    
    logger.info(f"Attempting to verify email with token: {token[:10]}...")
    
    try:
        # Verify JWT token
        settings_service = get_settings_service()
        secret_key = settings_service.auth_settings.SECRET_KEY.get_secret_value()
        algorithm = settings_service.auth_settings.ALGORITHM
        
        try:
            # Decode and verify the JWT token
            payload = jwt.decode(token, secret_key, algorithms=[algorithm])
            
            # Extract token information
            user_id = payload.get("sub")
            token_type = payload.get("type")
            email = payload.get("email")
            
            # Validate token properties
            if not user_id or token_type != "email_verification" or not email:
                logger.warning(f"Invalid verification token contents: {payload}")
                raise HTTPException(status_code=400, detail="Invalid verification token")
            
            # Find the user by ID - convert string ID to UUID properly
            from sqlmodel import select
            from langflow.services.database.models.user.model import User
            from uuid import UUID
            
            # First convert the string ID to a UUID object
            try:
                uuid_obj = UUID(user_id)
                user_query = select(User).where(User.id == uuid_obj)
                result = await session.execute(user_query)
                user = result.scalar_one_or_none()
            except ValueError as e:
                logger.error(f"Invalid UUID format: {user_id}, error: {e}")
                raise HTTPException(status_code=400, detail="Invalid user ID format")
            
            if not user:
                logger.warning(f"User not found for ID: {user_id}")
                raise HTTPException(status_code=400, detail="User not found")
                
            # Verify email matches
            if user.email != email:
                logger.warning(f"Email mismatch: token {email} vs user {user.email}")
                raise HTTPException(status_code=400, detail="Email verification failed")
            
        except JWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid or expired verification token")
        
        # Current time in UTC
        now = datetime.now(timezone.utc)
        
        logger.info(f"Verifying email for user: {user.username}, email: {user.email}")
        
        # Update user verification status
        user.is_verified = True
        user.is_active = True
        # Set last_login_at to bypass the admin approval requirement
        # This will allow the user to log in immediately after verifying
        user.last_login_at = now
        # Clear any legacy verification tokens
        user.verification_token = None
        user.verification_token_expiry = None
        
        # Start transaction
        await session.commit()
        logger.info(f"User verification status updated: {user.username}, is_verified={user.is_verified}, is_active={user.is_active}, last_login_at={user.last_login_at}")
        
        # Double-check the changes were saved
        await session.refresh(user)
        logger.info(f"User status after commit: {user.username}, is_verified={user.is_verified}, is_active={user.is_active}, last_login_at={user.last_login_at}")
        
        # Send welcome email
        email_service = get_email_service()
        await email_service.send_welcome_email(user)
        logger.info(f"Welcome email sent to: {user.email}")
        
        return {"message": "Email verified successfully. You can now log in."}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Error verifying email: {e}")
        raise HTTPException(status_code=500, detail=f"Error verifying email: {str(e)}")


@router.post("/password-reset-request", status_code=200)
async def request_password_reset(
    request: Request,
    email: str,
    session: DbSession,
    _: None = Depends(password_reset_limiter),
):
    """Request a password reset link via email"""
    # Find user with this email
    user_query = select(User).where(func.lower(User.email) == func.lower(email))
    result = await session.execute(user_query)
    user = result.scalar_one_or_none()
    
    # Always return success to prevent email enumeration
    if not user:
        return {"message": "If your account exists, a password reset link has been sent to your email"}
    
    # Prevent password reset for accounts linked to OAuth providers like Google
    if user.oauth_provider:
        return {"message": "If your account exists, a password reset link has been sent to your email"}
    
    # Send password reset email
    email_service = get_email_service()
    await email_service.send_password_reset_email(user, session)
    
    return {"message": "If your account exists, a password reset link has been sent to your email"}


@router.post("/reset-password", status_code=200)
async def reset_password(
    request: Request,
    reset_data: PasswordResetRequest,
    session: DbSession,
    _: None = Depends(password_reset_limiter),
):
    """Reset a user's password using the token sent via email"""
    from loguru import logger
    from jose import JWTError, jwt
    from langflow.services.deps import get_settings_service
    from langflow.services.auth.utils import get_password_hash
    
    token = reset_data.token
    new_password = reset_data.new_password
    
    logger.info(f"Attempting to reset password with token: {token[:10]}...")
    
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    
    try:
        # Verify JWT token
        settings_service = get_settings_service()
        secret_key = settings_service.auth_settings.SECRET_KEY.get_secret_value()
        algorithm = settings_service.auth_settings.ALGORITHM
        
        try:
            # Decode and verify JWT token
            payload = jwt.decode(token, secret_key, algorithms=[algorithm])
            
            # Extract token information
            user_id = payload.get("sub")
            token_type = payload.get("type")
            email = payload.get("email")
            
            # Validate token properties
            if not user_id or token_type != "password_reset" or not email:
                logger.warning(f"Invalid reset token payload: {payload}")
                raise HTTPException(status_code=400, detail="Invalid or expired token")
            
            # Find user by ID - convert string ID to UUID properly
            from uuid import UUID
            
            # First convert the string ID to a UUID object
            try:
                uuid_obj = UUID(user_id)
                user_query = select(User).where(User.id == uuid_obj)
                result = await session.execute(user_query)
                user = result.scalar_one_or_none()
            except ValueError as e:
                logger.error(f"Invalid UUID format: {user_id}, error: {e}")
                raise HTTPException(status_code=400, detail="Invalid user ID format")
            
            if not user:
                logger.warning(f"User not found for ID: {user_id}")
                raise HTTPException(status_code=400, detail="Invalid or expired token")
                
            # Verify email matches
            if user.email != email:
                logger.warning(f"Email mismatch: token {email} vs user {user.email}")
                raise HTTPException(status_code=400, detail="Invalid or expired token")
            
            # Check if user is authenticated via OAuth
            if user.oauth_provider:
                logger.warning(f"Password reset attempted for OAuth account: {user.email}, provider: {user.oauth_provider}")
                raise HTTPException(status_code=400, detail="Password reset is not available for accounts connected with social login. Please use your social login provider to access your account.")
            
        except JWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid or expired token")
        
        # Update user's password
        hashed_password = get_password_hash(new_password)
        user.password = hashed_password
        
        # Remove any old verification tokens
        user.verification_token = None
        user.verification_token_expiry = None
        
        # Commit changes
        await session.commit()
        await session.refresh(user)
        
        logger.info(f"Password reset successful for user: {user.username}")
        return {"message": "Password reset successful. You can now log in with your new password."}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Error resetting password: {e}")
        raise HTTPException(status_code=500, detail="Error resetting password")


@router.get("/whoami", response_model=UserRead)
async def read_current_user(
    current_user: CurrentActiveUser,
) -> User:
    """Retrieve the current user's data."""
    return current_user


@router.get("/", dependencies=[Depends(get_current_active_superuser)])
async def read_all_users(
    *,
    skip: int = 0,
    limit: int = 10,
    session: DbSession,
) -> UsersResponse:
    """Retrieve a list of users from the database with pagination."""
    query: SelectOfScalar = select(User).offset(skip).limit(limit)
    users = (await session.exec(query)).fetchall()

    count_query = select(func.count()).select_from(User)
    total_count = (await session.exec(count_query)).first()

    return UsersResponse(
        total_count=total_count,
        users=[UserRead(**user.model_dump()) for user in users],
    )


@router.patch("/{user_id}", response_model=UserRead)
async def patch_user(
    user_id: UUID,
    user_update: UserUpdate,
    user: CurrentActiveUser,
    session: DbSession,
) -> User:
    """Update an existing user's data."""
    update_password = bool(user_update.password)

    if not user.is_superuser and user_update.is_superuser:
        raise HTTPException(status_code=403, detail="Permission denied")

    if not user.is_superuser and user.id != user_id:
        raise HTTPException(status_code=403, detail="Permission denied")
    if update_password:
        if not user.is_superuser:
            raise HTTPException(status_code=400, detail="You can't change your password here")
        user_update.password = get_password_hash(user_update.password)

    if user_db := await get_user_by_id(session, user_id):
        if not update_password:
            user_update.password = user_db.password
        return await update_user(user_db, user_update, session)
    raise HTTPException(status_code=404, detail="User not found")


@router.patch("/{user_id}/reset-password", response_model=UserRead)
async def reset_password(
    user_id: UUID,
    user_update: UserUpdate,
    user: CurrentActiveUser,
    session: DbSession,
) -> User:
    """Reset a user's password."""
    if user_id != user.id:
        raise HTTPException(status_code=400, detail="You can't change another user's password")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check if user is authenticated via OAuth
    if user.oauth_provider:
        raise HTTPException(
            status_code=400, 
            detail="Password reset is not available for accounts connected with social login. Please use your social login provider to access your account."
        )
        
    if verify_password(user_update.password, user.password):
        raise HTTPException(status_code=400, detail="You can't use your current password")
    new_password = get_password_hash(user_update.password)
    user.password = new_password
    await session.commit()
    await session.refresh(user)

    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_superuser)],
    session: DbSession,
) -> dict:
    """Delete a user from the database."""
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="You can't delete your own user account")
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Permission denied")

    stmt = select(User).where(User.id == user_id)
    user_db = (await session.exec(stmt)).first()
    if not user_db:
        raise HTTPException(status_code=404, detail="User not found")

    await session.delete(user_db)
    await session.commit()

    return {"detail": "User deleted"}


@router.get("/debug-email-templates", status_code=200)
async def debug_email_templates():
    """Debug endpoint to check email templates"""
    try:
        from loguru import logger
        email_service = get_email_service()
        debug_info = email_service.debug_template_paths()
        return {"status": "success", "debug_info": debug_info}
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/test-email", status_code=200)
async def test_email(email: str):
    """Test endpoint to send a test email"""
    try:
        from loguru import logger
        logger.info(f"Sending test email to: {email}")
        
        email_service = get_email_service()
        html_content = """
        <html>
            <body>
                <h1>Langflow Test Email</h1>
                <p>This is a test email from Langflow.</p>
                <p>If you're receiving this, email sending is working correctly.</p>
            </body>
        </html>
        """
        
        result = await email_service.send_email(
            to_email=email, 
            subject="Langflow Test Email", 
            html_content=html_content
        )
        
        if result:
            return {"status": "success", "message": f"Test email sent to {email}"}
        else:
            return {"status": "error", "message": "Failed to send test email. Check server logs for details."}
    except Exception as e:
        logger.error(f"Error sending test email: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/check-verification", status_code=200)
async def check_user_verification(email: str, session: DbSession):
    """Check if a user is verified and active"""
    from loguru import logger
    from sqlalchemy import func
    from sqlmodel import select
    from langflow.services.database.models.user.model import User
    
    try:
        # Find user with this email
        user_query = select(User).where(func.lower(User.email) == func.lower(email))
        result = await session.execute(user_query)
        user = result.scalar_one_or_none()
        
        if not user:
            return {"status": "error", "message": "User not found"}
        
        return {
            "status": "success", 
            "user_info": {
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "verification_token": user.verification_token is not None,
                "verification_token_expiry": str(user.verification_token_expiry) if user.verification_token_expiry else None
            }
        }
    except Exception as e:
        logger.error(f"Error checking user verification: {e}")
        return {"status": "error", "message": str(e)}
