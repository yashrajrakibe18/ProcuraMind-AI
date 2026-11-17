"""LLM provider adapters. ``none`` runs fully offline; callers must always have a deterministic fallback.

Bounded retries and timeouts apply to every call. Prompts/responses are never logged (confidential data).
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

import httpx

from procureai.config.settings import Settings, get_settings
from procureai.shared.errors import ExternalServiceError

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    name: str
    model: str

    def available(self) -> bool: ...

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str: ...


class NullLLM:
    name = "none"
    model = ""

    def available(self) -> bool:
        return False

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        raise ExternalServiceError("No LLM provider is configured.")


class HttpLLM:
    """Anthropic Messages API or an OpenAI-compatible chat-completions endpoint."""

    def __init__(self, settings: Settings) -> None:
        self.name = settings.llm_provider.lower()
        self.model = settings.llm_model
        self._key = settings.llm_api_key
        self._timeout = settings.llm_timeout_seconds
        self._retries = max(0, settings.llm_max_retries)
        if self.name == "anthropic":
            self._url = (settings.llm_base_url or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        else:
            self._url = (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"

    def available(self) -> bool:
        return bool(self._key and self.model)

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        if not self.available():
            raise ExternalServiceError("LLM provider is not fully configured.")
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.post(self._url, headers=self._headers(), json=self._payload(system, user, max_tokens))
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                resp.raise_for_status()
                return self._extract(resp.json())
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last = exc
                logger.warning("LLM call failed (attempt %s): %s", attempt + 1, type(exc).__name__)
                if attempt < self._retries:
                    time.sleep(min(2**attempt, 4))
        raise ExternalServiceError("The language model service is unavailable.") from last

    def _headers(self) -> dict[str, str]:
        if self.name == "anthropic":
            return {"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        return {"Authorization": f"Bearer {self._key}", "content-type": "application/json"}

    def _payload(self, system: str, user: str, max_tokens: int) -> dict:
        if self.name == "anthropic":
            return {
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "temperature": 0,
            }
        return {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }

    def _extract(self, data: dict) -> str:
        try:
            if self.name == "anthropic":
                return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ExternalServiceError("Unexpected response from the language model service.") from exc


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    if settings.llm_provider.lower() in ("anthropic", "openai"):
        client = HttpLLM(settings)
        return client if client.available() else NullLLM()
    return NullLLM()
