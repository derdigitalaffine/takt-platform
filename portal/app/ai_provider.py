"""Safe OpenAI-compatible backend adapter; intentionally no web search/tool execution.

Provider URLs are administrative configuration only. All outbound requests stay on
the server and use TLS verification, no redirects and no environment proxies.
"""
import asyncio
import ipaddress
import json
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
    return [item["id"] for item in data[:200] if isinstance(item, dict)
            and isinstance(item.get("id"), str) and len(item["id"]) < 200]


async def complete(provider, messages: list[dict], *, image: bool = False, max_tokens: int = 1024) -> str:
    payload = {
        "model": provider.model_id,
        "stream": False,  # OpenWebUI/Gemma profiles may require this.
        "max_tokens": max(64, min(int(max_tokens), 2048)),
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
