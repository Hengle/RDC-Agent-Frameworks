# RenderDoc/RDC GPU Debug Local-First CLI Reference

本文用于说明 framework 在 local-first 场景下如何依赖 daemon-backed `CLI` 入口。

本文把 `CLI` 定义为 local-first 的 daemon adapter。对能直接访问本地进程、文件系统与 daemon 的宿主，`CLI` 是默认入口之一。

## 1. 使用原则

- 先判断宿主是否能直接访问本地环境。
  - 如果能，默认 local-first，优先使用 daemon-backed `CLI`。
  - 如果不能，或用户明确要求按 `MCP` 接入，则切换到 `MCP`。
- 任务开始时，Agent 必须向用户说明当前采用的是 `CLI` 还是 `MCP`。
- 如果当前选择 `MCP`，但宿主没有配置对应 MCP server，必须像 `tools_root` 未配置一样直接阻断。
- `CLI` 的业务命令都经 daemon / context 执行。
- daemon 是长生命周期 runtime / context 持有层，不是 `CLI` 或 `MCP` 的附属模式。

## 2. local-first 最小链路

`CLI` 路径下，允许依赖这条最小顺序链路：

1. 打开 `.rdc`
2. 建立 session
3. 选择 frame
4. 读取事件列表或状态
5. 在必要时读取 event 级上下文

在当前平台默认实现里，这类动作通常由以下命令族承担：

- `capture open`
- `capture status`
- `call rd.event.get_actions`
- `daemon status`

Agent 应把它们理解为“已知入口”，而不是把 `CLI` 当成只给人工排障的壳层。

## 3. 允许依赖的关键状态名

`CLI` 路径下，Agent 可依赖这些 daemon-owned 平台状态名：

- `capture_file_id`
- `session_id`
- `frame_index`
- `active_event_id`
- `context`

这些值都应被视为短生命周期运行时句柄，不应当作长期稳定主键。

## 4. 命令族边界

下列命令族可以被当作已知入口类别，而不是完整清单：

- capture/session
  - 打开 capture
  - 读取当前 session 状态
- daemon/context
  - 读取 daemon 状态
  - 读取或清理当前 context
- raw tool call
  - 通过 `call rd.*` 调用已知工具

如果某个任务必须依赖未声明的命令族才成立，Agent 不应通过猜测补全平台定义。

## 5. 输出读取原则

- 优先读取结构化字段，不依赖人类描述性输出推断平台语义。
- 遇到共享响应契约输出时，优先检查：
  - `ok`
  - `error.message`
- 遇到 session 相关输出时，优先抽取：
  - `capture_file_id`
  - `session_id`
  - `active_event_id`

## 6. 何时停止当前入口

出现以下情况时，停止把当前入口当作可继续推进的前提：

- 当前宿主并不能直接访问本地环境，却仍试图走 `CLI`
- 用户明确要求按 `MCP` 接入
- 任务已切换到外部宿主桥接，且对应 MCP server 尚未配置
- 命令输出无法稳定映射为已知状态对象

这时应改为：

- 切换到 `MCP` 路径并先校验 MCP server 配置，或
- 请求用户补全入口前置条件
