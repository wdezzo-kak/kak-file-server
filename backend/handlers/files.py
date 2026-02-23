import os
import shutil
import json
import time
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
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


async def serve_file(request: Request, file_path: Path, rel_path: str):
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
    
    if range_header:
        try:
            range_match = range_header.replace("bytes=", "")
            if range_match.startswith("-"):
                start = max(0, file_size - int(range_match[1:]))
                end = file_size - 1
            elif "-" in range_match:
                start, end = map(int, range_match.split("-"))
            else:
                start = int(range_match)
                end = file_size - 1
            
            if start >= file_size or end >= file_size:
                raise HTTPException(status_code=416, detail="Range not satisfiable")
            
            async def file_iterator():
                async with aiofiles.open(file_path, 'rb') as f:
                    await f.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk_size = min(65536, remaining)
                        chunk = await f.read(chunk_size)
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(end - start + 1)
            
            return StreamingResponse(
                file_iterator(),
                status_code=206,
                headers=headers
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid range")
    
    headers["Content-Length"] = str(file_size)
    
    async def file_iterator():
        async with aiofiles.open(file_path, 'rb') as f:
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    break
                yield chunk
    
    return StreamingResponse(
        file_iterator(),
        headers=headers
    )


async def upload_file(request: Request, file_path: Path, create_parents: bool = True):
    parent_dir = file_path.parent
    if create_parents:
        await _to_thread(os.makedirs, parent_dir, exist_ok=True)
    
    exists = file_path.exists()
    
    content_length = request.headers.get("Content-Length")
    if content_length:
        content_length = int(content_length)
    
    async with aiofiles.open(file_path, 'wb') as f:
        async for chunk in request.stream():
            await f.write(chunk)
    
    if exists:
        return Response(status_code=204)
    else:
        return Response(status_code=201)


async def append_to_file(request: Request, file_path: Path):
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    async with aiofiles.open(file_path, 'ab') as f:
        async for chunk in request.stream():
            await f.write(chunk)
    
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
    query_lower = query.lower()
    
    async def walk_directory(path: Path, rel_path: str):
        try:
            async with aiofiles.os.scandir(path) as it:
                async for entry in it:
                    entry_path = Path(entry.path)
                    
                    if is_hidden(entry_path, config.hidden):
                        continue
                    
                    rel = os.path.join(rel_path, entry.name)
                    if not rel.startswith('/'):
                        rel = '/' + rel
                    
                    if query_lower in entry.name.lower():
                        stat = await _to_thread(os.stat, entry_path)
                        results.append({
                            "name": entry.name,
                            "path": rel,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                            "is_file": entry.is_file(),
                            "is_dir": entry.is_dir(),
                        })
                    
                    if entry.is_dir():
                        await walk_directory(entry_path, rel)
        except Exception:
            pass
    
    await walk_directory(root, "")
    
    return results[:1000]
