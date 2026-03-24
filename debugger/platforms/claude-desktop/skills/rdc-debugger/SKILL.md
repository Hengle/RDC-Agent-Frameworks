# `RDC Debugger` 主技能包装说明

当前文件是 Claude Desktop 的 public main skill 入口。

平台启动后默认保持普通对话态。只有用户手动召唤 `rdc-debugger`，才进入 RenderDoc/RDC GPU Debug 调试框架。

进入 `rdc-debugger` 后，本 skill 负责：

- `intent_gate`
- preflight
- 缺失输入补料
- intake 规范化
- case/run 初始化
- specialist 分派、阶段推进与质量门裁决

本 skill 只引用当前平台根目录的 `common/`：

- common/skills/rdc-debugger/SKILL.md
- 进入任何平台真相相关工作前，必须先校验 common/config/platform_adapter.json
- coordination_mode 与降级边界以 common/config/platform_capabilities.json 的当前平台定义为准。

未先将顶层 `debugger/common/` 拷入当前平台根目录的 `common/` 之前，不允许在宿主中使用当前平台模板。

运行时 case/run 现场与第二层报告统一写入平台根目录下的 `workspace/`
