"""Regression lock for existing provider behaviour.

Existing users depend on these defaults and meanings. Adding a provider
must never change any of them — if one of these tests fails, a change
has broken backward compatibility.
"""

import json
from pathlib import Path

import pytest

from selenium_agent.utils import config_manager
from selenium_agent.utils.llm import (
    API_KEY_ENV_VARS,
    DEFAULT_MODELS,
    DEFAULT_PROVIDER,
    AnthropicLLMClient,
    OpenAILLMClient,
    create_llm_client,
    infer_provider_for_model,
    normalize_provider,
    resolve_api_key,
)


# ── defaults ───────────────────────────────────────────────────────────


def test_default_provider_is_anthropic():
    assert DEFAULT_PROVIDER == "anthropic"
    assert normalize_provider(None) == "anthropic"
    assert config_manager.DEFAULTS["provider"] == "anthropic"


def test_existing_default_models_unchanged():
    assert DEFAULT_MODELS["anthropic"] == "claude-sonnet-5"
    assert DEFAULT_MODELS["openai"] == "gpt-5-mini"


def test_existing_api_key_env_vars_unchanged():
    assert API_KEY_ENV_VARS["anthropic"] == "ANTHROPIC_API_KEY"
    assert API_KEY_ENV_VARS["openai"] == "OPENAI_API_KEY"


def test_explicit_api_key_wins_over_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert resolve_api_key("anthropic", "explicit") == "explicit"
    assert resolve_api_key("anthropic") == "from-env"


# ── model → provider inference ─────────────────────────────────────────


@pytest.mark.parametrize("model", ["gpt-5", "gpt-4o-mini", "o1-preview", "o3-mini",
                                   "o4-mini", "chatgpt-4o-latest", "GPT-5"])
def test_openai_model_names_infer_openai(model):
    assert infer_provider_for_model(model) == "openai"


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-5-5", "Claude-3"])
def test_claude_model_names_infer_anthropic(model):
    assert infer_provider_for_model(model) == "anthropic"


@pytest.mark.parametrize("model", [None, "", "llama3", "mistral-large", "my-custom-model"])
def test_unknown_model_names_infer_nothing(model):
    assert infer_provider_for_model(model) is None


# ── provider names ─────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [("anthropic", "anthropic"), ("OpenAI", "openai"),
                                          ("  ANTHROPIC ", "anthropic")])
def test_existing_provider_names_normalize(raw, expected):
    assert normalize_provider(raw) == expected


def test_unknown_provider_still_rejected():
    with pytest.raises(ValueError):
        normalize_provider("not-a-provider")


# ── client construction ────────────────────────────────────────────────


def test_create_client_returns_existing_classes():
    assert isinstance(create_llm_client("anthropic", "k"), AnthropicLLMClient)
    assert isinstance(create_llm_client("openai", "k"), OpenAILLMClient)
    assert create_llm_client("anthropic", "k").model == "claude-sonnet-5"
    assert create_llm_client("openai", "k").model == "gpt-5-mini"
    assert create_llm_client("openai", "k", model="gpt-4o-mini").model == "gpt-4o-mini"


def test_sdk_base_url_env_vars_are_honoured(monkeypatch: pytest.MonkeyPatch):
    """Gateway / Azure users point the SDKs at their endpoint with the SDKs'
    own env vars — no framework flag involved. Must keep working."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example.com/v1")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.example.com")
    openai_client = create_llm_client("openai", "k")
    anthropic_client = create_llm_client("anthropic", "k")
    assert str(openai_client.client.base_url).startswith("https://gateway.example.com/v1")
    assert str(anthropic_client.client.base_url).startswith("https://gateway.example.com")


# ── config meaning ─────────────────────────────────────────────────────


def test_config_base_url_means_the_website_under_test(tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch):
    """`config --base-url` stores the WEBSITE url under 'base_url'. Existing
    .selenium-agent.json files rely on this key and meaning."""
    monkeypatch.chdir(tmp_path)
    from selenium_agent.cli import _handle_config

    _handle_config(["--base-url", "https://www.saucedemo.com"])

    saved = json.loads((tmp_path / ".selenium-agent.json").read_text())
    assert saved["base_url"] == "https://www.saucedemo.com"
    assert saved["provider"] == "anthropic"


def test_old_config_files_still_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".selenium-agent.json").write_text(json.dumps({
        "provider": "openai", "model": "gpt-4o-mini", "headless": True,
        "mode": "bdd", "base_url": "https://example.com",
    }))
    cfg = config_manager.load()
    assert cfg["provider"] == "openai"
    assert cfg["model"] == "gpt-4o-mini"
    assert cfg["base_url"] == "https://example.com"
    assert cfg["mode"] == "bdd"
