# RenderDoc/RDC GPU Debug

`debugger/` 是 framework 源码与模板生成根目录，不是宿主平台的直接运行根。Agent 的目标始终是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

运行时共享文档入口位于 `common/docs/`：

- `common/docs/cli-mode-reference.md`
- `common/docs/model-routing.md`
- `common/docs/platform-capability-matrix.md`
- `common/docs/platform-capability-model.md`
- `common/docs/runtime-coordination-model.md`

平台模板位于 `platforms/<platform>/`。用户工作流：

1. 选择目标平台模板目录。
2. 将根目录 `debugger/common/` 拷贝到该平台根的 `common/`。
3. 完成覆盖后，在对应宿主中打开该平台根目录使用。

说明：

- 平台内 `common/` 默认只保留最小占位目录，用来等待整包覆盖。
- 未完成 `debugger/common/ -> platforms/<platform>/common/` 覆盖前，平台模板不可用。

维护者说明位于 `docs/多平台适配说明.md`，其中描述模板 contract、`common/` 拷贝工作流与 scaffold 生成/校验方式。
