# CLI Mode Reference

用户明确要求 `CLI` 模式时，先阅读以下规范文件，再执行调试任务：

- `../../../../docs/cli-mode-reference.md`
- `../../../../docs/platform-capability-model.md`

使用约束：

- 不把 `CLI` 当成 tool discovery 载体。
- 不通过 `--help`、枚举命令、随机试跑来猜测能力面。
- 仅依赖已文档化的最小链路、关键状态名和常见命令族。
