# RDC-Agent Frameworks

本仓库提供构建在 RenderDoc/RDC 平台能力之上的上层 Agent framework。

## 使用前准备

本仓库不是自带平台真相的独立运行仓库。开始使用前，必须先配置：

- `debugger/common/config/platform_adapter.json`

其中：

- `paths.tools_root` 必须指向有效的 `RDC-Agent-Tools` 根目录
- 在 `validation.required_paths` 校验通过前，Agent 必须拒绝进入任何 platform-truth-dependent 工作

如果未完成这一步，framework 中的 `README`、`AGENTS.md`、`AGENT_CORE.md`、skills 与平台模板都只能被视为上层约束，不得被当成 Tools 真相替代品。

## 仓库定位与层级关系

本仓库不是“直接暴露 RenderDoc 运行时能力”的平台仓库，而是构建在底层 `RDC-Agent Tools` 之上的上层 framework。

两者解决的问题不同，而且是明确的上下层关系，不是替代关系：

- 本仓库负责“任务编排与认知组织”
  - 把用户目标翻译成阶段性任务与角色分工
  - 决定什么时候做 discovery、什么时候建立 session、什么时候进入 event / resource / shader / driver 分析
  - 提供业务护栏、术语约定、输出格式、artifact 合同，以及失败后的重试、重建、降级原则
- `RDC-Agent Tools` 负责“平台能力与运行时约束”
  - 暴露稳定的 `rd.*` tool 能力面，并以 catalog / contract 作为规范源
  - 定义 `.rdc -> capture_file_id -> session_id -> frame/event focus` 的最小平台链路
  - 说明 `context`、daemon、local session state、runtime internal objects、artifact、context snapshot 的关系
  - 固化共享错误契约与句柄生命周期边界

这层分离的意义在于：

- 上层 framework 可以持续演进 prompts、roles、workflow，而不改写平台真相
- 底层平台可以收紧 contract、修正生命周期语义、扩展 tool 能力，而不把业务 workflow 混进平台定义
- 无论更换多少套宿主适配、skill 或 prompt，Agent 都应建立在同一套 RenderDoc/RDC 平台真相之上

## 当前结构

- `debugger/`
  - 当前最完整的 framework
  - 聚焦 GPU 渲染 Bug 调试，强调不变量、证据链、反事实验证和知识沉淀
- `analyzer/`
  - 仍处于骨架阶段
- `optimizer/`
  - 仍处于骨架阶段

## 建议阅读顺序

1. `debugger/common/config/platform_adapter.json`
2. `debugger/README.md`
3. `debugger/common/AGENT_CORE.md`
4. `<resolved tools_root>/README.md`
5. `<resolved tools_root>/docs/tools.md`
6. `<resolved tools_root>/docs/session-model.md`
7. `<resolved tools_root>/docs/agent-model.md`
