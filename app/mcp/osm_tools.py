"""MCP tool exposing OpenStreetMap (Overpass) discovery of nearby blood banks."""
import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.services.osm_discovery import discover_nearby_blood_banks


def register_osm_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def discover_osm_blood_banks(latitude: float, longitude: float, radius_km: float = 25.0, limit: int = 20) -> dict[str, Any]:
        """Find blood banks and blood donation centres near a point using OpenStreetMap (Overpass). Returns facilities only; stock levels are unknown."""
        return await asyncio.to_thread(discover_nearby_blood_banks, latitude, longitude, radius_km, limit)
