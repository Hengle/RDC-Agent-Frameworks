# 反事实评分与独立复核规范

反事实评分引擎不再只回答“修复后看起来是不是更好了”，而是同时回答两件事：

1. 干预是否量化地改善了症状；
2. 变量隔离是否经过独立复核，而不是由提出修复的人自己判自己通过。

## 核心原则

- `counterfactual_submitted` 只负责提交结构化实验事实。
- `counterfactual_reviewed` 才负责给出独立复核结论。
- proposer 与 reviewer 必须是不同 agent。
- `S_counterfactual < 0.80`、缺少隔离字段、或缺少独立 reviewer，均不得结案。

## 评分维度与权重

### Dimension 1：像素级恢复度（Pixel Recovery Score）

$$S_{pixel} = 1 - \frac{||pixel_{after} - pixel_{baseline}||}{||pixel_{before} - pixel_{baseline}||}$$

### Dimension 2：变量隔离度（Variable Isolation Score）

隔离维度由提交者给出结构化检查项，再由 reviewer 审核其是否可信。

| 检查项 | 通过得 1 分，失败得 0 分 |
|--------|----------------------|
| `only_target_changed` | 仅改变目标变量，没有引入其他逻辑修改 |
| `same_scene_same_input` | 修复前后在同一场景、同一输入下对比 |
| `same_drawcall_count` | 渲染结构未变形，DrawCall 数量一致 |

$$S_{isolation} = \frac{\text{通过项数}}{3}$$

### Dimension 3：症状覆盖度（Symptom Coverage Score）

$$S_{coverage} = \frac{\text{修复后消失的症状数}}{\text{目标症状总数}}$$

### Dimension 4：跨场景稳定性（Stability Score，可选）

$$S_{stability} = \frac{\text{通过验证的场景数}}{\text{总验证场景数}}$$

## 综合评分

$$S_{counterfactual} = 0.50 \times S_{pixel} + 0.25 \times S_{isolation} + 0.20 \times S_{coverage} + 0.05 \times S_{stability}$$

当 `stability` 不可用时，权重重分配为 `0.50 / 0.25 / 0.25 / 0.00`。

## Ledger 记录方式

### `counterfactual_submitted`

写入 `action_chain.jsonl` 的提交事件必须至少包含：

```json
{
  "event_type": "counterfactual_submitted",
  "status": "submitted",
  "payload": {
    "review_id": "CF-001",
    "hypothesis_id": "H-001",
    "proposer_agent": "shader_ir_agent",
    "intervention": "half diffuse -> float diffuse",
    "target_variable": "shader precision",
    "isolation_checks": {
      "only_target_changed": true,
      "same_scene_same_input": true,
      "same_drawcall_count": true
    },
    "measurements": {
      "pixel_before": {"x": 512, "y": 384, "rgba": [0.21, 0.19, 0.18, 1.0]},
      "pixel_after": {"x": 512, "y": 384, "rgba": [0.37, 0.34, 0.32, 1.0]},
      "pixel_baseline": {"x": 512, "y": 384, "rgba": [0.38, 0.35, 0.33, 1.0]}
    },
    "scoring": {
      "pixel_recovery": 0.94,
      "variable_isolation": 1.0,
      "symptom_coverage": 1.0,
      "stability": 1.0,
      "total": 0.97
    },
    "evidence_refs": ["evt-0003-pixel-history"]
  }
}
```

### `counterfactual_reviewed`

写入 `action_chain.jsonl` 的复核事件必须至少包含：

```json
{
  "event_type": "counterfactual_reviewed",
  "status": "approved",
  "payload": {
    "review_id": "CF-001",
    "hypothesis_id": "H-001",
    "reviewer_agent": "skeptic_agent",
    "isolation_verdict": {
      "verdict": "isolated",
      "rationale": "结构化证据显示只修改了目标变量，且 drawcall 拓扑未变化"
    },
    "evidence_refs": ["evt-0007-counterfactual-submit", "evt-0003-pixel-history"]
  }
}
```

## Snapshot 记录方式

`session_evidence.yaml` 中只保留复核后的摘要：

```yaml
counterfactual_reviews:
  - review_id: CF-001
    hypothesis_id: H-001
    proposer_agent: shader_ir_agent
    reviewer_agent: skeptic_agent
    status: approved
    submission_event_id: evt-0007-counterfactual-submit
    review_event_id: evt-0008-counterfactual-review
    evidence_refs:
      - evt-0003-pixel-history
      - evt-0007-counterfactual-submit
```

## 与质量 Hook 的集成

`counterfactual_validator.py` 必须检查：

- `session_evidence.counterfactual_reviews` 中存在至少一条 `status=approved` 的 review
- `submission_event_id` 和 `review_event_id` 可在 `action_chain.jsonl` 中解析
- `proposer_agent != reviewer_agent`
- `isolation_checks`、像素量化数据和 `scoring.total >= 0.80` 完整
- 不存在未仲裁冲突，且目标 hypothesis 不处于 `CONFLICTED`
