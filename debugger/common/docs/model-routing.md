# Model Routing

This document defines the single source of truth for role-to-model routing in the debugger framework.

## Source of Truth

- `common/config/model_routing.json`
  - Owns model capability requirements, platform classes, and per-profile platform routing.
- `common/config/role_policy.json`
  - Owns reasoning effort, verbosity, tool policy, hook policy, and delegation.
- `debugger/scripts/sync_platform_scaffolds.py`
  - Renders the shared truth into host-native wrappers, config files, and plugin metadata.

No platform wrapper may invent its own model mapping. No second model-routing table may exist in `role_policy.json` or in generated host artifacts.

## Global Model Requirements

All debugger roles inherit the same baseline model constraints:

- Native multimodal support is required.
- The model must be suitable for texture and framebuffer driven visual analysis.
- Long-context support is required.
- A 1M context window is preferred whenever the host/provider supports it.

These constraints exist because debugger sessions routinely move texture exports, framebuffer evidence, shader source, IR output, JSON tool payloads, and report artifacts through the same conversation.

## Role Priorities

- `orchestrator`
  - Prioritizes planning depth, branching control, imagination, and verdict gating.
- `investigator`
  - Prioritizes evidence handling, long evidence chains, and medium-latency deep inspection.
- `verifier`
  - Prioritizes logic rigor, adversarial review, and counterfactual pressure testing.
- `reporter`
  - Prioritizes writing quality, knowledge curation, and stakeholder-facing web/report composition.

## Platform Classes

- Explicit per-agent routing
  - `code-buddy`, `copilot-ide`, `copilot-cli`
- Host-limited per-agent routing
  - `claude-code`
- Inherit-only hosts
  - `claude-desktop`, `manus`
- Single approved family per-agent routing
  - `codex`

## Current Routing Policy

- `code-buddy`, `copilot-ide`, `copilot-cli`
  - `orchestrator` -> latest Opus
  - `investigator` -> latest Sonnet
  - `verifier` -> latest GPT
  - `reporter` -> latest Gemini
- `claude-code`
  - `orchestrator` -> Opus
  - `investigator` -> Sonnet
  - `verifier` -> Opus
  - `reporter` -> Sonnet
- `claude-desktop`, `manus`
  - all roles -> `inherit`
- `codex`
  - all roles -> latest GPT
  - role differentiation happens through reasoning and verbosity, not a different model family

## Constraints

- Generated platform files must always come from `model_routing.json`.
- Inherit-only platforms must not carry dead explicit model strings in routing.
- Platforms that render per-agent models must surface the model selected by the routing table.
- Platforms that cannot render per-agent models may keep role boundaries and workflow boundaries, but must not pretend to expose unsupported model controls.
