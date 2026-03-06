# RenderDoc/RDC GPU Debug
## Invariant-Driven Rendering Debugger

`RenderDoc/RDC GPU Debug` 是构建在 RenderDoc/RDC 平台能力之上的多 Agent 渲染调试 framework。

它的主驱动不是“多试几次工具”，而是：

- 用不变量把现象转成可裁决约束
- 用证据链把猜测推进到可验证结论
- 用反事实验证阻止“看起来像”的误判
- 用 BugCard / BugFull / Action Chain 沉淀可复用知识

## 当前成熟度

- `debugger/` 已具备完整框架基础，可作为当前仓库的主入口。
- `analyzer/` 与 `optimizer/` 仍是骨架，不应被误读为同等成熟度的 framework。

## 阅读顺序

1. `common/AGENT_CORE.md`
2. `docs/platform-capability-model.md`
3. `docs/platform-capability-matrix.md`
4. `docs/model-routing.md`
5. `docs/cli-mode-reference.md`
6. `common/agents/*.md`
7. `common/knowledge/spec/*`

## 目录概览

- `common/`
  - 平台无关 SSOT：Agent prompt、知识规范、质量门槛、project plugin、adapter config。
- `platforms/`
  - 各宿主平台适配物。
- `docs/`
  - 平台能力模型、平台能力矩阵、模型路由、`CLI` 模式附属说明、平台适配文档。
- `scripts/`
  - 校验与同步脚本。

## 平台接入原则

框架层只依赖这些第一性平台能力：

- 规范化的 `rd.*` tool 能力面
- 共享响应契约
- `.rdc -> capture handle -> session handle -> frame/event context` 的最小状态链路
- `context`、daemon、artifact、failure surface

具体实现路径、catalog 位置、`MCP`/`CLI` 启动入口属于 adapter/config 层，集中定义在：

- `common/config/platform_adapter.json`

## `MCP` 与 `CLI`

### `MCP` 模式

- 允许 tool discovery。
- 适合上层 Agent 动态编排。

### `CLI` 模式

- 不允许 discovery-by-trial-and-error。
- 用户明确要求 `CLI` 模式时，先读 `docs/cli-mode-reference.md`。

## 维护入口

### 校验 tool contract

```bash
python debugger/scripts/validate_tool_contract.py --strict
```

### 同步平台 prompt 镜像

```bash
python debugger/scripts/sync_platform_agents.py
```

## Session Artifact Contract

结案前必须存在：

- `common/knowledge/library/sessions/<session_id>/session_evidence.yaml`
- `common/knowledge/library/sessions/<session_id>/skeptic_signoff.yaml`
- `common/knowledge/library/sessions/<session_id>/action_chain.jsonl`
- `common/knowledge/library/sessions/.current_session`



