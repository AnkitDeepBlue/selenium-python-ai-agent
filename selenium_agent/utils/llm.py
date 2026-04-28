"""
LLM provider helpers for Anthropic and OpenAI.
"""

import os
from importlib import import_module


DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-5-mini",
}
API_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def normalize_provider(provider: str | None) -> str:
    normalized = (provider or DEFAULT_PROVIDER).strip().lower()
    if normalized not in API_KEY_ENV_VARS:
        supported = ", ".join(sorted(API_KEY_ENV_VARS))
        raise ValueError(f"Unsupported provider '{provider}'. Supported providers: {supported}")
    return normalized


def get_default_model(provider: str) -> str:
    normalized = normalize_provider(provider)
    return DEFAULT_MODELS[normalized]


def get_api_key_env_var(provider: str) -> str:
    normalized = normalize_provider(provider)
    return API_KEY_ENV_VARS[normalized]


def format_missing_api_key_error(provider: str) -> str:
    normalized = normalize_provider(provider)
    env_var = get_api_key_env_var(normalized)
    provider_name = "Anthropic Claude" if normalized == "anthropic" else "OpenAI"
    return (
        f"{provider_name} API key required!\n"
        f"Pass it as: SeleniumAgent(provider='{normalized}', api_key='your-key')\n"
        f"Or set env var: export {env_var}='your-key'\n"
        f"Get your key at: https://console.anthropic.com"
    )


def resolve_api_key(provider: str, api_key: str | None = None) -> str | None:
    normalized = normalize_provider(provider)
    if api_key:
        return api_key
    env_var = get_api_key_env_var(normalized)
    return os.environ.get(env_var)


class BaseLLMClient:
    """Minimal interface shared by all provider implementations."""

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        raise NotImplementedError


class AnthropicLLMClient(BaseLLMClient):
    """Anthropic Claude-backed text generation client."""

    def __init__(self, api_key: str, model: str):
        try:
            anthropic = import_module("anthropic")
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "The 'anthropic' package is required for provider='anthropic'. "
                "Install it with: pip install anthropic"
            ) from exc
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        parts = []
        for content_block in message.content:
            text = getattr(content_block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()


class OpenAILLMClient(BaseLLMClient):
    """OpenAI-backed text generation client."""

    def __init__(self, api_key: str, model: str):
        try:
            openai = import_module("openai")
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "The 'openai' package is required for provider='openai'. "
                "Install it with: pip install openai"
            ) from exc
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = self.client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=user_prompt,
            max_output_tokens=max_tokens,
        )
        return (response.output_text or "").strip()


def create_llm_client(
    provider: str,
    api_key: str,
    model: str | None = None,
) -> BaseLLMClient:
    """Create a provider-specific LLM client."""
    normalized = normalize_provider(provider)
    resolved_model = model or get_default_model(normalized)

    if normalized == "anthropic":
        return AnthropicLLMClient(api_key=api_key, model=resolved_model)
    if normalized == "openai":
        return OpenAILLMClient(api_key=api_key, model=resolved_model)

    raise ValueError(f"Unsupported provider '{provider}'")
