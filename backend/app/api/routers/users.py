from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client
from typing import Any, List
import datetime

from app.core.security import get_supabase_client, get_current_user

router = APIRouter()

class ProfileUpdate(BaseModel):
    full_name: str | None = None
    avatar_url: str | None = None
    username: str | None = None

class ProfileResponse(BaseModel):
    id: str
    username: str
    full_name: str | None
    avatar_url: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

@router.get("/", response_model=List[ProfileResponse])
async def list_users(
    supabase: Client = Depends(get_supabase_client),
    limit: int = 50,
    offset: int = 0
):
    """
    Retrieve a list of public user profiles.
    Supported by RLS 'Profiles are viewable by anyone'.
    """
    try:
        res = supabase.table("profiles").select("*").range(offset, offset + limit - 1).execute()
        return res.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch profiles: {str(e)}"
        )

@router.put("/me", response_model=ProfileResponse)
async def update_my_profile(
    profile_data: ProfileUpdate,
    current_user: Any = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Update the authenticated user's profile.
    Since we rely on RLS, we must ensure we only update our own ID.
    However, our standard Supabase client in FastAPI operates with the anon/service key.
    To trigger RLS properly as the user, we should ideally use a client with the user's JWT.
    As a workaround for the standard client, we explicitly restrict the update to `current_user.id`.
    """
    update_payload = profile_data.model_dump(exclude_unset=True)
    update_payload["updated_at"] = datetime.datetime.utcnow().isoformat()
    
    if not update_payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields provided for update"
        )
        
    try:
        # We ensure we only update the row where id matches the securely validated current_user.id
        res = supabase.table("profiles").update(update_payload).eq("id", current_user.id).execute()
        
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found or update restricted"
            )
        return res.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )

@router.get("/{user_id}", response_model=ProfileResponse)
async def get_user_by_id(
    user_id: str,
    supabase: Client = Depends(get_supabase_client)
):
    """
    Retrieve a specific user's public profile by ID.
    """
    try:
        res = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        return res.data
    except Exception as e:
        # Supabase raises an error if single() finds nothing, we catch it
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User profile not found"
        )
