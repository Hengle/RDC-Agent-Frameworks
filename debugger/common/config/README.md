# Platform Adapter Config

本目录保存 framework 连接 `RDC-Agent Tools` 与多平台模板生成所需的共享配置真相。

约束：

- `debugger/common/` 是唯一长期维护来源。
- `debugger/platforms/*` 全部视为生成产物；宿主模板只允许 direct-reference 到当前平台根目录的 `common/`。
- 平台 tools 的真实路径、`tools_root`、MCP/CLI 启动命令属于 adapter/config 层，不属于 framework 真相。
- `platform_adapter.json` 现在是强制用户配置入口，不再是“默认猜路径”的 convenience 文件。

当前文件：

- `platform_adapter.json`
  - framework 级 Tools 定位入口
  - 用户必须先配置 `paths.tools_root`
  - Agent 必须按 `validation.required_paths` 做 fail-closed 校验
- `role_manifest.json`
  - 角色清单、共享 prompt 源、role skill 源、formal user entry 元数据与各平台文件名映射
- `role_policy.json`
  - 角色模型意图、reasoning/verbosity、delegation 与 tool/hook policy
- `model_routing.json`
  - 抽象模型策略与各宿主渲染映射
- `mcp_servers.json`
  - 逻辑 MCP server 定义
- `platform_capabilities.json`
  - 宿主能力真相、降级方式与 required paths
- `platform_targets.json`
  - 平台生成目标、目录布局与渲染面

`platform_adapter.json` 的使用规则：

1. 用户先把 `paths.tools_root` 配到有效的 `RDC-Agent-Tools` 根目录。
2. 可使用绝对路径，或相对于当前 framework/package 根目录的相对路径。
3. 在通过 `validation.required_paths` 校验前，Agent 必须拒绝执行任何依赖平台真相的工作。

不允许在平台模板里手工散落第二份 Tools 路径真相、第二份 skill 路由或宿主专属平台定义。
