"""
LLM provider helpers for Anthropic and OpenAI.

All agents talk to the LLM through this module, which provides:
- provider normalization + API-key resolution
- automatic retries with exponential backoff on transient failures
  (rate limits, 5xx, timeouts, connection errors)
- special handling for OpenAI reasoning models (gpt-5*, o*) whose
  reasoning tokens count against max_output_tokens
"""

import os
import time
from importlib import import_module

from selenium_agent.utils.logger import setup_logger

logger = setup_logger("LLM")

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-5-mini",
}
API_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0

# Error class-name fragments that must NOT be retried — the request itself is bad.
_NON_RETRYABLE = (
    "authentication", "permissiondenied", "notfound",
    "badrequest", "invalidrequest", "unprocessable",
)


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


def _is_retryable(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    if any(fragment in name for fragment in _NON_RETRYABLE):
        return False
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    # Rate limits, overload, timeouts, connection drops → retry
    return any(f in name for f in ("ratelimit", "overloaded", "timeout", "connection",
                                   "internalserver", "apierror", "apistatus"))


class BaseLLMClient:
    """Minimal interface shared by all provider implementations."""

    model: str = ""

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int,
                      json_mode: bool = False) -> str:
        """
        Generate text with automatic retries on transient failures.

        json_mode=True engages the provider's native structured-output
        mechanism (OpenAI json_object format / Anthropic '{' prefill) so
        responses are valid JSON instead of best-effort prose.
        """
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return self._generate_once(system_prompt, user_prompt, max_tokens, json_mode)
            except Exception as exc:  # noqa: BLE001 — provider SDKs raise many types
                if not _is_retryable(exc) or attempt == MAX_RETRIES:
                    raise
                delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    f"⚠️  LLM call failed ({type(exc).__name__}) — "
                    f"retry {attempt}/{MAX_RETRIES - 1} in {delay:.0f}s"
                )
                time.sleep(delay)
                last_exc = exc
        raise last_exc  # pragma: no cover — unreachable

    def _generate_once(self, system_prompt: str, user_prompt: str, max_tokens: int,
                       json_mode: bool = False) -> str:
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

    def _generate_once(self, system_prompt: str, user_prompt: str, max_tokens: int,
                       json_mode: bool = False) -> str:
        messages = [{"role": "user", "content": user_prompt}]
        if json_mode:
            # Prefill trick: forcing the assistant to start at '{' makes
            # Claude emit pure JSON with no prose or fences.
            messages.append({"role": "assistant", "content": "{"})

        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        parts = []
        for content_block in message.content:
            text = getattr(content_block, "text", None)
            if text:
                parts.append(text)
        text = "\n".join(parts).strip()
        if json_mode and not text.startswith("{"):
            text = "{" + text
        return text


class OpenAILLMClient(BaseLLMClient):
    """OpenAI-backed text generation client (Responses API)."""

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

    def _is_reasoning_model(self) -> bool:
        m = self.model.lower()
        return m.startswith(("gpt-5", "o1", "o3", "o4"))

    def _generate_once(self, system_prompt: str, user_prompt: str, max_tokens: int,
                       json_mode: bool = False) -> str:
        params = {
            "model": self.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            # Native structured output — the model cannot emit invalid JSON.
            # The API requires the word 'json' in the input message itself.
            params["text"] = {"format": {"type": "json_object"}}
            if "json" not in user_prompt.lower():
                params["input"] = user_prompt + "\n\nRespond with a valid JSON object."
        if self._is_reasoning_model():
            # Reasoning tokens count against max_output_tokens — keep effort low
            # and leave headroom so the visible answer isn't starved.
            params["reasoning"] = {"effort": "low"}
            params["max_output_tokens"] = max(max_tokens * 2, 4000)

        try:
            response = self.client.responses.create(**params)
        except TypeError:
            # Older SDK without `reasoning`/`text` support
            params.pop("reasoning", None)
            params.pop("text", None)
            response = self.client.responses.create(**params)

        text = (response.output_text or "").strip()
        if not text and getattr(response, "status", "") == "incomplete":
            # Reasoning consumed the entire budget — one retry with a bigger cap
            params["max_output_tokens"] = params["max_output_tokens"] * 2
            response = self.client.responses.create(**params)
            text = (response.output_text or "").strip()

        if not text:
            raise RuntimeError(
                f"OpenAI model '{self.model}' returned an empty response "
                f"(status={getattr(response, 'status', 'unknown')}). "
                f"Try a larger max_tokens or a non-reasoning model like gpt-4o-mini."
            )
        return text


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
