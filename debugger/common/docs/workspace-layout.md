# 工作区布局契约

本文定义 debugger framework 的 `workspace/` 合同。

```text
workspace/
  cases/
    <case_id>/
      case.yaml
      artifacts/
        entry_gate.yaml
      case_input.yaml
      inputs/
        captures/
          manifest.yaml
          <capture>.rdc
        references/
          manifest.yaml
      runs/
        <run_id>/
          run.yaml
          capture_refs.yaml
          artifacts/
            intake_gate.yaml
            runtime_session.yaml
            runtime_snapshot.yaml
            ownership_lease.yaml
            runtime_failure.yaml
            fix_verification.yaml
            remote_prerequisite_gate.yaml
            remote_capability_gate.yaml
            remote_recovery_decision.yaml
          notes/
            hypothesis_board.yaml
            remote_planning_brief.yaml
            remote_runtime_inconsistency.yaml
          screenshots/
          reports/
            report.md
            visual_report.html
```

硬规则：

- `.rdc` 是创建 case 的硬前置；未拿到 `.rdc` 不创建 case/run
- `strict_ready` fix reference 是 accepted intake 的硬前置
- `runtime_session.yaml`、`runtime_snapshot.yaml`、`ownership_lease.yaml`、`runtime_failure.yaml` 是 run 级 runtime 真相
- `runtime_failure` 未清、`ownership_lease` 未释放时不得 finalized
- specialist brief 只写 `notes/**`
- `reports/report.md` 与 `reports/visual_report.html` 是对外交付层，不是第一层真相