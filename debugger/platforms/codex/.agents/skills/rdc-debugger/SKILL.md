---
name: rdc-debugger
description: Use for the RenderDoc/RDC GPU debugger framework when the user wants GPU rendering defect diagnosis, root-cause analysis, regression explanation, or fix verification from one or more `.rdc` captures in a compatible workspace.
metadata:
  short-description: Enter the RenderDoc/RDC GPU debugger workflow
---

# RDC Debugger Main Skill Wrapper

This file is the public main skill entry for Codex in the RenderDoc/RDC debugger framework.

Stay in ordinary conversation mode unless the user explicitly invokes `rdc-debugger`.

After `rdc-debugger` is invoked, this skill owns:

- `intent_gate`
- preflight
- missing-input collection
- intake normalization
- case/run initialization
- specialist dispatch
- stage progression
- verdict gating

This wrapper only points to the current workspace `common/` content:

- `common/skills/rdc-debugger/SKILL.md`
- validate `common/config/platform_adapter.json` before platform-truth work
- use `common/config/platform_capabilities.json` for the current `coordination_mode` and degradation boundaries

Preconditions:

1. `common/AGENT_CORE.md` exists
2. `tools/spec/tool_catalog.json` exists
3. The workspace is a RenderDoc/RDC debugger platform template

Blocking rules:

- Do not use this platform template until `debugger/common/` has been copied into the platform-root `common/`
- If the user has not provided an importable `.rdc`, stop at `BLOCKED_MISSING_CAPTURE`

Runtime case/run artifacts and second-layer reports are written under the platform-root `workspace/`.
