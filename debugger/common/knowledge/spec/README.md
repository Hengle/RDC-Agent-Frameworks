# Versioned Spec Store（版本化规范库）

`common/knowledge/spec/` 只承载正式生效的版本化知识。

目录职责：

- `registry/`
  - `active_manifest.yaml`：当前生效版本入口
  - `spec_registry.yaml`：全部 family 的版本登记
- `policy/`
  - `evolution_policy.yaml`：晋升、回滚、去冗余阈值
- `ledger/`
  - `evolution_ledger.jsonl`：append-only 治理账本
- `objects/`
  - `sops/`：SOP catalog 对象与 payload
  - `invariants/`：Invariant catalog 对象与 payload
  - `taxonomy/`：Taxonomy catalog 对象与 payload
- `negative_memory.yaml`
  - 高区分度反证与回滚记忆

## 查找路径

- 当前生效 SOP：先读 `registry/active_manifest.yaml`，再解析 `objects/sops/` 下的目标对象
- 当前生效 Invariant：先读 `registry/active_manifest.yaml`，再解析 `objects/invariants/` 下的目标对象
- 当前生效 Taxonomy：先读 `registry/active_manifest.yaml`，再解析 `objects/taxonomy/` 下的目标对象

硬规则：

- 读取方必须先经过 `registry/active_manifest.yaml`，再解析对应版本对象
- 版本对象允许被新增，但不得原地改写旧版本
- 自动晋升和自动回滚只切 manifest/registry 指针，不删除历史版本