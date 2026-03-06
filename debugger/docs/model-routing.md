# Model Routing

本文定义平台无关的角色到模型偏好矩阵，以及各平台的映射与降级方式。

## 全局角色偏好

- `team_lead`
  - 角色：orchestrator
  - 优先模型：`opus-4.6`
- `skeptic_agent`
  - 角色：verifier
  - 优先模型：`gpt-5.4`
- `curator_agent`
  - 角色：reporter / knowledge
  - 优先模型：`gemini-3.1-pro`
- `triage_agent`、`capture_repro_agent`、`pass_graph_pipeline_agent`、`pixel_forensics_agent`、`shader_ir_agent`、`driver_device_agent`
  - 角色：investigator
  - 优先模型：`grok-4.1` 或 `sonnet-4.6`

## 平台回退原则

- 平台支持显式 per-agent model 时，按 `common/config/model_routing.json` 直接映射。
- 平台只支持 model alias 时，保留角色分工，映射到最接近的家族别名。
- 平台忽略或不支持 per-agent model 时，保留角色设计，降级为 `inherit` 或宿主默认模型。
- 不因平台能力不足而改写角色边界。

权威配置文件：

- `common/config/model_routing.json`
