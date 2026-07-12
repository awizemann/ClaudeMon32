---
title: Project Overview
type: note
permalink: claudemon32/project/project-overview
created: 2026-07-12
updated: 2026-07-12
tags:
- project
- usage-monitoring
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: README.md, docs/architecture.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [project] ClaudeMon is a macOS desktop app + embedded firmware that displays Claude subscription usage (5-hour and weekly windows) across multiple accounts on an e-paper display. Not affiliated with Anthropic; reads the same undocumented usage endpoint as Claude Code's `/usage` panel via OAuth. #overview
- [project] Recently added CrowPanel support: a 5" color LVGL display (800×480) that shows Claude usage alongside Cloudflare analytics and GitHub repository stats in a dense tile dashboard. #crowpanel #recent-addition
- [audience] Target users: power users monitoring their Claude API usage across multiple accounts; the tool is personal-scale, not an Anthropic-endorsed product. #positioning

## Relations
- depends_on [[Hardware Targets]]
- drives [[Architecture Decision]]
