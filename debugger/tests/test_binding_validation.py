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
    def test_validate_binding_accepts_fixed_package_local_tools_root(self) -> None:
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "debugger"
            tools_root = root / "tools"
            tool_names = sorted(validator.REQUIRED_FRAMEWORK_TOOLS)

            for rel in (
                "README.md",
                "common/README.md",
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
                        "paths": {"tools_root": "tools"},
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
                        "tool_count": len(tool_names),
                        "tools": [{"name": name} for name in tool_names],
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
                        "tool_count": len(tool_names),
                        "tools": [{"name": name} for name in tool_names],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            findings = validator.validate_binding(root, platform="codex")

            self.assertEqual(findings, [])

    def test_validate_binding_rejects_legacy_configurable_tools_root(self) -> None:
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

            self.assertEqual(
                findings,
                ["platform_adapter.json must keep paths.tools_root='tools' and use the package-local tools/ directory"],
            )

    def test_validate_binding_rejects_non_package_local_tools_root(self) -> None:
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "debugger"
            _write(
                root / "common" / "config" / "platform_adapter.json",
                json.dumps(
                    {
                        "paths": {"tools_root": str(Path(tmp) / "external-tools")},
                        "validation": {"required_paths": ["README.md"]},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            findings = validator.validate_binding(root)

            self.assertEqual(
                findings,
                ["platform_adapter.json must keep paths.tools_root='tools' and use the package-local tools/ directory"],
            )

    def test_validate_binding_rejects_placeholder_common_readme(self) -> None:
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "debugger"
            tools_root = root / "tools"
            tool_names = sorted(validator.REQUIRED_FRAMEWORK_TOOLS)

            for rel in (
                "README.md",
                "AGENTS.md",
                "common/AGENT_CORE.md",
                "common/docs/cli-mode-reference.md",
                "common/docs/model-routing.md",
                "common/docs/platform-capability-matrix.md",
                "common/docs/platform-capability-model.md",
                "common/docs/runtime-coordination-model.md",
                "common/docs/workspace-layout.md",
                "common/config/tool_catalog.snapshot.json",
                "common/config/platform_capabilities.json",
                "common/config/platform_adapter.json",
            ):
                _write(root / rel, "ok\n")

            _write(root / "common/README.md", "# Platform Local Common Placeholder\n")
            _write(tools_root / "README.md", "tools\n")
            _write(tools_root / "docs/tools.md", "ok\n")
            _write(tools_root / "docs/session-model.md", "ok\n")
            _write(tools_root / "docs/agent-model.md", "ok\n")
            _write(
                tools_root / "spec/tool_catalog.json",
                json.dumps(
                    {
                        "tool_count": len(tool_names),
                        "tools": [{"name": name} for name in tool_names],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            _write(
                root / "common" / "config" / "tool_catalog.snapshot.json",
                json.dumps(
                    {
                        "tool_count": len(tool_names),
                        "tools": [{"name": name} for name in tool_names],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            _write(
                root / "common" / "config" / "platform_capabilities.json",
                json.dumps({"platforms": {}}, ensure_ascii=False, indent=2),
            )
            _write(
                root / "common" / "config" / "platform_adapter.json",
                json.dumps(
                    {
                        "paths": {"tools_root": "tools"},
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

            findings = validator.validate_binding(root)

            self.assertIn(
                "common/README.md is still a platform placeholder - copy debugger/common/ into the platform root common/ again",
                findings,
            )

    def test_validate_binding_reports_invalid_adapter_json(self) -> None:
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "debugger"
            _write(
                root / "common" / "config" / "platform_adapter.json",
                '{"paths":{"tools_root":"tools",}}\n',
            )

            findings = validator.validate_binding(root)

            self.assertEqual(len(findings), 1)
            self.assertIn("invalid JSON in", findings[0])
            self.assertNotIn("forward slashes or escaped backslashes", findings[0])


if __name__ == "__main__":
    unittest.main()
