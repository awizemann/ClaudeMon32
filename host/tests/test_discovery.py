"""Tests for global-token source discovery: Cloudflare `list_zones` and GitHub
`list_repos`. No live tokens — a fake httpx client returns queued responses so we
can exercise pagination, parsing, and the never-raises failure classification."""

from __future__ import annotations

import httpx
import pytest

from claudemon import cloudflare, github


class FakeClient:
    """Stand-in for the shared httpx.Client. Serves queued httpx.Response objects
    in order and records the params of each GET for pagination assertions."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, params=None):
        self.calls.append({"url": url, "params": params})
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _cf_page(zones, page, total_pages, status=200, success=True):
    body = {
        "success": success,
        "errors": [] if success else [{"message": "bad token"}],
        "result": [{"id": zid, "name": name} for zid, name in zones],
        "result_info": {"page": page, "total_pages": total_pages},
    }
    return httpx.Response(status, json=body, request=httpx.Request("GET", cloudflare.ZONES_URL))


def _gh_page(slugs, next_url=None, status=200):
    headers = {}
    if next_url:
        headers["Link"] = f'<{next_url}>; rel="next"'
    body = [{"full_name": s} for s in slugs]
    return httpx.Response(
        status, json=body, headers=headers,
        request=httpx.Request("GET", github.USER_REPOS_URL),
    )


# --------------------------------------------------------------- Cloudflare


class TestListZones:
    def test_single_page(self, monkeypatch):
        fake = FakeClient([_cf_page([("z1", "a.com"), ("z2", "b.com")], 1, 1)])
        monkeypatch.setattr(cloudflare, "client", fake)
        zones = cloudflare.list_zones("tok")
        assert zones == [{"id": "z1", "name": "a.com"}, {"id": "z2", "name": "b.com"}]
        assert len(fake.calls) == 1

    def test_paginates_until_total_pages(self, monkeypatch):
        fake = FakeClient([
            _cf_page([("z1", "a.com")], 1, 3),
            _cf_page([("z2", "b.com")], 2, 3),
            _cf_page([("z3", "c.com")], 3, 3),
        ])
        monkeypatch.setattr(cloudflare, "client", fake)
        zones = cloudflare.list_zones("tok")
        assert [z["id"] for z in zones] == ["z1", "z2", "z3"]
        assert len(fake.calls) == 3
        assert [c["params"]["page"] for c in fake.calls] == [1, 2, 3]

    def test_missing_name_falls_back_to_id(self, monkeypatch):
        fake = FakeClient([_cf_page([("z1", None)], 1, 1)])
        monkeypatch.setattr(cloudflare, "client", fake)
        assert cloudflare.list_zones("tok") == [{"id": "z1", "name": "z1"}]

    def test_zone_without_id_is_skipped(self, monkeypatch):
        page = _cf_page([], 1, 1)
        # Hand-craft a result with a missing id.
        page = httpx.Response(
            200,
            json={"success": True, "result": [{"name": "x.com"}], "result_info": {"total_pages": 1}},
            request=httpx.Request("GET", cloudflare.ZONES_URL),
        )
        fake = FakeClient([page])
        monkeypatch.setattr(cloudflare, "client", fake)
        assert cloudflare.list_zones("tok") == []

    def test_auth_failure_returns_empty(self, monkeypatch):
        fake = FakeClient([_cf_page([], 1, 1, status=403)])
        monkeypatch.setattr(cloudflare, "client", fake)
        assert cloudflare.list_zones("tok") == []

    def test_api_success_false_returns_empty(self, monkeypatch):
        fake = FakeClient([_cf_page([], 1, 1, success=False)])
        monkeypatch.setattr(cloudflare, "client", fake)
        assert cloudflare.list_zones("tok") == []

    def test_network_error_returns_empty(self, monkeypatch):
        fake = FakeClient([httpx.ConnectError("boom")])
        monkeypatch.setattr(cloudflare, "client", fake)
        assert cloudflare.list_zones("tok") == []

    def test_partial_pages_stop_on_network_error(self, monkeypatch):
        # First page OK, second page errors -> discovery bails to [] (never raises).
        fake = FakeClient([
            _cf_page([("z1", "a.com")], 1, 2),
            httpx.ConnectError("boom"),
        ])
        monkeypatch.setattr(cloudflare, "client", fake)
        assert cloudflare.list_zones("tok") == []


# ------------------------------------------------------------------- GitHub


class TestListRepos:
    def test_single_page(self, monkeypatch):
        fake = FakeClient([_gh_page(["o/r1", "o/r2"])])
        monkeypatch.setattr(github, "client", fake)
        assert github.list_repos("tok") == ["o/r1", "o/r2"]
        assert len(fake.calls) == 1

    def test_follows_link_next(self, monkeypatch):
        next_url = "https://api.github.com/user/repos?page=2&per_page=100&sort=pushed"
        fake = FakeClient([
            _gh_page(["o/r1"], next_url=next_url),
            _gh_page(["o/r2"]),
        ])
        monkeypatch.setattr(github, "client", fake)
        assert github.list_repos("tok") == ["o/r1", "o/r2"]
        assert len(fake.calls) == 2
        # First hop carries our params; the second reuses the next URL (params dropped).
        assert fake.calls[0]["params"] == {"per_page": 100, "sort": "pushed"}
        assert fake.calls[1]["url"] == next_url
        assert fake.calls[1]["params"] is None

    def test_auth_failure_returns_empty(self, monkeypatch):
        fake = FakeClient([_gh_page([], status=401)])
        monkeypatch.setattr(github, "client", fake)
        assert github.list_repos("tok") == []

    def test_network_error_returns_empty(self, monkeypatch):
        fake = FakeClient([httpx.ConnectError("boom")])
        monkeypatch.setattr(github, "client", fake)
        assert github.list_repos("tok") == []

    def test_repo_without_full_name_is_skipped(self, monkeypatch):
        page = httpx.Response(
            200, json=[{"name": "r1"}, {"full_name": "o/r2"}],
            request=httpx.Request("GET", github.USER_REPOS_URL),
        )
        fake = FakeClient([page])
        monkeypatch.setattr(github, "client", fake)
        assert github.list_repos("tok") == ["o/r2"]

    def test_unexpected_shape_returns_empty(self, monkeypatch):
        page = httpx.Response(
            200, json={"message": "not a list"},
            request=httpx.Request("GET", github.USER_REPOS_URL),
        )
        fake = FakeClient([page])
        monkeypatch.setattr(github, "client", fake)
        assert github.list_repos("tok") == []
