# Codex Template

当前目录是 Codex 的 workspace-native 模板。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

使用方式：

1. 将仓库根目录 debugger/common/ 整体拷贝到当前平台根目录的 common/，覆盖占位内容。
2. 打开当前目录作为 Codex workspace root。
3. AGENTS.md、.agents/skills/、.codex/config.toml 与 .codex/agents/*.toml 只允许引用当前平台根目录的 common/。

约束：

- common/ 默认只保留占位骨架；正式共享正文仍由顶层 debugger/common/ 提供，并由用户显式拷入。
- multi_agent 当前按 experimental / CLI-first 理解，但共享规则与 role config 已完整生成。
