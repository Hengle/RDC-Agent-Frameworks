# RenderDoc/RDC GPU Debug · Quality Hooks 系统

Quality Hooks 系统将 Debugger 框架的质量门槛从“被建议的”提升为“被强制执行的”。

补充说明：

- 对拥有 native hooks 的宿主，Hook 负责阻断不合规结案。
- 对没有 native hooks 的宿主，最终以 `workspace/cases/<case_id>/runs/<run_id>/artifacts/run_compliance.yaml` 为统一审计裁决。
- 审计现在同时校验 `session_evidence.yaml` 与 versioned spec snapshot 的绑定关系。

## 架构

```text
common/hooks/
├── README.md
├── validators/
│   ├── bugcard_validator.py
│   ├── counterfactual_validator.py
│   └── skeptic_signoff_checker.py
├── utils/
│   ├── spec_store.py
│   ├── knowledge_evolution.py
│   ├── run_compliance_audit.py
│   └── validate_tool_contract_runtime.py
└── schemas/
    ├── bugcard_required_fields.yaml
    ├── skeptic_signoff_schema.yaml
    └── run_compliance_schema.yaml
```

## 审计边界

`run_compliance.yaml` 现在只承担派生审计职责，并额外输出 run 级 metrics：

- per-agent 耗时与事件数
- tool success / failure 与失败率
- hypothesis 状态分布
- conflict 总数、仲裁数、平均仲裁时延
- counterfactual 独立复核覆盖率
- knowledge candidate 发射与状态迁移数

这些指标全部从 `action_chain.jsonl`、`session_evidence.yaml`、`registry/active_manifest.yaml` 派生，不从 prose report 反推。

## 新的知识演化约束

- `bugcard_validator.py` 的 strict 模式只认 active manifest 当前指向的 taxonomy / invariant / SOP。
- `run_compliance_audit.py` 会在合规 run 上自动发射 candidate，并把事件写入 `evolution_ledger.jsonl`。
- 自动晋升、自动回滚与 negative memory 由 `knowledge_evolution.py` 管理；不得绕过它直接改 manifest。

## 依赖

推荐安装方式：

```bash
python3 -m pip install -r common/hooks/requirements.txt
```

验证脚本仅依赖 Python 标准库 + PyYAML。
