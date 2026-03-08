# RenderDoc/RDC GPU Debug Skill Wrapper

当前文件是 Code Buddy 的 skill 入口。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

本 skill 只引用当前平台根目录的 common/：

- ../../common/skills/renderdoc-rdc-gpu-debug/SKILL.md
- coordination_mode 与降级边界以 ../../common/config/platform_capabilities.json 的当前平台定义为准。

若这些路径仍是占位内容，先将顶层 debugger/common/ 拷入当前平台根目录的 common/ 后再继续。

运行时 case/run 现场与第二层报告统一写入：../workspace
