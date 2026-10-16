"""Provider-reported token usage aggregation (no provider calls live here)."""

from threading import Lock
from typing import Any

TOKEN_USAGE: dict[str, int] = {
    "requests": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
}
_lock = Lock()


def record_usage(usage: dict[str, Any]) -> None:
    """Aggregate only actual Gemini metadata; mock's marked zeroes are excluded."""
    if usage.get("is_mock"):
        return
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    if not all(isinstance(value, int) and value >= 0 for value in (input_tokens, output_tokens, total_tokens)):
        return
    with _lock:
        TOKEN_USAGE["requests"] += 1
        TOKEN_USAGE["prompt_tokens"] += input_tokens
        TOKEN_USAGE["completion_tokens"] += output_tokens
        TOKEN_USAGE["total_tokens"] += total_tokens
