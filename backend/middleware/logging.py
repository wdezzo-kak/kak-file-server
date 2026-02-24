import time
import json
import logging
from typing import Callable, Dict, Any, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers
from starlette.responses import Response as StarletteResponse

logger = logging.getLogger("dufs")

# Global config for log format
_log_format: str = "plain"
_metrics_enabled: bool = False


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Track connection
        metrics = None
        if _metrics_enabled:
            try:
                from ..metrics import get_metrics
                metrics = get_metrics()
                metrics.inc_connections()
            except Exception:
                pass
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        
        # Record metrics
        if metrics:
            metrics.dec_connections()
            metrics.record_request(
                method=request.method,
                path=str(request.url.path),
                status=response.status_code,
                duration=process_time
            )
        
        # Log the request based on format
        remote_addr = request.client.host if request.client else "unknown"
        method = request.method
        path = str(request.url.path)
        query = str(request.url.query) if request.url.query else ""
        full_path = f"{method} {path}"
        if query:
            full_path += f"?{query}"
        
        status = response.status_code
        
        if _log_format == "json":
            # JSON structured logging
            log_data = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "remote_addr": remote_addr,
                "method": method,
                "path": path,
                "query": query,
                "status": status,
                "duration_ms": round(process_time * 1000, 2),
                "user_agent": request.headers.get("user-agent", "-"),
            }
            print(json.dumps(log_data))
        else:
            # Plain text with colors
            if status >= 500:
                color = "\033[91m"  # Red
            elif status >= 400:
                color = "\033[93m"  # Yellow
            elif status >= 200:
                color = "\033[92m"  # Green
            else:
                color = "\033[0m"   # Reset
            
            reset = "\033[0m"
            
            print(f"{remote_addr} - {full_path} {color}{status}{reset} - {process_time*1000:.1f}ms")
        
        return response


class StructuredLogger:
    def __init__(self, format_string: str = '$remote_addr "$request" $status', log_file: Optional[str] = None):
        self.format_string = format_string
        self.log_file = log_file
        
    def format_log(self, request: Request, response: Response, user: Optional[str] = None) -> str:
        remote_addr = request.client.host if request.client else "unknown"
        method = request.method
        path = str(request.url.path)
        query = str(request.url.query) if request.url.query else ""
        full_request = f"{method} {path}"
        if query:
            full_request += f"?{query}"
        
        status = response.status_code
        
        remote_user = user or "-"
        
        log_line = self.format_string
        log_line = log_line.replace('$remote_addr', remote_addr)
        log_line = log_line.replace('$request', full_request)
        log_line = log_line.replace('$status', str(status))
        log_line = log_line.replace('$remote_user', remote_user)
        
        for header in ['user_agent', 'referer', 'authorization']:
            header_value = request.headers.get(header, '-')
            log_line = log_line.replace(f'$http_{header}', header_value)
        
        return log_line
    
    def log(self, request: Request, response: Response, user: Optional[str] = None):
        log_line = self.format_log(request, response, user)
        
        if response.status_code >= 500:
            logger.error(log_line)
        elif response.status_code >= 400:
            logger.warning(log_line)
        else:
            logger.info(log_line)


structured_logger: Optional[StructuredLogger] = None


def init_logger(format_string: str = '$remote_addr "$request" $status', log_file: Optional[str] = None, json_format: bool = False):
    global structured_logger, _log_format, _metrics_enabled
    
    # Determine log format
    if json_format or format_string == "json":
        _log_format = "json"
    else:
        _log_format = "plain"
    
    # Enable metrics by default when using JSON logging
    if json_format:
        _metrics_enabled = True
    
    structured_logger = StructuredLogger(format_string, log_file)
    
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    return structured_logger


def enable_metrics():
    """Enable metrics collection."""
    global _metrics_enabled
    _metrics_enabled = True


def get_logger() -> 'Optional[StructuredLogger]':
    return structured_logger
