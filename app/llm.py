"""Клиент OpenAI-совместимого Chat Completions API (OpenAI, LiteLLM, OpenRouter и т. п.)."""

import httpx

from app.config import Settings


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.model = settings.llm_model
        self._reasoning_effort = settings.llm_reasoning_effort
        self._client = httpx.Client(
            base_url=settings.llm_base_url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout,
            transport=transport,
        )

    def complete(self, system: str, user: str) -> str:
        """Возвращает текст ответа модели. Любая неудача — LLMError."""
        required = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # temperature и max_tokens не шлём: reasoning-модели (gpt-5.x) их отвергают
        optional = {"response_format": {"type": "json_object"}}
        if self._reasoning_effort:
            optional["reasoning_effort"] = self._reasoning_effort

        response = self._post(required | optional)
        if response.status_code == 400:
            # Шлюз не знает необязательных параметров — повторяем с минимальным телом
            response = self._post(required)
        if response.status_code != 200:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:200]}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, LookupError, TypeError) as exc:
            raise LLMError(f"Неожиданный формат ответа: {response.text[:200]}") from exc
        if not isinstance(content, str):
            raise LLMError("В ответе модели нет текста")
        return content

    def _post(self, payload: dict) -> httpx.Response:
        try:
            return self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Сеть: {type(exc).__name__}: {exc}") from exc
