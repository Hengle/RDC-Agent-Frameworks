# Workspace Layout

本文定义 Debugger 框架的运行时 `workspace/` 合同。

Agent 的目标始终是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题；`workspace/` 只负责承载这次调试的运行现场和对外交付，不负责保存 framework 真相。

## 1. 基本分层

- `common/`：唯一共享真相
  - agents
  - config
  - docs
  - hooks
  - knowledge/spec
  - knowledge/library
  - knowledge/proposals
- `workspace/`：运行区
  - case/run 工作现场
  - 第二层图文报告与 HTML summary

硬规则：

- 不把运行期截图、capture、日志直接写回 `common/`。
- 不把共享 spec、agent 职责、平台 config 写进 `workspace/`。
- 第二层 deliverables 只能派生自第一层证据，不得反向改写第一层真相。

## 2. 平台本地相对路径

用户会把顶层 `debugger/common/` 拷贝到目标平台模板根目录的 `common/` 后再使用。运行时 `workspace/` 不是仓库根目录的一部分，而是每个平台模板根目录预生成的 sibling 占位骨架。

因此，shared prompt / skill / docs 中引用运行区时，统一使用：

- `../workspace`

它始终解析到当前平台根目录下、与 `common/` 同级的 `workspace/`。

## 3. Capture-First case/run 模型

目录约定：

```text
workspace/
  cases/
    <case_id>/
      case.yaml
      inputs/
        captures/
          manifest.yaml
          <capture_id>.rdc
      runs/
        <run_id>/
          run.yaml
          capture_refs.yaml
          artifacts/
          logs/
          notes/
          screenshots/
          reports/
```

最小规则：

- `.rdc` 是创建 case 的硬前置条件；未拿到 `.rdc` 前，不创建 `case_id`、`run_id`、`workspace_run_root`
- 同一 case 只允许一个 `current_run`
- `reports/` 只放 `report.md` 与 `visual_report.html`
- 图片默认复用 `screenshots/`
- 第一层 gate artifacts 不复制到 `workspace/`，只在 `run.yaml` 中记录引用

## 4. 写权限边界

### 第一层：Curator + Knowledge

可直接维护：

- `common/knowledge/library/bugcards/`
- `common/knowledge/library/bugfull/`
- `common/knowledge/library/sessions/`
- `common/knowledge/library/bugcard_index.yaml`
- `common/knowledge/library/cross_device_fingerprint_graph.yaml`
- `common/knowledge/proposals/`

不得直接改写：

- `common/agents/`
- `common/config/`
- `common/knowledge/spec/objects/`
- `common/knowledge/spec/registry/`
- `common/knowledge/spec/policy/`

说明：

- agent 可以发射 candidate、记录 shadow 观察、触发自动晋升。
- 但正式 active spec 只能由知识演化流程通过 manifest/registry 切换。

### 第二层：Stakeholder-facing Report

可直接维护：

- `../workspace/cases/<case_id>/runs/<run_id>/reports/report.md`
- `../workspace/cases/<case_id>/runs/<run_id>/reports/visual_report.html`
- `../workspace/cases/<case_id>/runs/<run_id>/screenshots/`
- `../workspace/cases/<case_id>/runs/<run_id>/notes/`
- `../workspace/cases/<case_id>/runs/<run_id>/artifacts/`
- `../workspace/cases/<case_id>/runs/<run_id>/logs/`
- `../workspace/cases/<case_id>/case.yaml`
- `../workspace/cases/<case_id>/inputs/captures/manifest.yaml`
- `../workspace/cases/<case_id>/runs/<run_id>/capture_refs.yaml`

第二层额外规则：

- derived deliverables，不是 source of truth
- 不得把原始 `.rdc` 复制到 `runs/<run_id>/`
- 不得创造第一层不存在的新事实
- 不得为了展示效果反写 `BugFull`、`BugCard`、session artifacts
