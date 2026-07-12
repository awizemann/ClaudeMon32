---
title: Serial Protocol
type: note
permalink: claudemon32/conventions/serial-protocol
created: 2026-07-12
updated: 2026-07-12
tags:
- protocol
- serial
- framing
- json
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/protocol.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [protocol] Newline-delimited JSON over USB-CDC at 115200 baud (nominal — native USB). Max line **2048 bytes** (e-paper firmware) or **8192 bytes** (CrowPanel); longer lines truncate. Firmware also prints logs (`[INIT]`, `[BLE RX]`) on the same port; hosts skip non-JSON lines. #framing
- [protocol] On connect, send a bare `\n` and discard any error: it clears a stale partial line from an interrupted session. Allow ≥3 s response timeout (firmware may block 2–4 s during e-ink refresh). DTR/RTS must be asserted on open — device gates transmit on DTR. #handshake #usb-cdc
- [protocol] Main commands: `ping` (port discovery), `set_usage` (e-paper payload), `set_dashboard` (CrowPanel payload). Responses echo `cmd` name; errors are `{"status":"error","msg":"..."}` (no `cmd`). Match replies by echoed cmd to disambiguate stale errors from concurrent requests. #command-structure
- [protocol] Both USB and **BLE** (Nordic UART Service) transports supported. BLE-received commands queue to main loop before processing, so both behave identically. #ble-support

## Relations
- defines [[Host-Rendering Contract]]
- related_to [[Hardware Targets]]
