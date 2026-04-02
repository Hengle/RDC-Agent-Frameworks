from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(f"PyYAML is required for tests: {exc}")


REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUGGER_ROOT = REPO_ROOT / "debugger"
ENTRY_GATE_PATH = DEBUGGER_ROOT / "common" / "hooks" / "utils" / "entry_gate.py"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class EntryGateTests(unittest.TestCase):
    def _prepare_root(self) -> Path:
        root = Path(tempfile.mkdtemp()) / "debugger"
        shutil.copytree(DEBUGGER_ROOT / "common", root / "common")
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        return root

    def test_entry_gate_emits_single_runtime_broker_contract(self) -> None:
        root = self._prepare_root()
        module = _load_module(ENTRY_GATE_PATH, f"entry_gate_{id(self)}")
        case_root = root / "workspace" / "cases" / "case_001"
        capture = root / "incoming" / "broken.rdc"
        _write(capture, "fixture")

        payload = module.run_entry_gate(
            root,
            case_root,
            platform="codex",
            entry_mode="cli",
            backend="local",
            capture_paths=[str(capture)],
            fix_reference_status="strict_ready",
        )

        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["platform_contract"]["coordination_mode"], "staged_handoff")
        self.assertEqual(payload["platform_contract"]["orchestration_mode"], "multi_agent")
        self.assertEqual(payload["platform_contract"]["live_runtime_policy"], "single_runtime_single_context")
        self.assertEqual(payload["runtime_mode_truth"]["runtime_parallelism_ceiling"], "single_runtime_single_context")
        artifact = yaml.safe_load((case_root / "artifacts" / "entry_gate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "passed")

    def test_entry_gate_blocks_missing_strict_ready_fix_reference(self) -> None:
        root = self._prepare_root()
        module = _load_module(ENTRY_GATE_PATH, f"entry_gate_fixref_{id(self)}")
        case_root = root / "workspace" / "cases" / "case_001"
        capture = root / "incoming" / "broken.rdc"
        _write(capture, "fixture")

        payload = module.run_entry_gate(
            root,
            case_root,
            platform="codex",
            entry_mode="cli",
            backend="local",
            capture_paths=[str(capture)],
            fix_reference_status="missing",
        )

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("BLOCKED_MISSING_FIX_REFERENCE", {item["code"] for item in payload["blockers"]})


if __name__ == "__main__":
    unittest.main()
