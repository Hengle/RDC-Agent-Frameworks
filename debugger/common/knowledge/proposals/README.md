# Knowledge Candidates

本目录存放自动演化体系中的正式候选对象。

这里的 YAML 不是“等待人工 review 的 proposal 草稿”，而是 versioned spec 的候选版本入口。候选对象会经历：

`candidate -> replay_validated -> shadow_active -> active -> rolled_back/rejected/manual_hold`

## 允许类型

- `sop_candidate`
- `invariant_candidate`
- `taxonomy_candidate`

结构定义见 [`proposal_schema.yaml`](./proposal_schema.yaml)。

## 生成来源

candidate 只能由结构化真相生成：

- `action_chain.jsonl`
- `session_evidence.yaml`
- BugCard / BugFull
- counterfactual approved reviews
- cross-device fingerprint graph

`report.md` / `visual_report.html` 不参与正式知识晋升。

## 治理规则

- candidate 是自动治理体系的一部分，会参与 replay、shadow、自动晋升和自动回滚。
- candidate 不得绕过 `registry/active_manifest.yaml` 直接宣称自己已生效。
- 相同 dedupe group 命中时，必须更新同一 candidate 的统计与状态，不得重复创建同类候选。
- 一旦 candidate 晋升或回滚，必须同步写入 `spec/ledger/evolution_ledger.jsonl` 与 `spec/negative_memory.yaml`。
