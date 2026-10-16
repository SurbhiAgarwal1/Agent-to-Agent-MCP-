"""Provider contract and safety tests; Gemini requests are always faked here."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agents.coordinator_agent import CoordinatorAgent
from app.llm.reasoners import (
    GeminiConfigurationError,
    GeminiProviderError,
    GeminiReasoner,
    MockReasoner,
    create_reasoner,
)
from app.llm.schemas import BloodRequestPlan


def test_mock_reasoner_normal_request_returns_shared_structured_plan():
    output = MockReasoner().generate_plan("Need 2 units of O+ in Bengaluru")
    plan = BloodRequestPlan.model_validate(output.plan)
    assert plan.blood_group == "O+"
    assert plan.units_required == 2
    assert plan.location == "Bengaluru"
    assert plan.urgency.value == "MEDIUM"
    assert output.provider == "mock"
    assert output.usage == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "is_mock": True}


def test_mock_reasoner_normalizes_urgent_request():
    plan = BloodRequestPlan.model_validate(
        MockReasoner().generate_plan("Urgently need 1 unit of a+ at General Hospital").plan
    )
    assert plan.blood_group == "A+"
    assert plan.urgency.value == "HIGH"
    assert plan.location == "General Hospital"


@pytest.mark.parametrize("text,missing", [
    ("Need blood urgently at General Hospital", "blood_group"),
    ("Need O+ urgently at General Hospital", "units_required"),
    ("Need 2 units O+ urgently", "location"),
])
def test_mock_reasoner_preserves_missing_required_information(text, missing):
    plan = BloodRequestPlan.model_validate(MockReasoner().generate_plan(text).plan)
    assert getattr(plan, missing) is None


@pytest.mark.parametrize("scenario", ["invalid_capability", "malformed_plan", "missing_required_field"])
def test_coordinator_rejects_untrusted_or_incomplete_plans(scenario):
    with pytest.raises((ValidationError, ValueError)):
        CoordinatorAgent(reasoner=MockReasoner(scenario=scenario)).generate_plan(
            "Need 2 units O+ in General Hospital"
        )


def test_unknown_plan_fields_are_rejected():
    raw = MockReasoner().generate_plan("Need 2 units O+ in General Hospital").plan
    raw["mcp_url"] = "http://attacker.invalid"
    with pytest.raises(ValidationError):
        BloodRequestPlan.model_validate(raw)


def test_mock_is_default_and_does_not_depend_on_gemini_key(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder-that-mock-must-ignore")
    assert isinstance(create_reasoner(), MockReasoner)
    first = MockReasoner().generate_plan("Need 1 unit O+ at General Hospital")
    second = MockReasoner().generate_plan("Need 1 unit O+ at General Hospital")
    assert first == second
    assert first.provider == "mock"
    assert "placeholder-that-mock-must-ignore" not in str(first.model_dump())


def test_gemini_can_be_configured_without_making_a_request(monkeypatch):
    from google import genai

    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(genai, "Client", fake_client)
    provider = GeminiReasoner(api_key="placeholder-only", model="test-model")
    assert provider.model == "test-model"
    assert provider.max_retries >= 0
    assert provider._client_for_request() is not None
    assert captured["api_key"] == "placeholder-only"
    assert captured["http_options"].timeout == 20_000
    assert captured["http_options"].retry_options.attempts == 1


def test_selecting_gemini_without_a_key_does_not_fail_provider_creation(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert isinstance(create_reasoner(), GeminiReasoner)


def test_missing_gemini_key_is_a_call_time_configuration_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    provider = GeminiReasoner(api_key="")
    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY"):
        provider.generate_plan("Need O+ blood")


class FakeGeminiClient:
    def __init__(self, response=None, errors=()):
        self.response = response
        self.errors = list(errors)
        self.calls = 0
        self.models = self

    def generate_content(self, **kwargs):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        assert kwargs["config"].response_mime_type == "application/json"
        return self.response


def _fake_response(plan):
    return SimpleNamespace(
        parsed=plan,
        text=None,
        model_version="fake-gemini-model",
        usage_metadata=SimpleNamespace(
            prompt_token_count=17, candidates_token_count=8, total_token_count=25
        ),
    )


def test_gemini_uses_fake_client_and_reports_provider_usage_without_network():
    raw = MockReasoner().generate_plan("Need 2 units O+ in General Hospital").plan
    fake = FakeGeminiClient(_fake_response(raw))
    result = GeminiReasoner(api_key="fake-test-key", client=fake, max_retries=0).generate_plan(
        "Need 2 units O+ in General Hospital"
    )
    assert fake.calls == 1
    assert result.provider == "gemini"
    assert result.usage == {"input_tokens": 17, "output_tokens": 8, "total_tokens": 25, "is_mock": False}


def test_gemini_provider_errors_are_sanitized_and_retried_when_rate_limited():
    class RateLimitError(RuntimeError):
        status_code = 429

    raw = MockReasoner().generate_plan("Need 2 units O+ in General Hospital").plan
    fake = FakeGeminiClient(_fake_response(raw), errors=[RateLimitError("secret-key-content")])
    provider = GeminiReasoner(
        api_key="secret-key-content", client=fake, max_retries=1, sleep=lambda _delay: None
    )
    result = provider.generate_plan("Need 2 units O+ in General Hospital")
    assert fake.calls == 2
    assert result.provider == "gemini"

    bad_key = FakeGeminiClient(errors=[type("AuthError", (RuntimeError,), {"status_code": 401})("secret")])
    with pytest.raises(GeminiProviderError) as error:
        GeminiReasoner(api_key="do-not-print-this", client=bad_key, max_retries=3).generate_plan("request")
    assert "do-not-print-this" not in str(error.value)
    assert bad_key.calls == 1


def test_explicit_gemini_fallback_to_mock_is_reported(monkeypatch):
    class FailingReasoner(GeminiReasoner):
        def generate_plan(self, user_request):
            raise GeminiProviderError("provider unavailable")

    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "mock")
    coordinator = CoordinatorAgent(reasoner=FailingReasoner(api_key="placeholder", client=object()))
    _, metadata = coordinator.generate_plan("Need 2 units O+ in General Hospital")
    assert metadata["provider"] == "mock"
    assert metadata["fallback_used"] is True

