from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    PROJECT_NAME: str = "GrowPath API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    
    # Supabase Configuration
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    
    # CORS Configuration
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"]

    class Config:
        env_file = ".env"
        # Optional fallback to search parent directory
        env_file_encoding = "utf-8"
        extra = "ignore"

@lru_cache
def get_settings() -> Settings:
    # Try to load .env from root if not found in backend directory
    import os
    from dotenv import load_dotenv
    
    # Load backend env
    load_dotenv()
    
    # Load root env
    root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env")
    if os.path.exists(root_env):
        load_dotenv(root_env)
        
    return Settings()
