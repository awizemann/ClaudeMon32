"""OAuth PKCE login and token refresh for Claude subscription accounts.

Each monitored account gets its own OAuth grant, fully independent of
Claude Code's credential (refresh-token rotation means a shared credential
would invalidate whichever client refreshes second).

Flow: paste-code mode. We open the claude.ai authorize page with `code=true`;
after sign-in the page displays "code#state" for the user to paste back.

Error contract:
- OAuthError          — definitive auth failure (grant rejected); re-login needed
- OAuthTransientError — network / 5xx / timeout; retry later, auth is NOT dead
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import urllib.parse

import httpx

from . import keychain
from .http import client
from .models import AccountCredentials

# Claude Code's public OAuth client (no client secret; PKCE only).
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
SCOPES = "user:profile user:inference"


class OAuthError(RuntimeError):
    """Definitive auth failure — the grant is dead; the user must re-login."""


class OAuthTransientError(RuntimeError):
    """Network / server-side failure — the grant is still presumed valid."""


def make_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def build_authorize_url(challenge: str, state: str) -> str:
    params = {
        "code": "true",  # paste-code mode: page displays code#state after sign-in
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def _creds_from_token_response(data: dict) -> AccountCredentials:
    try:
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]
        expires_in = int(data.get("expires_in", 3600))
    except KeyError as e:
        raise OAuthError(f"Token response missing field {e}: keys={sorted(data)}") from e
    return AccountCredentials(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=int((time.time() + expires_in) * 1000),
        scopes=str(data.get("scope", "")).split(),
        subscription_type=(data.get("account") or {}).get("subscription_type")
        or data.get("subscription_type"),
    )


def exchange_code(pasted: str, verifier: str, expected_state: str) -> AccountCredentials:
    """Exchange a pasted "code#state" string for tokens."""
    pasted = pasted.strip()
    if "#" in pasted:
        code, state = pasted.split("#", 1)
    else:
        code, state = pasted, expected_state
    if state != expected_state:
        raise OAuthError("State mismatch — restart the login (possible CSRF or stale paste)")

    try:
        resp = client.post(
            TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "state": state,
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            },
        )
    except httpx.HTTPError as e:
        raise OAuthError(f"Token exchange failed (network): {e}") from e
    if resp.status_code != 200:
        raise OAuthError(f"Token exchange failed ({resp.status_code}): {resp.text[:500]}")
    return _creds_from_token_response(resp.json())


def refresh(creds: AccountCredentials) -> AccountCredentials:
    """Refresh an access token.

    Raises OAuthError on a definitive rejection (grant dead) and
    OAuthTransientError on network/5xx (grant still presumed valid). The
    caller MUST persist the returned credentials immediately — the refresh
    token rotates, and the old one is dead after this call succeeds.
    """
    try:
        resp = client.post(
            TOKEN_URL,
            json={
                "grant_type": "refresh_token",
                "refresh_token": creds.refresh_token,
                "client_id": CLIENT_ID,
            },
        )
    except httpx.HTTPError as e:
        raise OAuthTransientError(f"refresh network error: {e}") from e
    if resp.status_code in (400, 401, 403):
        raise OAuthError(f"Refresh rejected ({resp.status_code}): {resp.text[:500]}")
    if resp.status_code != 200:
        raise OAuthTransientError(f"refresh HTTP {resp.status_code}: {resp.text[:300]}")
    new = _creds_from_token_response(resp.json())
    if new.subscription_type is None:
        new.subscription_type = creds.subscription_type
    if not new.scopes:
        new.scopes = creds.scopes
    return new


def load_fresh(label: str) -> AccountCredentials:
    """Load an account's credentials, refreshing (and persisting the rotated
    token) if they are near expiry. The single entry point every consumer of
    a live token must use — the rotation-persist step is security-critical
    and must not be duplicated.

    Raises: keychain.KeychainError (incl. KeychainNotFoundError), OAuthError,
    OAuthTransientError.
    """
    creds = keychain.load_account(label)
    if creds.expires_within():
        creds = refresh(creds)
        keychain.save_account(label, creds)  # rotated token — persist NOW
    return creds


def new_state() -> str:
    return secrets.token_urlsafe(24)
