"""FastAPI main application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from app.database import init_db
from app.api import api_v1_router

settings = get_settings()

STATIC_DIR = Path(__file__).resolve().parent / "static"


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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory if present
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Mount Part 13 frontend directory if present
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

# Add Observability Metrics Middleware (Part 16)
from app.observability.metrics import MetricsMiddleware, get_metrics_snapshot
app.add_middleware(MetricsMiddleware)


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


@app.get("/metrics", tags=["Observability"])
def get_metrics():
    """Real-time observability operational metrics snapshot (Part 16)."""
    return get_metrics_snapshot()


@app.get("/dashboard", tags=["Dashboard"])
@app.get("/ui", tags=["Dashboard"])
def get_dashboard():
    """Interactive emergency coordinator frontend dashboard."""
    dashboard_file = STATIC_DIR / "dashboard.html"
    return FileResponse(dashboard_file)

