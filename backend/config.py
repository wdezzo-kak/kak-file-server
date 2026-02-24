import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml


class Config:
    def __init__(self):
        self.host: str = "0.0.0.0"
        self.port: int = 8080
        self.serve_path: str = "."
        self.root: Path = Path(".").resolve()
        self.prefix: str = ""
        self.single_file: Optional[Path] = None
        
        # Authentication
        self.auth: Dict[str, Any] = {}
        self.allow_anonymous: bool = True
        
        # Access control
        self.access: List[Dict[str, Any]] = []
        self.hidden: List[str] = []
        
        # Features
        self.allow_upload: bool = True
        self.allow_delete: bool = True
        self.allow_search: bool = True
        self.allow_archive: bool = True
        
        # Rendering
        self.render_index: bool = False
        self.render_try_index: bool = False
        self.render_spa: bool = False
        
        # WebDAV
        self.enable_webdav: bool = True
        
        # CORS
        self.cors: List[str] = []
        
        # Logging
        self.log_format: str = '$remote_addr "$request" $status'
        self.log_file: Optional[str] = None
        
        # TLS
        self.tls_cert: Optional[str] = None
        self.tls_key: Optional[str] = None
        
        # Token
        self.token_secret: Optional[str] = None
        
        # Security - Rate limiting
        self.rate_limit: int = 60  # requests per minute
        self.burst_limit: int = 10  # max requests in 5 seconds
        
        # Security - Request size limits
        self.max_request_size: int = 100 * 1024 * 1024  # 100MB default
        self.max_upload_size: int = 10 * 1024 * 1024 * 1024  # 10GB default

    def load_from_file(self, config_path: str) -> None:
        if not os.path.exists(config_path):
            return
            
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        if 'host' in data:
            self.host = data['host']
        if 'port' in data:
            self.port = data['port']
        if 'serve_path' in data:
            self.serve_path = data['serve_path']
            self.root = Path(self.serve_path).resolve()
        if 'single_file' in data:
            self.single_file = Path(data['single_file'])
        if 'prefix' in data:
            self.prefix = data['prefix']
            
        if 'auth' in data:
            self.auth = data['auth']
        if 'allow_anonymous' in data:
            self.allow_anonymous = data['allow_anonymous']
            
        if 'access' in data:
            self.access = data['access']
        if 'hidden' in data:
            self.hidden = data['hidden']
            
        if 'allow_upload' in data:
            self.allow_upload = data['allow_upload']
        if 'allow_delete' in data:
            self.allow_delete = data['allow_delete']
        if 'allow_search' in data:
            self.allow_search = data['allow_search']
        if 'allow_archive' in data:
            self.allow_archive = data['allow_archive']
            
        if 'render_index' in data:
            self.render_index = data['render_index']
        if 'render_try_index' in data:
            self.render_try_index = data['render_try_index']
        if 'render_spa' in data:
            self.render_spa = data['render_spa']
            
        if 'enable_webdav' in data:
            self.enable_webdav = data['enable_webdav']
            
        if 'cors' in data:
            self.cors = data['cors']
            
        if 'log_format' in data:
            self.log_format = data['log_format']
        if 'log_file' in data:
            self.log_file = data['log_file']
            
        if 'tls_cert' in data:
            self.tls_cert = data['tls_cert']
        if 'tls_key' in data:
            self.tls_key = data['tls_key']
            
        if 'token_secret' in data:
            self.token_secret = data['token_secret']
        
        # Security - Rate limiting
        if 'rate_limit' in data:
            self.rate_limit = int(data['rate_limit'])
        if 'burst_limit' in data:
            self.burst_limit = int(data['burst_limit'])
        
        # Security - Request size limits
        if 'max_request_size' in data:
            if isinstance(data['max_request_size'], str):
                from .middleware.security import parse_size_limit
                self.max_request_size = parse_size_limit(data['max_request_size'])
            else:
                self.max_request_size = int(data['max_request_size'])
        if 'max_upload_size' in data:
            if isinstance(data['max_upload_size'], str):
                from .middleware.security import parse_size_limit
                self.max_upload_size = parse_size_limit(data['max_upload_size'])
            else:
                self.max_upload_size = int(data['max_upload_size'])

    def to_dict(self) -> Dict[str, Any]:
        return {
            'host': self.host,
            'port': self.port,
            'serve_path': self.serve_path,
            'root': str(self.root),
            'prefix': self.prefix,
            'single_file': str(self.single_file) if self.single_file else None,
            'auth': self.auth,
            'allow_anonymous': self.allow_anonymous,
            'access': self.access,
            'hidden': self.hidden,
            'allow_upload': self.allow_upload,
            'allow_delete': self.allow_delete,
            'allow_search': self.allow_search,
            'allow_archive': self.allow_archive,
            'render_index': self.render_index,
            'render_try_index': self.render_try_index,
            'render_spa': self.render_spa,
            'enable_webdav': self.enable_webdav,
            'cors': self.cors,
            'log_format': self.log_format,
            'log_file': self.log_file,
            'tls_cert': self.tls_cert,
            'tls_key': self.tls_key,
            'token_secret': self.token_secret,
            'rate_limit': self.rate_limit,
            'burst_limit': self.burst_limit,
            'max_request_size': self.max_request_size,
            'max_upload_size': self.max_upload_size,
        }


config = Config()
