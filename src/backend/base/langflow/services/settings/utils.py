import platform
from pathlib import Path
import os

from loguru import logger


def set_secure_permissions(file_path: Path) -> None:
    try:
        if os.name == 'nt':  # Windows
            import win32security
            import ntsecuritycon as con
            
            # Get the SID for the current user
            username = os.getlogin()
            user, domain, type = win32security.LookupAccountName(None, username)
            
            # Create a new security descriptor
            sd = win32security.SECURITY_DESCRIPTOR()
            
            # Create a new DACL
            dacl = win32security.ACL()
            
            # Add ACE for the current user (Full Control)
            dacl.AddAccessAllowedAce(
                win32security.ACL_REVISION,
                con.FILE_ALL_ACCESS,
                user
            )
            
            # Set the DACL to the security descriptor
            sd.SetSecurityDescriptorDacl(1, dacl, 0)
            
            try:
                # Try to set the file security
                win32security.SetFileSecurity(
                    str(file_path),
                    win32security.DACL_SECURITY_INFORMATION,
                    sd
                )
            except Exception as e:
                logger.warning(f"Could not set file security: {e}")
                # Continue even if we can't set permissions
                pass
        else:
            # Unix-like systems
            file_path.chmod(0o600)
    except Exception as e:
        logger.warning(f"Could not set secure permissions: {e}")
        # Continue even if we can't set permissions
        pass


def write_secret_to_file(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    try:
        set_secure_permissions(path)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to set secure permissions on secret key")


def read_secret_from_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")
