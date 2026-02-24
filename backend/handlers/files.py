import os
import shutil
import json
import time
import asyncio
import hashlib
import fcntl
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
import aiofiles
import aiofiles.os

from ..utils import (
    validate_path, get_mime_type, generate_etag, format_size, format_time,
    is_hidden, decode_uri, check_not_modified
)
from ..config import config
from ..auth import AccessPerm

import sys
if sys.version_info >= (3, 9):
    from asyncio import to_thread as _to_thread
else:
    async def _to_thread(func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# Binary content types that should never be compressed
BINARY_CONTENT_TYPES = frozenset([
    'application/octet-stream', 'application/pdf', 'application/zip',
    'application/x-tar', 'application/x-gzip', 'application/x-rar-compressed',
    'application/x-7z-compressed', 'application/x-bzip2', 'application/x-xz',
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
    'image/x-icon', 'image/bmp', 'image/tiff', 'audio/mpeg', 'audio/wav',
    'audio/ogg', 'audio/flac', 'video/mp4', 'video/webm', 'video/ogg',
    'video/x-msvideo', 'video/x-matroska', 'font/ttf', 'font/otf',
    'font/woff', 'font/woff2', 'application/javascript', 'application/json',
    'application/xml', 'text/plain', 'text/html', 'text/css',
])



async def get_file_info(path: Path, rel_path: str) -> Dict[str, Any]:
    stat = await _to_thread(os.stat, path)
    
    return {
        "name": path.name,
        "path": rel_path,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
    }


async def list_directory(path: Path, rel_path: str, show_hidden: bool = False) -> List[Dict[str, Any]]:
    entries = []
    
    try:
        async with aiofiles.os.scandir(path) as it:
            async for entry in it:
                entry_path = Path(entry.path)
                
                if not show_hidden and is_hidden(entry_path, config.hidden):
                    continue
                
                rel = os.path.join(rel_path, entry.name)
                if not rel.startswith('/'):
                    rel = '/' + rel
                
                stat = await _to_thread(os.stat, entry_path)
                
                entries.append({
                    "name": entry.name,
                    "path": rel,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "is_file": entry.is_file(),
                    "is_dir": entry.is_dir(),
                })
    except Exception as e:
        pass
    
    return entries


def parse_range_header(range_header: str, file_size: int) -> List[Tuple[int, int]]:
    """
    Parse HTTP Range header and return list of (start, end) tuples.
    Supports:
    - Range: bytes=start-end
    - Range: bytes=-suffix (last N bytes)
    - Range: bytes=start- (from start to end)
    - Range: bytes=0-99,200-299 (multiple ranges - returned as list)
    """
    ranges = []
    
    # Handle multiple ranges
    if ',' in range_header:
        for part in range_header.split(','):
            part = part.strip()
            if part:
                parsed = _parse_single_range(part.strip(), file_size)
                if parsed:
                    ranges.append(parsed)
    else:
        parsed = _parse_single_range(range_header.strip(), file_size)
        if parsed:
            ranges.append(parsed)
    
    return ranges


def _parse_single_range(range_str: str, file_size: int) -> Optional[Tuple[int, int]]:
    """Parse a single range specification."""
    if not range_str.startswith("bytes="):
        return None
    
    range_match = range_str[6:]  # Remove "bytes="
    
    # Case: bytes=-500 (last 500 bytes)
    if range_match.startswith("-"):
        suffix_length = int(range_match[1:])
        start = max(0, file_size - suffix_length)
        end = file_size - 1
        return (start, end)
    
    # Case: bytes=500- (from byte 500 to end)
    if range_match.endswith("-"):
        start = int(range_match[:-1])
        if start >= file_size:
            return None
        end = file_size - 1
        return (start, end)
    
    # Case: bytes=500-999 (bytes 500 to 999)
    if "-" in range_match:
        parts = range_match.split("-")
        start = int(parts[0])
        end = int(parts[1])
        
        # Handle invalid ranges
        if start > end:
            return None
        if start >= file_size:
            return None
        if end >= file_size:
            end = file_size - 1
        
        return (start, end)
    
    return None


async def serve_file(request: Request, file_path: Path, rel_path: str):
    """Serve a file with full HTTP Range support."""
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    stat = await _to_thread(os.stat, file_path)
    file_size = stat.st_size
    
    etag = generate_etag(stat)
    last_modified = stat.st_mtime
    
    request_etag = request.headers.get("If-None-Match")
    request_mtime = None
    if_modified_since = request.headers.get("If-Modified-Since")
    if if_modified_since:
        try:
            request_mtime = time.mktime(time.strptime(if_modified_since, "%a, %d %b %Y %H:%M:%S GMT"))
        except Exception:
            pass
    
    if check_not_modified(etag, last_modified, request_etag, request_mtime):
        return Response(status_code=304)
    
    range_header = request.headers.get("Range")
    
    mime_type, _ = get_mime_type(file_path)
    
    headers = {
        "ETag": etag,
        "Last-Modified": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(last_modified)),
        "Accept-Ranges": "bytes",
        "Content-Type": mime_type,
    }
    
    # Check if we should disable compression (binary files)
    # Note: Compression is handled at server level, we just indicate content type
    
    # If no Range header, serve entire file
    if not range_header:
        headers["Content-Length"] = str(file_size)
        
        # Try to use sendfile for better performance
        return await _serve_with_sendfile(file_path, file_size, headers)
    
    # Parse Range header
    try:
        ranges = parse_range_header(range_header, file_size)
        
        if not ranges:
            # Invalid range specification
            return Response(
                status_code=416,
                headers={
                    "Content-Range": f"bytes */{file_size}",
                    "Accept-Ranges": "bytes",
                }
            )
        
        # Handle single range - most common case
        if len(ranges) == 1:
            start, end = ranges[0]
            
            # Validate the range
            if start >= file_size or end >= file_size:
                return Response(
                    status_code=416,
                    headers={
                        "Content-Range": f"bytes */{file_size}",
                        "Accept-Ranges": "bytes",
                    }
                )
            
            # For single range, use streaming response
            content_length = end - start + 1
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(content_length)
            
            async def range_file_iterator():
                async with aiofiles.open(file_path, 'rb') as f:
                    await f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk_size = min(65536, remaining)
                        chunk = await f.read(chunk_size)
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            
            return StreamingResponse(
                range_file_iterator(),
                status_code=206,
                headers=headers
            )
        
        # Multiple ranges - create multipart response
        # This is more complex and less commonly used
        return await _serve_multiple_ranges(file_path, file_size, ranges, headers, mime_type)
    
    except (ValueError, IndexError) as e:
        raise HTTPException(status_code=400, detail="Invalid range header")


