import os
import re
import fnmatch
import mimetypes
from pathlib import Path
from typing import Optional, Tuple
import chardet
import aiofiles


def decode_uri(path: str) -> str:
    try:
        return re.sub(r'%[0-9A-Fa-f]{2}', lambda m: bytes.fromhex(m.group(0)[1:]).decode('utf-8'), path)
    except Exception:
        return path


def validate_path(path: str, root: Path, prefix: str = "") -> Optional[Path]:
    if prefix and not path.startswith(prefix):
        return None
    
    if prefix:
        path = path[len(prefix):]
    
    if not path.startswith('/'):
        path = '/' + path
    
    path = decode_uri(path)
    
    parts = path.split('/')
    for part in parts:
        if not part or part == '.':
            continue
        if part == '..':
            return None
    
    try:
        full_path = root.joinpath(path.lstrip('/')).resolve()
        full_path = full_path.resolve()
        
        if not str(full_path).startswith(str(root.resolve())):
            return None
        
        return full_path
    except Exception:
        return None


def is_hidden(path: Path, hidden_patterns: list) -> bool:
    name = path.name
    for pattern in hidden_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def get_mime_type(path: Path) -> Tuple[str, str]:
    mime, encoding = mimetypes.guess_type(str(path))
    
    if mime is None:
        mime = "application/octet-stream"
    
    if path.suffix in ['.js', '.mjs']:
        mime = "application/javascript"
    elif path.suffix == '.json':
        mime = "application/json"
    elif path.suffix == '.xml':
        mime = "application/xml"
    
    charset = ""
    if mime.startswith('text/') or mime in ['application/javascript', 'application/json', 'application/xml']:
        charset = "; charset=utf-8"
    
    return mime + charset, mime


async def detect_text_encoding(path: Path, sample_size: int = 1024) -> Optional[str]:
    try:
        async with aiofiles.open(path, 'rb') as f:
            sample = await f.read(sample_size)
        
        if not sample:
            return "utf-8"
        
        result = chardet.detect(sample)
        if result and result.get('encoding'):
            return result['encoding']
    except Exception:
        pass
    
    return "utf-8"


def format_size(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def format_time(timestamp: float) -> str:
    from datetime import datetime
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def generate_etag(stat: os.stat_result) -> str:
    return f'"{stat.st_mtime}-{stat.st_size}"'


def parse_etag(etag: str) -> Optional[Tuple[float, int]]:
    if not etag or not etag.startswith('"') or not etag.endswith('"'):
        return None
    
    try:
        parts = etag[1:-1].split('-')
        if len(parts) == 2:
            return (float(parts[0]), int(parts[1]))
    except Exception:
        pass
    
    return None


def check_not_modified(etag: Optional[str], mtime: float, request_etag: Optional[str], request_mtime: Optional[float]) -> bool:
    if request_etag and etag:
        if request_etag == etag:
            return True
    
    if request_mtime and mtime:
        if request_mtime >= mtime:
            return True
    
    return False
