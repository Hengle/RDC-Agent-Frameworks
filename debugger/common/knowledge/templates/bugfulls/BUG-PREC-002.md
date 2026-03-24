# BugFull ???BUG-PREC-002

## 1. 问题概述

- 现象：Adreno 740 上头发/披风区域整体塌黑。
- 复现率：必现。

## 2. Intake 合同

- `case_input.yaml`：`../workspace/cases/case-adreno740-black/case_input.yaml`
- `reference_contract.source_kind`：`capture_baseline`
- `verification_mode`：`device_parity`
- strict / fallback：`strict`

## 3. 调试时间线

- Triage：命中 `I-PREC-01`
- Capture：建立 `anomalous + baseline`
- Pixel Forensics：锁定 `first_bad_event`
- Shader/IR：定位到 `half KajiyaDiffuse = 1 - abs(dot(N, L));`
- Fix Verification：`structural=passed`，`semantic=passed`

## 4. 反事实验证记录

- `reference_contract_ref`：`../workspace/cases/case-adreno740-black/case_input.yaml#reference_contract`
- `baseline_source`：`capture:baseline`
- 量化 probe：`hair_shadow`

## 5. 修复方案

- 修复模式：将关键 `half` 计算替换为 `float`
- `fix_verification.yaml`：
  - `structural_verification.status = passed`
  - `semantic_verification.status = passed`
  - `overall_result.status = passed`

## 6. 知识沉淀

- BugCard：`common/knowledge/library/bugcards/bugcard_BUG-PREC-002.yaml`
- 指纹：`half KajiyaDiffuse = 1 - abs(dot(N, L));`
