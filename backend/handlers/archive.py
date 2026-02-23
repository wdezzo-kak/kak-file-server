import os
import zipfile
import io
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from ..utils import is_hidden
from ..config import config


async def serve_directory_zip(request, dir_path: Path, rel_path: str):
    if not dir_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    
    compression_type = request.query_params.get("compression", "deflate")
    
    if compression_type == "none":
        compression = zipfile.ZIP_STORED
    elif compression_type == "bz2":
        compression = zipfile.ZIP_BZIP2
    elif compression_type == "xz":
        compression = zipfile.ZIP_LZMA
    else:
        compression = zipfile.ZIP_DEFLATED
    
    dir_name = dir_path.name or "archive"
    
    # Create zip synchronously
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
