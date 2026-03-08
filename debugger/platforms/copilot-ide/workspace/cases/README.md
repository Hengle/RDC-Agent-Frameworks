# Workspace Cases Placeholder

当前目录用于承载运行时 case。

目录约定：

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

规则：

- `case_id` 是问题实例/需求线程的稳定标识。
- `run_id` 承担 debug version。
- 第一层 session artifacts 仍写入同级 `common/knowledge/library/sessions/`；`workspace/` 不复制 gate 真相。
