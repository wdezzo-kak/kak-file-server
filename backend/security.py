"""
Advanced security features for kak file server.

Features:
- IP allowlist/denylist
- Audit logging
- 2FA/TOTP support
- Fail2ban integration
"""

import os
import time
import json
import ipaddress
import secrets
import hashlib
from typing import List, Optional, Set
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict
import threading

# 2FA/TOTP imports
try:
    import pyotp
    TOTP_AVAILABLE = True
except ImportError:
    TOTP_AVAILABLE = False


# ==================== IP Access Control ====================

class IPAccessControl:
    """IP-based access control (allowlist/denylist)."""
    
    def __init__(self):
        self.allowlist: Set[str] = set()
        self.denylist: Set[str] = set()
        self.deny_mode = "deny"  # "deny" = deny specified, "allow" = allow specified only
        self._lock = threading.RLock()
    
    def add_allow(self, ip: str):
        """Add IP to allowlist."""
        with self._lock:
            self.allowlist.add(ip)
            if ip in self.denylist:
                self.denylist.discard(ip)
    
    def add_deny(self, ip: str):
        """Add IP to denylist."""
        with self._lock:
            self.denylist.add(ip)
            if ip in self.allowlist:
                self.allowlist.discard(ip)
    
    def set_deny_mode(self, mode: str):
        """Set deny mode: 'deny' (default) or 'allow'."""
        if mode in ("deny", "allow"):
            self.deny_mode = mode
    
    def is_allowed(self, ip: str) -> bool:
        """Check if IP is allowed."""
        with self._lock:
            # Check denylist first
            if ip in self.denylist:
                return False
            
            # Check allowlist
            if self.allowlist:
                return ip in self.allowlist
            
            # Default based on mode
            return self.deny_mode == "deny"
    
    def check_ip(self, ip: str) -> tuple[bool, str]:
        """
        Check IP and return (allowed, reason).
        """
        if not self.is_allowed(ip):
            return False, "IP blocked by access control"
        return True, "allowed"


# ==================== Audit Logging ====================

@dataclass
class AuditEvent:
    """Represents an audit event."""
    timestamp: str
    event_type: str
    username: Optional[str]
    ip_address: str
    method: str
    path: str
    status: int
    details: dict


