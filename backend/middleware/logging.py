import time
import logging
from typing import Callable, Dict, Any, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers

logger = logging.getLogger("dufs")


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


def init_logger(format_string: str = '$remote_addr "$request" $status', log_file: Optional[str] = None):
    global structured_logger
    structured_logger = StructuredLogger(format_string, log_file)
    
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    return structured_logger


def get_logger() -> StructuredLogger:
    return structured_logger
