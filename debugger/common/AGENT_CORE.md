# RenderDoc/RDC GPU Debug 框架核心约束

本文档是 `RenderDoc/RDC GPU Debug` framework 的全局硬约束入口。

## 1. 平台真相与 framework 真相边界

`RDC-Agent Tools` 负责平台真相：tool catalog、runtime 生命周期、session/context/event 语义与错误面。

framework 只负责：

- `intent_gate`、`entry_gate`、`intake_gate`
- `triage -> specialist -> skeptic -> curator -> final_audit` 的阶段推进
- 共享 artifact / audit contract
- broker-owned staged handoff 的角色边界

## 2. 唯一运行模型

当前 framework 只承认以下模型：

- `coordination_mode = staged_handoff`
- `orchestration_mode = multi_agent`
- `live_runtime_policy = single_runtime_single_context`
- shared harness / broker 是唯一 enforcement SSOT

local 与 remote 都不再拥有不同的多 context 语义。所有平台都统一为：

- 同一 run 只有一个 live runtime
- 同一 live runtime 同时只有一个 active session
- 同一 active session 同时只有一个 active context
- broker 始终直接持有 tools process
- 被 dispatch 的 specialist 只持有逻辑 owner lease，不直接持有 process

## 3. Runtime SSOT Artifacts

run 级 live runtime 真相只允许落在以下 artifacts：

- `artifacts/runtime_session.yaml`
- `artifacts/runtime_snapshot.yaml`
- `artifacts/ownership_lease.yaml`
- `artifacts/runtime_failure.yaml`

结案所需 gate / final artifacts 仍为：

- `entry_gate.yaml`
- `intake_gate.yaml`
- `fix_verification.yaml`
- `skeptic_signoff.yaml`
- `run_compliance.yaml`

## 4. Handle 与跨阶段引用规则

跨阶段稳定主键只允许使用 framework ids，例如：`case_id`、`run_id`、`investigation_round`、`brief_id`、`evidence_id`、`action_request_id`。

以下 runtime ids 只属于 broker runtime view，不得作为跨阶段稳定主键传播：

- `session_id`
- `context_id`
- `active_event_id`
- 临时 resource / shader / pipeline handles

specialist brief、skeptic challenge、curator 结案都只允许引用：

- framework artifact ids
- `runtime_generation + snapshot_rev`

## 5. 主 Agent 越权属于流程偏差

当 workflow 处于 `waiting_for_specialist_brief`、`redispatch_pending`、`specialist_reinvestigation` 或 `skeptic_challenged` 时，`rdc-debugger` 只允许：

- 读取 brief / challenge
- 更新 `hypothesis_board.yaml`
- 记录 blocker
- 做 timeout / redispatch / request-more-input 决策

禁止：

- 继续 live 调查
- 替 specialist 补调查
- 抢写 specialist 证据
- 通过临时 wrapper 批处理 live CLI

违反时必须在 `action_chain.jsonl` 记为 `process_deviation`。

## 6. 失败与恢复策略

失败分类固定为：

- `TOOL_CONTRACT_VIOLATION`
- `TOOL_RUNTIME_FAILURE`
- `TOOL_CAPABILITY_LIMIT`
- `INVESTIGATION_INCONCLUSIVE`

恢复策略固定为：

- 只有 `TOOL_RUNTIME_FAILURE` 允许 broker 做一次受控恢复
- 恢复成功后 `runtime_generation + 1`
- 连续性只允许判定为 `reattached_equivalent`、`reattached_shifted`、`reattach_failed`
- 无法证明连续性时必须 blocker