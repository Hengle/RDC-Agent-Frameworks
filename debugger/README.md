# RenderDoc/RDC GPU Debug

`debugger/` 是 framework 源码与模板生成根目录，不是宿主平台的直接运行根。

## 使用前提

开始使用 `debugger/` 之前，必须先完成：

1. 配置 `common/config/platform_adapter.json`
2. 将 `paths.tools_root` 指向有效的 `RDC-Agent-Tools` 根目录
3. 确认 `validation.required_paths` 中的文件在 `<resolved tools_root>/` 下存在

未完成以上步骤前：

- Agent 不得进入依赖平台真相的工作
- skills、README、AGENT_CORE 与平台模板都只能提供 framework 约束，不能替代 Tools 真相

## 运行时共享文档入口

- `common/AGENT_CORE.md`
- `common/docs/cli-mode-reference.md`
- `common/docs/model-routing.md`
- `common/docs/platform-capability-matrix.md`
- `common/docs/platform-capability-model.md`
- `common/docs/runtime-coordination-model.md`
- `common/docs/workspace-layout.md`

## 平台模板使用方式

平台模板位于 `platforms/<platform>/`。用户工作流：

1. 选择目标平台模板目录
2. 将根目录 `debugger/common/` 拷贝到该平台根的 `common/`
3. 在平台根目录的 `common/config/platform_adapter.json` 中配置 `paths.tools_root`
4. 确认 `validation.required_paths` 校验通过
5. 完成覆盖后，在对应宿主中打开该平台根目录
6. 正常用户请求从 `team_lead` 发起；其他 specialist 角色默认是 internal/debug-only

说明：

- 平台内 `common/` 默认只保留最小占位目录，用来等待整包覆盖
- 未完成 `debugger/common/ -> platforms/<platform>/common/` 覆盖前，平台模板不可用

维护者说明位于 `docs/多平台适配说明.md`，其中描述模板 contract、`common/` 拷贝工作流与 scaffold 生成/校验方式。
