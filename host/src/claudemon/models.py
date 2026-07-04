"""Data models shared across ClaudeMon modules."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class AccountState(str, Enum):
    OK = "ok"
    AUTH = "auth"    # refresh/auth failure — needs re-login
    ERROR = "err"    # repeated fetch failures (network/5xx)
    DRIFT = "drift"  # endpoint responded but schema didn't parse cleanly


@dataclass
class AccountCredentials:
    access_token: str
    refresh_token: str
    expires_at: int  # epoch milliseconds
    scopes: list[str] = field(default_factory=list)
    subscription_type: str | None = None
    organization_id: str | None = None  # used to detect duplicate logins

    def expires_within(self, margin_seconds: int = 120) -> bool:
        return (self.expires_at / 1000) - time.time() < margin_seconds

    def to_json(self) -> str:
        return json.dumps(
            {
                "accessToken": self.access_token,
                "refreshToken": self.refresh_token,
                "expiresAt": self.expires_at,
                "scopes": self.scopes,
                "subscriptionType": self.subscription_type,
                "organizationId": self.organization_id,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "AccountCredentials":
        d = json.loads(raw)
        return cls(
            access_token=d["accessToken"],
            refresh_token=d["refreshToken"],
            expires_at=int(d["expiresAt"]),
            scopes=list(d.get("scopes") or []),
            subscription_type=d.get("subscriptionType"),
            organization_id=d.get("organizationId"),
        )


@dataclass
class WindowUsage:
    pct: int | None = None            # 0-100, None = unknown
    resets_at: datetime | None = None

    @property
    def known(self) -> bool:
        return self.pct is not None


@dataclass
class AccountUsage:
    label: str
    five_hour: WindowUsage = field(default_factory=WindowUsage)
    week: WindowUsage = field(default_factory=WindowUsage)
    state: AccountState = AccountState.OK
    fetched_at: datetime | None = None

    def to_state_dict(self) -> dict:
        def win(w: WindowUsage) -> dict:
            return {
                "pct": w.pct,
                "resets_at": w.resets_at.isoformat() if w.resets_at else None,
            }

        return {
            "label": self.label,
            "five_hour": win(self.five_hour),
            "week": win(self.week),
            "state": self.state.value,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
