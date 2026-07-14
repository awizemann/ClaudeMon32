---
id: t-0e9adea6
title: Fix collapsed header status pill (same flex trap as the WiFi icon)
status: todo
added: 2026-07-13
priority: low
---

## Description

The home-header status pill (s_pill / s_pillTxt — shows "2 info" / "1 warning" / "all clear" from the alert set via applyPill) is a SIZE_CONTENT child of the header's `right` flex cluster, which collapses SIZE_CONTENT children to zero — so it never renders on device. Same root cause and fix as the WiFi icon: make it fixed-size or a FLOATING absolutely-aligned overlay (see conventions/crowpanel-header-widget-layout). Low priority — cosmetic; the Alerts panel already shows the count. esp32/crowpanel/src/UI.cpp (buildHeaders, applyPill).

## Plan



## Artifacts



