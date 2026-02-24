"""
Share links and pre-signed URL management for kak file server.

Features:
- Pre-signed temporary download links with HMAC
- Share links with expiration, download limits, and optional password
"""

import os
import time
import json
import hmac
import hashlib
import secrets
import uuid
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

# Import config - will be set after initialization
_config = None


def _get_config():
    """Get config, lazily imported to avoid circular imports."""
    global _config
    if _config is None:
        from .config import config
        _config = config
    return _config


# In-memory storage for share links (use database for production)
_shares: Dict[str, Dict[str, Any]] = {}


@dataclass
class ShareLink:
    """Represents a share link."""
    id: str
    path: str
    created_at: float
    expires_at: Optional[float]
    download_limit: Optional[int]
    download_count: int
    password_hash: Optional[str]
    token: str


def _get_secret() -> str:
    """Get or generate a secret for signing tokens."""
    cfg = _get_config()
    if cfg.token_secret:
        return cfg.token_secret
    
    # Generate a random secret if not configured
    return secrets.token_hex(32)


def generate_presigned_url(
    path: str,
    expires_in: int = 3600,
    allow_upload: bool = False
) -> Tuple[str, str]:
    """
    Generate a pre-signed URL for temporary access.
    
    Returns:
        (token, url) - The token and the full URL
    
    The token is a HMAC-SHA256 of the path + expiration, signed with server secret.
    """
    # Create token data
    expires_at = int(time.time()) + expires_in
    token_data = f"{path}:{expires_at}:{allow_upload}"
    
    # Generate HMAC
    secret = _get_secret()
    token = hmac.new(
        secret.encode(),
        token_data.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Create share link entry
    share_id = secrets.token_urlsafe(16)
    _shares[share_id] = {
        "id": share_id,
        "path": path,
        "token": token,
        "created_at": time.time(),
        "expires_at": expires_at,
        "download_limit": None,
        "download_count": 0,
        "password_hash": None,
        "allow_upload": allow_upload,
        "type": "presigned"
    }
    
    # Build URL
    base_url = f"http://localhost:{_get_config().port}"
    url = f"{base_url}{path}?token={token}&share={share_id}"
    
    return token, url


def create_share_link(
    path: str,
    expires_in: Optional[int] = None,
    download_limit: Optional[int] = None,
    password: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a share link with optional constraints.
    
    Args:
        path: The file/folder path to share
        expires_in: Seconds until link expires (None = never)
        download_limit: Max downloads allowed (None = unlimited)
        password: Optional password protection
    
    Returns:
        Share link info dict
    """
    share_id = secrets.token_urlsafe(16)
    created_at = time.time()
    
    # Calculate expiration
    expires_at = None
    if expires_in:
        expires_at = created_at + expires_in
    
    # Hash password if provided
    password_hash = None
    if password:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    # Generate unique token for this share
    token = secrets.token_urlsafe(32)
    
    _shares[share_id] = {
        "id": share_id,
        "path": path,
        "token": token,
        "created_at": created_at,
        "expires_at": expires_at,
        "download_limit": download_limit,
        "download_count": 0,
        "password_hash": password_hash,
        "allow_upload": False,
        "type": "share"
    }
    
    # Build share URL
    base_url = f"http://localhost:{_get_config().port}"
    share_url = f"{base_url}/__dufs__/s/{share_id}"
    
    result = {
        "id": share_id,
        "url": share_url,
        "path": path,
        "token": token,
        "created_at": datetime.fromtimestamp(created_at).isoformat(),
    }
    
    if expires_at:
        result["expires_at"] = datetime.fromtimestamp(expires_at).isoformat()
        result["expires_in"] = expires_in
    
    if download_limit:
        result["download_limit"] = download_limit
    
    if password:
        result["password"] = "***"  # Don't return actual password
    
    return result


def verify_share_link(
    share_id: str,
    password: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Verify a share link and increment download count.
    
    Returns:
        Share info if valid, None if invalid/expired
    """
    if share_id not in _shares:
        return None
    
    share = _shares[share_id]
    
    # Check expiration
    if share["expires_at"] and time.time() > share["expires_at"]:
        del _shares[share_id]
        return None
    
    # Check download limit
    if share["download_limit"] is not None:
        if share["download_count"] >= share["download_limit"]:
            return None
    
    # Check password
    if share["password_hash"]:
        if not password:
            return None
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash != share["password_hash"]:
            return None
    
    # Increment download count
    share["download_count"] += 1
    
    return share


def verify_presigned_token(path: str, token: str) -> bool:
    """
    Verify a pre-signed token for a path.
    
    The token is valid if it matches the HMAC for the given path
    and hasn't expired.
    """
    # Search for matching share
    for share in _shares.values():
        if share.get("type") != "presigned":
            continue
        
        if share["token"] != token:
            continue
        
        # Check if token matches this path
        if share["path"] != path:
            continue
        
        # Check expiration
        if share["expires_at"] and time.time() > share["expires_at"]:
            continue
        
        return True
    
    return False


def get_share(share_id: str) -> Optional[Dict[str, Any]]:
    """Get share info by ID."""
    return _shares.get(share_id)


def list_shares() -> list:
    """List all active shares."""
    result = []
    now = time.time()
    
    for share_id, share in list(_shares.items()):
        # Clean up expired shares
        if share["expires_at"] and now > share["expires_at"]:
            del _shares[share_id]
            continue
        
        result.append({
            "id": share_id,
            "path": share["path"],
            "type": share["type"],
            "created_at": datetime.fromtimestamp(share["created_at"]).isoformat(),
            "expires_at": datetime.fromtimestamp(share["expires_at"]).isoformat() if share["expires_at"] else None,
            "download_count": share["download_count"],
            "download_limit": share["download_limit"],
        })
    
    return result


def delete_share(share_id: str) -> bool:
    """Delete a share link."""
    if share_id in _shares:
        del _shares[share_id]
        return True
    return False


def cleanup_expired_shares():
    """Remove expired shares from memory."""
    now = time.time()
    expired = [
        sid for sid, share in _shares.items()
        if share["expires_at"] and now > share["expires_at"]
    ]
    
    for sid in expired:
        del _shares[sid]
    
    return len(expired)
