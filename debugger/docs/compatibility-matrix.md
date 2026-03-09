# Debugger / Tools 兼容矩阵

本文定义 `RDC-Agent-Frameworks/debugger` 与 `RDC-Agent-Tools` 的推荐配对关系。

## 当前推荐配对

| Frameworks/debugger | Tools | 说明 |
|---|---|---|
| 当前主线 | 当前主线（`tool_count = 202`） | 必须包含 `rd.vfs.ls` / `rd.vfs.cat` / `rd.vfs.tree` / `rd.vfs.resolve` |

## 最低对齐要求

- `tool_catalog.snapshot.json` 的 `tool_count` 必须等于 `Tools/spec/tool_catalog.json`
- snapshot 中必须包含：
  - `rd.vfs.ls`
  - `rd.vfs.cat`
  - `rd.vfs.tree`
  - `rd.vfs.resolve`
- `debugger` 文档中涉及探索面时，应按“只读 VFS + canonical `rd.*` tools”口径编写，不得把 `rd.vfs.*` 写成第二套平台真相

## 手工接线前必跑

```bat
python common/config/validate_binding.py --strict
python debugger/scripts/validate_tool_contract.py --mode source --strict
```
