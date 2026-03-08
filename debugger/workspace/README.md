# Debugger Workspace

`debugger/workspace/` 是 Debugger 框架的运行时工作区骨架，不属于共享 framework 真相。

约束：

- `common/` 仍是唯一共享真相；`workspace/` 只承载 case/run 运行现场与面向需求方的交付物。
- 本仓库只跟踪占位结构，不提交真实调试 case、截图、capture、日志或报告。
- 用户把 `debugger/common/` 拷贝到某个平台模板根目录的 `common/` 后，应继续使用同级 `workspace/` 作为运行区。

目录约定：

```text
workspace/
  README.md
  cases/
    README.md
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

语义：

- `case_id`：同一个需求线程/问题实例的稳定标识。
- `run_id`：该 case 的一次具体调试轮次，承担 debug version。
- `artifacts/`：结构化机器产物，不放自由文本。
- `logs/`：过程日志。
- `notes/`：人工笔记、brief、阶段性分析。
- `captures/`：原始或可重放输入（如 `.rdc`）。
- `screenshots/`：视觉证据与 before/after 图。
- `reports/`：第二层交付物，只放 `report.md` 与 `summary.html`。

规则：

- 同一 case 只允许 `case.yaml.current_run` 指向一个当前有效 run。
- `reports/` 默认引用同一 run 下的 `../screenshots/` 素材，不复制第二套图片。
- 第一层 session artifacts 仍沉淀到 `common/knowledge/library/sessions/<session_id>/`；`run.yaml` 只记录引用路径，不在 `workspace/` 中复制 gate 真相。
