# RenderDoc/RDC Debugger Runtime Coordination Model（运行时协作模型）

本文只定义 debugger framework 如何消费 Tools 的 runtime ceiling，并把它落成可执行、可审计的协作合同。

## 1. 先区分三层概念

- `entry_mode`
  - `CLI` 或 `MCP`
- `backend`
  - `local` 或 `remote`
- `coordination_mode`
  - `concurrent_team`、`staged_handoff`、`workflow_stage`

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
- 可以有临时 worker，但不形成稳定 specialist 网络。
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
- `staged_handoff` 仍然允许多 specialist、多轮 handoff、多轮裁决
- 它只是把 peer coordination 收敛到主 agent，把 remote live ownership 收敛到单 owner

## 5. Runtime baton 合同

跨 agent、跨轮次、跨重连传递 live 调查上下文时：

- 必须使用 `runtime_baton`
- `rd.session.resume` / `rd.session.rehydrate_runtime_baton` 必须声明 `baton_ref`
- 对 `multi_context_orchestrated`，跨 context 的 live 续接、焦点转交或 owner 变更都必须有 baton
- baton 只承载 live 恢复所需事实，不改变 remote 单 owner 规则

## 6. Framework 对 Tools runtime ceiling 的消费方式

Tools 只定义：

- local runtime ceiling 可到 `multi_context_multi_owner`
- remote runtime ceiling 固定为 `single_runtime_owner`

Frameworks 负责再根据平台能力裁决最终政策：

- `team_agents + concurrent_team + local`
  - 才能把 ceiling 用成 `multi_context_multi_owner`
- `puppet_sub_agents + staged_handoff + local`
  - 收敛成 `multi_context_orchestrated`
- `instruction_only_sub_agents + workflow_stage`
  - 只能形成阶段化串行流
