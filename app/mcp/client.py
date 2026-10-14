"""Official MCP client helpers for Streamable HTTP tool discovery and invocation."""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from opentelemetry import trace
from app.observability.tracing import (
    MCP_CALLS, MCP_DISCOVERIES, MCP_DURATION, MCP_ERRORS,
    configure_telemetry, instrument_http_client,
)

tracer = trace.get_tracer("app.mcp.client")
_KNOWN_TOOLS = {"validate_blood_request", "find_blood_sources", "calculate_distance", "dispatch_notifications"}


def _safe_tool_name(name: str) -> str:
    return name if name in _KNOWN_TOOLS else "unknown"


class MCPClientError(RuntimeError):
    """Structured failure from MCP discovery or tool invocation."""

    def __init__(self, message: str, *, code: str, tool: str | None = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.tool = tool
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        return {"error": str(self), "error_code": self.code, "tool": self.tool, "retryable": self.retryable}


def _mcp_url() -> str:
    return os.getenv("MCP_URL", "http://127.0.0.1:8001/mcp")


@asynccontextmanager
async def _open_session():
    """Open a fresh SDK transport with the configured request timeout."""
    timeout = float(os.getenv("MCP_TIMEOUT_SECONDS", "20"))
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        async with streamable_http_client(_mcp_url(), http_client=http_client) as streams:
            yield streams


async def discover_remote_tools() -> list[dict[str, Any]]:
    """Initialize Streamable HTTP and return discovered names and SDK schemas."""
    configure_telemetry(os.getenv("OTEL_SERVICE_NAME", "agent"))
    instrument_http_client()
    started = time.perf_counter()
    status = "error"
    with tracer.start_as_current_span("mcp.list_tools", record_exception=False, set_status_on_exception=False) as span:
        try:
            async with _open_session() as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    response = await session.list_tools()
                    status = "success"
                    MCP_DISCOVERIES.add(1, {"status": "success"})
                    return [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema,
                            "outputSchema": getattr(tool, "outputSchema", None),
                        }
                        for tool in response.tools
                    ]
        except Exception as exc:
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            span.set_attribute("error.type", type(exc).__name__)
            MCP_DISCOVERIES.add(1, {"status": "error"})
            MCP_ERRORS.add(1, {"tool": "discovery", "status": "error"})
            raise _connection_error(exc) from exc
        finally:
            MCP_DURATION.record((time.perf_counter() - started) * 1000, {"tool": "discovery", "status": status})


async def call_remote_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Discover, schema-check, and invoke a tool using the official MCP client."""
    configure_telemetry(os.getenv("OTEL_SERVICE_NAME", "agent"))
    instrument_http_client()
    started = time.perf_counter()
    status = "error"
    metric_tool = _safe_tool_name(name)
    with tracer.start_as_current_span("mcp.tool", attributes={"mcp.tool": metric_tool}, record_exception=False, set_status_on_exception=False) as span:
        try:
            result = await _invoke_remote_tool(name, arguments)
            status = "success"
            MCP_CALLS.add(1, {"tool": metric_tool, "status": status})
            return result
        except Exception as exc:
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            span.set_attribute("error.type", type(exc).__name__)
            MCP_ERRORS.add(1, {"tool": metric_tool, "status": status})
            MCP_CALLS.add(1, {"tool": metric_tool, "status": status})
            raise
        finally:
            MCP_DURATION.record((time.perf_counter() - started) * 1000, {"tool": metric_tool, "status": status})


async def _invoke_remote_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise MCPClientError("Tool arguments must be an object.", code="invalid_arguments", tool=name)

        timeout = float(os.getenv("MCP_TIMEOUT_SECONDS", "20"))
        attempts = max(1, int(os.getenv("MCP_MAX_RETRIES", "2")) + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                async with _open_session() as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        with tracer.start_as_current_span("mcp.list_tools", record_exception=False, set_status_on_exception=False) as discovery_span:
                            try:
                                discovery = await session.list_tools()
                                MCP_DISCOVERIES.add(1, {"status": "success"})
                            except Exception as exc:
                                discovery_span.set_status(trace.Status(trace.StatusCode.ERROR))
                                discovery_span.set_attribute("error.type", type(exc).__name__)
                                MCP_DISCOVERIES.add(1, {"status": "error"})
                                MCP_ERRORS.add(1, {"tool": "discovery", "status": "error"})
                                raise
                        tool = next((item for item in discovery.tools if item.name == name), None)
                        if tool is None:
                            raise MCPClientError(
                                f"MCP server does not provide tool '{name}'.", code="tool_not_found", tool=name
                            )
                        schema = tool.inputSchema or {}
                        required = schema.get("required", [])
                        missing = [field for field in required if field not in arguments]
                        if missing:
                            raise MCPClientError(
                                f"Missing required arguments for '{name}': {', '.join(missing)}.",
                                code="invalid_arguments", tool=name,
                            )

                        try:
                            with tracer.start_as_current_span("mcp.tool.invoke", attributes={"mcp.tool": _safe_tool_name(name)}, record_exception=False, set_status_on_exception=False):
                                result = await session.call_tool(name, arguments=arguments)
                        except Exception as exc:
                            connection_error = _connection_error(exc)
                            if connection_error.retryable:
                                raise connection_error from exc
                            raise MCPClientError(
                                f"MCP tool '{name}' failed: {exc}", code="tool_execution_failed", tool=name
                            ) from exc
                        if result.isError:
                            detail = "; ".join(
                                getattr(item, "text", "MCP tool execution failed") for item in result.content
                            )
                            raise MCPClientError(detail, code="tool_execution_failed", tool=name)

                        structured = getattr(result, "structuredContent", None)
                        if isinstance(structured, dict):
                            return structured
                        for item in result.content:
                            text = getattr(item, "text", None)
                            if not text:
                                continue
                            try:
                                decoded = json.loads(text)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(decoded, dict):
                                return decoded
                        raise MCPClientError(
                            f"MCP tool '{name}' returned no valid JSON object.",
                            code="malformed_response", tool=name,
                        )
            except MCPClientError:
                raise
            except Exception as exc:
                last_error = exc
                error = _connection_error(exc)
                if not error.retryable or attempt + 1 >= attempts:
                    raise error from exc
                await asyncio.sleep(0.2 * (attempt + 1))

        raise _connection_error(last_error or RuntimeError("MCP call did not complete"))


def _connection_error(exc: Exception) -> MCPClientError:
    nested = getattr(exc, "exceptions", None)
    if nested:
        for inner in nested:
            if isinstance(inner, MCPClientError):
                return inner
            classified = _connection_error(inner)
            if classified.code != "protocol_error":
                return classified
    text = str(exc)
    lowered = text.lower()
    if "error executing tool" in lowered:
        return MCPClientError(text, code="tool_execution_failed")
    if isinstance(exc, httpx.TimeoutException):
        return MCPClientError("MCP server request timed out.", code="timeout", retryable=True)
    if isinstance(exc, httpx.ConnectError):
        return MCPClientError("MCP server connection failed.", code="connection_failed", retryable=True)
    if "timeout" in lowered or isinstance(exc, TimeoutError):
        return MCPClientError("MCP server request timed out.", code="timeout", retryable=True)
    if any(term in lowered for term in ("connect", "refused", "network", "unavailable", "closedresource")):
        return MCPClientError("MCP server connection failed.", code="connection_failed", retryable=True)
    return MCPClientError("MCP protocol request failed.", code="protocol_error")
