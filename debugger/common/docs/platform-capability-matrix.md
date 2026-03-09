# Platform Capability Matrix

This matrix mirrors `common/config/platform_capabilities.json`.

| Platform | Custom Agents | Skills | Hooks | MCP | Per-Agent Model | Handoffs | Coordination Mode | Packaging |
|---|---|---|---|---|---|---|---|---|
| Code Buddy | Yes | Yes | Yes | Yes | Explicit | Prompt-directed | `concurrent_team` | Plugin bundle |
| Claude Code | Yes | Shared-entry | Yes | Yes | Alias-level | Prompt-directed | `concurrent_team` | Project config plus subagents |
| Copilot CLI | Yes | Yes | Yes | Yes | Explicit | Limited | `staged_handoff` | CLI plugin |
| Copilot IDE | Yes | Yes (wrapper) | Documented boundary | Yes | Preferred | Native | `staged_handoff` | `.github/agents` plus MCP |
| Claude Desktop | No | No | No | Yes | Inherit-only | Workflow brief only | `workflow_stage` | Desktop MCP config |
| Manus | Workflow-only | No | No | No | Inherit-only | Workflow-level | `workflow_stage` | Workflow package |
| Codex | Yes | Yes | No | Yes | Config-file | Multi-agent | `concurrent_team` | Workspace-native |

## Notes

- `code-buddy`, `copilot-ide`, and `copilot-cli` are treated as explicit per-agent routing hosts in this repo.
- `claude-code` supports per-agent routing, but the available family is constrained by the host model pool.
- `claude-desktop` and `manus` are inherit-only downgrade hosts.
- `codex` keeps per-agent config files, but the approved routed family is currently GPT across all roles.
- Remote live-debug ownership still follows the shared runtime rule: one runtime owner per live chain.
