# Workspace Cases Placeholder（`cases/` 占位说明）

当前目录用于承载运行时 case。

目录约定：

```text
cases/
  <case_id>/
    case.yaml
    case_input.yaml
    inputs/
      captures/
        manifest.yaml
        <capture_id>.rdc
      references/
        manifest.yaml
        <reference_id>.png|.jpg|.md|.txt
    runs/
      <run_id>/
        run.yaml
        capture_refs.yaml
        artifacts/
          fix_verification.yaml
        logs/
        notes/
        screenshots/
        reports/
```

规则：

- `.rdc` 是创建 case 的硬前置条件；未提供 capture 时不得初始化 case/run
- `case_input.yaml` 是 case 级 intake SSOT
- `inputs/captures/` 只放 replayable `.rdc`
- `inputs/references/` 只放非 replay reference
- `fix_verification.yaml` 是 run 级修复验证唯一权威 artifact
- 第一层 session artifacts 仍写入同级 `common/knowledge/library/sessions/`；`workspace/` 不复制 gate 真相
