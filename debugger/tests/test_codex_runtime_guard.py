from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(f"PyYAML is required for tests: {exc}")


REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUGGER_ROOT = REPO_ROOT / "debugger"
CODEX_ROOT = DEBUGGER_ROOT / "platforms" / "codex"
GUARD_PATH = CODEX_ROOT / ".codex" / "runtime_guard.py"


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


def _seed_tools(root: Path) -> None:
    snapshot = json.loads((DEBUGGER_ROOT / "common" / "config" / "tool_catalog.snapshot.json").read_text(encoding="utf-8-sig"))
    _write(root / "tools" / "README.md", "ok\n")
    _write(root / "tools" / "docs" / "tools.md", "ok\n")
    _write(root / "tools" / "docs" / "session-model.md", "ok\n")
    _write(root / "tools" / "docs" / "agent-model.md", "ok\n")
    _write(root / "tools" / "spec" / "tool_catalog.json", json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")


def _prepare_platform_root(*, with_common: bool = True, with_tools: bool = True) -> Path:
    root = Path(tempfile.mkdtemp()) / "codex"
    shutil.copytree(CODEX_ROOT, root)
    if with_common:
        shutil.rmtree(root / "common", ignore_errors=True)
        shutil.copytree(DEBUGGER_ROOT / "common", root / "common")
    if with_tools:
        shutil.rmtree(root / "tools", ignore_errors=True)
        _seed_tools(root)
    return root


class CodexRuntimeGuardTests(unittest.TestCase):
    def _load_guard(self):
        return _load_module(GUARD_PATH, f"codex_runtime_guard_{id(self)}")

    def test_preflight_blocks_missing_common_and_tools(self) -> None:
        root = _prepare_platform_root(with_common=False, with_tools=False)
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()

        payload = guard.run_preflight(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["blocking_codes"], ["BLOCKED_ENTRY_PREFLIGHT", "BLOCKED_ENTRY_PREFLIGHT"])

    def test_accept_intake_bootstraps_shared_runtime_broker(self) -> None:
        root = _prepare_platform_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        case_root = root / "workspace" / "cases" / "case_001"
        capture_a = root / "incoming" / "broken.rdc"
        capture_b = root / "incoming" / "baseline.rdc"
        _write(capture_a, "broken")
        _write(capture_b, "baseline")

        payload = guard.run_accept_intake(root, case_root, platform="codex", entry_mode="cli", backend="local", capture_paths=[str(capture_a), str(capture_b)])

        run_root = case_root / "runs" / "run_001"
        self.assertEqual(payload["status"], "passed")
        self.assertTrue((run_root / "artifacts" / "runtime_session.yaml").is_file())
        self.assertTrue((run_root / "artifacts" / "runtime_snapshot.yaml").is_file())
        self.assertTrue((run_root / "artifacts" / "ownership_lease.yaml").is_file())
        self.assertTrue((run_root / "artifacts" / "runtime_failure.yaml").is_file())

    def test_dispatch_specialist_uses_shared_ownership_lease(self) -> None:
        root = _prepare_platform_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        case_root = root / "workspace" / "cases" / "case_001"
        capture_a = root / "incoming" / "broken.rdc"
        capture_b = root / "incoming" / "baseline.rdc"
        _write(capture_a, "broken")
        _write(capture_b, "baseline")
        guard.run_accept_intake(root, case_root, platform="codex", entry_mode="cli", backend="local", capture_paths=[str(capture_a), str(capture_b)])
        run_root = case_root / "runs" / "run_001"

        payload = guard.run_dispatch_specialist(root, run_root, platform="codex", target_agent="pixel_forensics_agent", objective="inspect hotspot")

        self.assertEqual(payload["status"], "passed")
        self.assertIn("ownership_lease", payload)
        lease = yaml.safe_load((run_root / "artifacts" / "ownership_lease.yaml").read_text(encoding="utf-8"))
        self.assertEqual(lease["status"], "active")
        self.assertEqual(lease["owner_agent_id"], "pixel_forensics_agent")

    def test_final_audit_delegates_to_shared_writer(self) -> None:
        guard = self._load_guard()
        root = Path(tempfile.mkdtemp())
        run_root = root / "workspace" / "cases" / "case_001" / "runs" / "run_01"
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        expected = {"status": "passed", "paths": {"action_chain": "dummy"}}

        with mock.patch.object(guard, "shared_run_final_audit", return_value=expected) as mocked:
            payload = guard.run_final_audit(root, run_root, platform="codex")

        self.assertIs(payload, expected)
        mocked.assert_called_once_with(root, run_root.resolve(), platform="codex")

    def test_codex_truth_uses_shared_harness_and_single_runtime_context(self) -> None:
        capabilities = json.loads((DEBUGGER_ROOT / "common" / "config" / "platform_capabilities.json").read_text(encoding="utf-8-sig"))
        compliance = json.loads((DEBUGGER_ROOT / "common" / "config" / "framework_compliance.json").read_text(encoding="utf-8-sig"))
        codex = capabilities["platforms"]["codex"]

        self.assertEqual(codex["enforcement_layer"], "shared_harness")
        self.assertEqual(codex["live_runtime_policy"], "single_runtime_single_context")
        self.assertFalse(codex["capabilities"]["hooks"]["supported"])
        self.assertEqual(compliance["platforms"]["codex"]["enforcement_mode"], "shared_harness")
        self.assertIn("platforms/codex/.codex/runtime_guard.py", codex["required_paths"])
        self.assertIn("platforms/codex/.codex/agents/rdc-debugger.toml", codex["required_paths"])


if __name__ == "__main__":
    unittest.main()
