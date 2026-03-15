# RenderDoc/RDC GPU Debug · Knowledge Root（common/knowledge/）

`common/knowledge/` 是 Debugger framework 的知识真相根目录。

这里固定分成三层：

- `spec/`
  - 正式生效的 versioned knowledge store
  - 由 `registry/active_manifest.yaml`、`spec_registry.yaml`、`objects/`、`policy/`、`ledger/` 组成
- `library/`
  - run/session 沉淀的共享真相与检索资产
  - `bugcards/`、`bugfull/`、`sessions/`、索引与图谱
- `proposals/`
  - 正式 candidate 对象
  - 会进入 replay、shadow、自动晋升、自动回滚

运行现场仍位于 `../workspace/`，不与 `common/knowledge/` 混写。

## Session 真相分工

session 级真相固定拆成四层：

- `library/sessions/<session_id>/action_chain.jsonl`
  - append-only event ledger
- `library/sessions/<session_id>/session_evidence.yaml`
  - 当前裁决快照，必须记录 `spec_snapshot_ref`
- `spec/registry/active_manifest.yaml`
  - 当前生效 spec 快照指针
- `../workspace/cases/<case_id>/runs/<run_id>/artifacts/run_compliance.yaml`
  - 审计派生产物

这四者的角色定义见 [`../docs/truth_store_contract.md`](../docs/truth_store_contract.md)。

## 自动演化流程

知识演进流程固定为：

`compliant run -> auto candidate -> replay validation -> shadow observation -> active / rolled_back`

自动演化只允许使用结构化真相：

- `action_chain.jsonl`
- `session_evidence.yaml`
- BugCard / BugFull
- approved counterfactual reviews
- cross-device fingerprint graph

`report.md` 和 `visual_report.html` 不是知识晋升真相源。

## 与 `workspace/` 的边界

- `common/knowledge/**`：共享真相、候选对象、版本化 spec 和示例
- `../workspace/cases/<case_id>/runs/<run_id>/**`：run 现场、日志、报告和审计产物

硬规则：

- report 只能引用已经成立的 ledger / snapshot / active spec snapshot
- `run_compliance.yaml` 只能派生，不能反向充当 session 真相源
- 正式知识切换只能通过 manifest/registry 指针完成，不得绕过版本库直接改写 active 内容
