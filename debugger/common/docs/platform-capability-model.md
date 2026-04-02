# 平台能力模型

当前 `debugger` 只承认一套平台 contract：

- `coordination_mode = staged_handoff`
- `orchestration_mode = multi_agent`
- `live_runtime_policy = single_runtime_single_context`
- `hook_ssot = shared_harness`

含义：

- `rdc-debugger` 是唯一 public entrypoint，也是唯一 orchestrator。
- specialist 继续存在，但只能通过 staged handoff 接力，不再各自维持独立 live context。
- broker / coordinator 始终直接持有 live tools process。
- 同一 run 只允许一个 live session、一个 active context、一个 active ownership lease。
- specialist 只通过 ownership lease + broker action 请求访问 live runtime。
- local / remote 不再分叉成两套 runtime 语义；统一服从 shared harness 的单 runtime / 单 context 规则。
