---
name: rdc-debugger
description: Public main skill for the RenderDoc/RDC GPU debugger framework. Use when the user wants defect diagnosis, root-cause analysis, regression explanation, or fix verification from one or more `.rdc` captures. This skill owns intent gate classification, preflight, missing-input collection, fix-reference readiness gating, intake normalization, case/run initialization, broker-owned specialist dispatch, redispatch, timeout handling, and verdict gating.
---

# RDC 调试器

你必须按固定阶段链推进：

1. `intent_gate`
2. `entry_gate`
3. `accept_intake / intake_gate`
4. `triage`
5. `dispatch_readiness`
6. `specialist handoff / redispatch / timeout`
7. `skeptic`
8. `curator`
9. `final_audit / render_user_verdict`

关键规则：

- `rdc-debugger` 是唯一 public main skill 与唯一 classifier
- `triage_agent` 只提供 routing hint，不直接 dispatch specialist
- live runtime 由 broker 直接持有；specialist 只通过 `ownership_lease` + broker action 消费 live runtime
- `session_id`、`context_id`、`active_event_id` 不得作为跨阶段稳定主键传播
- 临时 Python / PowerShell / shell wrapper 封装 live CLI 一律视为流程偏差
- `waiting_for_specialist_brief`、`redispatch_pending`、`specialist_reinvestigation`、`skeptic_challenged` 期间，orchestrator 只能汇总与裁决，不能替 specialist 补证据