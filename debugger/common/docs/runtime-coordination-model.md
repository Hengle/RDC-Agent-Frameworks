# RenderDoc/RDC GPU Debug Runtime Coordination Model

本文把 framework 的协作编排与 `rdx-tools` 的 runtime 真相拆开描述。

目标不是改写 `RDC-Agent-Tools` 的平台定义，而是把已经确认的约束上升为 framework 的显式协作规则。

## 1. 先区分入口层与 runtime 层

framework 必须把以下三层分开理解：

- `CLI adapter`
  - daemon-backed 本地命令入口。
  - 适用于能直接访问本地进程、文件系统与 daemon 的宿主。
- daemon owner
  - 长生命周期 runtime / context 持有层。
  - 是唯一的 live session / focus / recent artifacts / runtime owner。
- `MCP adapter`
  - 协议桥接入口。
  - 适用于无法直接进入本地环境的宿主，或用户明确要求按 `MCP` 接入的场景。

这意味着：

- `CLI` 与 `MCP` 的差异只在 adapter / 接入方式，不在执行真相。
- 不应把 `MCP` 写成所有 Agent 的默认主入口。
- 对可直达本地环境的宿主，framework 默认 local-first。
- 对不能直达本地环境的宿主，framework 默认 `MCP`。

## 2. 入口声明与前置阻断

进入平台真相相关工作前，Agent 必须先完成两件事：

1. 向用户说明当前采用的入口模式是 `CLI` 还是 `MCP`。
2. 校验该入口的前置条件是否已经满足。

固定阻断规则：

- local-first 路径下，如 `tools_root` 未配置或必需路径校验未通过，必须阻断。
- `MCP` 路径下，如宿主没有配置对应 MCP server，必须阻断。
- 阻断时不允许假设工具可用，也不允许继续编造平台能力面。

## 3. `context` 的真实含义

`context` 是 live runtime 隔离单元，不是“多个 agent 共享黑板”。

硬规则：

- 同一 `context` 下只允许维护一条当前 live 调试链路。
- 同一 `context` 不允许并行保有多套当前 `session_id` / `capture_file_id` / `active_event_id`。
- 若需要 local 并行调查，必须为每条 live 链路分配独立 `context/daemon`。

因此：

- 高能力本地宿主可以并行分工。
- 但并行分工不等于多个 agent 共享同一条 live session 并发操作。

## 4. 统一协作拓扑

framework 只使用以下三种 `coordination_mode`：

### `concurrent_team`

适用：高能力宿主，且本地链路可并行。

规则：

- Team Lead 可以把不同专家任务分派到不同 `context/daemon`。
- 每个 live investigator 自己独占一个 `context`。
- 若任务进入 remote 路径，仍然必须降级到 `single_runtime_owner`。

### `staged_handoff`

适用：宿主能表达 agent/handoff，但不适合多 live owners。

规则：

- sub agents 先提交 `investigation brief`、证据需求与下一轮目标。
- 当前 runtime owner 负责实际调用 `rd.*` 工具并回填证据。
- 任何轮次都不得让多个 agent 同时持有同一条 live 调试链路。

### `workflow_stage`

适用：仅支持 workflow 的降级宿主。

规则：

- 只允许阶段化串行推进。
- 不模拟实时 team handoff。
- 若任务需要动态 discovery 或多 live owners，必须切回更高能力平台。

## 5. Remote 统一规则

remote 一律采用：

- `remote_coordination_mode = single_runtime_owner`

含义：

- 任一时刻只有一个 live remote session owner 可以执行 `rd.*`。
- 其他专家角色只能提交 brief / question / evidence request。
- framework 不设计 remote 多 live session 并发协作流程。

这是一条 correctness 约束，不是把 `MCP` 误写成 remote 的唯一概念入口。

## 6. `runtime_baton` 合同

跨 agent、跨轮次、跨重连传递 live 调查上下文时，必须使用 `runtime_baton`。

