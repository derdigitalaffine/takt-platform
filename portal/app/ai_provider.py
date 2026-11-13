"""Safe OpenAI-compatible backend adapter; intentionally no web search/tool execution.

Provider URLs are administrative configuration only. All outbound requests stay on
the server and use TLS verification, no redirects and no environment proxies.
"""
import asyncio
import ipaddress
import json
import math
import socket
from urllib.parse import urlsplit

import httpx

from .security import decrypt

MAX_RESPONSE_BYTES = 2_000_000


class AIProviderError(Exception):
    """A deliberately redacted error safe to display to end users."""


def _host_check(url: str, allow_private: bool = False) -> None:
    try:
        p = urlsplit(url)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment:
            raise ValueError()
        if not p.path.startswith("/") or "//" in p.path or "\\" in p.path:
            raise ValueError()
        port = p.port or 443
        if port <= 0 or port > 65535:
            raise ValueError()
    except ValueError as exc:
        raise AIProviderError("Es ist eine gültige HTTPS-Basis-URL ohne Parameter erforderlich.") from exc
    if allow_private:
        return
    try:
        addresses = socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
            raise AIProviderError("Der Zielhost ist nicht als öffentlich erreichbarer HTTPS-Host zugelassen.")
    except (OSError, ValueError) as exc:
        raise AIProviderError("Der konfigurierte LLM-Host konnte nicht sicher aufgelöst werden.") from exc


async def validate_destination(url: str, allow_private: bool = False) -> None:
    """Resolve on each request, not only when saving administrative settings."""
    await asyncio.to_thread(_host_check, url, allow_private)


def endpoint(base_url: str, operation: str) -> str:
    """An /api remains /api, never force /v1 or /api/v1."""
    return base_url.rstrip("/") + "/" + operation.lstrip("/")


