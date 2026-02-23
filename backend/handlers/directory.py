import json
import os
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse

from ..utils import is_hidden, format_size, format_time, validate_path
from ..config import config
from ..auth import AccessPerm


async def list_directory_json(request: Request, dir_path: Path, rel_path: str, access_perm: AccessPerm) -> JSONResponse:
    entries = []
    
    try:
        for entry in os.scandir(dir_path):
            entry_path = Path(entry.path)
            
            if is_hidden(entry_path, config.hidden):
                continue
            
            rel = os.path.join(rel_path, entry.name)
            if not rel.startswith('/'):
                rel = '/' + rel
            
            stat = entry.stat()
            
            entries.append({
                "name": entry.name,
                "path": rel,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "is_file": entry.is_file(),
                "is_dir": entry.is_dir(),
            })
    except Exception:
        pass
    
    entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    
    return JSONResponse({
        "href": rel_path if rel_path.startswith('/') else '/' + rel_path,
        "kind": "Index",
        "uri_prefix": config.prefix,
        "allow_upload": access_perm == AccessPerm.READ_WRITE and config.allow_upload,
        "allow_delete": access_perm == AccessPerm.READ_WRITE and config.allow_delete,
        "allow_search": access_perm != AccessPerm.INDEX_ONLY and config.allow_search,
        "allow_archive": access_perm != AccessPerm.INDEX_ONLY and config.allow_archive,
        "dir_exists": True,
        "auth": False,
        "user": None,
        "paths": entries
    })


async def list_directory_simple(request: Request, dir_path: Path, rel_path: str) -> str:
    lines = []
    
    try:
        for entry in os.scandir(dir_path):
            entry_path = Path(entry.path)
            
            if is_hidden(entry_path, config.hidden):
                continue
            
            if entry.is_dir():
                lines.append(f"{entry.name}/")
            else:
                lines.append(f"{entry.name}")
    except Exception:
        pass
    
    lines.sort(key=str.lower)
    
    return "\n".join(lines)


async def list_directory_html(request: Request, dir_path: Path, rel_path: str, access_perm: AccessPerm) -> HTMLResponse:
    sort_by = request.query_params.get("sort", "name")
    order = request.query_params.get("order", "asc")
    
    entries = []
    
    try:
        for entry in os.scandir(dir_path):
            entry_path = Path(entry.path)
            
            if is_hidden(entry_path, config.hidden):
                continue
            
            rel = os.path.join(rel_path, entry.name)
            if not rel.startswith('/'):
                rel = '/' + rel
            
            stat = entry.stat()
            
            entries.append({
                "name": entry.name,
                "path": rel,
                "size": stat.st_size,
                "size_formatted": format_size(stat.st_size),
                "mtime": stat.st_mtime,
                "mtime_formatted": format_time(stat.st_mtime),
                "is_file": entry.is_file(),
                "is_dir": entry.is_dir(),
            })
    except Exception as e:
        pass
    
    def sort_key(e):
        if sort_by == "size":
            return e["size"]
        elif sort_by == "mtime":
            return e["mtime"]
        return e["name"].lower()
    
    reverse = order == "desc"
    entries.sort(key=sort_key, reverse=reverse)
    
    parent_path = os.path.dirname(rel_path.rstrip('/'))
    
    name_order = "desc" if sort_by == "name" and order == "asc" else "asc"
    size_order = "desc" if sort_by == "size" and order == "asc" else "asc"
    mtime_order = "desc" if sort_by == "mtime" and order == "asc" else "asc"
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Index of {rel_path}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 20px; color: #333; }}
        .sort-bar {{ margin-bottom: 15px; display: flex; gap: 10px; align-items: center; }}
        .sort-bar a {{ padding: 4px 8px; border-radius: 4px; text-decoration: none; color: #666; font-size: 0.875rem; }}
        .sort-bar a:hover {{ background: #f0f0f0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ font-weight: 600; color: #666; font-size: 0.875rem; }}
        a {{ color: #0066cc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .icon {{ margin-right: 5px; }}
        .size, .mtime {{ color: #888; font-size: 0.875rem; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Index of {rel_path}</h1>
        <div class="sort-bar">
            <span>Sort:</span>
            <a href="?sort=name&order={name_order}">Name</a>
            <a href="?sort=size&order={size_order}">Size</a>
            <a href="?sort=mtime&order={mtime_order}">Modified</a>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Size</th>
                    <th>Modified</th>
                </tr>
            </thead>
            <tbody>
"""
    
    if parent_path and rel_path != "/":
        html += f"""                <tr>
                    <td><a href="{parent_path}/" class="icon">📁</a><a href="{parent_path}/">..</a></td>
                    <td class="size">-</td>
                    <td class="mtime">-</td>
                </tr>
"""
    
    for entry in entries:
        icon = "📄" if entry["is_file"] else "📁"
        href = entry["path"]
        if entry["is_dir"]:
            href += "/"
        
        size = entry["size_formatted"] if entry["is_file"] else "-"
        
        html += f"""                <tr>
                    <td><a href="{href}" class="icon">{icon}</a><a href="{href}">{entry["name"]}</a></td>
                    <td class="size">{size}</td>
                    <td class="mtime">{entry["mtime_formatted"]}</td>
                </tr>
"""
    
    html += """            </tbody>
        </table>
    </div>
</body>
</html>
"""
    
    return HTMLResponse(content=html)
