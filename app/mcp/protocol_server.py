"""Official MCP Streamable HTTP server exposing the existing domain tools."""

from mcp.server.fastmcp import FastMCP
import os
from functools import wraps
from typing import Any
from opentelemetry import trace

from app.database.session import SessionLocal
from app.mcp.tools.requirement_tool import handle_validate_blood_request
from app.mcp.tools.matching_tool import handle_find_blood_sources
from app.mcp.tools.location_tool import handle_calculate_distance
from app.mcp.tools.notification_tool import handle_dispatch_notifications
from app.observability.tracing import configure_telemetry, instrument_asgi

configure_telemetry("blood-donation-mcp")
_tracer = trace.get_tracer("app.mcp.domain")


def _domain_operation(name: str, function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _tracer.start_as_current_span("domain.operation", attributes={"domain.operation": name}, record_exception=False, set_status_on_exception=False) as span:
            try:
                return function(*args, **kwargs)
            except Exception as exc:
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.set_attribute("error.type", type(exc).__name__)
                raise
    return wrapped

mcp = FastMCP(
    "blood-donation-tools",
    instructions="Blood request validation, compatible source discovery, and distance tools.",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    port=int(os.getenv("MCP_PORT", "8001")),
    streamable_http_path="/mcp",
)


def _database_tool(handler, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run an existing deterministic tool with a short-lived database session."""
    db = SessionLocal()
    try:
        return handler(arguments, db=db)
    finally:
        db.close()


@mcp.tool()
def validate_blood_request(hospital_id: int, blood_group: str, units_required: int, urgency: str, request_id: int | None = None) -> dict:
    """Validate and normalize a blood request."""
    return _domain_operation("validate_blood_request", lambda: _database_tool(handle_validate_blood_request, {"hospital_id": hospital_id, "blood_group": blood_group, "units_required": units_required, "urgency": urgency, "request_id": request_id}))()


@mcp.tool()
def find_blood_sources(
    blood_group: str,
    request_id: int | None = None,
    inventories: list[dict[str, Any]] | None = None,
    donors: list[dict[str, Any]] | None = None,
) -> dict:
    """Find compatible, currently eligible blood sources."""
    return _domain_operation("find_blood_sources", lambda: _database_tool(handle_find_blood_sources, {
        "blood_group": blood_group, "request_id": request_id,
        "inventories": inventories, "donors": donors,
    }))()


@mcp.tool()
def calculate_distance(origin_latitude: float, origin_longitude: float, destination_latitude: float, destination_longitude: float, include_eta: bool = True) -> dict:
    """Calculate distance and estimated travel time between coordinates."""
    return _domain_operation("calculate_distance", lambda: handle_calculate_distance({"origin_latitude": origin_latitude, "origin_longitude": origin_longitude, "destination_latitude": destination_latitude, "destination_longitude": destination_longitude, "include_eta": include_eta}))()


@mcp.tool()
def dispatch_notifications(
    hospital_id: int,
    request_id: int,
    fulfillment_plan: dict[str, Any],
    hospital_name: str | None = None,
) -> dict[str, Any]:
    """Dispatch notifications for the supplied fulfillment plan."""
    return _domain_operation("dispatch_notifications", lambda: handle_dispatch_notifications({
        "hospital_id": hospital_id,
        "request_id": request_id,
        "fulfillment_plan": fulfillment_plan,
        "hospital_name": hospital_name,
    }))()


from app.security.service_auth import ServiceAuthenticationMiddleware


def create_mcp_app():
    """Build the authenticated, telemetry-instrumented MCP Streamable HTTP ASGI application."""
    secured = ServiceAuthenticationMiddleware(mcp.streamable_http_app(), protected_prefix="/mcp")
    return instrument_asgi(secured, "mcp-server")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_mcp_app(), host="0.0.0.0", port=int(os.getenv("MCP_PORT", "8001")), access_log=False)

