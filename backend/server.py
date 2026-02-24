import os
import sys
import json
import click
from pathlib import Path
from typing import Optional, Tuple
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from .config import config
from .auth import init_auth, get_auth_store, AccessPerm
from .auth.token import init_token_manager, generate_token, verify_token
from .middleware.logging import init_logger, get_logger, LoggingMiddleware
from .middleware.security import (
    SecurityMiddleware, RequestSizeLimitMiddleware,
    init_rate_limiter, get_rate_limiter, parse_size_limit
)
from .sharing import (
    generate_presigned_url, create_share_link, verify_share_link,
    verify_presigned_token, get_share, list_shares, delete_share
)
from .metrics import get_metrics, init_metrics
from .handlers import (
    serve_file, upload_file, append_to_file, delete_path, create_directory,
    list_directory_json, list_directory_simple, list_directory_html,
    serve_directory_zip, get_file_hash, search_files,
    handle_propfind, handle_proppatch, handle_lock, handle_unlock,
    handle_copy, handle_move, parse_destination
)
from .utils import validate_path


app = FastAPI(title="kak File Server")

app.add_middleware(LoggingMiddleware)

# Security middleware - add before CORS
app.add_middleware(SecurityMiddleware)

# Request size limit middleware
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_request_size=config.max_request_size
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors if config.cors else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    config.root = Path(config.serve_path).resolve()
    
    if config.single_file:
        config.root = Path(config.single_file).resolve()
    
    init_auth(config.auth, config.access)
    init_token_manager(config.token_secret)
    init_logger(config.log_format, config.log_file)
    
    # Initialize rate limiter
    init_rate_limiter(config.rate_limit, config.burst_limit)
    
    # Initialize metrics
    init_metrics()
    
    os.makedirs(config.root, exist_ok=True)


@app.get("/__dufs__/health")
async def health_check():
    return JSONResponse({
        "status": "ok",
        "version": "0.3.0"
    })


# ==================== Share Links & Pre-signed URLs ====================

@app.post("/__dufs__/share")
async def create_share(request: Request):
    """Create a share link with optional expiration, download limits, password."""
    username, access = check_auth(request)
    
    if access != AccessPerm.READ_WRITE:
        raise HTTPException(status_code=403, detail="Write permission required")
    
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path is required")
    
    # Validate path
    file_path = validate_path(path, config.root, config.prefix)
    if file_path is None:
        raise HTTPException(status_code=404, detail="Path not found")
    
    expires_in = data.get("expires_in")  # seconds
    download_limit = data.get("download_limit")
    password = data.get("password")
    
    share = create_share_link(
        path=path,
        expires_in=expires_in,
        download_limit=download_limit,
        password=password
    )
    
    return JSONResponse(share)


@app.get("/__dufs__/shares")
async def list_all_shares(request: Request):
    """List all active share links."""
    username, access = check_auth(request)
    
    if access != AccessPerm.READ_WRITE:
        raise HTTPException(status_code=403, detail="Write permission required")
    
    return JSONResponse({"shares": list_shares()})


@app.delete("/__dufs__/share/{share_id}")
async def remove_share(request: Request, share_id: str):
    """Delete a share link."""
    username, access = check_auth(request)
    
    if access != AccessPerm.READ_WRITE:
        raise HTTPException(status_code=403, detail="Write permission required")
    
    if delete_share(share_id):
        return JSONResponse({"status": "deleted"})
    else:
        raise HTTPException(status_code=404, detail="Share not found")


@app.post("/__dufs__/presign")
async def create_presigned(request: Request):
    """Create a pre-signed URL for temporary access."""
    username, access = check_auth(request)
    
    if access != AccessPerm.READ_WRITE:
        raise HTTPException(status_code=403, detail="Write permission required")
    
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path is required")
    
    # Validate path
    file_path = validate_path(path, config.root, config.prefix)
    if file_path is None:
        raise HTTPException(status_code=404, detail="Path not found")
    
    expires_in = data.get("expires_in", 3600)  # default 1 hour
    allow_upload = data.get("allow_upload", False)
    
    token, url = generate_presigned_url(
        path=path,
        expires_in=expires_in,
        allow_upload=allow_upload
    )
    
    return JSONResponse({
        "url": url,
        "token": token,
        "expires_in": expires_in
    })


