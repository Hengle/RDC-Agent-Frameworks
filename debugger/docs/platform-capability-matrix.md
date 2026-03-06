# Platform Capability Matrix

本文按宿主平台能力定义各平台适配的“最佳实现上限”，避免把所有宿主都简化成 prompt 镜像。

| Platform | Custom Agents/Subagents | Skills | Hooks | MCP | Per-Agent Model | Nested Delegation / Handoffs | Packaging |
|---|---|---|---|---|---|---|---|
| Code Buddy | Yes | Yes | Yes | Yes | Yes | Yes | Plugin bundle |
| Claude Code | Yes | Partial / local docs | Yes | Yes | Alias-level | Yes | Project config + subagents |
| Copilot CLI | Yes | Yes | Yes | Yes | Inherit-first | Limited | CLI plugin |
| Copilot IDE | Yes | Plugin guidance | Yes | Yes | Preferred models | Yes | IDE custom agents / plugin |
| Claude Work | Local contract only | Local docs | Unclear / weak | Yes | Unclear | Weak | Local plugin contract |
| Manus | Workflow-level only | No first-class skill layer | Workflow gate | Possible by docs/manual | Workflow-level | Workflow-level | Workflow package |

## 解释

- `Code Buddy` 是当前最高完成度参考实现。
- `Claude Code` 应升级到 `subagents + hooks + MCP + model alias`。
- `Copilot` 不能再混成一个目录，至少要拆成 `CLI` 与 `IDE` 两条适配线。
- `Claude Work` 与 `Manus` 暂按次优宿主处理，不把它们当成满配基线。

