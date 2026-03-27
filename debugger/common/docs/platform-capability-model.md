# Platform Capability Model（平台能力模型）

本文解释 `common/config/platform_capabilities.json` 的字段语义。
`platform_capabilities.json` 是平台能力的唯一权威源；README、AGENTS、wrapper skill 和矩阵文档都只允许镜像它，不得另发明第二套口径。

## 1. 两层真相必须分开

平台能力必须拆成两层：

- 平台 agentic 能力
  - `coordination_mode`
  - `sub_agent_mode`
  - `peer_communication`
  - `agent_description_mode`
  - `dispatch_topology`
  - `local_live_runtime_policy`
  - `remote_live_runtime_policy`
- runtime/backends 能力
  - `local_support`
  - `remote_support`
  - `supported_entry_modes`
  - `supported_backends`
  - `remote_coordination_mode`
  - `enforcement_layer`

Tools 只定义 transport/runtime ceiling；Frameworks 才定义平台如何利用这层 ceiling。

固定口径：

- sub agent 支持不等于 team agents
- sub agent runtime 支持不等于 team agents
- sub agent runtime 支持不等于支持静态 `json+md` / 独立 agent 文件预声明
- `staged_handoff` 是 hub-and-spoke 多轮接力
- `remote` 可以支持 multi-agent coordination，但永远不支持 multi-owner live runtime

## 2. Agentic 能力字段

### `sub_agent_mode`

- `team_agents`
  - 子 agent 之间可直接通信。
  - 当前只有 `claude-code` 与 `code-buddy` 属于这一档。
- `puppet_sub_agents`
  - 子 agent 可存在稳定 specialist 角色，但不能彼此直连；所有协调经主 agent 中转。
- `instruction_only_sub_agents`
  - 宿主支持 sub agent runtime，但不承载独立 agent 描述文件；需要子 agent 时，只能由主 agent 在实例化时注入 instruction。

### `agent_description_mode`

- `independent_files`
  - 支持用平台原生文件形态预声明 agent / skill。
- `spawn_instruction_only`
  - 不支持静态预声明 agent 壳；子 agent 只能在运行时临时注入 instruction。

### `peer_communication`

- `direct`
  - specialist 之间可直接交换上下文。
- `via_main_agent`
  - specialist 之间不直连；主 agent 是唯一通信与裁决中枢。
- `none`
  - 不建立稳定的 peer 网络；specialist 由主 agent 串行实例化并回填阶段 brief。

### `dispatch_topology`

- `mesh`
  - team agents 允许直接协作。
- `hub_and_spoke`
  - `staged_handoff` 的权威拓扑；主 agent 负责任务拆分、证据汇总、冲突裁决和下一轮 brief 重组。
- `workflow_serial`
  - `workflow_stage` 的权威拓扑；specialist 可被串行实例化，但不形成稳定 specialist 网络。

### `local_live_runtime_policy`

- `multi_context_multi_owner`
  - 只适用于 `team_agents + concurrent_team + local`。
- `multi_context_orchestrated`
  - 适用于 `puppet_sub_agents + staged_handoff + local`；多个 specialist 可各持独立 context，但协调必须经 `rdc-debugger`。
- `single_runtime_owner`
  - 适用于 `workflow_stage` local 以及其他被强制串行的场景。

### `remote_live_runtime_policy`

- 当前统一固定为 `single_runtime_owner`。
- 这不禁止 multi-agent coordination，只禁止多个 agent 并行持有 live remote runtime。

## 3. 协作模式的精确定义

### `concurrent_team`

- 只适用于 `team_agents` 宿主。
- local 下可利用 multi-context runtime ceiling。
- remote 仍必须收敛到单 owner。

### `staged_handoff`

- 不是单 agent 串行。
- 它是主 agent 中枢式的多 specialist 多轮接力。
- specialist 之间不能直连，但可以通过主 agent 的重新裁决形成 N+1 轮 brief、probe request 与 evidence 回填。
- 在 local 下可以是 `multi_context_orchestrated`。
- 在 remote 下仍允许多 agent 协作，但 live runtime owner 只能有一个。

### `workflow_stage`

- 这是阶段化串行流。
- specialist 可存在，但必须由主 agent 串行实例化与串行回收。
- 不模拟实时 team-agent handoff。
- `serial_only` remote 只能落在这一档。

## 4. Support 与 Enforcement

### `local_support`

- `verified`
- `degraded`
- `unsupported`

### `remote_support`

- `verified`
- `serial_only`
- `unsupported`

其中 `serial_only` 表示 remote 是正式支持路径，但 live runtime 只能按 `workflow_stage + single_runtime_owner` 或等价单 owner 语义推进。

### `enforcement_layer`

- `hooks`
  - 宿主可在 host-side 提前阻断。
- `runtime_owner`
  - 主要依赖 Tools 的 owner/context/baton surface 与 Frameworks 的 gate/audit。
- `audit_only`
  - 无法做 host-side 拦截，只能依赖显式 artifacts 与审计。

## 5. 平台默认矩阵解释

- `claude-code` / `code-buddy`
  - `concurrent_team + team_agents + multi_context_multi_owner`
- `codex` / `cursor` / `copilot-cli` / `copilot-ide`
  - `staged_handoff + puppet_sub_agents + multi_context_orchestrated`
- `manus` / `claude-desktop`
  - `workflow_stage + instruction_only_sub_agents + single_runtime_owner`

所有平台都要遵守：

- 默认 specialist dispatch 是 framework 正常路径
- 只有 `claude-code` / `code-buddy` 可被表述为 `team_agents`
- `remote_coordination_mode = single_runtime_owner`
- `remote` 不允许多个 live owners 共享同一条 runtime
- 用户若显式要求不要 multi-agent context，应进入 `single_agent_by_user`，这属于用户选择，不属于宿主降级
