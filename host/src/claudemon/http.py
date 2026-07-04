"""Shared HTTP client: one connection pool (keep-alive) for all API calls."""

from __future__ import annotations

import httpx

client = httpx.Client(timeout=30)
