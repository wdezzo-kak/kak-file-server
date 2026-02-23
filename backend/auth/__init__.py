import hashlib
import hmac
import secrets
import time
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from enum import Enum


class AccessPerm(Enum):
    INDEX_ONLY = "index_only"
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


@dataclass
class User:
    username: str
    password: str
    password_hash: Optional[str] = None
    access: AccessPerm = AccessPerm.READ_WRITE


class AuthStore:
    def __init__(self, auth_config: Dict, access_config: list):
        self.users: Dict[str, User] = {}
        self.access_tree: Dict = {}
        self.nonces: Dict[str, Tuple[str, float]] = {}
        self.allow_anonymous = True
        
        if 'users' in auth_config:
            for user_data in auth_config['users']:
                username = user_data.get('username', '')
                password = user_data.get('password', '')
                password_hash = user_data.get('password_hash')
                
                access_str = user_data.get('access', 'read_write')
                if access_str == 'index_only':
                    access = AccessPerm.INDEX_ONLY
                elif access_str == 'read_only':
                    access = AccessPerm.READ_ONLY
                else:
                    access = AccessPerm.READ_WRITE
                
                self.users[username] = User(
                    username=username,
                    password=password,
                    password_hash=password_hash,
                    access=access
                )
        
        if 'allow_anonymous' in auth_config:
            self.allow_anonymous = auth_config['allow_anonymous']
        
        self._build_access_tree(access_config)
    
    def _build_access_tree(self, access_config: list):
        for entry in access_config:
            path = entry.get('path', '/')
            perm_str = entry.get('perm', 'read_write')
            
            if perm_str == 'index_only':
                perm = AccessPerm.INDEX_ONLY
            elif perm_str == 'read_only':
                perm = AccessPerm.READ_ONLY
            else:
                perm = AccessPerm.READ_WRITE
            
            parts = [p for p in path.split('/') if p]
            current = self.access_tree
            
            for part in parts:
                if part not in current:
                    current[part] = {'_perm': perm, '_children': {}}
                current = current[part]['_children']
            
            if '_perm' not in current:
                current['_perm'] = perm
    
    def get_access_for_path(self, username: Optional[str], path: str) -> AccessPerm:
        if username and username in self.users:
            user = self.users[username]
            return user.access
        
        parts = [p for p in path.split('/') if p]
        current = self.access_tree
        
        for part in parts:
            if part in current:
                if '_perm' in current[part]:
                    return current[part]['_perm']
                current = current[part].get('_children', {})
        
        return AccessPerm.READ_WRITE if self.allow_anonymous else AccessPerm.READ_ONLY
    
    def verify_basic(self, username: str, password: str) -> Optional[str]:
        if username not in self.users:
            return None
        
        user = self.users[username]
        
        if user.password_hash:
            hashed = hashlib.sha512(password.encode()).hexdigest()
            if hashed == user.password_hash:
                return username
        elif user.password == password:
            return username
        
        return None
    
    def generate_nonce(self, username: str) -> str:
        timestamp = str(int(time.time()))
        random = secrets.token_hex(16)
        nonce_data = f"{timestamp}:{random}:{username}"
        nonce = hashlib.md5(nonce_data.encode()).hexdigest()
        
        self.nonces[nonce] = (username, time.time() + 7 * 24 * 60 * 60)
        
        return nonce
    
    def verify_nonce(self, nonce: str, username: str) -> bool:
        if nonce not in self.nonces:
            return False
        
        stored_username, expiry = self.nonces[nonce]
        
        if time.time() > expiry:
            del self.nonces[nonce]
            return False
        
        return stored_username == username
    
    def verify_digest(self, authorization: str, method: str, uri: str) -> Optional[str]:
        if not authorization.startswith('Digest '):
            return None
        
        auth_params = {}
        for part in authorization[7:].split(','):
            if '=' in part:
                key, value = part.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"')
                auth_params[key] = value
        
        username = auth_params.get('username')
        if not username or username not in self.users:
            return None
        
        nonce = auth_params.get('nonce')
        if not nonce or not self.verify_nonce(nonce, username):
            return None
        
        response = auth_params.get('response')
        if not response:
            return None
        
        user = self.users[username]
        
        ha1 = user.password_hash if user.password_hash else hashlib.md5(f"{username}:DUFS:{user.password}".encode()).hexdigest()
        
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        
        expected_response = hashlib.md5(f"{ha1}:{nonce}:{auth_params.get('cnonce', '')}:{auth_params.get('qop', 'auth')}:{ha2}".encode()).hexdigest()
        
        if hmac.compare_digest(response, expected_response):
            return username
        
        return None


auth_store: Optional[AuthStore] = None


def init_auth(auth_config: Dict, access_config: list):
    global auth_store
    auth_store = AuthStore(auth_config, access_config)
    return auth_store


def get_auth_store() -> AuthStore:
    return auth_store
