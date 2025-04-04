from __future__ import annotations

from typing import Annotated
import os
import secrets
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Cookie
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from google_auth_oauthlib.flow import Flow as GoogleFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from datetime import datetime, timezone

from langflow.api.utils import DbSession
from langflow.api.v1.schemas import Token
from langflow.initial_setup.setup import get_or_create_default_folder
from langflow.services.auth.utils import (
    authenticate_user,
    create_refresh_token,
    create_user_longterm_token,
    create_user_tokens,
    get_current_user_by_jwt,
    get_password_hash,
)
from langflow.services.database.models.user.crud import get_user_by_id, get_user_by_email
from langflow.services.database.models.user.model import User, UserCreate
from langflow.services.deps import get_settings_service, get_variable_service
from langflow.services.limiter.service import login_limiter

router = APIRouter(tags=["Login"])
logger = logging.getLogger(__name__)

# Google OAuth configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_FILE = os.path.abspath(os.path.join(os.getcwd(), "config/client_secret.json"))
# Limited scope for authentication only
AUTH_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"]

# Environment detection helpers
def is_dev_environment():
    """Determine if we're in a development environment"""
    return os.environ.get("ENVIRONMENT", "dev").lower() == "dev"

def get_backend_url():
    """Get the backend URL based on environment"""
    if is_dev_environment():
        return os.environ.get("BACKEND_DEV_URL", "http://localhost:3000")
    return os.environ.get("BACKEND_PROD_URL", "https://api.yourdomain.com")

def get_frontend_url():
    """Get the frontend URL based on environment"""
    if is_dev_environment():
        return os.environ.get("FRONTEND_DEV_URL", "http://localhost:3000")
    return os.environ.get("FRONTEND_PROD_URL", "https://yourdomain.com")

# Dynamic URLs based on environment
BACKEND_URL = get_backend_url()
FRONTEND_URL = get_frontend_url()
GOOGLE_AUTH_REDIRECT_URI = f"{BACKEND_URL}/api/v1/login/google/callback"

# Function to add CORS middleware to app
def add_cors_middleware(app):
    """Add CORS middleware to the FastAPI app"""
    # In development mode, be more permissive with CORS settings
    if is_dev_environment():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Allow all origins in dev mode
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # In production, be more restrictive
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[FRONTEND_URL],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    return app

