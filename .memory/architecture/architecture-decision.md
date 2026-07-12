---
title: Architecture Decision
type: note
permalink: claudemon32/architecture/architecture-decision
created: 2026-07-12
updated: 2026-07-12
tags:
- architecture
- host-firmware-split
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/architecture.md, docs/protocol.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [decision] Strict separation of concerns: **Host** (macOS Python) owns OAuth, token refresh, polling, rendering, serial/BLE transport, launchd agent; **Firmware** (Arduino/PlatformIO) owns only display drawing. Host renders *every* string (time, account labels, counts) before sending. #design-invariant
- [rationale] This contract keeps the firmware deliberately dumb and portable: reimplement the display driver for any hardware, the host remains unchanged. Avoids clock/timezone/rendering logic on the embedded side. #portability #simplicity
- [scope] Max **4 accounts** per e-paper payload, **6 zones** + **6 repos** per CrowPanel dashboard; extras silently ignored to maintain line length <2048 bytes (e-paper) or <8192 bytes (CrowPanel). #payload-limits

## Relations
- informed_by [[Host-Rendering Contract]]
- enforces [[Serial Protocol]]
- related_to [[OAuth & Credential Model]]
