# BugFull BUG-PREC-001

## 1. 问题概述

- 现象：Adreno 650 上，带 local light 的场景中角色头发/衣物整体偏白。
- 复现率：必现。

## 2. Intake 合同

- `case_input.yaml`：`../workspace/cases/case-adreno650-white/case_input.yaml`
- `reference_contract.source_kind`：`capture_baseline`
- `verification_mode`：`device_parity`
- strict / fallback：`strict`

## 3. 调试时间线

- Triage：命中 `I-PREC-01`
- Capture：建立 `anomalous + baseline`
- Shader/IR：定位到 local light unpack precision lowering
- Fix Verification：`structural=passed`，`semantic=passed`

## 4. 反事实验证记录

- `reference_contract_ref`：`../workspace/cases/case-adreno650-white/case_input.yaml#reference_contract`
- `baseline_source`：`capture:baseline`
- 量化 probe：`hair_hotspot`

## 5. 修复方案

- 修复模式：Precision Fence / CastToFloat
- `fix_verification.yaml`：
  - `structural_verification.status = passed`
  - `semantic_verification.status = passed`
  - `overall_result.status = passed`

## 6. 知识沉淀

- BugCard：`common/knowledge/library/bugcards/bugcard_BUG-PREC-001.yaml`
- 指纹：`LightData.Color = LightIntensity * DwordToUNorm(Vec1.z).xyz`
