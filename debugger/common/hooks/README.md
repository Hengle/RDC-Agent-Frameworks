# RenderDoc/RDC GPU Debug · Quality Hooks 系统（质量 Hook）

Quality Hooks 系统将 Debugger 框架的质量门槛从“被建议的”提升为“被强制执行的”。

## 核心原则

- shared harness / broker 是唯一 enforcement SSOT
- 平台 native hooks / pseudo-hooks 只负责触发共享 harness，不承载第二套运行规则
- live runtime 调用只能通过官方 CLI 或 broker action
- 临时 Python / PowerShell / shell wrapper 封装 live CLI 一律视为流程偏差

## Shared Harness 入口

共享流程入口统一由 `utils/harness_guard.py` 提供：

- `preflight`
- `entry-gate`
- `accept-intake`
- `dispatch-readiness`
- `dispatch-specialist`
- `specialist-feedback`
- `final-audit`
- `render-user-verdict`

## 审计边界

`run_compliance.yaml` 负责裁决：

- gate / final artifacts 是否齐全
- `runtime_session` / `runtime_snapshot` / `ownership_lease` / `runtime_failure` 是否满足 broker-owned contract
- action chain 是否遵守 staged handoff 与 ownership 规则
- finalization 前是否仍有 active lease、blocked failure 或 continuity 问题