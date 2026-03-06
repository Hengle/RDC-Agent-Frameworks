# RenderDoc/RDC GPU Debug Skill

This skill exists to make the agent explicitly aware that the task is to use RenderDoc/RDC platform tools to debug GPU rendering problems.

Read first:

- `../../../../common/AGENT_CORE.md`
- `../../../../docs/platform-capability-model.md`
- `../../../../docs/model-routing.md`
- `../../../../docs/cli-mode-reference.md` when the user explicitly requests `CLI` mode

Rules:

- `MCP` mode may do tool discovery.
- `CLI` mode must not use discovery-by-trial-and-error.
- The objective is not to discuss an abstract framework; the objective is to drive `rd.*` / platform tools to inspect captures, sessions, events, resources, shaders, and evidence.
