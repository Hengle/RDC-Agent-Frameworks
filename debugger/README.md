# RenderDoc/RDC GPU Debug（调试框架）

`debugger/` 是 `RDC-Agent-Frameworks` 中面向 RenderDoc/RDC GPU 调试场景的专属 framework 根目录。

当前目标态已经收敛为单一主流程：

- 唯一协作模式是 `staged_handoff`
- 唯一编排模式是 `multi_agent`
- local / remote 统一遵守 `single_runtime_single_context`
- live tools process 由 shared broker/coordinator 直接持有
- specialist 只通过 broker action + ownership lease 消费 live runtime
- `session_id`、`context_id`、`active_event_id` 等 runtime id 只属于 broker runtime view，不作为跨阶段稳定主键传播
- 临时 Python / PowerShell / shell wrapper 封装 live CLI 一律视为流程偏差

正式流程固定为：`intent_gate -> entry_gate -> intake_gate -> triage -> dispatch/specialist loop -> skeptic -> curator -> final_audit`。

## 使用前提

开始使用 `debugger/` 之前，必须先完成：

1. 将仓库根目录 `debugger/common/` 整体拷贝到目标平台根目录的 `common/`
2. 将 `RDC-Agent-Tools` 根目录整包拷贝到目标平台根目录的 `tools/`
3. 运行 `python common/config/validate_binding.py --strict`，确认 package-local `tools/`、zero-install runtime、snapshot 与宿主入口文件全部对齐
4. 提供至少一份可导入 `.rdc`
5. 同时提供 `strict_ready` 的结构化 `fix reference`

未完成以上前置条件前：

- 缺少 `.rdc` 时必须以 `BLOCKED_MISSING_CAPTURE` 阻断
- 缺少 `strict_ready` fix reference 时必须以 `BLOCKED_MISSING_FIX_REFERENCE` 阻断
- 不得初始化 case/run，不得进入 live 调查

## 文档边界

- `common/AGENT_CORE.md`：`debugger` framework 的硬约束与运行原则
- `common/docs/`：唯一运行时共享文档入口
- `common/hooks/`：shared harness / broker / audit enforcement
- `docs/`：仅服务维护者的模板与 scaffold 说明，不是运行时共享资料区

## 平台模板使用方式

平台模板位于 `platforms/<platform>/`。标准用户工作流：

1. 选择目标平台模板目录
2. 覆盖 `common/`
3. 覆盖 `tools/`
4. 运行 `python common/config/validate_binding.py --strict`
5. 在对应宿主中打开该平台根目录
6. 统一从 `rdc-debugger` 发起请求；其他角色默认是 internal/debug-only specialist

说明：

- `CLI` / `MCP` 只表示工具入口模式，不改变 `staged_handoff + multi_agent + single_runtime_single_context` 的统一协作 contract
- shared harness 是唯一 enforcement SSOT；平台 hooks/runtime guard 只负责接入与转发
- accepted intake 后由 agent 创建 case/run，并导入 `.rdc` 到 `workspace/cases/<case_id>/inputs/captures/`