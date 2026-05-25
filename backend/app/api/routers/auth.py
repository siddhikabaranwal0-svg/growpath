from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from supabase import Client
from typing import Any

from app.core.config import get_settings, Settings
from app.core.security import get_supabase_client, get_current_user

router = APIRouter()

class UserCredentials(BaseModel):
    email: EmailStr
    password: str
    username: str | None = None
    full_name: str | None = None

class LoginCredentials(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None
    token_type: str = "bearer"
    user_id: str

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    credentials: UserCredentials,
    supabase: Client = Depends(get_supabase_client)
):
    """
    Register a new user using email and password via Supabase Auth.
    """
    try:
        # Pass optional metadata to Supabase to populate our public.profiles table trigger
        user_meta_data = {}
        if credentials.username:
            user_meta_data["username"] = credentials.username
        if credentials.full_name:
            user_meta_data["full_name"] = credentials.full_name
            
        res = supabase.auth.sign_up({
            "email": credentials.email,
            "password": credentials.password,
            "options": {
                "data": user_meta_data
            }
        })
        
        if not res.session:
            # If email confirmations are enabled, session is None
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail="Registration successful. Please check your email to verify your account."
            )
            
        return TokenResponse(
            access_token=res.session.access_token,
            refresh_token=res.session.refresh_token,
            user_id=res.user.id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}"
        )

@router.post("/login", response_model=TokenResponse)
async def login_user(
    credentials: LoginCredentials,
    supabase: Client = Depends(get_supabase_client)
):
    """
    Log in a user and return the Supabase JWT.
    """
    try:
        res = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password,
        })
        
        if not res.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login credentials"
            )
            
        return TokenResponse(
            access_token=res.session.access_token,
            refresh_token=res.session.refresh_token,
            user_id=res.user.id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Login failed: {str(e)}"
        )

@router.post("/google")
async def google_oauth(
    settings: Settings = Depends(get_settings),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Returns the Supabase Google OAuth authorization URL.
    The client should redirect the user to this URL to complete the OAuth flow.
    """
    try:
        # Supabase Python SDK doesn't natively expose the OAuth URL builder directly through auth.sign_in_with_oauth.
        # It typically returns a URL you must redirect to.
        res = supabase.auth.sign_in_with_oauth(
            {
                "provider": "google",
                "options": {
                    "redirect_to": f"{settings.BACKEND_CORS_ORIGINS[0]}/auth/callback" if settings.BACKEND_CORS_ORIGINS else "http://localhost:3000/auth/callback"
                }
            }
        )
        return {"authorization_url": res.url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth initialization failed: {str(e)}"
        )

@router.get("/me")
async def get_my_profile(
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Protected endpoint to retrieve the current user's profile from the database.
    Demonstrates connecting Supabase Auth JWT with Database Row Level Security (RLS).
    """
    try:
        # Because we're making a server-side request, we must pass the user's JWT to Supabase
        # to ensure RLS policies are applied correctly.
        # But wait, python SDK creates a client with the service role or anon key.
        # To make a request AS the user, we need to pass their token.
        # Alternatively, we can just fetch the profile using the user.id since our profile 
        # RLS allows read access to all profiles or at least our own.
        
        res = supabase.table("profiles").select("*").eq("id", current_user.id).single().execute()
        return res.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve profile: {str(e)}"
        )