固定字段：

```yaml
runtime_baton:
  coordination_mode: concurrent_team | staged_handoff | workflow_stage
  runtime_owner: team_lead | capture_repro_agent | <agent_id>
  context_id: "<live context id>"
  backend: local | remote
  entry_mode: cli | mcp
  capture_ref:
    rdc_path: "<path>"
    capture_file_id: "<optional short-lived handle>"
    session_id: "<optional short-lived handle>"
  rehydrate:
    required: true
    remote_connect:
      transport: renderdoc | adb_android
      host: "<host>"
      port: <port>
      options_ref: "<where bootstrap options are recorded>"
    frame_index: <int>
    active_event_id: <canonical event id or 0>
    causal_anchor_ref: "<event/draw/expression ref>"
    focus:
      pixel: "<optional>"
      resource_id: "<optional>"
      shader_id: "<optional>"
  evidence_refs:
    - "<session_evidence / action_chain / artifact ref>"
  task_goal: "<what the next executor must prove or falsify>"
```

硬规则：

- `capture_file_id`、`session_id`、`remote_id` 都只能当短生命周期提示。
- 它们不得成为 baton 的唯一真相源。
- baton 缺少 `task_goal`、`context_id`、`capture_ref.rdc_path`、`entry_mode` 或 `rehydrate.required=true` 时，不得视为可执行 baton。

## 7. Baton 的权威恢复来源

baton 的恢复真相源顺序固定为：

1. `causal_anchor` 与 `evidence_refs`
2. `action_chain.jsonl`、`session_evidence.yaml` 等 session artifacts
3. `rd.session.get_context` 快照

补充规则：

- `rd.session.get_context` 只作为恢复辅助，不是根因证据源。
- `rd.session.update_context` 只允许恢复 `focus.pixel`、`focus.resource_id`、`focus.shader_id`、`notes` 等 user-owned 字段。
- 禁止使用 `rd.session.update_context` 伪造 `session_id`、`capture_file_id`、`active_event_id` 或 `remote_id`。

## 8. Remote Rehydrate 顺序

remote baton 的完整恢复顺序固定如下：

1. 读取 baton 中的 `task_goal`、`evidence_refs`、`causal_anchor_ref`
2. 若 `entry_mode=mcp`，先确认宿主 MCP server 已配置；若未配置，直接阻断
3. 读取 catalog `prerequisites`，确认本轮调用序列满足前置状态
4. `rd.remote.connect`
5. `rd.remote.ping`
6. `rd.capture.open_file`
7. `rd.capture.open_replay(capture_file_id=..., options.remote_id=...)`
8. `rd.replay.set_frame`
9. 若 baton 中存在 canonical `active_event_id`，执行 `rd.event.set_active`
10. 使用 `rd.session.update_context` 恢复 `focus.pixel`、`focus.resource_id`、`focus.shader_id`、`notes`
11. 执行本轮调查，并把新增 evidence 回填到 artifacts 与 hypothesis board

默认规则：

- remote 下不做“专家各自重连抢 owner”。
- owner 可以跨轮次重建 session。
- 但 owner 身份在整个 remote case 内应保持稳定。
- 长操作期间，以 tools 提供的 progress/status 为准；不要把无输出等待当成“未知状态”。

## 9. 失败语义

若 baton 不能安全恢复，必须显式阻断，而不是依赖模型记忆继续工作。

允许的阻断语义：

- `BLOCKED_REANCHOR`
- `BLOCKED_RUNTIME_REHYDRATE`

典型触发条件：

- baton 缺少可复位的 `causal_anchor_ref`
- remote 无法重新建立 live endpoint
- `active_event_id` 不再可 round-trip
- evidence refs 与当前 session 重建结果冲突
- `entry_mode=mcp` 但宿主 MCP server 未配置

此时必须：

- 回报 Team Lead
- 补充缺失 artifact / evidence
- 或重新建立新的 anchor 与新的 baton
