from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from app.core.config import get_settings, Settings
import os

security = HTTPBearer()

def get_supabase_client(settings: Settings = Depends(get_settings)) -> Client:
    # Always create a new client for requests if needed, but for validation we can use a global or pass token
    # Wait, supabase-py supports setting the session using set_session.
    # We will instantiate a base client here.
    supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    return supabase

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings)
):
    """
    Dependency to validate the JWT token against Supabase Auth.
    Requires an Authorization header with a Bearer token.
    """
    token = credentials.credentials
    supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    
    try:
        # We can verify the user by fetching their user profile from Supabase Auth
        # The supabase client `get_user` method validates the JWT server-side
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_response.user
    except Exception as e:
        # Supabase auth errors (e.g. expired token) will trigger this
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
