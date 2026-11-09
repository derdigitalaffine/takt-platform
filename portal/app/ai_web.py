"""Opt-in, read-only public web search for TAKT's AI and agent chat.

Only the current, explicit user query is sent to the configured search engine.
No chat history, internal sources, system prompts, credentials, page crawling,
or follow-up tool calls. Search results are untrusted source material.
"""
import ipaddress
import json
import os
from urllib.parse import urlsplit

import httpx

from .db import get_settings
from .security import decrypt

_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
# Intentionally fixed, Docker-internal hostname, not user/admin editable:
# avoids arbitrary HTTP requests/SSRF through a configurable provider URL.
_SEARXNG_ENDPOINT = "http://searxng:8080/search"
_MAX_RESPONSE_BYTES = 200_000


class AIWebError(Exception):
    """Public error without provider details, response content, query or secrets."""


def public_url(url: str) -> bool:
    if not isinstance(url, str) or len(url) > 2048 or any(c in url for c in "\r\n\\"):
        return False
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
                parsed.password or parsed.port not in (None, 443)):
            return False
        hostname = parsed.hostname.casefold()
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
            return False
        try:
            return ipaddress.ip_address(hostname).is_global
        except ValueError:
            return "." in hostname and not hostname.endswith(".internal")
    except ValueError:
        return False


def searxng_installed() -> bool:
    """Infrastructure opt-in from setup.sh, independent of per-user permissions."""
    return os.environ.get("TAKT_SEARXNG_ENABLED", "0") == "1"


def selected_provider(cfg: dict, *, brave_key_configured: bool | None = None) -> str | None:
    """Choose an explicitly allowed search source; never silently switch on failure.

    'auto' prioritizes the locally configured SearXNG service, then Brave.
    Selecting 'searxng' explicitly prevents cloud-provider fallback.
    """
    choice = cfg.get("ai_web_provider", "auto")
    brave = (bool(cfg.get("ai_web_key_enc")) if brave_key_configured is None
             else brave_key_configured)
    local = searxng_installed()
    if choice == "searxng":
        return "searxng" if local else None
    if choice == "brave":
        return "brave" if brave else None
    if choice == "auto":
        return "searxng" if local else ("brave" if brave else None)
    return None


def available(db, user) -> bool:
    cfg = get_settings(db)
    return (user.can("ai_web") and cfg.get("module_ai") == "1" and
            cfg.get("ai_web_enabled") == "1" and selected_provider(cfg) is not None)


async def _request_json(endpoint: str, params: dict, headers: dict) -> dict:
    try:
        # No redirect or environment-based proxy; bounded read and short timeout.
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0), follow_redirects=False, trust_env=False
        ) as client:
            async with client.stream("GET", endpoint, params=params, headers=headers) as response:
                if response.status_code != 200:
                    raise AIWebError("Websuche ist aktuell nicht verfügbar.")
                if "json" not in response.headers.get("content-type", "").lower():
                    raise AIWebError("Ungültige Antwort der Websuche.")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > _MAX_RESPONSE_BYTES:
                        raise AIWebError("Antwort der Websuche ist zu groß.")
                    data.extend(chunk)
        payload = json.loads(data)
    except (httpx.TimeoutException, httpx.TransportError, ValueError, UnicodeDecodeError) as exc:
        raise AIWebError("Websuche ist aktuell nicht verfügbar.") from exc
    if not isinstance(payload, dict):
        raise AIWebError("Websuche hat ein unerwartetes Ergebnis geliefert.")
    return payload


async def search(db, user, query: str, limit: int = 4) -> list[dict]:
    if not available(db, user):
        raise AIWebError("Websuche ist nicht freigegeben.")
    if not query or not query.strip():
        return []

    cfg = get_settings(db)
    provider = selected_provider(cfg)
    # Limit untrusted input for *both* providers. Do not send hidden
    # conversation messages, internal documents or system prompts.
    q = " ".join(query.strip().split()[:75])[:600]
    count = max(1, min(limit, 5))
    if provider == "searxng":
        payload = await _request_json(
            _SEARXNG_ENDPOINT,
            {"q": q, "format": "json", "language": "de-DE", "safesearch": 2},
            {"Accept": "application/json"},
        )
        entries = payload.get("results")
    elif provider == "brave":
        key = decrypt(cfg.get("ai_web_key_enc", ""))
        if not key:
            raise AIWebError("Websuche ist nicht konfiguriert.")
        payload = await _request_json(
            _SEARCH_ENDPOINT,
            {"q": q, "count": count, "country": "DE",
             "search_lang": "de", "safesearch": "strict", "text_decorations": "false"},
            {"X-Subscription-Token": key, "Accept": "application/json"},
        )
        if not isinstance(payload.get("web"), dict):
            raise AIWebError("Websuche hat ein unerwartetes Ergebnis geliefert.")
        entries = payload["web"].get("results")
    else:
        raise AIWebError("Websuche ist nicht konfiguriert.")

    if not isinstance(entries, list):
        # Both providers normally return 'results', even for an empty response.
        raise AIWebError("Websuche hat ein unerwartetes Ergebnis geliefert.")

    results, seen = [], set()
    for item in entries[:15]:
        if not isinstance(item, dict):
            continue
        url, title = item.get("url"), item.get("title")
        desc = (item.get("content") if provider == "searxng"
                else item.get("description")) or ""
        if not public_url(url) or not isinstance(title, str) or not isinstance(desc, str):
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": title[:200], "url": url,
                        "text": desc[:650], "kind": "web"})
        if len(results) >= count:
            break
    return results