async def _serve_with_sendfile(file_path: Path, file_size: int, headers: Dict[str, str]) -> Response:
    """Serve file using optimized file streaming."""
    # Use async file streaming - efficient for most cases
    # For true zero-copy sendfile, you'd integrate with uvicorn's underlying transport
    return StreamingResponse(
        _stream_file_chunks(file_path),
        headers=headers
    )


async def _stream_file_chunks(file_path: Path):
    """Stream file in chunks - efficient async file reading."""
    async with aiofiles.open(file_path, 'rb') as f:
        while True:
            chunk = await f.read(65536)
            if not chunk:
                break
            yield chunk


async def _serve_multiple_ranges(
    file_path: Path,
    file_size: int,
    ranges: List[Tuple[int, int]],
    headers: Dict[str, str],
    mime_type: str
) -> Response:
    """Serve multiple ranges in a multipart response."""
    import io
    
    # Build multipart response
    boundary = "----FormBoundary" + str(time.time())
    content_type = f"multipart/byteranges; boundary={boundary}"
    headers["Content-Type"] = content_type
    
    async def multipart_iterator():
        async with aiofiles.open(file_path, 'rb') as f:
            for start, end in ranges:
                await f.seek(start)
                content_length = end - start + 1
                
                yield f"\r\n--{boundary}\r\n".encode()
                yield f"Content-Type: {mime_type}\r\n".encode()
                yield f"Content-Range: bytes {start}-{end}/{file_size}\r\n\r\n".encode()
                
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(65536, remaining)
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
            
            yield f"\r\n--{boundary}--\r\n".encode()
    
    return StreamingResponse(
        multipart_iterator(),
        status_code=206,
        headers=headers
    )


