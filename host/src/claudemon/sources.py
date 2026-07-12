"""Dashboard source configuration: which Cloudflare zones and GitHub repos to
watch. Non-secret — lives at ~/.claudemon/sources.json (tokens go to the
Keychain via keychain.save_secret). Shape:

    {"cloudflare": {"zones": [{"id": "<zone-tag>", "name": "example.com"}]},
     "github":     {"repos": ["owner/repo", ...]},
     "paddle":     {"products": ["PixelPeek", ...]}}

A missing/empty file just means "no extra sources configured" — the daemon then
behaves exactly like the classic Claude-only ClaudeMon.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .keychain import CONFIG_DIR

SOURCES_FILE = CONFIG_DIR / "sources.json"


@dataclass
class CloudflareZone:
    id: str
    name: str  # display name; falls back to the id if the user omits it


@dataclass
class Sources:
    cloudflare_zones: list[CloudflareZone] = field(default_factory=list)
    github_repos: list[str] = field(default_factory=list)
    paddle_products: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.cloudflare_zones and not self.github_repos and not self.paddle_products


def load() -> Sources:
    if not SOURCES_FILE.exists():
        return Sources()
    try:
        data = json.loads(SOURCES_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"{SOURCES_FILE} is unreadable ({e}); fix or delete it") from e
    zones = [
        CloudflareZone(id=z["id"], name=z.get("name") or z["id"])
        for z in data.get("cloudflare", {}).get("zones", [])
        if z.get("id")
    ]
    repos = [r for r in data.get("github", {}).get("repos", []) if _is_repo(r)]
    products = [
        p for p in data.get("paddle", {}).get("products", [])
        if isinstance(p, str) and p.strip()
    ]
    return Sources(cloudflare_zones=zones, github_repos=repos, paddle_products=products)


def save(sources: Sources) -> None:
    CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)
    data = {
        "cloudflare": {"zones": [{"id": z.id, "name": z.name} for z in sources.cloudflare_zones]},
        "github": {"repos": sources.github_repos},
        "paddle": {"products": sources.paddle_products},
    }
    SOURCES_FILE.write_text(json.dumps(data, indent=2) + "\n")


def add_zone(zone_id: str, name: str | None) -> Sources:
    sources = load()
    sources.cloudflare_zones = [z for z in sources.cloudflare_zones if z.id != zone_id]
    sources.cloudflare_zones.append(CloudflareZone(id=zone_id, name=name or zone_id))
    save(sources)
    return sources


def remove_zone(zone_id: str) -> Sources:
    sources = load()
    sources.cloudflare_zones = [z for z in sources.cloudflare_zones if z.id != zone_id]
    save(sources)
    return sources


def add_repo(repo: str) -> Sources:
    if not _is_repo(repo):
        raise ValueError(f"'{repo}' is not an owner/repo slug")
    sources = load()
    if repo not in sources.github_repos:
        sources.github_repos.append(repo)
    save(sources)
    return sources


def remove_repo(repo: str) -> Sources:
    sources = load()
    sources.github_repos = [r for r in sources.github_repos if r != repo]
    save(sources)
    return sources


def add_product(name: str) -> Sources:
    name = name.strip()
    if not name:
        raise ValueError("product name is empty")
    sources = load()
    if name not in sources.paddle_products:
        sources.paddle_products.append(name)
    save(sources)
    return sources


def remove_product(name: str) -> Sources:
    sources = load()
    sources.paddle_products = [p for p in sources.paddle_products if p != name]
    save(sources)
    return sources


def _is_repo(value: object) -> bool:
    return isinstance(value, str) and value.count("/") == 1 and all(value.split("/"))
