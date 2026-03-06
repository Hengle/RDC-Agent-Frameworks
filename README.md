# RDC-Agent Frameworks

本仓库提供构建在 RenderDoc/RDC 平台能力之上的上层 Agent framework。

仓库当前状态并不追求“所有方向都已完成”，而是区分成熟度：

- `debugger/`
  - 当前最完整的 framework。
  - 聚焦 GPU 渲染 Bug 调试，强调不变量、证据链、反事实验证和知识沉淀。
- `analyzer/`
  - 仍处于骨架阶段。
  - 目标是把未知渲染系统重建为可解释模型，但尚未形成完整 framework 契约。
- `optimizer/`
  - 仍处于骨架阶段。
  - 目标是形成可验证的优化闭环，但尚未形成完整 framework 契约。

## 设计原则

- 上层 framework 只依赖平台第一性能力，不把某个历史实现名当成框架概念本身。
- 平台工具接入和路径发现属于 adapter/config 层，不属于 framework 真相。
- 平台无关的 Prompt、知识库、质量门槛应保持单一真相来源。
- 平台适配物可以因宿主不同而变化，但角色职责和工作流约束不应漂移。

## 当前建议阅读顺序

1. `debugger/README.md`
2. `debugger/common/AGENT_CORE.md`
3. `debugger/docs/platform-capability-model.md`
4. `debugger/docs/cli-mode-reference.md`
