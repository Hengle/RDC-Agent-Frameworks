# RenderDoc/RDC GPU Debug 框架核心约束

本文档是 `RenderDoc/RDC GPU Debug` framework 的全局硬约束入口。

## 1. 平台真相与 framework 真相边界

`RDC-Agent Tools` 负责平台真相：tool catalog、runtime 生命周期、session/context/event 语义与错误面。

framework 只负责：

- `intent_gate`
- `Plan / Intake Phase -> debug_plan`
- `entry_gate`、`intake_gate`
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

`Plan / Intake Phase` 不产出 run 级 runtime artifact，也不创建 case/run。

严格 execution 从 `entry_gate` 开始；只有进入 `Audited Execution Phase` 后，run 级 live runtime 真相才允许落在以下 artifacts：

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

## 5. 主 Agent 硬边界约束 (VIOLATION = PROCESS_HALT)

### 5.1 状态锁定机制 (EXECUTION_LOCK)

当 `hypothesis_board.yaml` 中的 `current_phase` 属于以下任一值时，触发 **EXECUTION_LOCK**：

- `waiting_for_specialist_brief`
- `redispatch_pending`
- `specialist_reinvestigation`
- `skeptic_challenged`

**EXECUTION_LOCK 激活时的硬件阻断清单**：

| 操作类型 | 状态 | 说明 |
|---------|------|------|
| 调用任何 live runtime tool | [BLOCKED] | 包括但不限于 `rdc capture`, `rdc replay`, `rdc analyze` |
| 直接操作 broker-owned process | [BLOCKED] | 禁止绕过 broker 直接持有 process handle |
| 修改 session-level runtime state | [BLOCKED] | 禁止修改 context、event、resource 状态 |
| 执行临时 wrapper 脚本 | [BLOCKED] | 禁止通过 Python/PowerShell/shell 封装 live CLI |
| 替 specialist 补充调查 | [BLOCKED] | 禁止在 specialist 返回前进行平行调查 |
| 抢写 specialist 证据文件 | [BLOCKED] | 禁止覆盖 `session_evidence.yaml` 等 specialist 产出 |

### 5.2 允许操作白名单 (EXCLUSIVE LIST)

LOCK 状态下 **唯一** 允许的操作：

1. **读取 brief / challenge**
   - 读取 specialist 返回的 `brief.yaml`
   - 读取 skeptic 发出的 `challenge.yaml`

2. **更新 hypothesis_board.yaml 的 blocker 字段**
   - 记录 `blocker_type`: `SPECIALIST_TIMEOUT`, `INCONCLUSIVE_BRIEF`, `SKEPTIC_CHALLENGE`
   - 记录 `blocker_reason` 和 `next_action`

3. **执行 timeout / redispatch / request-more-input 决策**
   - 判定 specialist 是否超时
   - 决定是否 redispatch 到同一 specialist 或切换 specialist
   - 向用户请求补充输入

4. **记录决策到 action_chain.jsonl**
   - 仅记录 orchestration 决策，不记录调查动作

5. **当 specialist 长时间无回报时，明确进入 `BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT` 或等价阻断状态**
   - 设置 `blocker_type: SPECIALIST_FEEDBACK_TIMEOUT`
   - 触发 redispatch 或 escalation 流程

### 5.3 违规检测与后果

**违规判定标准**：

- 在 LOCKED 状态下执行了任何非白名单操作
- 通过临时 wrapper 间接执行被阻断操作
- 以"辅助"、"验证"名义替 specialist 补充证据

**违规后果**：

| 后果级别 | 动作 | 记录位置 |
|---------|------|---------|
| 立即阻断 | 当前 action 被强制终止 | `action_chain.jsonl` |
| 流程标记 | 标记为 `PROCESS_DEVIATION_MAIN_AGENT_OVERREACH` | `action_chain.jsonl`, `hypothesis_board.yaml` |
| 审计记录 | 记录违规详情：触发条件、尝试操作、调用栈 | `audit/process_deviation/` |
| 后续处理 | 根据 `deviation_severity` 决定是否强制进入 `curator` 复核 | `hypothesis_board.yaml` |

**严重级别定义**：

- `critical`: 直接操作 live runtime 或替 specialist 写证据 → 强制 curator 介入
- `major`: 尝试执行被阻断操作但未成功 → 记录并警告
- `minor`: 边界模糊操作 → 记录并提示

### 5.4 快速检查清单 (MUST CHECK BEFORE ACTION)

在每次执行操作前，必须完成以下检查：

```markdown
□ 当前 current_phase 是什么？
  □ 检查 `hypothesis_board.yaml` 中的 `current_phase` 字段

□ 如果处于 LOCKED 状态，我的操作在白名单中吗？
  □ 对照 5.2 节 EXCLUSIVE LIST 确认

□ 我是否正在尝试"辅助"specialist？
  □ 任何以"验证"、"确认"、"补充"为名义的调查都属于违规

□ 是否涉及 live runtime？
  □ 检查是否调用任何 runtime tool 或 wrapper

□ 是否修改了 specialist 的产出物？
  □ 检查是否写入 `session_evidence.yaml` 等 specialist 文件

□ 如果以上任一答案为"是"，立即停止并记录 blocker
```

**强制执行**：

- 每次 `current_phase` 变更后，必须在 `action_chain.jsonl` 中记录 CHECKPOINT_PASSED 或 CHECKPOINT_FAILED
- 未通过检查清单的操作将被 framework 层拒绝执行

## 6. Sub-Agent 分层

Plan 阶段默认通过以下轻量 sub-agent 收敛输入：

- `clarification_agent`
- `reference_contract_agent`
- `plan_compiler_agent`

它们的硬边界是：

- 不创建 case/run
- 不接触 live runtime
- 不写 `action_chain.jsonl`、`session_evidence.yaml`、`skeptic_signoff.yaml`
- 不进入 broker-owned execution flow

Execution 阶段只有以下节点明确必须经由 sub-agent：

- `triage`
- 所有正式 `specialist`
- `skeptic`
- `curator`

以下节点属于控制面，不 agent 化：

- `entry_gate`
- `accept_intake`
- `intake_gate`
- `dispatch_readiness`
- `dispatch_specialist`
- `specialist_feedback`
- `final_audit`
- `render_user_verdict`

## 7. 失败与恢复策略

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

## 8. Session 真相方向

当前仓库仍保留 `.current_session` 兼容路径，但它不应继续被视为新任务默认真相来源。

后续实现应统一转向以下优先顺序：

1. `run_root`
2. `run.yaml.session_id`
3. `debug_plan`

目标是避免新 session 因共享 marker 而看到其它 case/run 产生的历史现场。
