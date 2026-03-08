#!/usr/bin/env python3
import sys

MESSAGE = (
 "当前平台根目录的 common/ 仍然是占位内容。"
 "请先将仓库根目录 debugger/common/ 整体拷贝到当前平台根目录 common/，"
 "覆盖占位文件后再执行 hooks。"
)

print(MESSAGE, file=sys.stderr)
raise SystemExit(2)
