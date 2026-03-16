# Intake Contract（输入合同）

本文定义 Debugger framework 唯一的用户输入合同。

目标不是规定用户必须按某种语言风格提问，而是要求任何进入调试链的输入，最终都必须被 `team_lead` 规范化为同一个 `case_input.yaml`。

## 1. 双层模型

- 用户层：七段式 prompt
  - `§ SESSION`
  - `§ SYMPTOM`
  - `§ CAPTURES`
  - `§ ENVIRONMENT`
  - `§ REFERENCE`
  - `§ HINTS`
  - `§ PROJECT`
- 系统层：`case_input.yaml`
  - 这是唯一 SSOT
  - 后续 agent、validator、run artifact 只消费它，不直接消费用户原始 prose

硬规则：

- 未拿到至少一份异常 `.rdc` 前，不得创建 `case_input.yaml`
- 七段式 prompt 可以省略部分说明，但 `team_lead` 必须把缺失项显式归一化为 `unknown`、`[]` 或模式级阻断错误
- `case_input.yaml` 只能在 capture intake 成功后写入 `../workspace/cases/<case_id>/`

## 2. `case_input.yaml` 固定结构

```yaml
schema_version: "1"
case_id: "<case_id>"

session:
  mode: single                       # single | cross_device | regression
  goal: "<一句话问题目标>"
  requested_outcome: "<用户要确认什么>"

symptom:
  summary: "<症状摘要>"
  screenshots: []
  observed_symptoms: []

captures:
  - capture_id: cap-anomalous-001
    role: anomalous                  # anomalous | baseline | fixed
    file_name: broken.rdc
    source: user_supplied            # user_supplied | historical_good | generated_counterfactual
    provenance:
      build: "<optional>"
      device: "<optional>"
      note: "<optional>"

environment:
  api: Vulkan
  devices: []
  drivers: []
  render_settings: {}

reference_contract:
  source_kind: capture_baseline      # capture_baseline | external_image | design_spec | mixed
  source_refs:
    - capture:baseline
  verification_mode: device_parity   # pixel_value_check | device_parity | regression_check | visual_comparison
  probe_set:
    pixels: []
    regions: []
    symptoms: []
  acceptance:
    max_channel_delta: 0.05
    max_distance_l2: 0.08
    required_symptom_clearance: 1.0
    fallback_only: false

hints:
  suspected_modules: []
  likely_invariants: []
  notes: []

project:
  engine: Unreal
  modules: []
  branch: ""
  extra_context: []
```

规则：

- `captures` 只描述可重放 `.rdc`
- `reference_contract` 只描述语义验收合同，不等同于某个 capture
- `source_refs` 只允许引用 `capture:<role>` 或 `reference:<file_id>`
- `visual_comparison` 只能产生 `fallback_only` 语义验证，不得支撑严格结案

## 3. 三种模式

### `single`

- 必须有一份 `role=anomalous` capture
- 必须有 `reference_contract`
- 若 `reference_contract` 只有图片/描述，没有量化 probe，则只允许 `fallback_only=true`

### `cross_device`

- 必须有 `anomalous + baseline` 两份 capture
- `reference_contract.source_kind` 必须为 `capture_baseline`
- `reference_contract.source_refs` 必须引用 `capture:baseline`
- 默认 `verification_mode=device_parity`

### `regression`

- 必须有 `anomalous + baseline` 两份 capture
- `baseline.source` 必须为 `historical_good`
- `baseline.provenance` 必须包含 `build` 或 `revision`
- 默认 `verification_mode=regression_check`

## 4. 输入池分层

`workspace/` 中的输入池分成两类：

```text
../workspace/cases/<case_id>/
  case_input.yaml
  inputs/
    captures/
      manifest.yaml
      <capture_id>.rdc
    references/
      manifest.yaml
      <reference_id>.png|.jpg|.md|.txt
```

硬规则：

- `.rdc` 只能放在 `inputs/captures/`
- screenshot、golden image、设计稿、验收说明只能放在 `inputs/references/`
- 不得把 reference 图混放进 capture 清单

## 5. 严格验证与 fallback 验证

严格验证要求：

- `structural_verification.status = passed`
- `semantic_verification.status = passed`
- `reference_contract.acceptance.fallback_only = false`

fallback 验证允许：

- 调试继续推进
- 生成报告
- 记录 symptom coverage

fallback 验证禁止：

- `fix_verified=true`
- BugCard 入库
- strict finalization

## 6. 配套文件

- `USER_PROMPT_TEMPLATE.md`：完整版模板
- `USER_PROMPT_MINIMAL.md`：极简骨架
- `examples/`：三种模式的填写示例
