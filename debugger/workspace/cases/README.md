# Workspace Cases

本目录用于存放运行时 case。

本仓库只保留占位说明，不提交真实 case 数据。Agent 或用户在实际平台模板中运行时，应按以下结构创建内容：

```text
cases/
  <case_id>/
    case.yaml
    runs/
      <run_id>/
        run.yaml
        artifacts/
        logs/
        notes/
        captures/
        screenshots/
        reports/
```

最小 metadata contract：

```yaml
# case.yaml
case_id: "<case_id>"
title: "<问题标题>"
thread_ref: "<issue/task/thread>"
status: active
current_run: "<run_id>"
```

```yaml
# run.yaml
run_id: "<run_id>"
case_id: "<case_id>"
debug_version: 1
session_id: "<session_id>"
parent_run: null
status: active
paths:
  artifacts: "./artifacts"
  logs: "./logs"
  notes: "./notes"
  captures: "./captures"
  screenshots: "./screenshots"
  reports: "./reports"
  session_evidence_ref: "../../../common/knowledge/library/sessions/<session_id>/session_evidence.yaml"
```
