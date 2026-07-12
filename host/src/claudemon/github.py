"""Fetch repo stats (stars, forks, watchers, open issues, open PRs) from GitHub.

Preferred path: a single batched GraphQL query (one HTTP call for every repo)
with a Personal Access Token — this is the only way to get a clean issues-vs-PRs
split, because REST's `open_issues_count` lumps pull requests in with issues.

Fallback with no token: REST `GET /repos/{owner}/{repo}` for public repos, which
yields stars/forks/watchers but leaves the issue/PR split unknown (rendered as
"--") rather than reporting a conflated count as if it were issues.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from .http import client
from .models import AccountState, GitHubRepoStats, utcnow

log = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com/repos/{repo}"

_REPO_FRAGMENT = """
  %s: repository(owner: "%s", name: "%s") {
    stargazerCount
    forkCount
    watchers { totalCount }
    issues(states: OPEN) { totalCount }
    pullRequests(states: OPEN) { totalCount }
    pushedAt
    primaryLanguage { name }
    latestRelease { tagName }
    defaultBranchRef {
      target { ... on Commit { statusCheckRollup { state } } }
    }
  }
"""

# GitHub's check-rollup states -> our compact CI labels.
_CI_MAP = {
    "SUCCESS": "pass",
    "FAILURE": "fail",
    "ERROR": "fail",
    "PENDING": "run",
    "EXPECTED": "run",
}


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _ci_from_node(node: dict) -> str | None:
    ref = node.get("defaultBranchRef") or {}
    target = ref.get("target") or {}
    rollup = target.get("statusCheckRollup") or {}
    return _CI_MAP.get(rollup.get("state"))


def fetch_all(token: str | None, repos: list[str]) -> list[GitHubRepoStats]:
    if not repos:
        return []
    if token:
        return _fetch_graphql(token, repos)
    log.info("github: no token set — using unauthenticated REST (stars/forks only)")
    return [_fetch_rest(repo) for repo in repos]


def _fetch_graphql(token: str, repos: list[str]) -> list[GitHubRepoStats]:
    aliases = {f"r{i}": repo for i, repo in enumerate(repos)}
    fragments = []
    for alias, repo in aliases.items():
        owner, name = repo.split("/", 1)
        fragments.append(_REPO_FRAGMENT % (alias, owner, name))
    query = "query {\n" + "".join(fragments) + "}\n"

    try:
        resp = client.post(
            GRAPHQL_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": query},
        )
    except httpx.HTTPError as e:
        log.warning("github: network error: %s", e)
        return [GitHubRepoStats(name=r, state=AccountState.ERROR) for r in repos]

    if resp.status_code in (401, 403):
        log.warning("github: token rejected (HTTP %s)", resp.status_code)
        return [GitHubRepoStats(name=r, state=AccountState.AUTH) for r in repos]
    if resp.status_code != 200:
        log.warning("github: HTTP %s: %s", resp.status_code, resp.text[:200])
        return [GitHubRepoStats(name=r, state=AccountState.ERROR) for r in repos]

    body = resp.json()
    data = body.get("data") or {}
    if body.get("errors"):
        # Partial results: GitHub returns data for the repos it could resolve and
        # an errors[] for the rest (e.g. NOT_FOUND). Per-repo nulls handle those.
        log.warning(
            "github: %s", "; ".join(e.get("message", "") for e in body["errors"])[:200]
        )

    now = utcnow()
    results = []
    for alias, repo in aliases.items():
        node = data.get(alias)
        if not node:
            results.append(GitHubRepoStats(name=repo, state=AccountState.ERROR))
            continue
        release = node.get("latestRelease") or {}
        lang = node.get("primaryLanguage") or {}
        results.append(
            GitHubRepoStats(
                name=repo,
                stars=node["stargazerCount"],
                forks=node["forkCount"],
                watchers=node["watchers"]["totalCount"],
                open_issues=node["issues"]["totalCount"],
                open_prs=node["pullRequests"]["totalCount"],
                latest_release=release.get("tagName"),
                ci_status=_ci_from_node(node),
                pushed_at=_parse_dt(node.get("pushedAt")),
                language=lang.get("name"),
                fetched_at=now,
            )
        )
    return results


def _fetch_rest(repo: str) -> GitHubRepoStats:
    stats = GitHubRepoStats(name=repo)
    try:
        resp = client.get(
            REST_URL.format(repo=repo),
            headers={"Accept": "application/vnd.github+json"},
        )
    except httpx.HTTPError as e:
        log.warning("github %s: network error: %s", repo, e)
        stats.state = AccountState.ERROR
        return stats

    if resp.status_code == 403:  # unauthenticated rate limit exhausted
        log.warning("github %s: rate limited (set a token to raise the limit)", repo)
        stats.state = AccountState.ERROR
        return stats
    if resp.status_code != 200:
        log.warning("github %s: HTTP %s", repo, resp.status_code)
        stats.state = AccountState.ERROR
        return stats

    data = resp.json()
    stats.stars = data.get("stargazers_count")
    stats.forks = data.get("forks_count")
    stats.watchers = data.get("subscribers_count")
    # open_issues_count conflates issues + PRs; leave the split unknown rather
    # than mislabel it. Set a token to get real issue/PR counts.
    stats.fetched_at = utcnow()
    return stats
