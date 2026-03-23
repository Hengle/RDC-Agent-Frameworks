from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUGGER_ROOT = REPO_ROOT / "debugger"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class RepoBaselineValidationTests(unittest.TestCase):
    def test_doc_contract_markers_present(self) -> None:
        validator = _load_module(DEBUGGER_ROOT / "scripts" / "validate_debugger_repo.py", "validate_debugger_repo_docs_module")
        findings = validator._doc_contract_findings(DEBUGGER_ROOT)
        self.assertEqual(findings, [])

    def test_scaffold_expected_paths_cover_cursor(self) -> None:
        scaffold = _load_module(DEBUGGER_ROOT / "scripts" / "sync_platform_scaffolds.py", "sync_platform_scaffolds_module")
        ctx = scaffold.load_context(DEBUGGER_ROOT)
        expected = scaffold.expected_files(ctx, "cursor")
        self.assertIn(DEBUGGER_ROOT / "platforms" / "cursor" / ".cursorrules", expected)
        self.assertIn(DEBUGGER_ROOT / "platforms" / "cursor" / ".cursor" / "mcp.json", expected)
        self.assertIn(DEBUGGER_ROOT / "platforms" / "cursor" / "agents" / "01_team_lead.md", expected)
        self.assertIn(DEBUGGER_ROOT / "platforms" / "cursor" / "skills" / "renderdoc-rdc-gpu-debug" / "SKILL.md", expected)
        self.assertIn(DEBUGGER_ROOT / "platforms" / "cursor" / "hooks" / "hooks.json", expected)

    def test_claude_settings_matchers_are_strings(self) -> None:
        settings = json.loads(
            (DEBUGGER_ROOT / "platforms" / "claude-code" / ".claude" / "settings.json").read_text(
                encoding="utf-8-sig"
            )
        )
        hooks = settings.get("hooks") or {}

        for event_name, entries in hooks.items():
            self.assertIsInstance(entries, list, event_name)
            for entry in entries:
                self.assertIsInstance(entry.get("matcher"), str, f"{event_name} matcher must be string")

    def test_codex_coordination_mode_is_consistent(self) -> None:
        compliance = json.loads(
            (DEBUGGER_ROOT / "common" / "config" / "framework_compliance.json").read_text(encoding="utf-8-sig")
        )
        capabilities = json.loads(
            (DEBUGGER_ROOT / "common" / "config" / "platform_capabilities.json").read_text(encoding="utf-8-sig")
        )

        self.assertEqual(
            compliance["platforms"]["codex"]["coordination_mode"],
            capabilities["platforms"]["codex"]["coordination_mode"],
        )
        self.assertEqual(capabilities["platforms"]["codex"]["coordination_mode"], "staged_handoff")


if __name__ == "__main__":
    unittest.main()
