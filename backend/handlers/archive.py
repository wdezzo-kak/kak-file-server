import os
import zipfile
import io
import time
from pathlib import Path
from typing import AsyncGenerator
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from ..utils import is_hidden
from ..config import config


async def serve_directory_zip(request, dir_path: Path, rel_path: str):
    """
    Serve a directory as a ZIP file with streaming support.
    Uses chunked generation for large folders to avoid memory issues.
    """
    if not dir_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    
    compression_type = request.query_params.get("compression", "deflate")
    compression_level = request.query_params.get("level", 6)  # Default compression level 0-9
    
    if compression_type == "none":
        compression = zipfile.ZIP_STORED
    elif compression_type == "bz2":
        compression = zipfile.ZIP_BZIP2
    elif compression_type == "xz":
        compression = zipfile.ZIP_LZMA
    else:
        compression = zipfile.ZIP_DEFLATED
    
    # Parse compression level
    try:
        level = int(compression_level)
        level = max(0, min(9, level))  # Clamp to 0-9
    except (ValueError, TypeError):
        level = 6
    
    dir_name = dir_path.name or "archive"
    
    # For small directories, use the fast in-memory approach
    # For large directories, use streaming
    
    # Count files first to decide approach
    file_count = sum(1 for _ in os.scandir(dir_path))
    
    if file_count < 100:
        # Small directory - use in-memory approach
        return await _serve_zip_inmemory(dir_path, dir_name, compression, level)
    else:
        # Large directory - use streaming approach
        return await _serve_zip_streaming(dir_path, dir_name, compression, level)


async def _serve_zip_inmemory(dir_path: Path, dir_name: str, compression: int, level: int) -> StreamingResponse:
    """In-memory ZIP for small directories."""
    buffer = io.BytesIO()
    
    def add_directory(path: Path, archive_path: str):
        try:
            for entry in os.scandir(path):
                entry_path = Path(entry.path)
                
                if is_hidden(entry_path, config.hidden):
                    continue
                
                rel_path = os.path.join(archive_path, entry.name)
                
                if entry.is_file():
                    stat = entry.stat()
                    zf.write(entry.path, rel_path, compress_type=compression)
                    zinfo = zf.getinfo(rel_path)
                    zinfo.external_attr = (stat.st_mode & 0xFFFF) << 16
                
                elif entry.is_dir():
                    add_directory(entry_path, rel_path + "/")
        except Exception as e:
            print(f"Error creating zip: {e}")
    
    with zipfile.ZipFile(buffer, 'w', compression) as zf:
        add_directory(dir_path, dir_name)
    
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{dir_name}.zip"'
        }
    )


async def _serve_zip_streaming(dir_path: Path, dir_name: str, compression: int, level: int) -> StreamingResponse:
    """
    Streaming ZIP for large directories.
    Writes ZIP in chunks to avoid loading entire archive in memory.
    """
    
    async def zip_stream_generator() -> AsyncGenerator[bytes, None]:
        """Generate ZIP file in streaming fashion."""
        
        # Use a temporary file for building the ZIP
        import tempfile
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Build ZIP in temp file
            with zipfile.ZipFile(tmp_path, 'w', compression) as zf:
                _add_directory_to_zip(zf, dir_path, dir_name, compression)
            
            # Stream the file in chunks
            chunk_size = 65536  # 64KB chunks
            with open(tmp_path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        
        finally:
            # Clean up temp file
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    
    return StreamingResponse(
        zip_stream_generator(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{dir_name}.zip"',
            "X-Content-Type-Options": "nosniff"
        }
    )


def _add_directory_to_zip(zf: zipfile.ZipFile, path: Path, archive_path: str, compression: int):
    """Recursively add directory contents to ZIP file."""
    try:
        for entry in os.scandir(path):
            entry_path = Path(entry.path)
            
            if is_hidden(entry_path, config.hidden):
                continue
            
            rel_path = os.path.join(archive_path, entry.name)
            
            if entry.is_file():
                stat = entry.stat()
                zf.write(entry.path, rel_path, compress_type=compression)
                zinfo = zf.getinfo(rel_path)
                zinfo.external_attr = (stat.st_mode & 0xFFFF) << 16
            
            elif entry.is_dir():
                _add_directory_to_zip(zf, entry_path, rel_path + "/", compression)
    except Exception as e:
        print(f"Error adding to zip: {e}")
