from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.routers import auth, users, skills, paths, recommendations, realtime
from contextlib import asynccontextmanager
from app.realtime.adaptation_loop import startup_realtime_subscriptions, shutdown_realtime_subscriptions

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await startup_realtime_subscriptions()
    yield
    # Shutdown
    await shutdown_realtime_subscriptions()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(skills.router, prefix=f"{settings.API_V1_STR}/skills", tags=["skills"])
app.include_router(paths.router, prefix=f"{settings.API_V1_STR}/paths", tags=["paths"])
app.include_router(recommendations.router, prefix=f"{settings.API_V1_STR}/recommendations", tags=["recommendations"])
app.include_router(realtime.router, prefix=f"{settings.API_V1_STR}/realtime", tags=["realtime"])


@app.get("/")
def root():
    return {"message": "Welcome to the GrowPath API"}
