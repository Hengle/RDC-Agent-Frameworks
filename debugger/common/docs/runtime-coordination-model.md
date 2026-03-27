# RenderDoc/RDC Debugger Runtime Coordination Model（运行时协作模型）

本文只定义 debugger framework 如何消费 Tools 的 runtime ceiling，并把它落成可执行、可审计的协作合同。

## 1. 先区分四层概念

- `entry_mode`
  - `CLI` 或 `MCP`
- `backend`
  - `local` 或 `remote`
- `coordination_mode`
  - `concurrent_team`、`staged_handoff`、`workflow_stage`
- `orchestration_mode`
  - `multi_agent`、`single_agent_by_user`

它们不是同一维度。

## 2. Context 与 live runtime 的硬约束

- `context` 是 live runtime 隔离单元，不是“多个 agent 共享的黑板”。
- 同一 `context` 任一时刻只允许维护一条当前 live 调试链。
- 并行 case 也必须拆成独立 `context/daemon`。
- 并行 case 只能共享仓库，不得共享同一条 live `context`。
- 一个 `context` 可以保留多条 session 记录，但这不等于允许多个 specialist 共享同一条 live runtime。

## 3. 三种 coordination mode

### `workflow_stage`

- 阶段化串行推进。
- specialist 可被主 agent 串行实例化，但不形成稳定 specialist 网络。
- 不模拟实时 team-agent handoff。

### `staged_handoff`

- 不是单 agent 串行切换。
- 它是主 agent 作为通信与裁决中枢的多 specialist 多轮接力。
- specialist 先提交 brief、evidence request、下一轮 probe 目标。
- 主 agent 负责重组证据、解决冲突、决定 redispatch。
- specialist 之间不直连，所有依赖都经主 agent 中转。
- local 下允许 `multi_context_orchestrated`：多个 specialist 可各持独立 context，但不能绕过主 agent 做 peer coordination。

### `concurrent_team`

- specialist 可以直接通信。
- 只有 team-agents 宿主才允许进入这一档。
- local 下可以利用 `multi_context_multi_owner`。

## 4. Local / Remote live policy

权威规则：

- `remote_coordination_mode = single_runtime_owner`
- `remote` 一律只允许一个 live runtime owner
- `workflow_stage` 一律采用 `single_runtime_owner`
- `staged_handoff remote` 一律采用 `single_runtime_owner`
- `staged_handoff local` 采用 `multi_context_orchestrated`
- 只有 `local + concurrent_team` 才允许 `multi_context_multi_owner`

换句话说：

- `single_runtime_owner != single_agent_flow`
- `remote` 可以支持 multi-agent coordination，但不允许 multi-owner live runtime
- `staged_handoff` 仍然允许多 specialist、多轮 handoff、多轮裁决
- 它只是把 peer coordination 收敛到主 agent，把 remote live ownership 收敛到单 owner

## 5. Orchestration Mode

### `multi_agent`

- 这是默认模式。
- 所有平台默认都应通过 specialist dispatch 进入调查、验证、审查与报告链。
- `rdc-debugger` 负责 orchestration，不直接以 orchestrator 身份执行 investigator live `rd.*`。

### `single_agent_by_user`

- 只有用户显式要求不要 multi-agent context 时才允许进入。
- 这不是 degraded path。
- 必须显式落盘到 `entry_gate.yaml` 与 `runtime_topology.yaml`：
  - `orchestration_mode: single_agent_by_user`
  - `single_agent_reason: user_requested`
- `runtime_topology.yaml` 还必须同步记录：
  - `delegation_status: single_agent_by_user`
  - `fallback_execution_mode: wrapper | local_renderdoc_python`
  - `degraded_reasons` 只用于 direct-runtime wrapper fallback，不再用于 surrogate specialist / curator
- 进入该模式后，主 agent 必须先向用户说明不会分派 specialist。

## 6. Delegation Patience / Progress Contract

- specialist dispatch 后必须有结构化阶段回报，不能无限黑盒。
- `rdc-debugger` 必须持续把这些回报汇总到用户可观察状态源，例如 `hypothesis_board.yaml`。
- dispatch 成功后，主 agent 必须先把当前状态切到“等待 specialist 首次 brief”，不得因短时 silence 自行抢活。

统一最小 progress brief 字段：

- `active_owner`
- `current_task`
- `working_hypothesis`
- `evidence_collected`
- `blocking_issues`
- `next_actions`
- `status`

统一阶段状态：

- `accepted`
- `current_task`
- `blocking_issues`
- `completed_handoff`

统一等待预算：

- 首次 brief：60 秒内应有阶段确认
- 持续执行中：超过 5 分钟无阶段更新，进入 `BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT` 或等价阻断状态

统一 reclaim 规则：

- 短时 silence 不等于 dispatch 失败
- specialist feedback timeout 只允许导致 block / 重新确认 / redispatch
- 不允许因为 impatience 自动退回到 orchestrator 自执行

## 7. Runtime Baton 合同

跨 agent、跨轮次、跨重连传递 live 调查上下文时：

- 必须使用 `runtime_baton`
- `rd.session.resume` / `rd.session.rehydrate_runtime_baton` 必须声明 `baton_ref`
- 对 `multi_context_orchestrated`，跨 context 的 live 续接、焦点转交或 owner 变更都必须有 baton
- baton 只承载 live 恢复所需事实，不改变 remote 单 owner 规则

## 8. Framework 对 Tools runtime ceiling 的消费方式

Tools 只定义：

- local runtime ceiling 可到 `multi_context_multi_owner`
- remote runtime ceiling 固定为 `single_runtime_owner`

Frameworks 负责再根据平台能力裁决最终政策：

- `team_agents + concurrent_team + local`
  - 才能把 ceiling 用成 `multi_context_multi_owner`
- `puppet_sub_agents + staged_handoff + local`
  - 收敛成 `multi_context_orchestrated`
- `instruction_only_sub_agents + workflow_stage`
  - 形成串行 specialist 流，而不是无 specialist

## 9. Finalization

- `curator_agent` 在 `multi_agent` 下仍然是 finalization-required。
- `single_agent_by_user` 下，主 agent 负责最终报告输出，但必须在 action chain 与 runtime topology 中显式体现该模式。
- 不存在“宿主不允许起 curator，于是 surrogate curator 代写”的 shared contract。