async def upload_file(request: Request, file_path: Path, create_parents: bool = True):
    """Upload a file with optional SHA256 verification."""
    parent_dir = file_path.parent
    if create_parents:
        await _to_thread(os.makedirs, parent_dir, exist_ok=True)
    
    exists = file_path.exists()
    
    content_length = request.headers.get("Content-Length")
    if content_length:
        content_length = int(content_length)
    
    # Check for expected hash header (client can send this for verification)
    expected_hash = request.headers.get("X-Content-SHA256")
    
    # For new uploads, use atomic write with temp file
    if not exists:
        # Create temp file in same directory for atomic rename
        temp_fd, temp_path = await _to_thread(
            tempfile.mkstemp, dir=file_path.parent, prefix='.kak_upload_'
        )
        os.close(temp_fd)
        
        try:
            hasher = hashlib.sha256()
            
            async with aiofiles.open(temp_path, 'wb') as f:
                async for chunk in request.stream():
                    await f.write(chunk)
                    if expected_hash:
                        hasher.update(chunk)
            
            # Verify hash if provided
            if expected_hash:
                actual_hash = hasher.hexdigest()
                if actual_hash != expected_hash:
                    await _to_thread(os.remove, temp_path)
                    raise HTTPException(
                        status_code=422,
                        detail="SHA256 mismatch",
                        headers={"X-Content-SHA256-Actual": actual_hash}
                    )
            
            # Atomic rename
            await _to_thread(os.rename, temp_path, file_path)
            
        except Exception:
            # Clean up temp file on error
            try:
                await _to_thread(os.remove, temp_path)
            except Exception:
                pass
            raise
    else:
        # File exists - use regular write
        async with aiofiles.open(file_path, 'wb') as f:
            async for chunk in request.stream():
                await f.write(chunk)
    
    # Calculate final hash if requested
    final_hash = None
    if request.headers.get("X-Verify-SHA256") == "true":
        final_hash = await get_file_hash(file_path)
    
    if final_hash:
        return Response(
            status_code=201 if not exists else 204,
            headers={"X-Content-SHA256": final_hash}
        )
    
    if exists:
        return Response(status_code=204)
    else:
        return Response(status_code=201)


