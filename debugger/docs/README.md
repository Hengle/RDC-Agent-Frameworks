# Docs Scope（维护者文档范围）

`debugger/docs/` 只服务 `debugger/` 维护者，用来说明平台模板、脚手架与目录治理。

这里不是运行时共享文档区，不对其他 framework 产生约束，也不允许被平台 runtime 直接依赖。

运行时共享文档统一位于 `../common/docs/`。

当前维护者入口：

- `多平台适配说明.md`：`debugger/` 平台模板 contract、`common/` 拷贝工作流、scaffold 生成与校验说明。
- `5分钟接线指南.md`：首次手工接线 `debugger` 到 `RDC-Agent-Tools` 的最短路径。
- `compatibility-matrix.md`：`debugger` 与 `Tools` 的推荐配对与 snapshot 对齐要求。

其中 `多平台适配说明.md` 负责解释 shared common 覆盖后的目录语义、`common/README.md` 入口和 Claude hooks 的 string matcher 口径；具体平台行为只在对应平台模板内定义。
