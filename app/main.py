"""Dokku Dashboard - Main application."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.config import get_settings
from app.routers import apps, config, logs

# Create FastAPI app
app = FastAPI(
    title="Dokku Dashboard",
    description="Web UI for managing Dokku applications",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dashboard.brewbytes.dev", "https://auth.brewbytes.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(apps.router)
app.include_router(logs.router)
app.include_router(config.router)

# Templates
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Redirect to apps list."""
    return RedirectResponse(url="/apps", status_code=302)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "app": get_settings().app_name}


@app.middleware("http")
async def add_user_to_request(request: Request, call_next):
    """Add user info to request state."""
    request.state.user = get_current_user(request)
    response = await call_next(request)
    return response

