# Codex 工作区说明（工作区约束）

当前目录是 Codex 的 platform-local 模板。所有角色在进入 role-specific 行为前，都必须先服从 shared `common/` 约束。

强制规则：

- 未完成 `common/` 与 `tools/` 覆盖、且未通过 `validate_binding.py --strict` 前，不得开始依赖平台真相的工作
- 用户未提供 `.rdc` 时，必须以 `BLOCKED_MISSING_CAPTURE` 停止
- 用户未提供 `strict_ready` 的 fix reference 时，必须以 `BLOCKED_MISSING_FIX_REFERENCE` 停止
- 当前平台通过 `shared_harness + runtime_broker + ownership_lease + audit artifacts` 执行强门禁
- `.codex/runtime_guard.py` 必须先后裁决 `artifacts/entry_gate.yaml`、`artifacts/intake_gate.yaml`、`artifacts/runtime_session.yaml`、`artifacts/runtime_snapshot.yaml`、`artifacts/ownership_lease.yaml`、`artifacts/runtime_failure.yaml`
- capture import 与 case/run bootstrap 只能发生在 accepted intake 内
- `waiting_for_specialist_brief`、`redispatch_pending`、`skeptic_challenged` 期间，orchestrator 不得抢做 live investigation
- reopen / reconnect 可能导致新的 runtime generation；只有 broker 判定 continuity 成立时，才允许继续沿用既有调查链
- specialist 不得直接持有 live CLI / process，不得临时写 Python、PowerShell 或 shell wrapper 批处理 live runtime
