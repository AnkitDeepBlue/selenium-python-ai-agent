"""Unit tests for the Google Gemini provider (no network calls)."""

from types import SimpleNamespace

import pytest

from selenium_agent.utils import llm
from selenium_agent.utils.llm import (
    GeminiAPIError,
    _is_retryable,
    format_missing_api_key_error,
    get_api_key_env_var,
    get_default_model,
    infer_provider_for_model,
    normalize_provider,
    resolve_api_key,
)


# ── provider helpers (no SDK needed) ───────────────────────────────────


def test_gemini_provider_registered():
    assert normalize_provider("Gemini") == "gemini"
    assert get_default_model("gemini") == "gemini-3.8-flash"
    assert get_api_key_env_var("gemini") == "GEMINI_API_KEY"


@pytest.mark.parametrize("model", ["gemini-3.8-flash", "gemini-2.5-pro", "Gemini-3.5-flash-lite"])
def test_gemini_model_names_infer_gemini(model):
    assert infer_provider_for_model(model) == "gemini"


def test_gemini_key_resolution_with_google_api_key_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert resolve_api_key("gemini") is None

    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    assert resolve_api_key("gemini") == "google-key"

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    assert resolve_api_key("gemini") == "gemini-key"
    assert resolve_api_key("gemini", "explicit") == "explicit"


def test_google_api_key_fallback_is_gemini_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    assert resolve_api_key("openai") is None


def test_missing_key_messages_point_to_the_right_console():
    gemini = format_missing_api_key_error("gemini")
    assert "Google Gemini API key required!" in gemini
    assert "GEMINI_API_KEY" in gemini
    assert "aistudio.google.com" in gemini

    openai = format_missing_api_key_error("openai")
    assert "OpenAI API key required!" in openai
    assert "platform.openai.com" in openai
    assert "anthropic" not in openai.lower()

    assert "console.anthropic.com" in format_missing_api_key_error("anthropic")


def test_retry_policy_for_gemini_errors():
    assert _is_retryable(GeminiAPIError("rate limited", 429))
    assert _is_retryable(GeminiAPIError("server", 503))
    assert not _is_retryable(GeminiAPIError("bad key", 401))
    assert not _is_retryable(GeminiAPIError("bad request", 400))


def test_missing_sdk_gives_install_hint(monkeypatch: pytest.MonkeyPatch):
    real_import = llm.import_module

    def fake_import(name):
        if name.startswith("google"):
            raise ModuleNotFoundError(name)
        return real_import(name)

    monkeypatch.setattr(llm, "import_module", fake_import)
    with pytest.raises(ModuleNotFoundError, match=r"selenium-python-ai-agent\[gemini\]"):
        llm.create_llm_client("gemini", "k")


# ── client behaviour (needs the optional google-genai SDK) ─────────────


@pytest.fixture
def genai_sdk():
    return pytest.importorskip("google.genai")


class FakeModels:
    """Records every generate_content call; replays scripted results."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents,
                           "config": config.model_copy(deep=True)})
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def response(text, finish_reason="STOP"):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish_reason)])


def api_error(code):
    from google.genai import errors as genai_errors
    return genai_errors.ClientError(code, {"error": {"code": code, "message": "boom",
                                                     "status": "X"}})


def make_client(model, results):
    client = llm.create_llm_client("gemini", "test-key", model=model)
    fake = FakeModels(results)
    client.client = SimpleNamespace(models=fake)
    return client, fake


def test_create_client_uses_default_model(genai_sdk):
    client = llm.create_llm_client("gemini", "test-key")
    assert isinstance(client, llm.GeminiLLMClient)
    assert client.model == "gemini-3.8-flash"


def test_request_shape_for_thinking_model_in_json_mode(genai_sdk):
    client, fake = make_client("gemini-3.8-flash", [response('{"a": 1}')])

    text = client.generate_text("SYSTEM", "USER", max_tokens=3000, json_mode=True)

    assert text == '{"a": 1}'
    call = fake.calls[0]
    assert call["model"] == "gemini-3.8-flash"
    assert call["contents"] == "USER"
    cfg = call["config"]
    assert cfg.system_instruction == "SYSTEM"
    assert cfg.response_mime_type == "application/json"
    assert cfg.max_output_tokens == 6000           # headroom for thought tokens
    assert str(cfg.thinking_config.thinking_level.value).upper() == "LOW"


def test_non_thinking_model_keeps_exact_cap_and_plain_text(genai_sdk):
    client, fake = make_client("gemini-2.5-flash", [response("hello")])

    assert client.generate_text("S", "U", max_tokens=1234) == "hello"
    cfg = fake.calls[0]["config"]
    assert cfg.max_output_tokens == 1234
    assert cfg.thinking_config is None
    assert cfg.response_mime_type is None


def test_rejected_thinking_level_retries_without_it(genai_sdk):
    client, fake = make_client("gemini-3.8-flash", [api_error(400), response("ok")])

    assert client.generate_text("S", "U", max_tokens=1000) == "ok"
    assert fake.calls[0]["config"].thinking_config is not None
    assert fake.calls[1]["config"].thinking_config is None


def test_auth_error_is_not_retried(genai_sdk):
    client, fake = make_client("gemini-2.5-flash", [api_error(401)])

    with pytest.raises(GeminiAPIError) as exc_info:
        client.generate_text("S", "U", max_tokens=100)
    assert exc_info.value.status_code == 401
    assert len(fake.calls) == 1


def test_rate_limit_is_retried(genai_sdk, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    client, fake = make_client("gemini-2.5-flash", [api_error(429), response("ok")])

    assert client.generate_text("S", "U", max_tokens=100) == "ok"
    assert len(fake.calls) == 2


def test_token_exhaustion_retries_with_bigger_cap(genai_sdk):
    client, fake = make_client("gemini-3.8-flash",
                               [response(None, "MAX_TOKENS"), response("done")])

    assert client.generate_text("S", "U", max_tokens=3000) == "done"
    assert fake.calls[0]["config"].max_output_tokens == 6000
    assert fake.calls[1]["config"].max_output_tokens == 12000


def test_empty_response_raises_clear_error(genai_sdk):
    client, _ = make_client("gemini-2.5-flash", [response("")])

    with pytest.raises(RuntimeError, match="empty response"):
        client.generate_text("S", "U", max_tokens=100)
