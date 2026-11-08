import json

import pytest
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)


@pytest.fixture
def fake(monkeypatch):
    state = {"hits": [], "vs_calls": [], "sql_calls": [], "eligible": None}

    def fake_vs(text, filters, k):
        state["vs_calls"].append((text, filters, k))
        return state["hits"]

    def fake_query(statement, params=None):
        state["sql_calls"].append((statement, params))
        ids = json.loads(params["ids"])
        keep = state["eligible"] if state["eligible"] is not None else ids
        return [{"repo_id": r} for r in ids if r in keep]

    monkeypatch.setattr(main, "vector_search", fake_vs)
    monkeypatch.setattr(main, "query", fake_query)
    monkeypatch.setattr(main, "SEARCH_MIN_SCORE", 0.5)
    monkeypatch.setattr(main, "SEARCH_SCORE_WINDOW", 1.0)
    return state


def test_returns_ranked_ids_above_threshold(fake):
    fake["hits"] = [("psf/requests", 0.9), ("encode/httpx", 0.8), ("noise/repo", 0.2)]
    body = client.get("/api/search", params={"q": "python http clients"}).json()
    assert body == {"query": "python http clients", "repo_ids": ["psf/requests", "encode/httpx"]}


def test_drops_weak_tail_relative_to_best(fake, monkeypatch):
    monkeypatch.setattr(main, "SEARCH_SCORE_WINDOW", 0.06)
    fake["hits"] = [("iamkun/dayjs", 0.68), ("lodash/lodash", 0.57)]
    assert client.get("/api/search", params={"q": "date lib"}).json()["repo_ids"] == ["iamkun/dayjs"]


def test_passes_scalar_filters_to_vector_search(fake):
    fake["hits"] = [("psf/requests", 0.9)]
    client.get("/api/search", params={"q": "http", "language": "Python", "status": "at_risk"})
    assert fake["vs_calls"][0][1] == {"language": "Python", "status": "at_risk"}


def test_sql_post_filter_drops_ineligible_and_keeps_rank(fake):
    fake["hits"] = [("a/a", 0.9), ("excluded/repo", 0.85), ("b/b", 0.7)]
    fake["eligible"] = {"b/b", "a/a"}
    body = client.get("/api/search", params={"q": "x", "vuln_bucket": "Injection",
                                             "investigated_only": "true"}).json()
    assert body["repo_ids"] == ["a/a", "b/b"]
    stmt, params = fake["sql_calls"][0]
    assert "FROM eligible_gold g" in stmt
    assert params["vuln_bucket"] == "Injection" and params["investigated_only"] is True


def test_zero_matches_skips_sql(fake):
    fake["hits"] = [("noise/repo", 0.1)]
    assert client.get("/api/search", params={"q": "zzz"}).json()["repo_ids"] == []
    assert fake["sql_calls"] == []


def test_empty_query_rejected(fake):
    assert client.get("/api/search", params={"q": ""}).status_code == 422


def test_vector_search_failure_is_502(fake, monkeypatch):
    def boom(*a):
        raise RuntimeError("index not ready")
    monkeypatch.setattr(main, "vector_search", boom)
    assert client.get("/api/search", params={"q": "x"}).status_code == 502
