# Versioned Spec Store

`common/knowledge/spec/` 现在只承载正式生效的版本化知识，不再接受直接手工编辑的聚合库。

目录职责：

- `registry/`
  - `active_manifest.yaml`：当前生效版本指针
  - `spec_registry.yaml`：全部 family 的版本登记
- `policy/`
  - `evolution_policy.yaml`：晋升、回滚、去冗余阈值
- `ledger/`
  - `evolution_ledger.jsonl`：append-only 治理账本
- `objects/`
  - 各 family 的不可变版本对象与 payload
- `negative_memory.yaml`
  - 高区分度反证与回滚记忆

硬规则：

- 不允许重新引入 `skills/sop_library.yaml`、`invariants/invariant_library.yaml`、`taxonomy/*.yaml` 作为正式入口。
- 读取方必须先经过 `registry/active_manifest.yaml`，再解析对应版本对象。
- 版本对象允许被新增，但不得原地改写旧版本。
- 自动晋升和自动回滚只切 manifest/registry 指针，不删除历史版本。