async def _request(provider, operation: str, key_enc: str, *, payload: dict | None = None) -> dict:
    if not provider.active:
        raise AIProviderError("Der gewählte KI-Provider ist deaktiviert.")
    token = decrypt(key_enc)
    if not token:
        raise AIProviderError("Für den KI-Provider ist kein API-Zugang eingerichtet.")
    await validate_destination(provider.base_url, provider.allow_private)
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    timeout = max(5, min(int(provider.timeout_seconds or 180), 180))
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            async with client.stream(
                "POST" if payload is not None else "GET",
                endpoint(provider.base_url, operation),
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    raise AIProviderError("Der Provider hat eine nicht zugelassene Weiterleitung gesendet.")
                if response.status_code == 401:
                    raise AIProviderError("Der KI-Provider hat den API-Schlüssel abgelehnt (401).")
                if response.status_code == 403:
                    raise AIProviderError("Der KI-Provider hat den Zugriff verweigert (403).")
                if response.status_code == 429:
                    raise AIProviderError("Das Anfragelimit des KI-Providers ist erreicht (429).")
                if response.status_code >= 400:
                    raise AIProviderError(f"Der KI-Provider meldet einen Fehler (HTTP {response.status_code}).")
                if "json" not in response.headers.get("content-type", "").lower():
                    raise AIProviderError("Der KI-Provider hat kein JSON geliefert (API-Pfad prüfen).")
                chunks = bytearray()
                async for part in response.aiter_bytes():
                    if len(chunks) + len(part) > MAX_RESPONSE_BYTES:
                        raise AIProviderError("Die Antwort des KI-Providers ist zu groß.")
                    chunks.extend(part)
                try:
                    result = json.loads(chunks)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise AIProviderError("Die Antwort des KI-Providers ist kein gültiges JSON.") from exc
                if not isinstance(result, dict):
                    raise AIProviderError("Die Antwort des KI-Providers hat ein ungültiges Format.")
                return result
    except AIProviderError:
        raise
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise AIProviderError("Der KI-Provider ist nicht erreichbar oder antwortet zu langsam.") from exc


async def list_models(provider, *, image: bool = False) -> list[str]:
    result = await _request(provider, "models", provider.image_key_enc if image else provider.text_key_enc)
    data = result.get("data")
    if not isinstance(data, list):
        raise AIProviderError("Der Modellkatalog hat ein unerwartetes Format.")
    if len(data) > 5000:
        raise AIProviderError("Der Modellserver meldet mehr als 5.000 Modelle; bitte Katalog eingrenzen.")
    return [item["id"] for item in data if isinstance(item, dict)
            and isinstance(item.get("id"), str) and 1 <= len(item["id"]) <= 200]


async def list_model_details(provider) -> list[dict]:
    """Sanitize provider-reported model capabilities for the admin model picker.

    OpenAI-compatible /models typically has *no* reliable capabilities. Unknown
    values remain unknown, never inferred from model names. This is deliberately
    a bounded, read-only call with the same destination restrictions as completions.
    """
    result = await _request(provider, "models", provider.text_key_enc)
    data = result.get("data")
    if not isinstance(data, list):
        raise AIProviderError("Der Modellkatalog hat ein unerwartetes Format.")

    # Show the complete returned catalog instead of silently truncating at
    # 200 entries. The upstream response is already bounded to 2 MB.
    if len(data) > 5000:
        raise AIProviderError("Der Modellserver meldet mehr als 5.000 Modelle; bitte Katalog eingrenzen.")
    models = []
    seen = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        identifier = row.get("id")
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200:
            continue
        if identifier in seen:
            continue
        seen.add(identifier)
        capabilities = row.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        modalities = row.get("modalities")
        modalities = modalities if isinstance(modalities, list) else []
        features = {}
        for feature, aliases in (
            ("vision", ("vision", "supports_vision")),
            ("tools", ("tools", "tool_calling", "supports_tool_calls")),
            ("json", ("json", "structured_output", "supports_json")),
            ("streaming", ("streaming", "stream", "supports_streaming")),
        ):
            evidence = next((capabilities[key] for key in aliases
                             if type(capabilities.get(key)) is bool), None)
            if evidence is None:
                evidence = next((row[key] for key in aliases
                                 if type(row.get(key)) is bool), None)
            if evidence is None and feature == "vision" and "image" in modalities:
                evidence = True
            features[feature] = ("reported" if evidence else "unsupported") if evidence is not None else "unknown"
        context = next((row[key] for key in ("context_length", "context_window", "max_context_tokens")
                        if type(row.get(key)) is int and 0 < row[key] <= 100_000_000), None)
        models.append({
            "id": identifier,
            "owner": str(row.get("owned_by") or "")[:100],
            "context_tokens": context,
            "features": features,
            "source": "provider",
        })
    return models


async def complete(provider, messages: list[dict], *, image: bool = False, max_tokens: int = 1024) -> str:
    payload = {
        "model": provider.model_id,
        "stream": False,  # OpenWebUI/Gemma profiles may require this.
        "max_tokens": max(64, min(int(max_tokens), 4096)),
        "messages": messages,
    }
    result = await _request(provider, "chat/completions",
                            provider.image_key_enc if image else provider.text_key_enc, payload=payload)
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AIProviderError("Der KI-Provider hat keine Textantwort zurückgegeben.")
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, str):
        raise AIProviderError("Der KI-Provider hat kein lesbares Nachrichtenfeld geliefert.")
    return content[:40_000]



