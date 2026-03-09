from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "debugger" / "common" / "config" / "validate_binding.py"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_binding_module", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class BindingValidationTests(unittest.TestCase):
    def test_validate_binding_accepts_configured_source_root(self) -> None:
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "debugger"
            tools_root = Path(tmp) / "tools"

            for rel in (
                "README.md",
                "common/AGENT_CORE.md",
                "common/docs/cli-mode-reference.md",
                "common/docs/model-routing.md",
                "common/docs/platform-capability-matrix.md",
                "common/docs/platform-capability-model.md",
                "common/docs/runtime-coordination-model.md",
                "common/docs/workspace-layout.md",
                "platforms/codex/README.md",
                "platforms/codex/AGENTS.md",
                "platforms/codex/.codex/config.toml",
                "platforms/codex/.codex/agents/team_lead.toml",
                "platforms/codex/.agents/skills/renderdoc-rdc-gpu-debug/SKILL.md",
            ):
                _write(root / rel, "ok\n")

            _write(
                root / "common" / "config" / "platform_adapter.json",
                json.dumps(
                    {
                        "paths": {"tools_root": str(tools_root)},
                        "validation": {
                            "required_paths": [
                                "README.md",
                                "docs/tools.md",
                                "docs/session-model.md",
                                "docs/agent-model.md",
                                "spec/tool_catalog.json",
                            ]
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            _write(
                root / "common" / "config" / "platform_capabilities.json",
                json.dumps(
                    {
                        "platforms": {
                            "codex": {
                                "required_paths": [
                                    "platforms/codex/README.md",
                                    "platforms/codex/AGENTS.md",
                                    "platforms/codex/.codex/config.toml",
                                    "platforms/codex/.codex/agents/team_lead.toml",
                                    "platforms/codex/.agents/skills/renderdoc-rdc-gpu-debug/SKILL.md",
                                ]
                            }
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            _write(
                root / "common" / "config" / "tool_catalog.snapshot.json",
                json.dumps(
                    {
                        "tool_count": 202,
                        "tools": [{"name": name} for name in sorted(validator.VFS_TOOLS | {"rd.session.get_context"})],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            for rel in ("README.md", "docs/tools.md", "docs/session-model.md", "docs/agent-model.md"):
                _write(tools_root / rel, "ok\n")
            _write(
                tools_root / "spec" / "tool_catalog.json",
                json.dumps(
                    {
                        "tool_count": 202,
                        "tools": [{"name": name} for name in sorted(validator.VFS_TOOLS | {"rd.session.get_context"})],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            findings = validator.validate_binding(root, platform="codex")

            self.assertEqual(findings, [])

    def test_validate_binding_rejects_placeholder_tools_root(self) -> None:
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "debugger"
            _write(
                root / "common" / "config" / "platform_adapter.json",
                json.dumps(
                    {
                        "paths": {"tools_root": "__CONFIGURE_TOOLS_ROOT__"},
                        "validation": {"required_paths": ["README.md"]},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            findings = validator.validate_binding(root)

            self.assertIn("platform_adapter.json missing configured paths.tools_root", findings)


if __name__ == "__main__":
    unittest.main()
