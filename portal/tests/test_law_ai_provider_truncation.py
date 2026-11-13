"""The OpenAI adapter must not pass token-clipped text to law validators."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app import ai_provider


def _provider():
    return SimpleNamespace(
        model_id="mock-law-model", active=True, base_url="https://example.org/v1",
        text_key_enc="enc", image_key_enc="enc",
        allow_private=False, timeout_seconds=5,
    )


def test_nonstreaming_length_finish_reason_is_an_explicit_error(monkeypatch):
    async def fake_request(*args, **kwargs):
        return {"choices": [{"message": {"content": '{"headings":['},
                              "finish_reason": "length"}]}
    monkeypatch.setattr(ai_provider, "_request", fake_request)
    with pytest.raises(ai_provider.AIOutputTruncated, match="Tokenlimit"):
        asyncio.run(ai_provider.complete(_provider(), [{"role": "user", "content": "x"}]))


def test_nonstreaming_response_is_never_silently_cut(monkeypatch):
    async def fake_request(*args, **kwargs):
        return {"choices": [{"message": {"content": "x" * 40_001},
                              "finish_reason": "stop"}]}
    monkeypatch.setattr(ai_provider, "_request", fake_request)
    with pytest.raises(ai_provider.AIOutputTruncated, match="Ausgabelimit"):
        asyncio.run(ai_provider.complete(_provider(), [{"role": "user", "content": "x"}]))


def test_streaming_length_finish_reason_is_an_explicit_error(monkeypatch):
    async def no_dns(*args, **kwargs):
        return None
    monkeypatch.setattr(ai_provider, "validate_destination", no_dns)
    monkeypatch.setattr(ai_provider, "decrypt", lambda _: "test")

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        async def handler(request):
            assert request.url.path.endswith("/chat/completions")
            stream = (
                'data: {"choices":[{"delta":{"content":"{\\"fields\\":["},'
                '"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{},'
                '"finish_reason":"length"}]}\n\n'
                'data: [DONE]\n\n'
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content=stream.encode("utf-8"))
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(ai_provider.httpx, "AsyncClient", fake_client)

    async def read():
        return [piece async for piece in ai_provider.stream_completion(
            _provider(), [{"role": "user", "content": "x"}], max_tokens=3072)]

    with pytest.raises(ai_provider.AIOutputTruncated, match="Tokenlimit"):
        asyncio.run(read())



@pytest.mark.parametrize("status,body", [
    (413, {"error": {"message": "request too large"}}),
    (400, {"error": {"code": "context_length_exceeded", "message": "too much input"}}),
])
def test_explicit_provider_input_context_limit_is_identified(monkeypatch, status, body):
    async def no_dns(*args, **kwargs):
        return None
    monkeypatch.setattr(ai_provider, "validate_destination", no_dns)
    monkeypatch.setattr(ai_provider, "decrypt", lambda _: "test")
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        async def handler(_request):
            return httpx.Response(status, json=body)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(ai_provider.httpx, "AsyncClient", fake_client)
    with pytest.raises(ai_provider.AIContextLimit, match="Eingabekontextlimit"):
        asyncio.run(ai_provider.complete(_provider(), [{"role": "user", "content": "x"}]))


def test_generic_http_400_is_not_misclassified_as_context_limit(monkeypatch):
    async def no_dns(*args, **kwargs):
        return None
    monkeypatch.setattr(ai_provider, "validate_destination", no_dns)
    monkeypatch.setattr(ai_provider, "decrypt", lambda _: "test")
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        async def handler(_request):
            return httpx.Response(400, json={"error": {"code": "bad_model"}})
        return real_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(ai_provider.httpx, "AsyncClient", fake_client)
    with pytest.raises(ai_provider.AIProviderError, match="HTTP 400") as error:
        asyncio.run(ai_provider.complete(_provider(), [{"role": "user", "content": "x"}]))
    assert not isinstance(error.value, ai_provider.AIContextLimit)