class AuditLogger:
    """Audit logger for security events."""
    
    def __init__(self, log_file: Optional[str] = None, max_events: int = 10000):
        self.log_file = log_file
        self.max_events = max_events
        self.events: List[AuditEvent] = []
        self._lock = threading.RLock()
        
        # Event counters
        self.counters: dict = defaultdict(int)
    
    def log_event(
        self,
        event_type: str,
        username: Optional[str],
        ip_address: str,
        method: str,
        path: str,
        status: int,
        details: dict = None
    ):
        """Log an audit event."""
        event = AuditEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            event_type=event_type,
            username=username,
            ip_address=ip_address,
            method=method,
            path=path,
            status=status,
            details=details or {}
        )
        
        with self._lock:
            self.events.append(event)
            
            # Trim old events if needed
            if len(self.events) > self.max_events:
                self.events = self.events[-self.max_events:]
            
            # Increment counter
            self.counters[event_type] += 1
        
        # Write to file if configured
        if self.log_file:
            self._write_to_file(event)
    
    def _write_to_file(self, event: AuditEvent):
        """Write event to audit log file."""
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(asdict(event)) + "\n")
        except Exception:
            pass
    
    def get_events(
        self,
        event_type: Optional[str] = None,
        username: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """Get filtered audit events."""
        with self._lock:
            events = self.events
            
            if event_type:
                events = [e for e in events if e.event_type == event_type]
            if username:
                events = [e for e in events if e.username == username]
            
            return [asdict(e) for e in events[-limit:]]
    
    def get_stats(self) -> dict:
        """Get audit statistics."""
        with self._lock:
            return {
                "total_events": len(self.events),
                "by_type": dict(self.counters)
            }
    
    def clear(self):
        """Clear audit log."""
        with self._lock:
            self.events.clear()
            self.counters.clear()


# ==================== 2FA/TOTP Support ====================

class TwoFactorAuth:
    """Two-factor authentication using TOTP."""
    
    def __init__(self):
        self.secrets: dict = {}  # username -> secret
        self.enabled: Set[str] = set()  # usernames with 2FA enabled
        self._lock = threading.RLock()
    
    def is_available(self) -> bool:
        """Check if 2FA is available (pyotp installed)."""
        return TOTP_AVAILABLE
    
    def generate_secret(self, username: str) -> str:
        """Generate a new TOTP secret for user."""
        if not TOTP_AVAILABLE:
            raise RuntimeError("pyotp not installed")
        
        secret = pyotp.random_base32()
        
        with self._lock:
            self.secrets[username] = secret
        
        return secret
    
    def get_provisioning_uri(self, username: str, issuer: str = "kak") -> str:
        """Get provisioning URI for authenticator app."""
        with self._lock:
            secret = self.secrets.get(username)
            if not secret:
                raise ValueError(f"No secret for user {username}")
        
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(username, issuer_name=issuer)
    
    def enable_2fa(self, username: str):
        """Enable 2FA for user."""
        with self._lock:
            if username in self.secrets:
                self.enabled.add(username)
    
    def disable_2fa(self, username: str):
        """Disable 2FA for user."""
        with self._lock:
            self.enabled.discard(username)
    
    def is_enabled(self, username: str) -> bool:
        """Check if 2FA is enabled for user."""
        with self._lock:
            return username in self.enabled
    
    def verify(self, username: str, code: str) -> bool:
        """Verify a TOTP code."""
        if not TOTP_AVAILABLE:
            return True  # Skip verification if not available
        
        with self._lock:
            secret = self.secrets.get(username)
            if not secret or username not in self.enabled:
                return True  # No 2FA configured
        
        totp = pyotp.TOTP(secret)
        
        # Allow some clock drift (±1 step = ±30 seconds)
        return totp.verify(code, valid_window=1)
    
    def remove_user(self, username: str):
        """Remove 2FA for user."""
        with self._lock:
            self.secrets.pop(username, None)
            self.enabled.discard(username)


# ==================== Fail2ban Integration ====================

def generate_fail2ban_jail(config_path: str = "/etc/fail2ban/jail.local"):
    """
    Generate Fail2ban jail configuration for kak.
    
    This creates a jail.local that can be added to Fail2ban
    to ban IPs that repeatedly fail authentication.
    """
    jail_config = """
[kak-http-auth]
enabled = true
port = http,https
filter = kak-http-auth
logpath = /var/log/kak/audit.log
maxretry = 5
findtime = 600
bantime = 3600
action = iptables-allports[name=kak-http-auth]
"""
    
    filter_config = """
[kak-http-auth]
enabled = true
port = http,https
filter = kak-http-auth
logpath = /var/log/kak/audit.log
maxretry = 5
findtime = 600
bantime = 3600

[Definition]
failregex = ^.*"event_type":\s*"auth_failed".*"ip_address":\s*"<HOST>"
            ^.*"event_type":\s*"rate_limited".*"ip_address":\s*"<HOST>"
ignoreregex =
"""
    
    return {
        "jail": jail_config,
        "filter": filter_config
    }


# ==================== Global Instances ====================

_ip_control: Optional[IPAccessControl] = None
_audit_logger: Optional[AuditLogger] = None
_2fa: Optional[TwoFactorAuth] = None


def get_ip_control() -> IPAccessControl:
    """Get IP access control instance."""
    global _ip_control
    if _ip_control is None:
        _ip_control = IPAccessControl()
    return _ip_control


def get_audit_logger() -> AuditLogger:
    """Get audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def get_2fa() -> TwoFactorAuth:
    """Get 2FA instance."""
    global _2fa
    if _2fa is None:
        _2fa = TwoFactorAuth()
    return _2fa


def init_security(
    allowlist: List[str] = None,
    denylist: List[str] = None,
    deny_mode: str = "deny",
    audit_log_file: str = None
):
    """Initialize security modules."""
    global _audit_logger
    
    # Initialize IP control
    ip_ctrl = get_ip_control()
    if allowlist:
        for ip in allowlist:
            ip_ctrl.add_allow(ip)
    if denylist:
        for ip in denylist:
            ip_ctrl.add_deny(ip)
    ip_ctrl.set_deny_mode(deny_mode)
    
    # Initialize audit logger
    _audit_logger = AuditLogger(log_file=audit_log_file)
