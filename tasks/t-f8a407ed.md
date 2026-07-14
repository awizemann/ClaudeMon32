---
id: t-f8a407ed
title: Wiki: document WiFi transport, admin OAuth/WiFi provisioning, and claudemon-admin.local
status: todo
added: 2026-07-13
priority: low
---

## Description

This session added user-facing features the wiki doesn't cover yet: WiFi transport (run --device tcp/auto), WiFi provisioning via the admin's Device tab + `set-wifi` CLI, Anthropic OAuth account management in the admin (add/remove), the mDNS names (panel claudemon.local, admin claudemon-admin.local — no IP needed), and the launchd agent running --device auto (WiFi-first, serial fallback). Add a short setup/usage page. Also the released-state memory notes cockpit-web-admin and cockpit-firmware-rendering are now incomplete (don't mention OAuth-in-admin / WiFi / header layout) — reconcile at branch merge. Source of truth: the new architecture/cockpit-wifi-transport note + commits d2e8439..3ca83a3.

## Plan



## Artifacts



