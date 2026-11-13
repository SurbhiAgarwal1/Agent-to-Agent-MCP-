"""Execution mode configuration for local development and distributed A2A deployments."""
import os


def get_execution_mode() -> str:
    configured = os.getenv("A2A_EXECUTION_MODE", "").strip().lower()
    if configured:
        if configured not in {"local", "distributed"}:
            raise ValueError("A2A_EXECUTION_MODE must be 'local' or 'distributed'")
        return configured
    legacy_enabled = any(os.getenv(key, "").strip().lower() in {"1", "true", "yes"} for key in (
        "COORDINATOR_USE_NETWORK", "COORDINATOR_USE_A2A", "COORDINATOR_REQUIRE_A2A",
    ))
    if legacy_enabled or os.getenv("COORDINATORAGENT_BASE_URL", "").strip() or os.getenv("COORDINATORAGENT_A2A_URL", "").strip():
        return "distributed"
    return "local"
