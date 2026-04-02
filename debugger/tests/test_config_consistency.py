from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUGGER_ROOT = REPO_ROOT / "debugger"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class ConfigConsistencyTests(unittest.TestCase):
    def test_platform_contract_collapses_to_single_runtime_broker_model(self) -> None:
        compliance = _read_json(DEBUGGER_ROOT / "common" / "config" / "framework_compliance.json")
        capabilities = _read_json(DEBUGGER_ROOT / "common" / "config" / "platform_capabilities.json")

        capability_platforms = set((capabilities.get("platforms") or {}).keys())
        compliance_platforms = set((compliance.get("platforms") or {}).keys())
        self.assertEqual(capability_platforms, compliance_platforms)
        self.assertEqual(capability_platforms, {"claude-code", "code-buddy", "codex", "copilot-cli"})

        for key, row in (capabilities.get("platforms") or {}).items():
            self.assertEqual(row["coordination_mode"], "staged_handoff", key)
            self.assertEqual(row["orchestration_mode"], "multi_agent", key)
            self.assertEqual(row["live_runtime_policy"], "single_runtime_single_context", key)
            self.assertEqual(row["hook_ssot"], "shared_harness", key)
            self.assertEqual(row["sub_agent_mode"], "puppet_sub_agents", key)

        for key, row in (compliance.get("platforms") or {}).items():
            self.assertEqual(row["coordination_mode"], "staged_handoff", key)
            self.assertEqual(row["enforcement_mode"], "shared_harness", key)

    def test_runtime_mode_truth_uses_single_runtime_single_context_everywhere(self) -> None:
        snapshot = _read_json(DEBUGGER_ROOT / "common" / "config" / "runtime_mode_truth.snapshot.json")
        for key, row in (snapshot.get("modes") or {}).items():
            self.assertEqual(row["runtime_parallelism_ceiling"], "single_runtime_single_context", key)
            self.assertEqual(row["recovery_contract"], "single_controlled_recovery", key)

    def test_tool_catalog_snapshot_reflects_shader_replace_and_debug_contracts(self) -> None:
        snapshot = _read_json(DEBUGGER_ROOT / "common" / "config" / "tool_catalog.snapshot.json")
        tools = {str(item.get("name") or ""): item for item in snapshot.get("tools") or []}

        replace_tool = tools["rd.shader.edit_and_replace"]
        self.assertIn("event_id", replace_tool.get("param_names") or [])
        self.assertIn("ops", replace_tool.get("param_names") or [])
        self.assertIn("replacement_id", replace_tool.get("returns_raw") or "")
        self.assertIn("resolved_event_id", replace_tool.get("returns_raw") or "")

        debug_tool = tools["rd.shader.debug_start"]
        self.assertIn("resolved_context", debug_tool.get("returns_raw") or "")
        self.assertIn("resolved_event_id", debug_tool.get("returns_raw") or "")
        self.assertIn("failure_reason", debug_tool.get("returns_raw") or "")

    def test_repo_validator_accepts_shared_harness_and_pseudo_hooks(self) -> None:
        module = _load_module(DEBUGGER_ROOT / "scripts" / "validate_debugger_repo.py", "validate_debugger_repo_surface_module")
        capabilities = _read_json(DEBUGGER_ROOT / "common" / "config" / "platform_capabilities.json")
        self.assertTrue(module._required_surface_supported(capabilities["platforms"]["code-buddy"], "hooks"))
        self.assertFalse(module._native_surface_supported(capabilities["platforms"]["code-buddy"], "hooks"))
        self.assertFalse(module._platform_is_inherit_only(capabilities["platforms"]["codex"]))
        self.assertEqual(capabilities["platforms"]["codex"]["enforcement_layer"], "shared_harness")

    def test_validate_tool_contract_reader_reports_invalid_adapter_json(self) -> None:
        module = _load_module(DEBUGGER_ROOT / "scripts" / "validate_tool_contract.py", "validate_tool_contract_module")
        with tempfile.TemporaryDirectory() as tmp:
            bad_json = Path(tmp) / "platform_adapter.json"
            bad_json.write_text('{"paths":{"tools_source_root":"tools",}}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                module.read_json(bad_json)


if __name__ == "__main__":
    unittest.main()
