import os
import smtplib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from loguru import logger
from jinja2 import Environment, FileSystemLoader, select_autoescape

from langflow.services.deps import get_settings_service
from langflow.services.database.models.user.model import User
from langflow.services.auth.utils import create_token


class EmailService:
    name = "email_service"

    def __init__(self):
        self.settings = get_settings_service().email_settings
        self.setup_templates()
        
        # Verify templates can be loaded
        try:
            template_files = ['verification_email.html', 'password_reset.html', 'welcome_email.html']
            for template_name in template_files:
                if self.env.get_template(template_name):
                    logger.info(f"Successfully loaded template: {template_name}")
        except Exception as e:
            logger.warning(f"Error loading templates during initialization: {e}")
            # Don't raise here, just log the warning
    
    def setup_templates(self):
        """Setup Jinja2 templates for emails"""
        try:
            # Use an absolute path based on the module location
            import os
            import pathlib
            
            # Get the path of the current module
            module_path = pathlib.Path(__file__).resolve()
            base_dir = module_path.parent.parent.parent  # Go up to the langflow root
            template_dir = base_dir / "emails" / "templates"
            
            # If templates aren't found at the expected location, try the direct path
            if not template_dir.exists():
                # Try with absolute path
                root_dir = pathlib.Path.cwd().resolve()
                template_dir = root_dir / "src" / "backend" / "base" / "langflow" / "emails" / "templates"
            
            # If still not found, try other possible locations
            if not template_dir.exists():
                # Try with relative path to module
                template_dir = base_dir.parent / "emails" / "templates"
            
            if not template_dir.exists():
                logger.warning(f"Email templates directory not found at expected locations. Creating at: {template_dir}")
                # Create template directory if it doesn't exist
                template_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Loading email templates from: {template_dir}")
            
            self.env = Environment(
                loader=FileSystemLoader(str(template_dir)),  # Convert Path to string for compatibility
                autoescape=select_autoescape(['html', 'xml'])
            )
        except Exception as e:
            logger.error(f"Error setting up email templates: {e}")
            raise
    
    async def send_email(self, to_email: str, subject: str, html_content: str):
        """Send an email using SMTP settings"""
        # Log SMTP settings for debugging
        logger.info(f"SMTP Server: {self.settings.SMTP_SERVER}")
        logger.info(f"SMTP Port: {self.settings.SMTP_PORT}")
        logger.info(f"SMTP Username: {self.settings.SMTP_USERNAME}")
        logger.info(f"SMTP From Name: {self.settings.EMAIL_FROM_NAME}")
        logger.info(f"SMTP From Address: {self.settings.EMAIL_FROM_ADDRESS}")
        logger.info(f"Sending email to: {to_email}")
        
        if not self.settings.SMTP_SERVER or not self.settings.SMTP_PORT:
            logger.warning("SMTP not configured. Cannot send emails.")
            return False
            
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.settings.EMAIL_FROM_NAME} <{self.settings.EMAIL_FROM_ADDRESS}>"
            msg['To'] = to_email
            
            msg.attach(MIMEText(html_content, 'html'))
            
            logger.info(f"Connecting to SMTP server: {self.settings.SMTP_SERVER}:{self.settings.SMTP_PORT}")
            with smtplib.SMTP(self.settings.SMTP_SERVER, self.settings.SMTP_PORT) as server:
                # Try without TLS first for dev environments like Mailhog
                try:
                    logger.info("Attempting connection without TLS (for dev environments like Mailhog)")
                    if self.settings.SMTP_USERNAME and self.settings.SMTP_PASSWORD:
                        logger.info("Authenticating with username/password")
                        server.login(self.settings.SMTP_USERNAME, self.settings.SMTP_PASSWORD)
                    server.send_message(msg)
                    logger.info(f"Email sent to {to_email} without TLS")
                    return True
                except Exception as e:
                    logger.warning(f"Failed to send without TLS, trying with TLS: {e}")
                    # If that fails, try with TLS
                    server.starttls()
                    if self.settings.SMTP_USERNAME and self.settings.SMTP_PASSWORD:
                        server.login(self.settings.SMTP_USERNAME, self.settings.SMTP_PASSWORD)
                    server.send_message(msg)
                    logger.info(f"Email sent to {to_email} with TLS")
                    return True
                
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def generate_verification_token(self) -> str:
        """Generate a secure token for email verification"""
        return secrets.token_urlsafe(32)
    
    def get_verification_token_expiry(self) -> datetime:
        """Get the expiry datetime for a verification token"""
        return datetime.now(timezone.utc) + timedelta(minutes=self.settings.VERIFICATION_TOKEN_EXPIRE_MINUTES)
    
    async def send_verification_email(self, user: User, db):
        """Send verification email to a newly registered user"""
        # Generate JWT verification token instead of database token
        token_expiry_minutes = self.settings.VERIFICATION_TOKEN_EXPIRE_MINUTES
        expiry = timedelta(minutes=token_expiry_minutes)
        
        # Create JWT with user ID and purpose
        verification_token = create_token(
            data={
                "sub": str(user.id),
                "type": "email_verification",
                "email": user.email
            },
            expires_delta=expiry
        )
        
        # Create verification URL - use the standalone verification page
        verify_url = f"{self.settings.FRONTEND_URL}/verify-email.html?token={verification_token}"
        
        # Get email template
        try:
            template = self.env.get_template('verification_email.html')
            html_content = template.render(
                username=user.username,
                verification_url=verify_url,
                expiry_hours=token_expiry_minutes // 60
            )
        except Exception as e:
            # Fallback to simple HTML if template fails
            logger.error(f"Template error: {e}")
            html_content = f"""
            <html>
                <body>
                    <h1>Verify your email for Langflow</h1>
                    <p>Hi {user.username},</p>
                    <p>Thank you for registering with Langflow! Please verify your email by clicking the link below:</p>
                    <p><a href="{verify_url}">Verify Email</a></p>
                    <p>This link will expire in {token_expiry_minutes // 60} hours.</p>
                </body>
            </html>
            """
        
        # Send the email
        subject = "Verify your email for Langflow"
        return await self.send_email(user.email, subject, html_content)
    
    async def send_welcome_email(self, user: User):
        """Send welcome email after user verifies their account"""
        # Create login URL
        login_url = f"{self.settings.FRONTEND_URL}/login"
        
        # Get email template
        try:
            template = self.env.get_template('welcome_email.html')
            html_content = template.render(
                username=user.username,
                login_url=login_url
            )
        except Exception as e:
            # Fallback to simple HTML if template fails
            logger.error(f"Template error: {e}")
            html_content = f"""
            <html>
                <body>
                    <h1>Welcome to Langflow!</h1>
                    <p>Hi {user.username},</p>
                    <p>Thank you for verifying your email and joining Langflow! Your account is now active.</p>
                    <p><a href="{login_url}">Login to your account</a></p>
                </body>
            </html>
            """
        
        # Send the email
        subject = "Welcome to Langflow"
        return await self.send_email(user.email, subject, html_content)
    
    async def send_password_reset_email(self, user: User, db):
        """Send password reset email"""
        # Generate reset token using JWT instead of database token
        token_expiry_minutes = self.settings.VERIFICATION_TOKEN_EXPIRE_MINUTES
        expiry = timedelta(minutes=token_expiry_minutes)
        
        # Create JWT with user ID and purpose
        reset_token = create_token(
            data={
                "sub": str(user.id),
                "type": "password_reset",
                "email": user.email
            },
            expires_delta=expiry
        )
        
        # Create reset URL - use standalone HTML page with hash fragment for security
        # Using hash fragment instead of query parameter prevents token from appearing in logs or being shared
        reset_url = f"{self.settings.FRONTEND_URL}/reset-password.html#{reset_token}"
        
        # Get email template
        try:
            template = self.env.get_template('password_reset.html')
            html_content = template.render(
                username=user.username,
                reset_url=reset_url,
                expiry_hours=token_expiry_minutes // 60
            )
        except Exception as e:
            # Fallback to simple HTML if template fails
            logger.error(f"Template error: {e}")
            html_content = f"""
            <html>
                <body>
                    <h1>Reset your Langflow password</h1>
                    <p>Hi {user.username},</p>
                    <p>We received a request to reset your Langflow password. Click the link below to set a new password:</p>
                    <p><a href="{reset_url}">Reset Password</a></p>
                    <p>This link will expire in {token_expiry_minutes // 60} hours.</p>
                    <p>If you didn't request this, you can safely ignore this email.</p>
                </body>
            </html>
            """
        
        # Send the email
        subject = "Reset your Langflow password"
        return await self.send_email(user.email, subject, html_content)

    def debug_template_paths(self):
        """Debug method to check template paths"""
        import os
        import pathlib
        
        # Get the path of the current module
        module_path = pathlib.Path(__file__).resolve()
        base_dir = module_path.parent.parent.parent  # langflow root
        template_dir = base_dir / "emails" / "templates"
        
        # Check possible paths
        possible_paths = [
            template_dir,
            pathlib.Path.cwd().resolve() / "src" / "backend" / "base" / "langflow" / "emails" / "templates",
            base_dir.parent / "emails" / "templates"
        ]
        
        results = {}
        for i, path in enumerate(possible_paths):
            logger.info(f"Path {i+1}: {path} - Exists: {path.exists()}")
            if path.exists():
                files = list(path.glob("*.html"))
                logger.info(f"Files in path {i+1}: {[f.name for f in files]}")
                results[f"path_{i+1}"] = {
                    "path": str(path),
                    "exists": path.exists(),
                    "files": [f.name for f in files]
                }
        
        # Check env loader path
        loader_paths = []
        if hasattr(self, 'env') and hasattr(self.env, 'loader'):
            loader_paths = getattr(self.env.loader, 'searchpath', ['Unknown'])
            logger.info(f"Template loader paths: {loader_paths}")
        
        results["loader_paths"] = loader_paths
        
        return results


# Singleton instance
_email_service = None

def get_email_service():
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service 