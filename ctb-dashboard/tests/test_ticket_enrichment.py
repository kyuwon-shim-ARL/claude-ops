import asyncio
import pytest
from ctb_dashboard.ticket_enrichment import attach_l1, _cache_key, _native_l1

def test_native_l1_github():
    ticket = {"id": "gh-1", "source": "github", "title": "Fix bug", "body": "Details here"}
    result = _native_l1(ticket)
    assert result is not None
    assert "l1_context" in result

def test_native_l1_manifest():
    ticket = {"id": "manifest-e001", "source": "manifest", "title": "Exp 1", "status": "final"}
    result = _native_l1(ticket)
    assert result is not None

def test_attach_l1_sync_no_semaphore():
    tickets = [
        {"id": "gh-1", "source": "github", "title": "T", "body": "B"},
        {"id": "manifest-e1", "source": "manifest", "title": "M", "status": "experimental"},
    ]
    result = asyncio.run(attach_l1(tickets, semaphore=None))
    assert len(result) == 2
    for t in result:
        # native should have filled body_structured for known sources
        assert "body_structured" in t or t.get("_l1_source") == "haiku_failed"

def test_cache_key_stable():
    k1 = _cache_key("github", "gh-1", "body text")
    k2 = _cache_key("github", "gh-1", "body text")
    assert k1 == k2

def test_cache_key_different_inputs():
    k1 = _cache_key("github", "gh-1", "body A")
    k2 = _cache_key("github", "gh-1", "body B")
    assert k1 != k2