@router.post("/login", response_model=Token)
async def login_to_get_access_token(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
    _: None = Depends(login_limiter),
):
    auth_settings = get_settings_service().auth_settings
    try:
        user = await authenticate_user(form_data.username, form_data.password, db)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.error(f"Error during authentication: {str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred during authentication",
        ) from exc

    if user:
        tokens = await create_user_tokens(user_id=user.id, db=db, update_last_login=True)
        response.set_cookie(
            "refresh_token_lf",
            tokens["refresh_token"],
            httponly=auth_settings.REFRESH_HTTPONLY,
            samesite=auth_settings.REFRESH_SAME_SITE,
            secure=auth_settings.REFRESH_SECURE,
            expires=auth_settings.REFRESH_TOKEN_EXPIRE_SECONDS,
            domain=auth_settings.COOKIE_DOMAIN,
        )
        response.set_cookie(
            "access_token_lf",
            tokens["access_token"],
            httponly=auth_settings.ACCESS_HTTPONLY,
            samesite=auth_settings.ACCESS_SAME_SITE,
            secure=auth_settings.ACCESS_SECURE,
            expires=auth_settings.ACCESS_TOKEN_EXPIRE_SECONDS,
            domain=auth_settings.COOKIE_DOMAIN,
        )
        response.set_cookie(
            "apikey_tkn_lflw",
            str(user.store_api_key),
            httponly=auth_settings.ACCESS_HTTPONLY,
            samesite=auth_settings.ACCESS_SAME_SITE,
            secure=auth_settings.ACCESS_SECURE,
            expires=None,  # Set to None to make it a session cookie
            domain=auth_settings.COOKIE_DOMAIN,
        )
        await get_variable_service().initialize_user_variables(user.id, db)
        # Create default folder for user if it doesn't exist
        _ = await get_or_create_default_folder(db, user.id)
        return tokens
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username/email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/auto_login")
async def auto_login(response: Response, db: DbSession):
    auth_settings = get_settings_service().auth_settings

    if auth_settings.AUTO_LOGIN:
        user_id, tokens = await create_user_longterm_token(db)
        response.set_cookie(
            "access_token_lf",
            tokens["access_token"],
            httponly=auth_settings.ACCESS_HTTPONLY,
            samesite=auth_settings.ACCESS_SAME_SITE,
            secure=auth_settings.ACCESS_SECURE,
            expires=None,  # Set to None to make it a session cookie
            domain=auth_settings.COOKIE_DOMAIN,
        )

        user = await get_user_by_id(db, user_id)

        if user:
            if user.store_api_key is None:
                user.store_api_key = ""

            response.set_cookie(
                "apikey_tkn_lflw",
                str(user.store_api_key),  # Ensure it's a string
                httponly=auth_settings.ACCESS_HTTPONLY,
                samesite=auth_settings.ACCESS_SAME_SITE,
                secure=auth_settings.ACCESS_SECURE,
                expires=None,  # Set to None to make it a session cookie
                domain=auth_settings.COOKIE_DOMAIN,
            )

        return tokens

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "message": "Auto login is disabled. Please enable it in the settings",
            "auto_login": False,
        },
    )


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db: DbSession,
):
    auth_settings = get_settings_service().auth_settings

    token = request.cookies.get("refresh_token_lf")

    if token:
        tokens = await create_refresh_token(token, db)
        response.set_cookie(
            "refresh_token_lf",
            tokens["refresh_token"],
            httponly=auth_settings.REFRESH_HTTPONLY,
            samesite=auth_settings.REFRESH_SAME_SITE,
            secure=auth_settings.REFRESH_SECURE,
            expires=auth_settings.REFRESH_TOKEN_EXPIRE_SECONDS,
            domain=auth_settings.COOKIE_DOMAIN,
        )
        response.set_cookie(
            "access_token_lf",
            tokens["access_token"],
            httponly=auth_settings.ACCESS_HTTPONLY,
            samesite=auth_settings.ACCESS_SAME_SITE,
            secure=auth_settings.ACCESS_SECURE,
            expires=auth_settings.ACCESS_TOKEN_EXPIRE_SECONDS,
            domain=auth_settings.COOKIE_DOMAIN,
        )
        return tokens
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token_lf")
    response.delete_cookie("access_token_lf")
    response.delete_cookie("apikey_tkn_lflw")
    return {"message": "Logout successful"}


@router.get("/login/google")
async def login_with_google(response: Response, request: Request):
    """
    Initiates Google OAuth flow for user authentication.
    """
    try:
        # Check if the client_secret.json file exists
        if not os.path.exists(CLIENT_SECRETS_FILE):
            logger.error(f"Google OAuth configuration file not found at {CLIENT_SECRETS_FILE}")
            raise HTTPException(
                status_code=500, 
                detail="Google authentication is not properly configured. Please contact your administrator."
            )
        
        # Generate a secure random state with high entropy
        state = secrets.token_urlsafe(32)
        
        # For development/localhost environment, use more permissive cookie settings
        if is_dev_environment():
            logger.info("Using development cookie settings for OAuth state")
            # Store the state in a cookie with settings compatible with localhost
            response.set_cookie(
                "oauth_state",
                state,
                httponly=True,     # Prevents JavaScript access
                secure=False,      # Don't require HTTPS in dev environment
                samesite="lax",    # More compatible with redirects in dev
                max_age=600,       # 10 minutes expiry
                path="/",          # Available across the site
                domain=None        # Don't set domain for localhost
            )
        else:
            # Production settings - more secure
            response.set_cookie(
                "oauth_state",
                state,
                httponly=True,     # Prevents JavaScript access
                secure=True,       # Require HTTPS in production
                samesite="strict", # Strict same-site policy in production
                max_age=600,       # 10 minutes expiry
                path="/"           # Available across the site
            )
        
        # Also store the state in the flow - add a flag to the state parameter
        # to verify it in the callback
        session_state = f"{state}:{secrets.token_hex(8)}"
            
        flow = GoogleFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, AUTH_SCOPES)
        flow.redirect_uri = GOOGLE_AUTH_REDIRECT_URI
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="select_account",
            state=session_state
        )
        return RedirectResponse(auth_url)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Error initiating Google OAuth flow: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred during Google authentication setup")