@app.get("/__dufs__/s/{share_id}")
async def access_share(request: Request, share_id: str):
    """Access a shared file via share link."""
    # Check for password
    password = request.query_params.get("password")
    
    share = verify_share_link(share_id, password)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found or expired")
    
    # Get the file path
    path = share["path"]
    file_path = validate_path(path, config.root, config.prefix)
    
    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Serve the file
    return await serve_file(request, file_path, path)


# ==================== Metrics Endpoint ====================

@app.get("/__dufs__/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    metrics = get_metrics()
    return PlainTextResponse(
        content=metrics.get_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


def check_auth(request: Request) -> Tuple[Optional[str], AccessPerm]:
    token = request.query_params.get("token")
    if token:
        username = verify_token(token)
        if username:
            auth_store = get_auth_store()
            access = auth_store.get_access_for_path(username, request.url.path)
            return username, access
    
    auth_header = request.headers.get("Authorization")
    
    if auth_header:
        if auth_header.startswith("Basic "):
            import base64
            try:
                credentials = base64.b64decode(auth_header[6:]).decode()
                username, password = credentials.split(":", 1)
                auth_store = get_auth_store()
                verified = auth_store.verify_basic(username, password)
                if verified:
                    access = auth_store.get_access_for_path(verified, request.url.path)
                    return verified, access
            except Exception:
                pass
        
        elif auth_header.startswith("Digest "):
            auth_store = get_auth_store()
            username = auth_store.verify_digest(auth_header, request.method, request.url.path)
            if username:
                access = auth_store.get_access_for_path(username, request.url.path)
                return username, access
    
    auth_store = get_auth_store()
    if auth_store.allow_anonymous:
        access = auth_store.get_access_for_path(None, request.url.path)
        return None, access
    
    return None, AccessPerm.READ_ONLY


@app.get("/")
async def handle_root(request: Request):
    """Serve the frontend UI at root path, or handle API requests"""
    # Check if there are query params that indicate API requests
    if request.query_params:
        # Handle API request - delegate to main handler logic
        return await handle_request(request, "/")
    else:
        # Serve frontend HTML for root path without query params
        frontend_dir = get_frontend_dir()
        return FileResponse(frontend_dir / "index.html")


@app.get("/styles.css")
@app.get("/app.js")
@app.get("/favicon.ico")
async def serve_frontend_assets(request: Request):
    """Serve frontend assets from root path"""
    path = request.url.path
    frontend_dir = get_frontend_dir()
    asset_file = frontend_dir / path.lstrip("/")
    if asset_file.exists() and asset_file.is_file():
        return FileResponse(asset_file)
    return Response(status_code=404)


@app.get("/{full_path:path}")
async def handle_request(request: Request, full_path: str = ""):
    # Check if it's a frontend asset request
    if full_path.startswith("__ui__") or full_path.startswith("__frontend__") or full_path.startswith("ui/") or full_path.startswith("files/"):
        frontend_dir = get_frontend_dir()
        if full_path.startswith("__ui__"):
            asset_path = full_path.replace("__ui__/", "", 1)
        elif full_path.startswith("__frontend__"):
            asset_path = full_path.replace("__frontend__/", "", 1)
        elif full_path.startswith("ui/"):
            asset_path = full_path.replace("ui/", "", 1)
        elif full_path.startswith("files/"):
            asset_path = full_path.replace("files/", "", 1)
        else:
            asset_path = ""
        
        if asset_path:
            asset_file = frontend_dir / asset_path
            if asset_file.exists() and asset_file.is_file():
                return FileResponse(asset_file)
        return FileResponse(frontend_dir / "index.html")
    
    username, access = check_auth(request)
    
    # Handle path - full_path comes with leading "/" already from route
    if full_path and not full_path.startswith("/"):
        full_path = "/" + full_path
    
    if config.prefix and not full_path.startswith(config.prefix):
        raise HTTPException(status_code=404, detail="Not found")
    
    if config.prefix:
        path = full_path[len(config.prefix):]
    else:
        path = full_path
    
    if not path:
        path = "/"
    
    file_path = validate_path(path, config.root, config.prefix)
    
    if file_path is None:
        raise HTTPException(status_code=404, detail="Not found")
    
    is_dir = file_path.is_dir() if file_path.exists() else path.endswith("/")
    
    if not file_path.exists():
        parent = file_path.parent
        if not parent.exists():
            raise HTTPException(status_code=404, detail="Not found")
    
    query_params = request.query_params
    
    if config.single_file and path == "/":
        file_path = config.root
    
    if "json" in query_params:
        return await list_directory_json(request, file_path, path, access)
    
    if "simple" in query_params:
        content = await list_directory_simple(request, file_path, path)
        return PlainTextResponse(content=content)
    
    if "zip" in query_params:
        if access == AccessPerm.INDEX_ONLY:
            raise HTTPException(status_code=403, detail="Forbidden")
        return await serve_directory_zip(request, file_path, path)
    
    if "q" in query_params:
        if access == AccessPerm.INDEX_ONLY:
            raise HTTPException(status_code=403, detail="Forbidden")
        query = query_params.get("q", "")
        results = await search_files(config.root, query)
        return JSONResponse({"results": results})
    
    if "recursive" in query_params:
        # Return all files recursively (for sidebar tree)
        results = await search_files(config.root, "")
        return JSONResponse({"results": results})
    
    if "stats" in query_params:
        # Return storage statistics
        import asyncio
        
        # Get filesystem stats using statvfs
        try:
            stat = os.statvfs(str(config.root))
            total_space = stat.f_frsize * stat.f_blocks
            free_space = stat.f_frsize * stat.f_bavail
            used_space = total_space - free_space
        except Exception:
            total_space = 0
            free_space = 0
            used_space = 0
        
        # Count files
        file_count = 0
        folder_count = 0
        
        def count_files(path: Path):
            nonlocal file_count, folder_count
            try:
                for entry in os.scandir(path):
                    if entry.is_file():
                        file_count += 1
                    elif entry.is_dir():
                        folder_count += 1
                        count_files(Path(entry.path))
            except Exception:
                pass
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: count_files(config.root))
        
        return JSONResponse({
            "total_space": total_space,
            "free_space": free_space,
            "used_space": used_space,
            "file_count": file_count,
            "folder_count": folder_count
        })
    
    if "hash" in query_params:
        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Not a file")
        hash_value = await get_file_hash(file_path)
        return PlainTextResponse(content=hash_value)
    
    if "tokengen" in query_params:
        if username is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        token = generate_token(username)
        return JSONResponse({"token": token})
    
    if "view" in query_params or "edit" in query_params:
        return await list_directory_html(request, file_path, path, access)
    
    if file_path.is_file():
        if access == AccessPerm.INDEX_ONLY:
            raise HTTPException(status_code=403, detail="Forbidden")
        return await serve_file(request, file_path, path)
    
    if file_path.is_dir():
        if config.render_index or config.render_try_index:
            index_file = file_path / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
        
        if config.render_try_index:
            return await list_directory_html(request, file_path, path, access)
        
        if config.render_spa:
            index_file = file_path / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
        
        return await list_directory_html(request, file_path, path, access)
    
    raise HTTPException(status_code=404, detail="Not found")


@app.head("/{full_path:path}")
async def head_request(request: Request, full_path: str = ""):
    username, access = check_auth(request)
    
    if access == AccessPerm.INDEX_ONLY:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if not full_path:
        full_path = "/"
    else:
        full_path = "/" + full_path
    
    if config.prefix:
        path = full_path[len(config.prefix):]
    else:
        path = full_path
    
    if not path:
        path = "/"
    
    file_path = validate_path(path, config.root, config.prefix)
    
    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    
    if not file_path.is_file():
        return Response(status_code=200)
    
    stat = os.stat(file_path)
    from .utils import generate_etag
    etag = generate_etag(stat)
    
    return Response(
        status_code=200,
        headers={
            "ETag": etag,
            "Last-Modified": str(stat.st_mtime),
            "Accept-Ranges": "bytes",
            "Content-Length": str(stat.st_size),
        }
    )


@app.put("/{full_path:path}")
async def put_request(request: Request, full_path: str = ""):
    username, access = check_auth(request)
    
    if access != AccessPerm.READ_WRITE:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if not full_path:
        full_path = "/"
    else:
        full_path = "/" + full_path
    
    if config.prefix:
        path = full_path[len(config.prefix):]
    else:
        path = full_path
    
    if not path:
        path = "/"
    
    file_path = validate_path(path, config.root, config.prefix)
    
    if file_path is None:
        raise HTTPException(status_code=400, detail="Invalid path")
    
    return await upload_file(request, file_path)


@app.patch("/{full_path:path}")
async def patch_request(request: Request, full_path: str = ""):
    username, access = check_auth(request)
    
    if access != AccessPerm.READ_WRITE:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if not full_path:
        full_path = "/"
    else:
        full_path = "/" + full_path
    
    if config.prefix:
        path = full_path[len(config.prefix):]
    else:
        path = full_path
    
    if not path:
        path = "/"
    
    file_path = validate_path(path, config.root, config.prefix)
    
    if file_path is None:
        raise HTTPException(status_code=400, detail="Invalid path")
    
    update_range = request.headers.get("X-Update-Range", "overwrite")
    
    if update_range == "append":
        return await append_to_file(request, file_path)
    
    return await upload_file(request, file_path)


@app.delete("/{full_path:path}")
async def delete_request(request: Request, full_path: str = ""):
    username, access = check_auth(request)
    
    if access != AccessPerm.READ_WRITE:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if not full_path:
        full_path = "/"
    else:
        full_path = "/" + full_path
    
    if config.prefix:
        path = full_path[len(config.prefix):]
    else:
        path = full_path
    
    if not path:
        path = "/"
    
    file_path = validate_path(path, config.root, config.prefix)
    
    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    
    return await delete_path(file_path)


@app.options("/{full_path:path}")
@app.options("/")
async def options_request(request: Request, full_path: str = ""):
    return Response(
        status_code=200,
        headers={
            "Allow": "GET, HEAD, PUT, PATCH, DELETE, OPTIONS, MKCOL, COPY, MOVE, PROPFIND, PROPPATCH, LOCK, UNLOCK",
            "DAV": "1, 2",
        }
    )


@app.post("/{full_path:path}")
async def post_request(request: Request, full_path: str = ""):
    if not full_path:
        full_path = "/"
    else:
        full_path = "/" + full_path
    
    if config.prefix:
        path = full_path[len(config.prefix):]
    else:
        path = full_path
    
    if not path:
        path = "/"
    
    file_path = validate_path(path, config.root, config.prefix)
    
    if file_path is None:
        raise HTTPException(status_code=400, detail="Invalid path")
    
    if file_path.exists():
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    return await create_directory(file_path)


@app.put("/")
async def put_root(request: Request):
    return await put_request(request, "")


@app.get("/__dufs_v0.1.0__/index.js")
async def get_js():
    js = """
// Dufs Web UI JavaScript
document.addEventListener('DOMContentLoaded', function() {
    console.log('Dufs Web UI loaded');
});
"""
    return Response(content=js, media_type="application/javascript")


@app.get("/__dufs_v0.1.0__/index.css")
async def get_css():
    css = """
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    padding: 20px;
    background: #f5f5f5;
}
"""
    return Response(content=css, media_type="text/css")


@app.get("/__dufs_v0.1.0__/favicon.ico")
async def get_favicon():
    return Response(status_code=204)


@app.api_route("/{full_path:path}", methods=["MKCOL", "COPY", "MOVE", "PROPFIND", "PROPPATCH", "LOCK", "UNLOCK"])
async def webdav_request(request: Request, full_path: str = ""):
    username, access = check_auth(request)
    
    if not full_path:
        full_path = "/"
    else:
        full_path = "/" + full_path
    
    if config.prefix:
        path = full_path[len(config.prefix):]
    else:
        path = full_path
    
    if not path:
        path = "/"
    
    file_path = validate_path(path, config.root, config.prefix)
    
    if file_path is None:
        raise HTTPException(status_code=400, detail="Invalid path")
    
    method = request.method
    
    if method == "PROPFIND":
        if access == AccessPerm.INDEX_ONLY:
            raise HTTPException(status_code=403, detail="Forbidden")
        depth = request.headers.get("Depth", "1")
        return await handle_propfind(request, file_path, path, depth)
    
    elif method == "PROPPATCH":
        return await handle_proppatch(request, file_path)
    
    elif method == "LOCK":
        return await handle_lock(request, file_path, path)
    
    elif method == "UNLOCK":
        return await handle_unlock(request, file_path)
    
    elif method == "MKCOL":
        if access != AccessPerm.READ_WRITE:
            raise HTTPException(status_code=403, detail="Forbidden")
        return await create_directory(file_path)
    
    elif method == "COPY":
        if access != AccessPerm.READ_WRITE:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        destination = request.headers.get("Destination")
        if not destination:
            raise HTTPException(status_code=400, detail="Destination required")
        
        dst_path = parse_destination(destination, str(request.base_url))
        dst_file_path = validate_path(dst_path, config.root, config.prefix)
        
        if dst_file_path is None:
            raise HTTPException(status_code=400, detail="Invalid destination")
        
        return await handle_copy(request, file_path, dst_file_path)
    
    elif method == "MOVE":
        if access != AccessPerm.READ_WRITE:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        destination = request.headers.get("Destination")
        if not destination:
            raise HTTPException(status_code=400, detail="Destination required")
        
        dst_path = parse_destination(destination, str(request.base_url))
        dst_file_path = validate_path(dst_path, config.root, config.prefix)
        
        if dst_file_path is None:
            raise HTTPException(status_code=400, detail="Invalid destination")
        
        return await handle_move(request, file_path, dst_file_path)
    
    raise HTTPException(status_code=405, detail="Method not allowed")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


def get_frontend_dir():
    return Path(__file__).resolve().parent / "frontend"


@app.get("/__frontend__/{file_path:path}")
async def serve_frontend(file_path: str):
    frontend_dir = get_frontend_dir()
    file = frontend_dir / file_path
    
    if file.exists() and file.is_file():
        return FileResponse(file)
    
    return FileResponse(frontend_dir / "index.html")


@app.get("/__frontend__/")
@app.get("/__frontend__")
async def serve_frontend_index():
    frontend_dir = get_frontend_dir()
    return FileResponse(frontend_dir / "index.html")


@app.get("/__ui__/")
@app.get("/ui/")
@app.get("/files/")
async def serve_ui_index():
    frontend_dir = get_frontend_dir()
    return FileResponse(frontend_dir / "index.html")


def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def run_server(host: str = "0.0.0.0", port: int = 8080, reload: bool = False):
    local_ip = get_local_ip()
    print(f"\n🚀 Server running at:")
    print(f"   📁 Files: {config.serve_path}")
    print(f"   🌐 http://localhost:{port}")
    print(f"   🌐 http://{local_ip}:{port}\n")
    
    uvicorn.run(
        "backend.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


@click.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@click.option('-p', '--port', default=8080, help='Port to bind to')
@click.option('--serve-path', default='.', help='Path to serve files from')
@click.option('--single-file', help='Serve a single file')
@click.option('--prefix', default='', help='URL prefix')
@click.option('--config', '-c', 'config_file', help='Configuration file path')
@click.option('--hidden', multiple=True, help='Hidden file patterns (can repeat)')
@click.option('-A', '--all', 'enable_all', is_flag=True, help='Enable all features (upload, delete, search, archive)')
@click.option('--allow-upload/--no-upload', default=None, help='Allow file uploads')
@click.option('--allow-delete/--no-delete', default=None, help='Allow file deletion')
@click.option('--allow-search/--no-search', default=None, help='Allow file search')
@click.option('--allow-archive/--no-archive', default=None, help='Allow archive downloads')
@click.option('--render-index', is_flag=True, help='Render index.html for directories')
@click.option('--render-try-index', is_flag=True, help='Try index.html, fallback to listing')
@click.option('--render-spa', is_flag=True, help='Render SPA mode')
@click.option('--cors', multiple=True, help='CORS origins (can repeat)')
@click.option('--log-format', default='$remote_addr "$request" $status', help='Log format')
@click.option('--log-file', help='Log file path')
@click.option('--tls-cert', help='TLS certificate file')
@click.option('--tls-key', help='TLS key file')
@click.option('--token-secret', help='Secret for token generation')
@click.option('--reload', is_flag=True, help='Enable auto-reload')
@click.option('--rate-limit', default=60, help='Rate limit: requests per minute')
@click.option('--burst-limit', default=10, help='Burst limit: max requests in 5 seconds')
@click.option('--max-request-size', default='100MB', help='Max request size (e.g., 100MB, 1GB)')
@click.option('--max-upload-size', default='10GB', help='Max upload size (e.g., 10GB, 1TB)')
def main(host, port, serve_path, single_file, prefix, config_file, hidden, enable_all,
         allow_upload, allow_delete, allow_search, allow_archive,
         render_index, render_try_index, render_spa, cors,
         log_format, log_file, tls_cert, tls_key, token_secret, reload,
         rate_limit, burst_limit, max_request_size, max_upload_size):
    """kak - A modern file server"""
    
    # Load config file if provided
    if config_file and os.path.exists(config_file):
        config.load_from_file(config_file)
    
    # Override with CLI arguments
    config.host = host
    config.port = port
    
    if serve_path:
        config.serve_path = serve_path
        config.root = Path(serve_path).resolve()
    
    if single_file:
        config.single_file = Path(single_file)
    
    if prefix:
        config.prefix = prefix
    
    if hidden:
        config.hidden = list(hidden)
    
    # Handle --all flag or individual flags
    if enable_all:
        config.allow_upload = True
        config.allow_delete = True
        config.allow_search = True
        config.allow_archive = True
    else:
        # Use CLI values if provided, otherwise use config file values or defaults
        if allow_upload is not None:
            config.allow_upload = allow_upload
        if allow_delete is not None:
            config.allow_delete = allow_delete
        if allow_search is not None:
            config.allow_search = allow_search
        if allow_archive is not None:
            config.allow_archive = allow_archive
    
    config.render_index = render_index
    config.render_try_index = render_try_index
    config.render_spa = render_spa
    
    if cors:
        config.cors = list(cors)
    
    config.log_format = log_format
    config.log_file = log_file
    config.tls_cert = tls_cert
    config.tls_key = tls_key
    config.token_secret = token_secret
    
    # Security settings
    config.rate_limit = rate_limit
    config.burst_limit = burst_limit
    
    # Parse size limits
    from .middleware.security import parse_size_limit
    config.max_request_size = parse_size_limit(max_request_size)
    config.max_upload_size = parse_size_limit(max_upload_size)
    
    # Ensure serve path exists
    os.makedirs(config.root, exist_ok=True)
    
    # Run server
    uvicorn.run(
        "backend.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="warning"
    )


if __name__ == "__main__":
    main()
