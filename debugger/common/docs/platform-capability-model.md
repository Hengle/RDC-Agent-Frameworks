# Platform Capability Model

This document explains how the debugger framework separates host capability truth from routing policy.

## Capability Layers

The framework depends on two distinct layers:

- Host capabilities
  - `custom_agents`
  - `skills`
  - `hooks`
  - `mcp`
  - `handoffs`
  - `per_agent_model`
- Runtime contract
  - `context_state_model`
  - `local_parallelism`
  - `remote_handle_lifecycle`
  - `remote_coordination_mode`
  - `rehydration_contract`

Host capabilities answer "what the host can express."
Runtime contract answers "what is safe when driving live RenderDoc/RDC state."

## Routing Policy vs Host Capability

- `model_routing.json` defines which model family each role wants on each platform.
- `platform_capabilities.json` defines whether the host can render that routing natively, partially, or only through downgrade semantics.
- Generated platform wrappers must preserve role boundaries even when the host downgrades model control.

## Platform Classes Used By This Repo

- Explicit per-agent routing
  - `code-buddy`, `copilot-ide`, `copilot-cli`
- Host-limited per-agent routing
  - `claude-code`
- Inherit-only
  - `claude-desktop`, `manus`
- Single approved family
  - `codex`

## Required Downgrade Behavior

- Explicit per-agent platforms
  - Must render the routed model for each role.
- Host-limited per-agent platforms
  - May map routed roles to the closest host-native model family or alias.
- Inherit-only platforms
  - Must not advertise per-agent model control.
  - Must route all roles as `inherit`.
- Single approved family platforms
  - May keep per-agent config files, but the routed model family is intentionally unified.

## What Is Not Framework Truth

The following remain adapter/config concerns, not framework concepts:

- actual tools repository path
- actual MCP command line
- actual CLI convenience wrapper
- host plugin package naming

Those details belong in `platform_adapter.json`, `mcp_servers.json`, or generated host packaging, not in role prompts or routing policy prose.