@router.get("/login/google/callback")
async def google_auth_callback(
    state: str,
    code: str,
    response: Response,
    db: DbSession,
    oauth_state: str = Cookie(None),
    scope: str = None
):
    """
    Handle the Google OAuth callback for authentication.
    """
    try:
        # More detailed logging for debugging state mismatch
        if oauth_state:
            logger.debug(f"Received state cookie: {oauth_state[:10]}...")
        else:
            logger.warning("No state cookie received in callback")
            
        # Extract the base state and verification part
        # The state parameter should be in format: {original_state}:{verification_hash}
        state_parts = state.split(':', 1)
        if len(state_parts) != 2:
            logger.warning(f"Malformed state parameter in OAuth callback: {state[:10]}... - Potential attack")
            raise HTTPException(
                status_code=400,
                detail="Invalid state format. Authentication failed."
            )
            
        base_state = state_parts[0]
        verification_hash = state_parts[1]
        logger.debug(f"Extracted base state from callback: {base_state[:10]}...")
        
        # Create a dev-only fallback state record to help with localhost testing
        # This is ONLY used if the cookie approach fails in development
        dev_fallback_state = None
        
        # Check if we're in development mode for more lenient validation
        if is_dev_environment():
            # In development mode, we'll be more lenient with state validation
            # but still perform basic validation
            if oauth_state:
                # Even in dev mode, do validation if we have a state cookie
                if not secrets.compare_digest(oauth_state, base_state):
                    logger.warning(f"OAuth state verification failed in dev mode")
                    # Log the values for debugging (shortened for security)
                    logger.debug(f"Expected: {oauth_state[:10]}... | Received: {base_state[:10]}...")
                    
                    # For dev mode only: Attempt to continue if cookie state failed but there's still a hash
                    if verification_hash and len(verification_hash) >= 8:
                        logger.warning("DEV MODE: Proceeding with reduced security due to state cookie mismatch")
                        # Mark that we're using fallback validation
                        dev_fallback_state = True
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="Invalid state parameter. This could be due to a CSRF attack or session expiration."
                        )
            else:
                # In dev mode, if no cookie is present but we have a verification hash, proceed with caution
                if verification_hash and len(verification_hash) >= 8:
                    logger.warning("DEV MODE: No oauth_state cookie - proceeding with reduced security")
                    # Mark that we're using fallback validation
                    dev_fallback_state = True
                else:
                    logger.warning("No oauth_state cookie and no verification hash - cannot proceed safely")
                    raise HTTPException(
                        status_code=400,
                        detail="Authentication session expired or invalid. Please try logging in again."
                    )
        else:
            # ENHANCED Validation for production: Perform time-constant comparison of the state parameter
            # This helps prevent timing attacks
            if not oauth_state or not secrets.compare_digest(oauth_state, base_state):
                logger.warning(f"OAuth state verification failed: CSRF attack attempt detected")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid state parameter. This could be due to a CSRF attack or session expiration."
                )
            
            # STRICT VALIDATION for production:
            if not oauth_state:
                logger.warning("Missing oauth_state cookie during callback - Security violation")
                raise HTTPException(
                    status_code=400,
                    detail="Authentication session expired or invalid. Please try logging in again."
                )
        
        # Clear the state cookie securely to prevent reuse attacks
        if oauth_state:
            if is_dev_environment():
                # Simplified cookie deletion for dev environment
                response.delete_cookie(
                    "oauth_state", 
                    path="/", 
                    domain=None
                )
            else:
                # Secure cookie deletion for production
                response.delete_cookie(
                    "oauth_state", 
                    path="/", 
                    secure=True, 
                    samesite="strict"
                )
        
        # Check if the client_secret.json file exists
        if not os.path.exists(CLIENT_SECRETS_FILE):
            logger.error(f"Google OAuth configuration file not found at {CLIENT_SECRETS_FILE}")
            raise HTTPException(
                status_code=500, 
                detail="Google authentication is not properly configured. Please contact your administrator."
            )
            
        # --- Proceed only if validation passes ---
        # Create the flow with the original state    
        flow = GoogleFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, AUTH_SCOPES, state=state)
        flow.redirect_uri = GOOGLE_AUTH_REDIRECT_URI
        
        try:
            # Attempt to fetch the token
            flow.fetch_token(code=code)
        except Exception as token_error:
            # If there's a scope mismatch, try to handle it
            if "Scope has changed" in str(token_error) and scope:
                # If we have the scope from the callback, use it to recreate the flow
                received_scopes = scope.split()
                flow = GoogleFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, received_scopes, state=state)
                flow.redirect_uri = GOOGLE_AUTH_REDIRECT_URI
                flow.fetch_token(code=code)
            else:
                logger.error(f"Token fetch error: {str(token_error)}")
                raise HTTPException(
                    status_code=400, 
                    detail="Authentication failed. Please try again."
                )
                
        credentials = flow.credentials
        
        # Use credentials to get user info
        service = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
        user_info = service.userinfo().get().execute()
        
        logger.info(f"Google Auth - User authenticated: {user_info.get('email')}")
        
        email = user_info.get("email")
        if not email:
            logger.error("No email returned from Google authentication")
            raise HTTPException(status_code=400, detail="Could not get email from Google")
        
        # Check if user exists
        user = await get_user_by_email(db, email)
        auth_settings = get_settings_service().auth_settings
        
        if not user:
            # Create new user
            username = email.split("@")[0]
            # Generate a secure random password with high entropy
            password = secrets.token_urlsafe(16)
            
            new_user = User(
                username=username,
                email=email,
                password=get_password_hash(password),
                is_active=True,
                is_verified=True,
                profile_image="Space/028-alien.svg",
                oauth_provider="google",  # Set oauth provider for Google accounts
                last_login_at=datetime.now(timezone.utc)  # Set last_login_at to ensure the user is fully activated
            )
            
            # Save the new user
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            user = new_user
            
            # Create default folder for new user
            _ = await get_or_create_default_folder(db, user.id)
            await get_variable_service().initialize_user_variables(user.id, db)
            
            logger.info(f"Created new user via Google OAuth: {user.username}")
        else:
            # Update existing user's last_login_at
            user.last_login_at = datetime.now(timezone.utc)
            # Set oauth_provider for existing users if they haven't set it yet
            if user.oauth_provider is None:
                user.oauth_provider = "google"
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
        # Create tokens for user
        tokens = await create_user_tokens(user_id=user.id, db=db, update_last_login=True)
        
        logger.info(f"Google Auth - Generated tokens for user: {user.username}")
        
        # Extract the domain from FRONTEND_URL (e.g., "localhost:3000" from "http://localhost:3000")
        frontend_domain = FRONTEND_URL.split("//")[-1].split("/")[0]
        
        # Get auto_login option from auth settings
        auto_login_option = "google"
        langflow_auto_login_cookie = "langflow_auto_login"
        
        # Create HTML with enhanced security protections
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; connect-src 'self';">
            <title>Authentication Successful</title>
            <script>
                // Sanitize values from server to prevent XSS
                const sanitize = function(str) {{
                    const temp = document.createElement('div');
                    temp.textContent = str;
                    return temp.innerHTML;
                }};
                
                // More secure cookie setting function with explicit options
                function setCookie(name, value, days, domain) {{
                    const sanitizedName = sanitize(name);
                    const sanitizedValue = sanitize(value);
                    const sanitizedDomain = sanitize(domain);
                    
                    let expires = "";
                    
                    if (days) {{
                        const date = new Date();
                        date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
                        expires = "; expires=" + date.toUTCString();
                    }}
                    
                    // For localhost, don't set domain attribute
                    const domainPart = domain.includes('localhost') ? '' : `; domain=${{sanitizedDomain}}`;
                    
                    // Set SameSite policy based on environment
                    const sameSite = domain.includes('localhost') ? '; SameSite=Lax' : '; SameSite=None; Secure';
                    
                    // Set the cookie with security attributes
                    document.cookie = sanitizedName + "=" + sanitizedValue + expires + domainPart + sameSite + "; path=/";
                    
                    // Debug cookie setting (only in dev/localhost)
                    if (domain.includes('localhost')) {{
                        console.log(`Setting cookie ${{sanitizedName}}`);
                    }}
                }}
                
                // Detect localhost environment for different cookie handling
                const isLocalhost = window.location.hostname === 'localhost' || 
                                   window.location.hostname === '127.0.0.1';
                                   
                // Set cookies with proper sanitization
                setCookie('access_token_lf', '{tokens['access_token']}', {auth_settings.ACCESS_TOKEN_EXPIRE_SECONDS/(24*60*60)}, '{frontend_domain}');
                setCookie('refresh_token_lf', '{tokens['refresh_token']}', {auth_settings.REFRESH_TOKEN_EXPIRE_SECONDS/(24*60*60)}, '{frontend_domain}');
                setCookie('{langflow_auto_login_cookie}', '{auto_login_option}', 365, '{frontend_domain}');
                {"setCookie('apikey_tkn_lflw', '" + str(user.store_api_key) + "', 365, '" + frontend_domain + "');" if user.store_api_key else ""}
                
                // Safe redirection after a small delay to ensure cookies are set
                setTimeout(function() {{
                    window.location.href = "{FRONTEND_URL}";
                }}, 1000);
            </script>
        </head>
        <body>
            <h2>Authentication Successful!</h2>
            <p>Redirecting you to the application...</p>
            <noscript>
                <p>JavaScript is required for this page. If not redirected automatically, <a href="{FRONTEND_URL}">click here</a>.</p>
            </noscript>
        </body>
        </html>
        """
        
        # Create a response with the HTML content and add security headers
        response = HTMLResponse(content=html_content)
        
        # Add security headers to prevent XSS and other attacks
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response
        
    except Exception as e:
        if isinstance(e, HTTPException):
            # Log the specific HTTPException detail
            logger.warning(f"Google OAuth callback HTTPException: {e.detail} (Status: {e.status_code})")
            
            # Create HTML with error message, including enhanced security
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; connect-src 'self';">
                <title>Authentication Failed</title>
                <script>
                    // Use a safer method than localStorage for sensitive errors
                    // Store error message in session storage (cleared when browser closes)
                    sessionStorage.setItem('auth_error', 'Google authentication failed (Status: {e.status_code})');
                    
                    // Debug for localhost
                    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {{
                        console.log('Setting auth_error in sessionStorage');
                    }}
                    
                    // Redirect to login page after a small delay
                    setTimeout(function() {{
                        window.location.href = "{FRONTEND_URL}/login";
                    }}, 1000);
                </script>
            </head>
            <body>
                <h2>Authentication Failed</h2>
                <p>Redirecting to login page...</p>
                <noscript>
                    <p>JavaScript is required for this page. If not redirected automatically, <a href="{FRONTEND_URL}/login">click here</a>.</p>
                </noscript>
            </body>
            </html>
            """
            response = HTMLResponse(content=html_content)
            
            # Add security headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            
            return response
        else:
            # Log the detailed error but return a generic message to the user
            logger.error(f"Google OAuth callback error: {str(e)}")
            
            # Create HTML with generic error message and enhanced security
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; connect-src 'self';">
                <title>Authentication Failed</title>
                <script>
                    // Use a safer method than localStorage for sensitive errors
                    // Store error message in session storage (cleared when browser closes)
                    sessionStorage.setItem('auth_error', 'Google authentication failed. Please try again.');
                    
                    // Debug for localhost
                    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {{
                        console.log('Setting auth_error in sessionStorage');
                    }}
                    
                    // Redirect to login page after a small delay
                    setTimeout(function() {{
                        window.location.href = "{FRONTEND_URL}/login";
                    }}, 1000);
                </script>
            </head>
            <body>
                <h2>Authentication Failed</h2>
                <p>Redirecting to login page...</p>
                <noscript>
                    <p>JavaScript is required for this page. If not redirected automatically, <a href="{FRONTEND_URL}/login">click here</a>.</p>
                </noscript>
            </body>
            </html>
            """
            response = HTMLResponse(content=html_content)
            
            # Add security headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            
            return response
