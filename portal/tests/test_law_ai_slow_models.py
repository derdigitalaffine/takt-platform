"""Slow OpenAI-compatible models need a real HTTP and job timeout budget."""
import asyncio
from types import SimpleNamespace

from app import ai_provider, law_ai_agent_jobs


def _provider(seconds: int, stream=False):
    return SimpleNamespace(timeout_seconds=seconds, stream_enabled=stream)


def test_law_nonstream_minimum_is_ten_minutes(monkeypatch):
    observed = {}

    async def fake_complete(provider, messages, **kwargs):
        observed.update(kwargs)
        return '{"fields":[]}'

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    result = asyncio.run(law_ai_agent_jobs._answer(
        _provider(180), [{"role": "user", "content": "example"}],
        1, "law_metadata", remaining=4000))
    assert result == '{"fields":[]}'
    assert observed["timeout_seconds"] == 600


def test_law_nonstream_honors_longer_provider_timeout(monkeypatch):
    observed = {}

    async def fake_complete(provider, messages, **kwargs):
        observed.update(kwargs)
        return "{}"

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    asyncio.run(law_ai_agent_jobs._answer(
        _provider(1500), [], 1, "law_structure", remaining=4000))
    assert observed["timeout_seconds"] == 1500


def test_law_timeout_is_bounded_by_remaining_job_budget(monkeypatch):
    observed = {}

    async def fake_complete(provider, messages, **kwargs):
        observed.update(kwargs)
        return "{}"

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    asyncio.run(law_ai_agent_jobs._answer(
        _provider(1800), [], 1, "law_verify", remaining=20))
    assert observed["timeout_seconds"] == 20


def test_law_streaming_timeout_uses_same_http_override(monkeypatch):
    observed = {}

    async def fake_stream(provider, messages, **kwargs):
        observed.update(kwargs)
        yield '{"fields":[]}' 

    monkeypatch.setattr(ai_provider, "stream_completion", fake_stream)
    monkeypatch.setattr(law_ai_agent_jobs, "_stream_progress", lambda *args: None)
    result = asyncio.run(law_ai_agent_jobs._answer(
        _provider(1200, stream=True), [], 1, "law_metadata", remaining=4000))
    assert result == '{"fields":[]}'
    assert observed["timeout_seconds"] == 1200


def test_job_budget_and_call_limits_remain_finite():
    assert law_ai_agent_jobs.MIN_STAGE_TIMEOUT == 600
    assert law_ai_agent_jobs.MAX_STAGE_TIMEOUT == 1800
    assert law_ai_agent_jobs.MAX_JOB_SECONDS >= 30 * 600
