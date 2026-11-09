"""Explicit, read-only web search for TAKT AI chat.

Only the user's current query is sent to the fixed Brave Search API endpoint,
never internal knowledge, prior messages or credentials. Returned snippets are
untrusted evidence, not instructions. No page fetching, crawling or tool calls.
"""
import ipaddress
import json
from urllib.parse import urlsplit

import httpx

from .db import get_settings
from .security import decrypt

_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
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


def available(db, user) -> bool:
    cfg = get_settings(db)
    return (user.can("ai_web") and cfg.get("module_ai") == "1" and
            cfg.get("ai_web_enabled") == "1" and bool(cfg.get("ai_web_key_enc")))


async def search(db, user, query: str, limit: int = 4) -> list[dict]:
    if not available(db, user):
        raise AIWebError("Websuche ist nicht freigegeben.")
    if not query or not query.strip():
        return []
    cfg = get_settings(db)
    key = decrypt(cfg.get("ai_web_key_enc", ""))
    if not key:
        raise AIWebError("Websuche ist nicht konfiguriert.")
    # Brave limits queries to 600 chars/75 words; do not send hidden
    # conversation messages or system prompts.
    q = " ".join(query.strip().split()[:75])[:600]
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0), follow_redirects=False, trust_env=False
        ) as client:
            async with client.stream(
                "GET", _SEARCH_ENDPOINT,
                params={"q": q, "count": max(1, min(limit, 5)),
                        "country": "DE", "search_lang": "de",
                        "safesearch": "strict", "text_decorations": "false"},
                headers={"X-Subscription-Token": key, "Accept": "application/json"},
            ) as response:
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
    if not isinstance(payload, dict) or not isinstance(payload.get("web"), dict):
        raise AIWebError("Websuche hat ein unerwartetes Ergebnis geliefert.")
    entries = payload["web"].get("results")
    if not isinstance(entries, list):
        return []
    results, seen = [], set()
    for item in entries[:15]:
        if not isinstance(item, dict):
            continue
        url, title = item.get("url"), item.get("title")
        desc = item.get("description") or ""
        if not public_url(url) or not isinstance(title, str) or not isinstance(desc, str):
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": title[:200], "url": url,
                        "text": desc[:650], "kind": "web"})
        if len(results) >= limit:
            break
    return results
