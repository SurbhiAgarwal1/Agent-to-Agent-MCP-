"""Interchangeable deterministic and Gemini-backed request planners for Blood & Medicine delivery."""

from abc import ABC, abstractmethod
import json
import logging
import os
import re
import time
from typing import Any

from app.llm.schemas import ALLOWED_CAPABILITIES, ReasoningResult

logger = logging.getLogger("app.llm.reasoners")


class ReasonerError(RuntimeError):
    """Base exception for reasoner failures."""


class GeminiConfigurationError(ReasonerError):
    """Raised when the Gemini provider cannot be initialized from the environment."""


class GeminiProviderError(ReasonerError):
    """Raised when Gemini returns an error status or invalid output."""


class LLMReasoner(ABC):
    """Provider contract shared by MockReasoner and GeminiReasoner."""

    @abstractmethod
    def generate_plan(self, user_request: str) -> ReasoningResult:
        """Return structured application data without executing tools or agents."""


class MockReasoner(LLMReasoner):
    """Deterministic, local-only planner. Handles both blood requests and medicine delivery."""

    def __init__(self, *, scenario: str = "normal") -> None:
        self.scenario = scenario

    def generate_plan(self, user_request: str) -> ReasoningResult:
        text = user_request or ""
        blood_match = re.search(r"\b(AB|A|B|O)\s*([+-])(?!\w)", text, re.IGNORECASE)
        units_match = re.search(r"\b(\d+)\s*(?:units?|bags?|pints?|packs?)\b", text, re.IGNORECASE)
        location_match = re.search(
            r"\b(?:at|in|near|to)\s+([A-Za-z][A-Za-z0-9 .'-]*?)"
            r"(?:\s+(hospital|clinic|medical center|center|pharmacy)\b|[,;.!?]|$)",
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

        # Location extraction: recognize preposition patterns or direct mentions of premier hospitals
        known_hospitals = [
            "AIIMS Apex Trauma Center & Hospital", "AIIMS Apex Trauma Center", "AIIMS Trauma Center", "AIIMS",
            "Safdarjung Emergency Trauma Hospital", "Safdarjung Hospital", "Safdarjung",
            "Indraprastha Apollo Super Speciality Hospital", "Indraprastha Apollo Hospital", "Apollo Hospital", "Apollo",
            "Max Super Speciality Hospital & Trauma Care", "Max Super Speciality Hospital", "Max Hospital", "Max Saket",
            "Sir Ganga Ram Multi-Speciality Hospital", "Sir Ganga Ram Hospital", "Ganga Ram",
            "Fortis Memorial Critical Care & Research Institute", "Fortis Memorial", "Fortis Hospital", "Fortis",
            "Medanta - The Medicity Multi-Organ Transplant Hospital", "Medanta - The Medicity", "Medanta The Medicity", "Medanta",
            "BLK-Max Super Speciality Hospital", "BLK-Max Hospital", "BLK Hospital",
            "Holy Family Emergency & Critical Care Hospital", "Holy Family Hospital", "Holy Family",
            "Dr. Ram Manohar Lohia (RML) Hospital & PGIMER", "Ram Manohar Lohia Hospital", "RML Hospital", "RML",
        ]

        location = None
        for hosp in known_hospitals:
            if re.search(rf"\b{re.escape(hosp)}\b", text, re.IGNORECASE):
                location = hosp
                break

        if not location and location_match:
            location = " ".join(part for part in location_match.groups() if part).strip()

        # Extract medicines (e.g. "2 strips of Dolo 650", "Augmentin", "Paracetamol")
        known_meds = [
            "Dolo 650", "Calpol 650", "Augmentin 625 Duo", "Augmentin", "Moxikind-CV 625",
            "Azithral 500", "Azithromycin", "Pan 40", "Pantocid 40", "Paracetamol"
        ]
        medicines_list = []
        for med in known_meds:
            med_pattern = re.compile(rf"(?:(\d+)\s*(?:strips?|tablets?|boxes?|bottles?|packs?)?\s*(?:of\s*)?)?\b{re.escape(med)}\b", re.IGNORECASE)
            m = med_pattern.search(text)
            if m:
                qty_str = m.group(1)
                qty = int(qty_str) if qty_str else 1
                medicines_list.append({
                    "name": med,
                    "quantity": qty,
                    "allow_substitute": True,
                })

        blood_group = (
            blood_match.group(1).upper() + blood_match.group(2)
            if blood_match else None
        )
        units_req = int(units_match.group(1)) if units_match else None
        component_type = "whole_blood" if re.search(r"\bwhole\s+blood\b", text, re.IGNORECASE) else "packed_red_blood_cells"

        req_type = "blood"
        if medicines_list and blood_group:
            req_type = "combined"
        elif medicines_list:
            req_type = "medicine"

        plan: dict[str, Any] = {
            "request_type": req_type,
            "blood_group": blood_group,
            "units_required": units_req,
            "component_type": component_type,
            "medicines": medicines_list,
            "location": location,
            "urgency": urgency,
            "required_capabilities": list(ALLOWED_CAPABILITIES),
        }

        # Deterministic negative cases exercise Coordinator validation
        if self.scenario == "invalid_capability":
            plan["required_capabilities"] = [*ALLOWED_CAPABILITIES, "execute_shell"]
        elif self.scenario == "malformed_plan":
            plan = {"unexpected": "malformed plan"}
        elif self.scenario == "missing_required_field":
            plan.pop("required_capabilities")
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
            "Convert this emergency healthcare / blood / medicine delivery request into JSON according to the schema. "
            "Extract request_type ('blood', 'medicine', or 'combined'). "
            "Extract blood_group (null if none), units_required (null if none), "
            "medicines list ([{name, quantity, allow_substitute}]), and location (hospital or delivery address). "
            "Do not provide reasoning text. Normalize urgency to LOW, MEDIUM, HIGH, or CRITICAL. "
            f"Set required_capabilities to {json.dumps(ALLOWED_CAPABILITIES)}. Never emit URLs, tools, functions, or code.\n\n"
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
                        temperature=0.0,
                    ),
                )
                raw_text = response.text or ""
                if raw_text.strip():
                    try:
                        plan = json.loads(raw_text)
                    except json.JSONDecodeError as exc:
                        raise GeminiProviderError("Gemini returned malformed JSON.") from exc
                else:
                    plan = getattr(response, "parsed", None)
                    if not isinstance(plan, dict):
                        raise GeminiProviderError("Gemini returned no structured plan.")

                usage_meta = getattr(response, "usage_metadata", None)
                usage = {
                    "input_tokens": getattr(usage_meta, "prompt_token_count", None),
                    "output_tokens": getattr(usage_meta, "candidates_token_count", None),
                    "total_tokens": getattr(usage_meta, "total_token_count", None),
                    "is_mock": False,
                }
                return ReasoningResult(
                    plan=plan,
                    provider="gemini",
                    model=self.model,
                    usage=usage,
                )
            except GeminiProviderError:
                raise
            except Exception as exc:
                last_error = exc
                error_status = getattr(exc, "status_code", getattr(exc, "code", None))
                if attempt < self.max_retries and error_status not in {400, 401, 403, 404, 422}:
                    self._sleep(0.5 * (2**attempt))
                    continue
                if error_status in {400, 401, 403, 404, 422}:
                    break

        category = "timeout" if "timeout" in str(last_error).lower() else "call failed"
        status = getattr(last_error, "status_code", getattr(last_error, "code", "network"))
        raise GeminiProviderError(f"Gemini provider {category} (HTTP {status}).") from last_error


def create_reasoner(provider: str | None = None) -> LLMReasoner:
    """Instantiate the active reasoner from parameter or environment."""
    selected = (provider or os.getenv("LLM_PROVIDER", "mock")).strip().lower()
    if selected in {"mock", "dummy"}:
        return MockReasoner()
    if selected == "gemini":
        return GeminiReasoner()
    raise ValueError(f"Unsupported LLM_PROVIDER '{selected}'. Choose 'mock' or 'gemini'.")
