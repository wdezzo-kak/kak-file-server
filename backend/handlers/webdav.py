import os
import shutil
import time
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, Request, Response
import asyncio
from starlette.responses import Response as StarletteResponse

from ..utils import validate_path, generate_etag
from ..config import config


class XMLResponse(Response):
    media_type = "application/xml; charset=utf-8"
    
    def __init__(self, content, status_code=200, **kwargs):
        if isinstance(content, str):
            body = content.encode('utf-8')
        else:
            body = content
        super().__init__(content=body, status_code=status_code, **kwargs)


async def handle_propfind(request: Request, path: Path, rel_path: str, depth: str = "1"):
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    
    if depth not in ["0", "1", "infinity"]:
        raise HTTPException(status_code=400, detail="Invalid depth")
    
    responses = []
    
    async def add_resource(res_path: Path, res_rel: str):
        if not res_path.exists():
            return
        
        stat = await asyncio.get_event_loop().run_in_executor(None, os.stat, res_path)
        
        displayname = res_path.name or "/"
        if res_rel == "/" or res_rel == "":
            displayname = res_path.name or ""
        
        is_collection = res_path.is_dir()
        
        href = res_rel
        if not href.startswith('/'):
            href = '/' + href
        if is_collection and not href.endswith('/'):
            href += '/'
        
        mtime = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(stat.st_mtime))
        
        response = f"""<D:response xmlns:D="DAV:">
<D:href>{href}</D:href>
<D:propstat>
<D:prop>
<D:displayname>{displayname}</D:displayname>
<D:getlastmodified>{mtime}</D:getlastmodified>
<D:getcontentlength>{stat.st_size}</D:getcontentlength>
<D:getetag>"{stat.st_mtime}-{stat.st_size}"</D:getetag>
<D:resourcetype>{"<D:collection/>" if is_collection else ""}</D:resourcetype>
</D:prop>
<D:status>HTTP/1.1 200 OK</D:status>
</D:propstat>
</D:response>"""
        
        responses.append(response)
    
    await add_resource(path, rel_path)
    
    if depth in ["1", "infinity"] and path.is_dir():
        try:
            async with os.scandir(path) as it:
                for entry in it:
                    entry_path = Path(entry.path)
                    entry_rel = os.path.join(rel_path, entry.name)
                    if not entry_rel.startswith('/'):
                        entry_rel = '/' + entry_rel
                    await add_resource(entry_path, entry_rel)
        except Exception:
            pass
    
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
{''.join(responses)}
</D:multistatus>"""
    
    return XMLResponse(
        content=body,
        status_code=207,
        media_type="application/xml; charset=utf-8"
    )


async def handle_proppatch(request: Request, path: Path):
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    
    body = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
<D:response>
<D:href>/</D:href>
<D:propstat>
<D:prop>
<D:displayname/>
</D:prop>
<D:status>HTTP/1.1 403 Forbidden</D:status>
</D:propstat>
</D:response>
</D:multistatus>"""
    
    return XMLResponse(
        content=body,
        status_code=207,
        media_type="application/xml; charset=utf-8"
    )


async def handle_lock(request: Request, path: Path, rel_path: str):
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    
    if path.is_dir():
        raise HTTPException(status_code=404, detail="Cannot lock directory")
    
    lock_token = f"urn:uuid:{os.urandom(16).hex()}"
    
    body = """<?xml version="1.0" encoding="utf-8"?>
<D:prop xmlns:D="DAV:">
<D:lockdiscovery>
<D:activelock>
<D:locktoken><D:href>"""
    body += lock_token
    body += """</D:href></D:locktoken>
<D:lockroot><D:href>/"""
    body += rel_path.lstrip('/')
    body += """</D:href></D:lockroot>
<D:depth>infinity</D:depth>
<D:timeout>Second-3600</D:timeout>
<D:owner/>
</D:activelock>
</D:lockdiscovery>
</D:prop>"""
    
    return XMLResponse(
        content=body,
        status_code=200,
        media_type="application/xml; charset=utf-8",
        headers={
            "Lock-Token": lock_token
        }
    )


async def handle_unlock(request: Request, path: Path):
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    
    return Response(status_code=204)


async def handle_copy(request: Request, src_path: Path, dst_path: Path):
    if not src_path.exists():
        raise HTTPException(status_code=404, detail="Source not found")
    
    if src_path.is_dir():
        raise HTTPException(status_code=403, detail="Cannot copy directory")
    
    await asyncio.get_event_loop().run_in_executor(None, shutil.copy2, src_path, dst_path)
    
    return Response(status_code=204)


async def handle_move(request: Request, src_path: Path, dst_path: Path):
    if not src_path.exists():
        raise HTTPException(status_code=404, detail="Source not found")
    
    await asyncio.get_event_loop().run_in_executor(None, os.rename, src_path, dst_path)
    
    return Response(status_code=204)


def parse_destination(header: str, base_url: str) -> str:
    if header.startswith("http"):
        path = "/".join(header.split("/")[3:])
        return "/" + path if not path.startswith("/") else path
    return header.lstrip("/")
