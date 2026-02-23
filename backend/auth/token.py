import secrets
import time
from typing import Optional
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import hashlib


class TokenManager:
    def __init__(self, secret: Optional[str] = None):
        self.secret = secret.encode() if secret else secrets.token_bytes(32)
        self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(self.secret[:32])
        self.public_key = self.private_key.public_key()
        
        self.expiry_seconds = 3 * 24 * 60 * 60
    
    def generate_token(self, username: str) -> str:
        expiration = int(time.time() + self.expiry_seconds)
        payload = f"{expiration}:{username}".encode()
        
        signature = self.private_key.sign(payload)
        
        token_data = signature + payload
        return token_data.hex()
    
    def verify_token(self, token: str) -> Optional[str]:
        try:
            token_bytes = bytes.fromhex(token)
            
            if len(token_bytes) < 64 + 10:
                return None
            
            signature = token_bytes[:64]
            payload = token_bytes[64:]
            
            try:
                self.public_key.verify(signature, payload)
            except Exception:
                return None
            
            payload_str = payload.decode()
            parts = payload_str.split(':', 1)
            
            if len(parts) != 2:
                return None
            
            expiration = int(parts[0])
            username = parts[1]
            
            if time.time() > expiration:
                return None
            
            return username
            
        except Exception:
            return None


token_manager: Optional[TokenManager] = None


def init_token_manager(secret: Optional[str] = None):
    global token_manager
    token_manager = TokenManager(secret)
    return token_manager


def get_token_manager() -> TokenManager:
    return token_manager


def generate_token(username: str) -> str:
    return token_manager.generate_token(username)


def verify_token(token: str) -> Optional[str]:
    return token_manager.verify_token(token)
