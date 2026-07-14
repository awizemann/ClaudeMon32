---
id: t-ddd03e87
title: P4.3 — On-device fetchers (Cloudflare/GitHub/Paddle in C++)
status: todo
added: 2026-07-13
---

## Description

Reimplement the token-driven fetchers (Cloudflare GraphQL, GitHub REST/GraphQL, Paddle Billing) on-device over HTTPS (esp_http_client + TLS) with JSON parse + host-equivalent formatting. These are stateless API calls — tractable. Mirror the caps/formatting in render.py/paddle.py/cloudflare.py/github.py. Watch internal RAM (TLS buffers vs the 96KB LVGL pool).

## Plan



## Artifacts



