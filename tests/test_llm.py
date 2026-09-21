import json

import httpx
import pytest

from app.config import Settings
from app.llm import LLMClient, LLMError

SETTINGS = Settings(llm_api_key="sk-secret", llm_base_url="https://proxy.example/v1", llm_model="m1")


def _ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _client(handler, settings=SETTINGS) -> LLMClient:
    return LLMClient(settings, transport=httpx.MockTransport(handler))


def test_posts_chat_completion_to_base_url_with_bearer_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _ok('{"a": 1}')

    answer = _client(handler).complete("системный", "пользовательский")

    assert answer == '{"a": 1}'
    assert seen["url"] == "https://proxy.example/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-secret"
    assert seen["body"]["model"] == "m1"
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "системный"},
        {"role": "user", "content": "пользовательский"},
    ]
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_does_not_send_sampling_params_unsupported_by_reasoning_models():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return _ok("{}")

    _client(handler).complete("s", "u")
    assert "temperature" not in bodies[0]
    assert "max_tokens" not in bodies[0]


def test_reasoning_effort_is_sent_only_when_configured():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return _ok("{}")

    _client(handler).complete("s", "u")
    configured = Settings(llm_api_key="k", llm_reasoning_effort="low")
    _client(handler, configured).complete("s", "u")
    assert "reasoning_effort" not in bodies[0]
    assert bodies[1]["reasoning_effort"] == "low"


def test_on_400_retries_once_without_optional_params():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format unsupported"}})
        return _ok('{"ok": true}')

    assert _client(handler).complete("s", "u") == '{"ok": true}'
    assert len(bodies) == 2
    assert set(bodies[1]) == {"model", "messages"}


def test_http_error_raises_llm_error_with_status_and_without_key():
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(LLMError) as exc:
        _client(handler).complete("s", "u")
    assert "401" in str(exc.value)
    assert "sk-secret" not in str(exc.value)


def test_network_failure_raises_llm_error():
    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(LLMError):
        _client(handler).complete("s", "u")


def test_unexpected_response_shape_raises_llm_error():
    def handler(request):
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(LLMError):
        _client(handler).complete("s", "u")
