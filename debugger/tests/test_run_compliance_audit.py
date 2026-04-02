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
AUDIT_PATH = DEBUGGER_ROOT / "common" / "hooks" / "utils" / "run_compliance_audit.py"
BROKER_PATH = DEBUGGER_ROOT / "common" / "hooks" / "utils" / "runtime_broker.py"


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


def _seed_happy_run(root: Path, *, release_lease: bool = True) -> tuple[object, object, object, Path]:
    guard = _load_module(HARNESS_PATH, f"harness_guard_{id(root)}")
    audit = _load_module(AUDIT_PATH, f"audit_{id(root)}")
    broker = _load_module(BROKER_PATH, f"broker_{id(root)}")
    case_root = root / "workspace" / "cases" / "case_001"
    capture_a = _seed_capture(root, "broken.rdc")
    capture_b = _seed_capture(root, "baseline.rdc")
    guard.run_accept_intake(root, case_root, platform="codex", entry_mode="cli", backend="local", capture_paths=[str(capture_a), str(capture_b)])
    run_root = case_root / "runs" / "run_001"
    guard.run_dispatch_specialist(root, run_root, platform="codex", target_agent="pixel_forensics_agent", objective="inspect hotspot")

    note = run_root / "notes" / "pixel_forensics.md"
    _write(note, "brief")
    action_chain = _action_chain_path(root, run_root)
    _append_event(action_chain, {
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
    if release_lease:
        guard.run_specialist_feedback(root, run_root)

    report_md = run_root / "reports" / "report.md"
    visual_report = run_root / "reports" / "visual_report.html"
    _write(report_md, "report")
    _write(visual_report, "<html></html>")
    (run_root / "artifacts" / "fix_verification.yaml").write_text(yaml.safe_dump({"verdict": "fixed", "overall_result": {"status": "passed", "verdict": "fixed"}}, sort_keys=False, allow_unicode=True), encoding="utf-8")

    session_root = root / "common" / "knowledge" / "library" / "sessions" / _session_id(run_root)
    (session_root / "session_evidence.yaml").parent.mkdir(parents=True, exist_ok=True)
    (session_root / "session_evidence.yaml").write_text(yaml.safe_dump({"reference_contract": {"readiness_status": "strict_ready"}, "fix_verification": {"status": "passed"}, "challenge_resolution": {}, "redispatch_summary": {}}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (session_root / "skeptic_signoff.yaml").write_text(yaml.safe_dump({"status": "passed", "strict_signoff": True}, sort_keys=False, allow_unicode=True), encoding="utf-8")

    _append_event(action_chain, {
        "schema_version": "2",
        "event_id": "evt-skeptic",
        "ts_ms": 3000,
        "run_id": "run_001",
        "session_id": _session_id(run_root),
        "agent_id": "skeptic_agent",
        "event_type": "artifact_write",
        "status": "written",
        "duration_ms": 5,
        "refs": [],
        "payload": {"path": str(session_root / "skeptic_signoff.yaml").replace('\\', '/'), "artifact_role": "skeptic_signoff", **_runtime_payload(run_root, owner_agent_id="skeptic_agent", action_request_id="ar-skeptic")},
    })
    _append_event(action_chain, {
        "schema_version": "2",
        "event_id": "evt-curator",
        "ts_ms": 4000,
        "run_id": "run_001",
        "session_id": _session_id(run_root),
        "agent_id": "curator_agent",
        "event_type": "artifact_write",
        "status": "written",
        "duration_ms": 5,
        "refs": [],
        "payload": {"path": str(report_md).replace('\\', '/'), "artifact_role": "final_report", **_runtime_payload(run_root, owner_agent_id="curator_agent", action_request_id="ar-curator")},
    })
    return guard, audit, broker, run_root


class RunComplianceAuditTests(unittest.TestCase):
    def test_write_run_audit_artifact_passes_on_broker_owned_happy_path(self) -> None:
        root = _prepare_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard, audit, _, run_root = _seed_happy_run(root, release_lease=True)

        payload = audit.write_run_audit_artifact(root, run_root, "codex")

        self.assertEqual(payload["status"], "passed")
        self.assertTrue((run_root / "artifacts" / "run_compliance.yaml").is_file())
        verdict = guard.run_render_user_verdict(root, run_root)
        self.assertEqual(verdict["status"], "passed")

    def test_write_run_audit_artifact_fails_when_lease_stays_active(self) -> None:
        root = _prepare_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        _, audit, broker, run_root = _seed_happy_run(root, release_lease=False)

        payload = audit.write_run_audit_artifact(root, run_root, "codex")

        self.assertEqual(payload["status"], "failed")
        failing = {item["id"] for item in payload["checks"] if item["result"] == "fail"}
        self.assertIn("ownership_lease_released", failing)
        lease = broker.load_ownership_lease(run_root)
        self.assertEqual(lease["status"], "active")


if __name__ == "__main__":
    unittest.main()
