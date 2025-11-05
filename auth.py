from typing import Optional, Dict, Any
from aiohttp import web
import hashlib
import secrets
from storage import JSONStorage
from config import DATA_DIR

users_storage = JSONStorage(f"{DATA_DIR}/users.json")

# Simple in-memory user store (resets on restart)
_current_users = {}

async def hash_password(password: str) -> str:
    # Simple hash with salt (not cryptographically secure, but works for demo)
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode('utf-8'))
    return f"{salt}:{hash_obj.hexdigest()}"

async def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, stored_hash = hashed.split(':', 1)
        hash_obj = hashlib.sha256()
        hash_obj.update((password + salt).encode('utf-8'))
        return hash_obj.hexdigest() == stored_hash
    except:
        return False

async def get_current_user(request: web.Request) -> Optional[Dict[str, Any]]:
    # Simple auth via Authorization header or ?user= parameter
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        username = auth_header[7:]  # Remove 'Bearer '
        return _current_users.get(username)
    
    # Or via query parameter
    username = request.query.get('user')
    if username:
        return _current_users.get(username)
    
    return None

def require_login(handler):
    async def wrapper(request: web.Request):
        user = await get_current_user(request)
        if not user:
            if request.headers.get('Accept', '').find('text/html') >= 0 and request.method == 'GET':
                raise web.HTTPFound('/login')
            raise web.HTTPUnauthorized()
        return await handler(request)
    return wrapper

def require_admin(handler):
    async def wrapper(request: web.Request):
        user = await get_current_user(request)
        if not user or user.get('role') != 'admin':
            raise web.HTTPForbidden()
        return await handler(request)
    return wrapper