async def stream_completion(provider, messages: list[dict], *, image: bool = False,
                            max_tokens: int = 1024):
    """Yield OpenAI-compatible SSE content tokens from a streaming provider.

    The caller is responsible for saving the complete answer. Non-streaming
    providers continue to use complete() with stream=False.
    """
    if not provider.active:
        raise AIProviderError("Der gewählte KI-Provider ist deaktiviert.")
    token = decrypt(provider.image_key_enc if image else provider.text_key_enc)
    if not token:
        raise AIProviderError("Für den KI-Provider ist kein API-Zugang eingerichtet.")
    await validate_destination(provider.base_url, provider.allow_private)
    payload = {"model": provider.model_id, "stream": True,
               "max_tokens": max(64, min(int(max_tokens), 2048)), "messages": messages}
    headers = {"Authorization": "Bearer " + token,
               "Accept": "text/event-stream", "Content-Type": "application/json"}
    timeout = max(5, min(int(provider.timeout_seconds or 180), 180))
    total = 0
    done = False
    data_lines = []
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            async with client.stream(
                "POST", endpoint(provider.base_url, "chat/completions"),
                headers=headers, json=payload,
            ) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    raise AIProviderError("Der Provider hat eine nicht zugelassene Weiterleitung gesendet.")
                if response.status_code == 401:
                    raise AIProviderError("Der KI-Provider hat den API-Schlüssel abgelehnt (401).")
                if response.status_code == 403:
                    raise AIProviderError("Der KI-Provider hat den Zugriff verweigert (403).")
                if response.status_code == 429:
                    raise AIProviderError("Das Anfragelimit des KI-Providers ist erreicht (429).")
                if response.status_code >= 400:
                    raise AIProviderError(f"Der KI-Provider meldet einen Fehler (HTTP {response.status_code}).")
                if "text/event-stream" not in response.headers.get("content-type", "").lower():
                    raise AIProviderError(
                        "Dieser Provider liefert keinen SSE-Stream. Streaming in der KI-Verwaltung deaktivieren."
                    )
                async for line in response.aiter_lines():
                    if len(line) > 100_000:
                        raise AIProviderError("Der KI-Provider hat eine zu große Streaming-Nachricht geliefert.")
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    elif not line.strip():
                        if not data_lines:
                            continue
                        payload_text = "\n".join(data_lines)
                        data_lines.clear()
                        if payload_text == "[DONE]":
                            done = True
                            break
                        try:
                            obj = json.loads(payload_text)
                        except ValueError as exc:
                            raise AIProviderError("Ungültige Streaming-Nachricht des KI-Providers.") from exc
                        if not isinstance(obj, dict):
                            raise AIProviderError("Ungültiges Streaming-Format.")
                        if obj.get("error"):
                            raise AIProviderError("Der KI-Provider hat den Stream mit einem Fehler abgebrochen.")
                        choices = obj.get("choices")
                        if not isinstance(choices, list) or not choices:
                            continue
                        choice = choices[0] if isinstance(choices[0], dict) else {}
                        delta = choice.get("delta")
                        content = delta.get("content") if isinstance(delta, dict) else None
                        if isinstance(content, str) and content:
                            total += len(content)
                            if total > 40_000:
                                raise AIProviderError("Die Textantwort überschreitet das Ausgabelimit.")
                            yield content
                        if choice.get("finish_reason"):
                            done = True
                if not done:
                    raise AIProviderError("Die Streaming-Verbindung wurde unvollständig beendet.")
    except AIProviderError:
        raise
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise AIProviderError("Der KI-Provider ist nicht erreichbar oder antwortet zu langsam.") from exc


async def embed(provider, texts: list[str], model_id: str) -> list[list[float]]:
    """OpenAI-compatible embeddings; reject malformed dimensions and non-finite values.

    Admin-configured provider and model only; no URL from untrusted documents.
    """
    if not texts or len(texts) > 16 or any(not isinstance(t, str) or not t or len(t) > 4000 for t in texts):
        raise AIProviderError("Ungültige Embedding-Eingaben.")
    if not model_id or len(model_id) > 200:
        raise AIProviderError("Bitte ein Embedding-Modell konfigurieren.")
    result = await _request(provider, "embeddings", provider.text_key_enc,
                            payload={"model": model_id, "input": texts})
    items = result.get("data")
    if not isinstance(items, list) or len(items) != len(texts):
        raise AIProviderError("Der Embedding-Provider lieferte eine unvollständige Antwort.")
    vectors = [None] * len(texts)
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("index"), int):
            raise AIProviderError("Ungültiger Embedding-Index.")
        pos = item["index"]
        values = item.get("embedding")
        if pos < 0 or pos >= len(vectors) or vectors[pos] is not None or not isinstance(values, list):
            raise AIProviderError("Ungültige Embedding-Daten.")
        if not 2 <= len(values) <= 4096 or not all(
                isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in values):
            raise AIProviderError("Embedding-Dimension oder Zahlenwerte ungültig.")
        vectors[pos] = [float(x) for x in values]
    if any(v is None for v in vectors) or len({len(v) for v in vectors}) != 1:
        raise AIProviderError("Die Embedding-Dimensionen stimmen nicht überein.")
    return vectors
