"""Interchangeable deterministic and Gemini-backed request planners."""

from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from app.llm.schemas import ALLOWED_CAPABILITIES, BloodRequestPlan, ReasoningResult


class ReasonerError(RuntimeError):
    """Base class for safe, user-facing reasoning provider errors."""


class GeminiConfigurationError(ReasonerError):
    pass


class GeminiProviderError(ReasonerError):
    pass


class LLMReasoner(ABC):
    """Provider contract shared by MockReasoner and GeminiReasoner."""

    @abstractmethod
    def generate_plan(self, user_request: str) -> ReasoningResult:
        """Return structured application data without executing tools or agents."""


class MockReasoner(LLMReasoner):
    """Deterministic, local-only planner. It never reads credentials or opens sockets."""

    def __init__(self, *, scenario: str = "normal") -> None:
        self.scenario = scenario

    def generate_plan(self, user_request: str) -> ReasoningResult:
        text = user_request or ""
        blood_match = re.search(r"\b(AB|A|B|O)\s*([+-])(?!\w)", text, re.IGNORECASE)
        units_match = re.search(r"\b(\d+)\s*(?:units?|bags?|pints?|packs?)\b", text, re.IGNORECASE)
        location_match = re.search(
            r"\b(?:at|in|near)\s+([A-Za-z][A-Za-z0-9 .'-]*?)"
            r"(?:\s+(hospital|clinic|medical center|center)\b|[,;.!?]|$)",
            text,
            re.IGNORECASE,
        )
        urgency = "MEDIUM"
        if re.search(r"\b(critical|stat|code blue|immediately)\b", text, re.IGNORECASE):
            urgency = "CRITICAL"
        elif re.search(r"\b(urgent|urgently|emergency|asap|rush)\b", text, re.IGNORECASE):
            urgency = "HIGH"
        elif re.search(r"\b(routine|low|scheduled)\b", text, re.IGNORECASE):
            urgency = "LOW"

        location = None
        if location_match:
            location = " ".join(part for part in location_match.groups() if part).strip()
        plan: dict[str, Any] = {
            "blood_group": (
                blood_match.group(1).upper() + blood_match.group(2)
                if blood_match else None
            ),
            "units_required": int(units_match.group(1)) if units_match else None,
            "location": location,
            "urgency": urgency,
            "required_capabilities": list(ALLOWED_CAPABILITIES),
        }

        # Deterministic negative cases exercise Coordinator validation, not any network.
        if self.scenario == "invalid_capability":
            plan["required_capabilities"] = [*ALLOWED_CAPABILITIES, "execute_shell"]
        elif self.scenario == "malformed_plan":
            plan = {"unexpected": "malformed plan"}
        elif self.scenario == "missing_required_field":
            plan.pop("units_required")
        elif self.scenario != "normal":
            raise ValueError(f"Unknown mock scenario: {self.scenario}")

        return ReasoningResult(
            plan=plan,
            provider="mock",
            model="deterministic-mock",
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "is_mock": True},
        )


class GeminiReasoner(LLMReasoner):
    """Gemini JSON planner using Google's maintained `google-genai` SDK."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        client: Any | None = None,
        sleep=time.sleep,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.timeout_seconds = timeout_seconds or float(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))
        self.max_retries = max(0, max_retries if max_retries is not None else int(os.getenv("GEMINI_MAX_RETRIES", "2")))
        self._client = client
        self._sleep = sleep

    def _client_for_request(self):
        if not self.api_key:
            raise GeminiConfigurationError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini.")
        if self._client is None:
            # Lazy import/client creation lets mock mode start without Gemini credentials.
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=int(self.timeout_seconds * 1000),
                    retry_options=types.HttpRetryOptions(
                        attempts=1,
                        initial_delay=0,
                        max_delay=0,
                        jitter=0,
                    ),
                ),
            )
        return self._client

    def generate_plan(self, user_request: str) -> ReasoningResult:
        client = self._client_for_request()
        prompt = (
            "Convert this blood donation request into the supplied JSON schema. "
            "Do not provide reasoning text. Use null for missing blood_group, units_required, or location. "
            "Normalize urgency to LOW, MEDIUM, HIGH, or CRITICAL. Set required_capabilities to exactly "
            f"{json.dumps(ALLOWED_CAPABILITIES)}. Never emit URLs, tools, functions, endpoints, or code.\n\n"
            f"Request: {user_request}"
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                from google.genai import types

                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=BloodRequestPlan,
                        temperature=0,
                    ),
                )
                parsed = getattr(response, "parsed", None)
                if isinstance(parsed, BloodRequestPlan):
                    plan = parsed.model_dump(mode="json")
                elif isinstance(parsed, dict):
                    plan = parsed
                else:
                    response_text = getattr(response, "text", None)
                    if not response_text:
                        raise GeminiProviderError("Gemini returned no structured plan.")
                    try:
                        plan = json.loads(response_text)
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise GeminiProviderError("Gemini returned malformed JSON.") from exc
                metadata = getattr(response, "usage_metadata", None)
                usage = {
                    "input_tokens": getattr(metadata, "prompt_token_count", None),
                    "output_tokens": getattr(metadata, "candidates_token_count", None),
                    "total_tokens": getattr(metadata, "total_token_count", None),
                    "is_mock": False,
                }
                return ReasoningResult(
                    plan=plan,
                    provider="gemini",
                    model=getattr(response, "model_version", None) or self.model,
                    usage=usage,
                )
            except GeminiProviderError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries or not _is_retryable_provider_error(exc):
                    break
                self._sleep(min(0.25 * (2 ** attempt), 2.0))
        status = _provider_status(last_error)
        category = "rate limited" if status == 429 else "unavailable or rejected the request"
        raise GeminiProviderError(f"Gemini provider {category} (HTTP {status}).") from last_error


def _provider_status(error: Exception | None) -> int | None:
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    return status if isinstance(status, int) else None


def _is_retryable_provider_error(error: Exception) -> bool:
    status = _provider_status(error)
    if status == 429 or (isinstance(status, int) and status >= 500):
        return True
    description = (type(error).__name__ + " " + str(error)).lower()
    return isinstance(error, (TimeoutError, ConnectionError)) or "timeout" in description or "connection" in description


def create_reasoner(provider: str | None = None) -> LLMReasoner:
    """Select the configured planner. Mock is the safe, keyless default."""
    selected = (provider or os.getenv("LLM_PROVIDER", "mock")).strip().lower()
    if selected in {"mock", "dummy"}:
        return MockReasoner()
    if selected == "gemini":
        return GeminiReasoner()
    raise ValueError(f"Unsupported LLM_PROVIDER '{selected}'. Choose 'mock' or 'gemini'.")

