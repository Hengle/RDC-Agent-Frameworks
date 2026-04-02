from __future__ import annotations

import importlib.util
import json
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
HARNESS_PATH = DEBUGGER_ROOT / "common" / "hooks" / "utils" / "harness_guard.py"


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


def _prepare_root() -> Path:
    root = Path(tempfile.mkdtemp()) / "debugger"
    shutil.copytree(DEBUGGER_ROOT / "common", root / "common")
    return root


def _seed_capture(root: Path, name: str) -> Path:
    path = root / "incoming" / name
    _write(path, f"fixture:{name}")
    return path


def _session_id(run_root: Path) -> str:
    data = yaml.safe_load((run_root / "run.yaml").read_text(encoding="utf-8"))
    return str(data["session_id"])


def _action_chain_path(root: Path, run_root: Path) -> Path:
    return root / "common" / "knowledge" / "library" / "sessions" / _session_id(run_root) / "action_chain.jsonl"


def _append_event(path: Path, event: dict) -> None:
    rows = []
    if path.is_file():
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows.append(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _runtime_payload(run_root: Path, *, owner_agent_id: str, action_request_id: str) -> dict[str, object]:
    session = yaml.safe_load((run_root / "artifacts" / "runtime_session.yaml").read_text(encoding="utf-8"))
    snapshot = yaml.safe_load((run_root / "artifacts" / "runtime_snapshot.yaml").read_text(encoding="utf-8"))
    return {
        "entry_mode": session["entry_mode"],
        "backend": session["backend"],
        "runtime_generation": session["runtime_generation"],
        "snapshot_rev": snapshot["snapshot_rev"],
        "owner_agent_id": owner_agent_id,
        "lease_epoch": session["lease_epoch"],
        "continuity_status": session["continuity_status"],
        "action_request_id": action_request_id,
    }


class HarnessGuardTests(unittest.TestCase):
    def _load_guard(self):
        return _load_module(HARNESS_PATH, f"harness_guard_{id(self)}")

    def test_accept_intake_bootstraps_runtime_broker_artifacts(self) -> None:
        root = _prepare_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        case_root = root / "workspace" / "cases" / "case_001"
        capture_a = _seed_capture(root, "broken.rdc")
        capture_b = _seed_capture(root, "baseline.rdc")

        payload = guard.run_accept_intake(root, case_root, platform="codex", entry_mode="cli", backend="local", capture_paths=[str(capture_a), str(capture_b)])

        run_root = case_root / "runs" / "run_001"
        self.assertEqual(payload["status"], "passed")
        self.assertTrue((run_root / "artifacts" / "runtime_session.yaml").is_file())
        self.assertTrue((run_root / "artifacts" / "runtime_snapshot.yaml").is_file())
        self.assertTrue((run_root / "artifacts" / "ownership_lease.yaml").is_file())
        self.assertTrue((run_root / "artifacts" / "runtime_failure.yaml").is_file())

    def test_dispatch_specialist_acquires_and_validates_ownership_lease(self) -> None:
        root = _prepare_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        case_root = root / "workspace" / "cases" / "case_001"
        capture_a = _seed_capture(root, "broken.rdc")
        capture_b = _seed_capture(root, "baseline.rdc")
        guard.run_accept_intake(root, case_root, platform="codex", entry_mode="cli", backend="local", capture_paths=[str(capture_a), str(capture_b)])
        run_root = case_root / "runs" / "run_001"

        payload = guard.run_dispatch_specialist(root, run_root, platform="codex", target_agent="pixel_forensics_agent", objective="inspect hotspot")

        self.assertEqual(payload["status"], "passed")
        lease = payload["ownership_lease"]
        self.assertTrue(Path(lease["path"]).is_file())
        valid = guard.validate_ownership_lease(run_root, lease_ref=lease["path"], owner_agent_id="pixel_forensics_agent", action_class="broker_action")
        self.assertEqual(valid["status"], "passed")
        wrong = guard.validate_ownership_lease(run_root, lease_ref=lease["path"], owner_agent_id="shader_ir_agent", action_class="broker_action")
        self.assertEqual(wrong["status"], "blocked")
        self.assertEqual(wrong["blocking_code"], "BLOCKED_OWNERSHIP_LEASE_OWNER_MISMATCH")

    def test_specialist_feedback_releases_active_lease_after_handoff_artifact(self) -> None:
        root = _prepare_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        case_root = root / "workspace" / "cases" / "case_001"
        capture_a = _seed_capture(root, "broken.rdc")
        capture_b = _seed_capture(root, "baseline.rdc")
        guard.run_accept_intake(root, case_root, platform="codex", entry_mode="cli", backend="local", capture_paths=[str(capture_a), str(capture_b)])
        run_root = case_root / "runs" / "run_001"
        guard.run_dispatch_specialist(root, run_root, platform="codex", target_agent="pixel_forensics_agent", objective="inspect hotspot")

        note = run_root / "notes" / "pixel_forensics.md"
        _write(note, "brief")
        path = _action_chain_path(root, run_root)
        _append_event(path, {
            "schema_version": "2",
            "event_id": "evt-pixel-brief",
            "ts_ms": 9999999999999,
            "run_id": "run_001",
            "session_id": _session_id(run_root),
            "agent_id": "pixel_forensics_agent",
            "event_type": "artifact_write",
            "status": "written",
            "duration_ms": 10,
            "refs": [],
            "payload": {"path": str(note).replace('\\', '/'), "artifact_role": "specialist_brief", **_runtime_payload(run_root, owner_agent_id="pixel_forensics_agent", action_request_id="ar-pixel-brief")},
        })

        payload = guard.run_specialist_feedback(root, run_root)

        self.assertEqual(payload["status"], "passed")
        lease = yaml.safe_load((run_root / "artifacts" / "ownership_lease.yaml").read_text(encoding="utf-8"))
        self.assertEqual(lease["status"], "released")

    def test_specialist_feedback_freezes_run_after_timeout(self) -> None:
        root = _prepare_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        case_root = root / "workspace" / "cases" / "case_001"
        capture_a = _seed_capture(root, "broken.rdc")
        capture_b = _seed_capture(root, "baseline.rdc")
        guard.run_accept_intake(root, case_root, platform="codex", entry_mode="cli", backend="local", capture_paths=[str(capture_a), str(capture_b)])
        run_root = case_root / "runs" / "run_001"
        guard.run_dispatch_specialist(root, run_root, platform="codex", target_agent="pixel_forensics_agent", objective="inspect hotspot")

        payload = guard.run_specialist_feedback(root, run_root, timeout_seconds=1, now_ms=9999999999999)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT", payload["blocking_codes"])
        self.assertTrue((run_root / "artifacts" / "freeze_state.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
