"""FastAPI main application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from app.database import init_db
from app.api import api_v1_router

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context: auto-creates tables on startup."""
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Emergency blood donation matching and coordination system backend API.",
    version="0.3.0",
    lifespan=lifespan,
)


# Register versioned API routers
app.include_router(api_v1_router, prefix="/api/v1")

from fastapi.middleware.cors import CORSMiddleware

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "src"

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Mount the Command Center frontend (single UI) if present
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

from app.observability.tracing import instrument_fastapi
instrument_fastapi(app, "gateway")


@app.get("/", tags=["Root"])
def read_root():
    """Root entry point returning system identity and running status."""
    return {
        "message": "Blood Donation Matching System API",
        "status": "running",
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint to verify backend service availability."""
    return {
        "status": "healthy",
    }


@app.get("/dashboard", include_in_schema=False)
@app.get("/ui", include_in_schema=False)
def get_dashboard():
    """Backwards-compatible aliases that redirect to the Command Center frontend."""
    return RedirectResponse(url="/frontend/")
