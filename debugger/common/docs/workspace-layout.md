# Workspace Layout（工作区布局）

本文定义 Debugger 框架的运行时 `workspace/` 合同。

Agent 的目标始终是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题；`workspace/` 只负责承载本次调试的输入池、运行现场和对外交付，不负责保存 framework 真相。

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
  - `case_input.yaml`
  - 输入池
  - run 级现场
  - 第二层图文报告与 HTML summary

硬规则：

- 不把运行期截图、capture、reference、日志直接写回 `common/`
- 不把共享 spec、agent 职责、平台 config 写进 `workspace/`
- 第二层 deliverables 只能派生自第一层证据，不得反向改写第一层真相

## 2. 平台本地相对路径

用户会把顶层 `debugger/common/` 拷贝到目标平台模板根目录的 `common/` 后再使用。运行时 `workspace/` 不是仓库根目录的一部分，而是每个平台模板根目录预生成的 sibling 占位骨架。

因此，shared prompt / skill / docs 中引用运行区时，统一使用：

- `../workspace`

## 3. Case / Run 模型

目录约定：

```text
workspace/
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

最小规则：

- `.rdc` 是创建 case 的硬前置条件；未拿到 `.rdc` 前，不创建 `case_id`、`run_id`、`workspace_run_root`
- `case_input.yaml` 只允许在 capture intake 成功后落盘
- `inputs/captures/` 只存 replayable `.rdc`
- `inputs/references/` 只存 golden image、设计稿、验收说明等非 replay reference
- `fix_verification.yaml` 是 run 级修复验证唯一权威 artifact
- 第一层 gate artifacts 不复制到 `workspace/`；`run.yaml` 只记录引用

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

### 第二层：Case / Run 运行区

可直接维护：

- `../workspace/cases/<case_id>/case.yaml`
- `../workspace/cases/<case_id>/case_input.yaml`
- `../workspace/cases/<case_id>/inputs/captures/manifest.yaml`
- `../workspace/cases/<case_id>/inputs/references/manifest.yaml`
- `../workspace/cases/<case_id>/runs/<run_id>/run.yaml`
- `../workspace/cases/<case_id>/runs/<run_id>/capture_refs.yaml`
- `../workspace/cases/<case_id>/runs/<run_id>/artifacts/fix_verification.yaml`
- `../workspace/cases/<case_id>/runs/<run_id>/logs/`
- `../workspace/cases/<case_id>/runs/<run_id>/notes/`
- `../workspace/cases/<case_id>/runs/<run_id>/screenshots/`
- `../workspace/cases/<case_id>/runs/<run_id>/reports/report.md`
- `../workspace/cases/<case_id>/runs/<run_id>/reports/visual_report.html`

额外规则：

- 派生 deliverables 不是 source of truth
- `case_input.yaml` 是 case 级 SSOT，不是 prose 备份
- 不得把原始 `.rdc` 复制到 `runs/<run_id>/`
- 不得把 reference 图片写进 capture manifest
- 不得创造第一层不存在的新事实
