"""OpenTelemetry metric instruments shared by the application services."""

from app.observability.tracing import (
    A2A_DURATION, A2A_ERRORS, A2A_REQUESTS, AGENT_DURATION, AGENT_ERRORS,
    AGENT_REQUESTS, HTTP_DURATION, HTTP_ERRORS, HTTP_REQUESTS,
    LLM_DURATION, LLM_ERRORS, LLM_INPUT_TOKENS, LLM_OUTPUT_TOKENS,
    LLM_REQUESTS, LLM_TOTAL_TOKENS, MCP_CALLS, MCP_DISCOVERIES,
    MCP_DURATION, MCP_ERRORS, WORKFLOWS, WORKFLOW_DURATION, WORKFLOW_ERRORS,
)

__all__ = [name for name in globals() if name.isupper()]
