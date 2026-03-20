# Codex Template（平台模板）

当前目录是 Codex 的 workspace-native 模板。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

入口规则：

- 当前宿主可直接访问本地进程、文件系统与 workspace，默认采用 local-first。
- 默认入口是 daemon-backed `CLI`；当前宿主的 `CLI` 与 `MCP` 都依赖同一 daemon-owned runtime / context。
- 只有用户明确要求按 `MCP` 接入时，才切换到 `MCP`。
- 任务开始时，Agent 必须向用户说明当前采用的是 `CLI` 还是 `MCP`。
- 若用户要求 `MCP`，但宿主未配置对应 MCP server，必须直接阻断并提示配置。

使用方式：

1. 将仓库根目录 `debugger/common/` 整体拷贝到当前平台根目录的 `common/`，覆盖占位内容。
2. 在复制后的平台包根目录 `common/config/platform_adapter.json` 中配置 `paths.tools_root`；JSON 文件中的 Windows 路径必须写成前斜杠或转义反斜杠。
3. 确认 `validation.required_paths` 在 `<resolved tools_root>/` 下全部存在。
4. 运行 `python common/config/validate_binding.py --strict`，确认 `tools_root`、snapshot、宿主入口文件与共享文档全部对齐。
5. 正式发起 debug 前，用户必须在当前对话提交至少一份 `.rdc`。
6. 使用当前平台根目录同级的 `workspace/` 作为运行区。
7. 完成覆盖后，打开当前目录作为 Codex workspace root。
8. 正常用户请求从 `team_lead` 发起；其他 specialist 默认是 internal/debug-only。
9. `AGENTS.md`、`.agents/skills/`、`.codex/config.toml` 与 `.codex/agents/*.toml` 只允许引用当前平台根目录的 common/。

约束：

- `common/` 默认只保留一个占位文件；正式共享正文仍由顶层 `debugger/common/` 提供，并由用户显式拷入。
- 未完成 `debugger/common/` 覆盖前，当前平台模板不可用。
- 未完成 `platform_adapter.json` 配置或 `tools_root` 校验前，Agent 必须拒绝执行依赖平台真相的工作。
- 当前工具 snapshot 必须与 `RDC-Agent-Tools` 当前 catalog 完整对齐，并覆盖 `rd.vfs.*`、扩展 `rd.session.*`、`rd.core.*` discovery/observability，以及 bounded event-tree 读取语义。
- 未提供 `.rdc` 时，Agent 必须以 `BLOCKED_MISSING_CAPTURE` 直接阻断，不得初始化 case/run 或继续 triage、investigation、planning。
- `workspace/` 预生成空骨架；真实运行产物在平台使用阶段按 case/run 写入。
- remote / live bridge / rehydrate 当前只保留为 `experimental` 协作路径；除非另有平台级验证说明，否则它不属于当前正式支持能力。
- 当前宿主没有 native hooks；只有生成 `artifacts/run_compliance.yaml` 且 `status=passed` 后，结案才算合规。

Sub-Agent 工作模型：

Codex sub-agent 现已正式可用。本平台采用 `staged_handoff` coordination mode，对应以下工作模型：

- `team_lead` 是唯一入口与 runtime_owner，负责 intake、分派、质量门裁决。
- **Sub-agents 之间不具备直接通信能力**，所有跨 agent 协调通过 workspace artifacts 间接完成。
- 标准分派顺序：`team_lead` → `triage_agent` → `capture_repro_agent` → specialists（`pass_graph_pipeline`、`pixel_forensics`、`shader_ir`、`driver_device`）→ `skeptic_agent` → `curator_agent`。
- 每个 specialist 将结果写入 `workspace/cases/<case_id>/runs/<run_id>/` 指定位置后返回，`team_lead` 读取后继续分派。
- Specialist 不得直接分派其他 specialist。
