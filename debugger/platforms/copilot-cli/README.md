# Copilot CLI Template

当前目录是 Copilot CLI 的 platform-local 模板。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

使用方式：

1. 将仓库根目录 debugger/common/ 整体拷贝到当前平台根目录的 common/，覆盖占位内容。
2. 使用当前平台根目录同级的 workspace/ 作为运行区。
3. 在对应宿主中打开当前平台根目录。
4. 平台内的 skill、hooks、agents、config 只允许引用本地 common/。

约束：

- common/ 默认只保留占位骨架；正式共享正文仍由顶层 debugger/common/ 提供，并由用户显式拷入。
- workspace/ 预生成空骨架；真实运行产物在平台使用阶段按 case/run 写入。
- 当前平台状态：$(@{display_name=Copilot CLI; status_label=full; packaging=cli-plugin; capabilities=; coordination_mode=staged_handoff; degradation_mode=native-no-per-agent-model; cli_discovery_policy=cli-reference-required; required_paths=System.Object[]}.status_label)。
- 当前平台生成面：$surfaces。
- 维护者若重跑 scaffold，必须继续产出 platform-local common/ 占位结构，不得回退到跨级引用。
