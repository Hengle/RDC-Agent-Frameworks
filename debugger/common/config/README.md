# Platform Adapter Config

This directory holds the shared config truth that bridges the debugger framework to generated platform templates.

## Rules

- `debugger/common/` is the only long-lived shared source tree.
- `debugger/platforms/*` are generated platform artifacts.
- Platform-local wrappers may only reference the platform-local `common/` directory after the shared tree is copied in.
- Tools repository paths, MCP startup commands, and CLI adapter details are adapter concerns, not framework truth.

## Files

- `platform_adapter.json`
  - fail-closed tools-root entrypoint
- `role_manifest.json`
  - role inventory, shared prompt mapping, shared skill mapping, and platform file names
- `role_policy.json`
  - reasoning effort, verbosity, tool policy, hook policy, and delegation
  - must not contain per-platform model routing
- `model_routing.json`
  - single source of truth for model capability requirements, platform classes, and role-to-platform model routing
- `mcp_servers.json`
  - logical MCP server definitions
- `platform_capabilities.json`
  - host capability truth, downgrade semantics, and required generated paths
- `platform_targets.json`
  - generation targets, directory layout, and render surfaces

## Usage

1. Set `paths.tools_root` in `platform_adapter.json`.
2. Validate every entry in `validation.required_paths`.
3. Reject debugger execution when validation fails.
4. Keep model routing in `model_routing.json` only.

Generated wrappers, plugin files, and role configs must be re-synced from this directory rather than patched by hand.
