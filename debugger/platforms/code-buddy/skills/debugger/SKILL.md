# RenderDoc/RDC GPU Debug Skill

## 描述

`RenderDoc/RDC GPU Debug` 调试技能包。

该 skill 提供三类输入：

- 框架级知识
  - 不变量库、taxonomy、SOP、session artifact 约束
- 平台能力层使用约束
  - `MCP` 与 `CLI` 的边界
  - session lifecycle
  - `ok` / `error_message` 的读取优先级
- 调试知识沉淀规则
  - BugCard / BugFull / Action Chain

## 必读入口

执行调试任务时，优先阅读：

- `../../../../common/AGENT_CORE.md`
- `../../../../docs/platform-capability-model.md`

## 动态加载文件

按任务需要读取以下文件：

```text
common/knowledge/spec/invariants/invariant_library.yaml
common/knowledge/spec/taxonomy/symptom_taxonomy.yaml
common/knowledge/spec/taxonomy/trigger_taxonomy.yaml
common/knowledge/spec/skills/sop_library.yaml
```

若存在项目插件，再读取：

```text
common/project_plugin/<project_name>.yaml
```

## 模式选择规则

### `MCP` 模式

- 可以先做 tool discovery，再决定后续编排。
- 适合动态选择 `rd.*` 工具。

### `CLI` 模式

用户明确要求 `CLI` 模式时，先阅读：

- `references/cli-mode-reference.md`
- `../../../../docs/cli-mode-reference.md`

硬约束：

- 不得通过 `--help`
- 不得通过枚举命令
- 不得通过随机试跑
- 不得通过观察式试错

来猜测平台能力面。

`CLI` 模式下只能依赖已文档化的：

- 会话最小链路
- 关键状态名
- 常见命令族
- 输出读取原则

## 外部参考的使用边界

可以借鉴“主 skill + 附属参考文档”的组织方式。

不得把外部参考中的以下内容直接带入本框架：

- 其他 CLI 语义体系
- 其他 session 模型
- 其他工作流定义
- 以命令清单驱动框架定义的写法

本框架的 SSOT 仍然是本仓库当前的：

- `common/AGENT_CORE.md`
- `common/agents/*.md`
- `common/knowledge/spec/*`

