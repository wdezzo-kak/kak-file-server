from typing import Callable, List
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers


class CorsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_origins: List[str] = None):
        super().__init__(app)
        self.allowed_origins = allowed_origins or ["*"]
        
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("origin")
        
        if request.method == "OPTIONS":
            response = Response(status_code=200)
        else:
            response = await call_next(request)
        
        if origin and (origin in self.allowed_origins or "*" in self.allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = origin if origin != "*" else "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD, MKCOL, COPY, MOVE, PROPFIND, PROPPATCH, LOCK, UNLOCK"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Update-Range, X-Requested-With, Depth, Destination, If-Match, If-None-Match, If-Modified-Since, If-Unmodified-Since, Range, Lock-Token"
            response.headers["Access-Control-Expose-Headers"] = "Content-Range, ETag, Lock-Token"
        
        return response
