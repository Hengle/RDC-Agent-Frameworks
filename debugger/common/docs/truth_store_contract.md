# 真相存储契约

本文定义 debugger framework 在文件系统上的真相存储合同。

## 共享真相 Artifact

- `action_chain.jsonl`
  - append-only ledger
- `session_evidence.yaml`
  - adjudicated snapshot
- `run_compliance.yaml`
  - derived audit
- `runtime_session.yaml`
  - broker-owned live runtime truth
- `runtime_snapshot.yaml`
  - current runtime view snapshot
- `ownership_lease.yaml`
  - exclusive logical owner lease
- `runtime_failure.yaml`
  - runtime/process/context failure and recovery verdict

## Required Cross References

- `session_evidence.reference_contract.ref` 必须指回 `case_input.yaml#reference_contract`
- `session_evidence.fix_verification.ref` 必须指回 `artifacts/fix_verification.yaml`
- report 只能引用 ledger、snapshot、workspace artifact 或 active spec snapshot 中已有的结构化对象

## Action Chain Required Runtime Fields

以下事件必须携带：

- `runtime_generation`
- `snapshot_rev`
- `owner_agent_id`
- `lease_epoch`
- `continuity_status`
- `action_request_id`

## Forbidden Patterns

- 不得维护第二套 runtime topology / baton / lock / token 真相对象
- 不得通过临时 wrapper 封装 live CLI
- 不得把 preview 状态或人类观察窗口写成验证真相
- 不得在 unresolved runtime failure、active ownership lease、未关闭 challenge 时 finalize