from fastapi import APIRouter
from app.api.v1.blood_requests import router as blood_requests_router
from app.api.v1.hospitals import router as hospitals_router
from app.api.v1.nl_request import router as nl_request_router
from app.api.v1.auth import router as auth_router
from app.mcp.server import mcp_router

api_v1_router = APIRouter()
api_v1_router.include_router(
    auth_router,
)
api_v1_router.include_router(
    blood_requests_router,
    prefix="/blood-requests",
    tags=["Blood Requests"],
)
api_v1_router.include_router(
    hospitals_router,
    prefix="/hospitals",
    tags=["Hospitals"],
)
api_v1_router.include_router(
    nl_request_router,
)
api_v1_router.include_router(
    mcp_router,
)
