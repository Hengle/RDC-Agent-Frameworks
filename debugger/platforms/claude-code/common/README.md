# Platform Local Common Placeholder

当前目录是平台本地 `common/` 的占位骨架，不是正式运行时内容。

使用方式：

1. 选择一个 `debugger/platforms/<platform>/` 模板。
2. 将仓库根目录 `debugger/common/` 整体拷贝到该平台根目录的 `common/`，覆盖当前占位内容。
3. 再在对应宿主中打开该平台根目录使用。

约束：

- 平台内所有 skill、hooks、agents、config 只允许引用当前平台根目录的 `common/`。
- 平台内运行时工作区固定为当前平台根目录同级的 `workspace/`。
- 占位文件只用于稳定路径，不代表最终角色定义、skill 正文、hook 逻辑或配置真相。
