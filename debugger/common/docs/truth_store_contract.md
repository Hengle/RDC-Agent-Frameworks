# Truth Store Contract（真相存储契约）

本文定义 Debugger framework 在文件系统上的真相存储契约。

本契约只规定 artifact 角色、寻址、引用和单写者约束；不引入 object store / database / cloud backend 抽象，也不替代底层 tools/infra 的持久化实现。

## 五类 Artifact

### 1. `action_chain.jsonl`

- 角色：`append_only_ledger`
- 真相定位：记录 run/session 中发生过什么
- 存储格式：每行一个 JSON event
- 写入方式：只允许 append，不允许覆盖历史事件

### 2. `session_evidence.yaml`

- 角色：`adjudicated_snapshot`
- 真相定位：记录已裁决的因果锚点、假设状态、反事实复核、`reference_contract` 摘要与 `fix_verification` 摘要
- 存储格式：YAML object
- 写入方式：单写者快照；重写时必须保持 `snapshot_version` 单调递增

### 3. `registry/active_manifest.yaml`

- 角色：`versioned_spec_pointer`
- 真相定位：记录当前生效的 SOP / invariant / taxonomy 版本
- 存储格式：YAML object
- 写入方式：只能由自动晋升 / 自动回滚流程切换指针

### 4. `evolution_ledger.jsonl`

- 角色：`append_only_governance_ledger`
- 真相定位：记录 candidate 发射、replay 通过、shadow 观察、active 切换、回滚与去冗余决策
- 存储格式：每行一个 JSON event
- 写入方式：只允许 append，不允许回写历史

### 5. `run_compliance.yaml`

- 角色：`derived_audit`
- 真相定位：仅表达审计结果与 run 级指标
- 存储格式：YAML object
- 写入方式：派生产物，不得作为上游推理输入的唯一来源

## `workspace` 输入与验证 Artifact

以下对象位于 `workspace/`，不是共享真相，但属于 finalization 必需输入：

- `case_input.yaml`
  - case 级唯一 intake SSOT
- `inputs/references/manifest.yaml`
  - 非 replay reference 清单
- `artifacts/fix_verification.yaml`
  - run 级唯一修复验证 artifact

它们不是 `common/knowledge/**` 真相对象，但 Stop Gate 必须验证其存在、结构和引用关系。

## 寻址与引用

- 事件之间只通过 `event_id` 互相引用。
- `session_evidence.yaml` 必须记录 `spec_snapshot_ref` 与 `active_spec_versions`，不得只写自然语言说明。
- `session_evidence.yaml` 必须记录 `reference_contract.ref` 与 `fix_verification.ref`。
- BugCard 必须通过 `verification.reference_contract_ref` 指回 `case_input.yaml#reference_contract`。
- report / visual report 只能引用已经存在于 ledger、snapshot、workspace artifact 或 active spec snapshot 中的结构化对象。

## 单写者与边界

- `action_chain.jsonl` 可由多个 agent 追加，但不得修改既有事件。
- `session_evidence.yaml` 只允许一个快照写者提交当前版本；推荐由 `curator_agent` 负责写入。
- `active_manifest.yaml` 与 `spec_registry.yaml` 只能由知识演化流程切换，不允许手工绕过 candidate 直接修改 active 指针。
- `fix_verification.yaml` 是 run 级唯一修复验证对象；不得并行维护第二套 before/after 验证文件。
- `run_compliance.yaml` 只能由审计过程生成，不允许手写伪造通过状态。

## 恢复顺序

1. `session_evidence.yaml` 中的 `causal_anchor`、`hypotheses`、`counterfactual_reviews`、`reference_contract`、`fix_verification`
2. `action_chain.jsonl` 中与上述对象绑定的事件
3. `../workspace/cases/<case_id>/case_input.yaml`
4. `../workspace/cases/<case_id>/runs/<run_id>/artifacts/fix_verification.yaml`
5. `registry/active_manifest.yaml` 与其指向的 versioned spec object
6. `evolution_ledger.jsonl`
7. `run_compliance.yaml`

## 禁止事项

- 不得把 `run_compliance.yaml` 当作唯一真相源回推 session 事实。
- 不得在 `session_evidence.yaml` 中复制整段 tool trace。
- 不得再维护旧 `fix_verification_data` 或第二套修复验证对象。
- 不得为了兼容旧 schema 同时维护第二套 intake、第二套 snapshot、第二套修复验证入口。
