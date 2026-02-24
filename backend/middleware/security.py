"""
Security middleware for kak file server.

Provides:
- Rate limiting (IP-based)
- Brute-force protection
- Secure HTTP headers
- Request size limits
"""

import time
import hashlib
from typing import Dict, Optional, Tuple
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse, PlainTextResponse
from fastapi import HTTPException

from ..config import config


class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self, requests_per_minute: int = 60, burst_limit: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.requests: Dict[str, list] = defaultdict(list)
        self.blocked_ips: Dict[str, float] = {}
        self.failed_auth: Dict[str, list] = defaultdict(list)
        self.cleanup_interval = 3600  # Clean up every hour
        self.last_cleanup = time.time()
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP, considering X-Forwarded-For header."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def _cleanup(self):
        """Clean up old entries."""
        now = time.time()
        if now - self.last_cleanup > self.cleanup_interval:
            # Clean up old requests
            for ip in list(self.requests.keys()):
                self.requests[ip] = [
                    t for t in self.requests[ip]
                    if now - t < 60
                ]
                if not self.requests[ip]:
                    del self.requests[ip]
            
            # Clean up expired blocks
            for ip in list(self.blocked_ips.keys()):
                if now - self.blocked_ips[ip] > 300:  # 5 min block
                    del self.blocked_ips[ip]
            
            # Clean up failed auth
            for ip in list(self.failed_auth.keys()):
                self.failed_auth[ip] = [
                    t for t in self.failed_auth[ip]
                    if now - t < 300  # 5 min window
                ]
                if not self.failed_auth[ip]:
                    del self.failed_auth[ip]
            
            self.last_cleanup = now
    
    def check_rate_limit(self, request: Request) -> Tuple[bool, Optional[str]]:
        """
        Check if request is within rate limit.
        Returns (allowed, error_message)
        """
        self._cleanup()
        
        ip = self._get_client_ip(request)
        now = time.time()
        
        # Check if IP is blocked
        if ip in self.blocked_ips:
            if now - self.blocked_ips[ip] < 300:
                return False, "Too many requests. IP temporarily blocked."
            else:
                del self.blocked_ips[ip]
        
        # Add current request
        self.requests[ip].append(now)
        
        # Remove requests older than 1 minute
        self.requests[ip] = [
            t for t in self.requests[ip]
            if now - t < 60
        ]
        
        # Check rate limit
        if len(self.requests[ip]) > self.requests_per_minute:
            # Block the IP
            self.blocked_ips[ip] = now
            return False, "Rate limit exceeded. IP blocked."
        
        # Check burst limit (requests in last 5 seconds)
        recent_requests = [
            t for t in self.requests[ip]
            if now - t < 5
        ]
        if len(recent_requests) > self.burst_limit:
            return False, "Burst limit exceeded. Please slow down."
        
        return True, None
    
    def record_failed_auth(self, request: Request):
        """Record failed authentication attempt."""
        ip = self._get_client_ip(request)
        now = time.time()
        
        self.failed_auth[ip].append(now)
        
        # Remove old entries
        self.failed_auth[ip] = [
            t for t in self.failed_auth[ip]
            if now - t < 300
        ]
        
        # Block after 5 failed attempts
        if len(self.failed_auth[ip]) >= 5:
            self.blocked_ips[ip] = now
    
    def record_successful_auth(self, request: Request):
        """Clear failed auth count on successful auth."""
        ip = self._get_client_ip(request)
        if ip in self.failed_auth:
            del self.failed_auth[ip]


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def init_rate_limiter(requests_per_minute: int = 60, burst_limit: int = 10):
    """Initialize the rate limiter."""
    global _rate_limiter
    _rate_limiter = RateLimiter(requests_per_minute, burst_limit)


def get_rate_limiter() -> Optional[RateLimiter]:
    """Get the rate limiter instance."""
    return _rate_limiter


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware for security features."""
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/__dufs__/health", "/health"]:
            return await call_next(request)
        
        # Check rate limit if enabled
        if _rate_limiter:
            allowed, error_msg = _rate_limiter.check_rate_limit(request)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": error_msg},
                    headers={
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(_rate_limiter.requests_per_minute),
                    }
                )
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        return self._add_security_headers(request, response)
    
    def _add_security_headers(self, request: Request, response: Response) -> Response:
        """Add security headers to response."""
        
        # X-Content-Type-Options
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # X-Frame-Options
        response.headers["X-Frame-Options"] = "DENY"
        
        # X-XSS-Protection (legacy but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer-Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content-Security-Policy - strict but functional
        # Allow same origin, inline styles/scripts for web UI
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        
        # Permissions-Policy (modern)
        permissions = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=()"
        )
        response.headers["Permissions-Policy"] = permissions
        
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request size limits."""
    
    def __init__(self, app, max_request_size: int = 100 * 1024 * 1024):  # 100MB default
        super().__init__(app)
        self.max_request_size = max_request_size
    
    async def dispatch(self, request: Request, call_next):
        # Skip for GET, HEAD, OPTIONS requests
        if request.method in ["GET", "HEAD", "OPTIONS", "DELETE"]:
            return await call_next(request)
        
        # Check Content-Length
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                length = int(content_length)
                if length > self.max_request_size:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Request too large. Maximum size: {self.max_request_size} bytes"
                        }
                    )
            except ValueError:
                pass
        
        return await call_next(request)


def parse_size_limit(size_str: str) -> int:
    """Parse size string like '100MB' to bytes."""
    size_str = size_str.strip().upper()
    
    units = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 * 1024,
        'GB': 1024 * 1024 * 1024,
        'TB': 1024 * 1024 * 1024 * 1024,
    }
    
    for unit, multiplier in units.items():
        if size_str.endswith(unit):
            try:
                return int(size_str[:-len(unit)]) * multiplier
            except ValueError:
                pass
    
    # Try parsing as plain number
    try:
        return int(size_str)
    except ValueError:
        return 100 * 1024 * 1024  # Default to 100MB
