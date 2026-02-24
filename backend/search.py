"""
Search indexing and metadata caching for kak file server.

Features:
- SQLite-based full-text search index
- Background indexing for large directories
- File metadata caching
- Incremental updates on file changes
"""

import os
import sqlite3
import time
import threading
import hashlib
from typing import List, Optional, Dict, Any, Set
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
import queue


# ==================== Database Schema ====================

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    parent_path TEXT NOT NULL,
    is_dir INTEGER NOT NULL DEFAULT 0,
    size INTEGER DEFAULT 0,
    mtime REAL NOT NULL,
    hash TEXT,
    indexed_at REAL NOT NULL,
    
    -- Full-text search
    name_lower TEXT,
    path_lower TEXT
);

CREATE INDEX IF NOT EXISTS idx_path ON files(path);
CREATE INDEX IF NOT EXISTS idx_parent ON files(parent_path);
CREATE INDEX IF NOT EXISTS idx_name_lower ON files(name_lower);
CREATE INDEX IF NOT EXISTS idx_mtime ON files(mtime);

-- Metadata cache table
CREATE TABLE IF NOT EXISTS metadata_cache (
    path TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    cached_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

-- Indexing state
CREATE TABLE IF NOT EXISTS index_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


# ==================== File Index ====================

class FileIndex:
    """SQLite-based file search index."""
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database and schema."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
    
    def _get_relative_path(self, root: Path, file_path: Path) -> str:
        """Get relative path from root."""
        try:
            return "/" + str(file_path.relative_to(root)).replace("\\", "/")
        except ValueError:
            return "/" + file_path.name
    
    def index_directory(self, root: Path, show_hidden: List[str] = None):
        """Index an entire directory tree."""
        with self._lock:
            # Clear existing index
            self.conn.execute("DELETE FROM files")
            
            # Walk directory
            count = 0
            for dirpath, dirnames, filenames in os.walk(root):
                dirpath = Path(dirpath)
                
                # Filter hidden
                if show_hidden:
                    dirnames[:] = [d for d in dirnames if not self._is_hidden(d, show_hidden)]
                
                parent_path = self._get_relative_path(root, dirpath)
                
                # Index directories
                for dirname in dirnames:
                    full_path = dirpath / dirname
                    self._index_file(full_path, parent_path + "/" + dirname, True)
                    count += 1
                
                # Index files
                for filename in filenames:
                    if self._is_hidden(filename, show_hidden):
                        continue
                    full_path = dirpath / filename
                    rel_path = self._get_relative_path(root, full_path)
                    self._index_file(full_path, rel_path, False)
                    count += 1
            
            self.conn.commit()
            return count
    
    def _is_hidden(self, name: str, patterns: List[str]) -> bool:
        """Check if file matches hidden patterns."""
        import fnmatch
        for pattern in patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False
    
    def _index_file(self, path: Path, rel_path: str, is_dir: bool):
        """Index a single file."""
        try:
            stat = path.stat()
            
            self.conn.execute("""
                INSERT OR REPLACE INTO files 
                (path, name, parent_path, is_dir, size, mtime, indexed_at, name_lower, path_lower)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rel_path,
                path.name,
                str(Path(rel_path).parent),
                1 if is_dir else 0,
                stat.st_size if not is_dir else 0,
                stat.st_mtime,
                time.time(),
                path.name.lower(),
                rel_path.lower()
            ))
        except Exception:
            pass
    
    def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search files by name."""
        query_lower = query.lower().strip()
        
        if not query_lower:
            return []
        
        with self._lock:
            # Try exact match first
            cursor = self.conn.execute("""
                SELECT path, name, is_dir, size, mtime
                FROM files
                WHERE name_lower = ?
                LIMIT ?
            """, (query_lower, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "path": row[0],
                    "name": row[1],
                    "is_dir": bool(row[2]),
                    "size": row[3],
                    "mtime": row[4]
                })
            
            # If not enough, search with LIKE
            if len(results) < limit:
                cursor = self.conn.execute("""
                    SELECT path, name, is_dir, size, mtime
                    FROM files
                    WHERE name_lower LIKE ? AND name_lower != ?
                    LIMIT ?
                """, (f"%{query_lower}%", query_lower, limit - len(results)))
                
                for row in cursor.fetchall():
                    results.append({
                        "path": row[0],
                        "name": row[1],
                        "is_dir": bool(row[2]),
                        "size": row[3],
                        "mtime": row[4]
                    })
            
            return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        with self._lock:
            cursor = self.conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_dir = 1 THEN 1 ELSE 0 END) as dirs,
                    SUM(CASE WHEN is_dir = 0 THEN 1 ELSE 0 END) as files,
                    SUM(size) as total_size
                FROM files
            """)
            row = cursor.fetchone()
            
            return {
                "total_entries": row[0] or 0,
                "directories": row[1] or 0,
                "files": row[2] or 0,
                "total_size": row[3] or 0
            }
    
    def clear(self):
        """Clear the index."""
        with self._lock:
            self.conn.execute("DELETE FROM files")
            self.conn.commit()
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


# ==================== Metadata Cache ====================

class MetadataCache:
    """In-memory and SQLite metadata cache."""
    
    def __init__(self, db_path: str = ":memory:", ttl: int = 300):
        """
        Args:
            db_path: Path to SQLite database (or :memory:)
            ttl: Time-to-live in seconds for cache entries
        """
        self.db_path = db_path
        self.ttl = ttl
        self.conn: Optional[sqlite3.Connection] = None
        self._memory_cache: Dict[str, Dict] = {}
        self._lock = threading.RLock()
        self._init_db()
    
    def _init_db(self):
        """Initialize cache database."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
    
    def get(self, path: str) -> Optional[Dict]:
        """Get cached metadata."""
        now = time.time()
        
        # Check memory cache first
        with self._lock:
            if path in self._memory_cache:
                entry = self._memory_cache[path]
                if now < entry["expires_at"]:
                    return entry["data"]
                else:
                    del self._memory_cache[path]
        
        # Check SQLite cache
        if self.conn:
            cursor = self.conn.execute("""
                SELECT data, expires_at FROM metadata_cache
                WHERE path = ?
            """, (path,))
            row = cursor.fetchone()
            
            if row and now < row[1]:
                import json
                data = json.loads(row[0])
                
                # Update memory cache
                with self._lock:
                    self._memory_cache[path] = {
                        "data": data,
                        "expires_at": row[1]
                    }
                
                return data
            elif row:
                # Expired, delete
                self.conn.execute("DELETE FROM metadata_cache WHERE path = ?", (path,))
                self.conn.commit()
        
        return None
    
    def set(self, path: str, data: Dict):
        """Cache metadata."""
        now = time.time()
        expires_at = now + self.ttl
        
        import json
        data_json = json.dumps(data)
        
        # Update memory cache
        with self._lock:
            self._memory_cache[path] = {
                "data": data,
                "expires_at": expires_at
            }
        
        # Update SQLite cache
        if self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO metadata_cache (path, data, cached_at, expires_at)
                VALUES (?, ?, ?, ?)
            """, (path, data_json, now, expires_at))
            self.conn.commit()
    
    def invalidate(self, path: str):
        """Invalidate cached entry."""
        with self._lock:
            self._memory_cache.pop(path, None)
        
        if self.conn:
            self.conn.execute("DELETE FROM metadata_cache WHERE path = ?", (path,))
            self.conn.commit()
    
    def clear(self):
        """Clear all cache."""
        with self._lock:
            self._memory_cache.clear()
        
        if self.conn:
            self.conn.execute("DELETE FROM metadata_cache")
            self.conn.commit()
    
    def close(self):
        """Close database."""
        if self.conn:
            self.conn.close()


# ==================== Background Indexer ====================

class BackgroundIndexer:
    """Background indexer that watches for file changes."""
    
    def __init__(self, index: FileIndex, root: Path, show_hidden: List[str] = None):
        self.index = index
        self.root = root
        self.show_hidden = show_hidden or []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._indexed_paths: Set[str] = set()
    
    def start(self):
        """Start background indexing."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop background indexing."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _run(self):
        """Background indexing loop."""
        # Initial full index
        self._full_index()
        
        # Watch for changes (polling approach)
        while self._running:
            time.sleep(60)  # Check every minute
            self._check_changes()
    
    def _full_index(self):
        """Perform full directory index."""
        try:
            count = self.index.index_directory(self.root, self.show_hidden)
            print(f"[Indexer] Indexed {count} entries")
        except Exception as e:
            print(f"[Indexer] Error: {e}")
    
    def _check_changes(self):
        """Check for file changes and update index."""
        # Simplified: re-index on changes detected
        # In production, you'd use filesystem notifications (inotify, FSEvents)
        try:
            # Quick check if any files changed
            for dirpath, dirnames, filenames in os.walk(self.root):
                for f in filenames:
                    path = Path(dirpath) / f
                    try:
                        mtime = path.stat().st_mtime
                        rel_path = self.index._get_relative_path(self.root, path)
                        
                        # Check if needs re-indexing
                        if rel_path not in self._indexed_paths:
                            self.index._index_file(path, rel_path, False)
                            self._indexed_paths.add(rel_path)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Indexer] Error checking changes: {e}")


# ==================== Global Instances ====================

_file_index: Optional[FileIndex] = None
_metadata_cache: Optional[MetadataCache] = None
_background_indexer: Optional[BackgroundIndexer] = None


def get_file_index() -> FileIndex:
    """Get file index instance."""
    global _file_index
    if _file_index is None:
        _file_index = FileIndex()
    return _file_index


def get_metadata_cache() -> MetadataCache:
    """Get metadata cache instance."""
    global _metadata_cache
    if _metadata_cache is None:
        _metadata_cache = MetadataCache()
    return _metadata_cache


def init_search_index(root: Path, db_path: str = None, enable_background: bool = False, show_hidden: List[str] = None):
    """Initialize search index."""
    global _file_index, _metadata_cache, _background_indexer
    
    # Create file index
    if db_path:
        _file_index = FileIndex(db_path)
    else:
        _file_index = FileIndex()
    
    # Create metadata cache
    _metadata_cache = MetadataCache()
    
    # Initial indexing
    count = _file_index.index_directory(root, show_hidden)
    print(f"[Search] Indexed {count} files")
    
    # Start background indexer if enabled
    if enable_background:
        _background_indexer = BackgroundIndexer(_file_index, root, show_hidden)
        _background_indexer.start()
    
    return _file_index
