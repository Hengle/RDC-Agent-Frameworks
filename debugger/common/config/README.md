# Platform Adapter Config（平台适配配置）

本目录保存的是连接 Debugger framework 与生成后平台模板的共享配置真相。

## 规则

- `debugger/common/` 是唯一长期存在的共享源目录。
- `debugger/platforms/*` 是生成后的平台产物。
- 只有在共享树被拷入后，平台本地 wrapper 才允许引用平台本地的 `common/` 目录。
- Tools 仓库路径、MCP 启动命令和 CLI adapter 细节都属于 adapter 关注点，不属于 framework 真相。

## 文件说明

- `platform_adapter.json`
  - fail-closed 的 tools-root 入口配置。
- `role_manifest.json`
  - 角色清单、共享 prompt 映射、共享 skill 映射与平台文件名。
- `role_policy.json`
  - reasoning effort、verbosity、tool policy、hook policy 与 delegation。
  - 不得包含按平台拆分的模型路由。
- `model_routing.json`
  - 模型能力要求、平台分类和角色到平台模型路由的唯一权威来源。
- `mcp_servers.json`
  - 逻辑 MCP server 定义。
- `platform_capabilities.json`
  - 宿主能力真相、降级语义与生成后的必需路径。
- `platform_targets.json`
  - 生成目标、目录布局与渲染面定义。

## 使用方式

1. 在 `platform_adapter.json` 中设置 `paths.tools_root`。
2. 校验 `validation.required_paths` 中的每个条目。
3. 校验失败时拒绝执行 debugger。
4. 模型路由只允许维护在 `model_routing.json` 中。

生成后的 wrapper、插件文件和角色配置都应从本目录重新同步，不应在平台产物上手工打补丁。
