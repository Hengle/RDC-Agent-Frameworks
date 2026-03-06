# Copilot IDE Adaptation

This directory packages the best-effort adaptation for VS Code / IDE custom agents.

Target capability set:

- custom agents / agent plugins
- hooks
- MCP
- preferred per-agent model routing

Notes:

- IDE hosts may support preferred model selection, but exact model availability is host-dependent.
- This package preserves role layering even when the host cannot satisfy every preferred model.