async def append_to_file(request: Request, file_path: Path):
    """
    Append to a file for resumable uploads with:
    - Offset validation
    - File locking
    - Atomic append (write to temp, then rename)
    """
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Parse Content-Range header for offset validation
    content_range = request.headers.get("Content-Range")
    expected_offset = 0
    
    if content_range:
        # Format: bytes start-end total
        # Example: bytes 1024-2047/2048
        try:
            range_part = content_range.split("/")[0].strip()
            if range_part.startswith("bytes "):
                range_vals = range_part[6:].split("-")
                if len(range_vals) == 2:
                    expected_offset = int(range_vals[0])
        except (ValueError, IndexError):
            pass
    
    # Get current file size for validation
    stat = await _to_thread(os.stat, file_path)
    current_size = stat.st_size
    
    # Validate offset - must match current file size for append
    if expected_offset != current_size:
        raise HTTPException(
            status_code=409,
            detail=f"Offset mismatch. Expected {current_size}, got {expected_offset}",
            headers={
                "X-Current-Size": str(current_size),
                "X-Expected-Offset": str(expected_offset)
            }
        )
    
    # Get content length
    content_length = request.headers.get("Content-Length")
    if content_length:
        content_length = int(content_length)
    
    # Check for hash verification
    expected_hash = request.headers.get("X-Content-SHA256")
    
    # Use atomic append: write to temp file, then append
    temp_fd, temp_path = await _to_thread(
        tempfile.mkstemp, dir=file_path.parent, prefix='.kak_append_'
    )
    os.close(temp_fd)
    
    try:
        hasher = hashlib.sha256() if expected_hash else None
        
        # Write incoming data to temp file
        async with aiofiles.open(temp_path, 'wb') as f:
            async for chunk in request.stream():
                await f.write(chunk)
                if hasher:
                    hasher.update(chunk)
        
        # Verify hash if provided
        if expected_hash:
            temp_hash = hasher.hexdigest()
            if temp_hash != expected_hash:
                await _to_thread(os.remove, temp_path)
                raise HTTPException(
                    status_code=422,
                    detail="SHA256 mismatch",
                    headers={"X-Content-SHA256-Actual": temp_hash}
                )
        
        # Use file locking for the append operation
        def atomic_append():
            # Lock the target file
            with open(file_path, 'ab') as target:
                fcntl.flock(target.fileno(), fcntl.LOCK_EX)
                try:
                    # Re-validate size after acquiring lock (another process might have appended)
                    current_stat = os.stat(file_path)
                    if current_stat.st_size != expected_offset:
                        raise HTTPException(
                            status_code=409,
                            detail="File modified during upload"
                        )
                    
                    # Append temp content to target
                    with open(temp_path, 'rb') as src:
                        shutil.copyfileobj(src, target)
                finally:
                    fcntl.flock(target.fileno(), fcntl.LOCK_UN)
            
            # Clean up temp file
            os.remove(temp_path)
        
        await _to_thread(atomic_append)
        
    except HTTPException:
        # Clean up temp file on error
        try:
            await _to_thread(os.remove, temp_path)
        except Exception:
            pass
        raise
    except Exception as e:
        # Clean up temp file on error
        try:
            await _to_thread(os.remove, temp_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
    
    # Return final file hash if requested
    final_hash = None
    if request.headers.get("X-Verify-SHA256") == "true":
        final_hash = await get_file_hash(file_path)
    
    if final_hash:
        return Response(
            status_code=204,
            headers={"X-Content-SHA256": final_hash}
        )
    
    return Response(status_code=204)


async def delete_path(file_path: Path):
    if file_path.is_file() or file_path.is_symlink():
        await _to_thread(os.remove, file_path)
    elif file_path.is_dir():
        await _to_thread(os.rmdir, file_path)
    
    return Response(status_code=204)


async def create_directory(file_path: Path):
    if file_path.exists():
        raise HTTPException(status_code=405, detail="Path already exists")
    
    await _to_thread(os.makedirs, file_path, exist_ok=True)
    
    return Response(status_code=201)


async def move_path(src: Path, dst: Path):
    await _to_thread(os.rename, src, dst)
    
    return Response(status_code=204)


async def copy_file(src: Path, dst: Path):
    if src.is_dir():
        raise HTTPException(status_code=403, detail="Cannot copy directory")
    
    await _to_thread(shutil.copy2, src, dst)
    
    return Response(status_code=204)


async def get_file_hash(file_path: Path) -> str:
    import hashlib
    
    hasher = hashlib.sha256()
    
    async with aiofiles.open(file_path, 'rb') as f:
        while True:
            chunk = await f.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    
    return hasher.hexdigest()


async def search_files(root: Path, query: str) -> List[Dict[str, Any]]:
    results = []
    
    # If query is empty, return all files (for recursive listing)
    if not query:
        query_lower = ""
    else:
        query_lower = query.lower()
    
    def walk_directory(path: Path, rel_path: str):
        try:
            for entry in os.scandir(path):
                entry_path = Path(entry.path)
                
                if is_hidden(entry_path, config.hidden):
                    continue
                
                rel = os.path.join(rel_path, entry.name)
                if not rel.startswith('/'):
                    rel = '/' + rel
                
                # Include all if query is empty, otherwise filter by name
                if not query_lower or query_lower in entry.name.lower():
                    stat = os.stat(entry_path)
                    results.append({
                        "name": entry.name,
                        "path": rel,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "is_file": entry.is_file(),
                        "is_dir": entry.is_dir(),
                    })
                
                if entry.is_dir():
                    walk_directory(entry_path, rel)
        except Exception:
            pass
    
    await _to_thread(walk_directory, root, "")
    
    return results[:5000]
