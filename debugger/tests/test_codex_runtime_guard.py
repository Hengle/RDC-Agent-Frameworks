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


def _rt_payload(**extra: object) -> dict[str, object]:
    return {
        "entry_mode": "cli",
        "backend": "local",
        "context_id": "ctx-orchestrator",
        "runtime_owner": "rdc-debugger",
        "baton_ref": "",
        "context_binding_id": "ctxbind-orchestrator",
        "capture_ref": "capture:anomalous",
        "canonical_anchor_ref": "event:523",
        **extra,
    }


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


def _seed_case(root: Path, *, intent_decision: str = "debugger") -> Path:
    case_root = root / "workspace" / "cases" / "case_001"
    run_root = case_root / "runs" / "run_01"
    _write(root / "common" / "knowledge" / "library" / "sessions" / ".current_session", "sess_fixture_001\n")
    _write(case_root / "case.yaml", "case_id: case_001\ncurrent_run: run_01\n")
    _write(
        case_root / "case_input.yaml",
        yaml.safe_dump(
            {
                "schema_version": "1",
                "case_id": "case_001",
                "session": {"mode": "cross_device", "goal": "validate fixture"},
                "symptom": {"summary": "fixture"},
                "captures": [
                    {
                        "capture_id": "cap-anomalous-001",
                        "role": "anomalous",
                        "file_name": "broken.rdc",
                        "source": "user_supplied",
                        "provenance": {"device": "fixture-a"},
                    },
                    {
                        "capture_id": "cap-baseline-001",
                        "role": "baseline",
                        "file_name": "good.rdc",
                        "source": "historical_good",
                        "provenance": {"build": "1487"},
                    },
                ],
                "environment": {"api": "Vulkan"},
                "reference_contract": {
                    "source_kind": "capture_baseline",
                    "source_refs": ["capture:baseline"],
                    "verification_mode": "device_parity",
                    "probe_set": {"pixels": [{"name": "probe", "x": 1, "y": 2}]},
                    "acceptance": {"fallback_only": False, "max_channel_delta": 0.05},
                },
                "hints": {},
                "project": {"engine": "fixture"},
            },
            sort_keys=False,
            allow_unicode=True,
        ),
    )
    _write(
        case_root / "inputs" / "captures" / "manifest.yaml",
        yaml.safe_dump(
            {
                "captures": [
                    {
                        "capture_id": "cap-anomalous-001",
                        "capture_role": "anomalous",
                        "file_name": "broken.rdc",
                        "source": "user_supplied",
                        "import_mode": "path",
                        "imported_at": "2026-03-24T00:00:00Z",
                        "sha256": "sha-broken",
                        "source_path": "C:/captures/broken.rdc",
                    },
                    {
                        "capture_id": "cap-baseline-001",
                        "capture_role": "baseline",
                        "file_name": "good.rdc",
                        "source": "historical_good",
                        "import_mode": "path",
                        "imported_at": "2026-03-24T00:00:00Z",
                        "sha256": "sha-good",
                        "source_path": "C:/captures/good.rdc",
                    },
                ]
            },
            sort_keys=False,
            allow_unicode=True,
        ),
    )
    _write(case_root / "inputs" / "captures" / "broken.rdc", "broken")
    _write(case_root / "inputs" / "captures" / "good.rdc", "good")
    _write(
        run_root / "run.yaml",
        yaml.safe_dump(
            {
                "run_id": "run_01",
                "session_id": "sess_fixture_001",
                "platform": "codex",
                "coordination_mode": "staged_handoff",
                "runtime": {
                    "coordination_mode": "staged_handoff",
                    "orchestration_mode": "multi_agent",
                    "backend": "local",
                    "context_id": "ctx-orchestrator",
                    "runtime_owner": "rdc-debugger",
                    "session_id": "sess_fixture_001",
                },
            },
            sort_keys=False,
            allow_unicode=True,
        ),
    )
    _write(
        run_root / "capture_refs.yaml",
        yaml.safe_dump(
            {
                "captures": [
                    {"capture_id": "cap-anomalous-001", "capture_role": "anomalous"},
                    {"capture_id": "cap-baseline-001", "capture_role": "baseline"},
                ]
            },
            sort_keys=False,
            allow_unicode=True,
        ),
    )
    _write(
        run_root / "notes" / "hypothesis_board.yaml",
        yaml.safe_dump(
            {
                "hypothesis_board": {
                    "session_id": "sess_fixture_001",
                    "entry_skill": "rdc-debugger",
                    "user_goal": "validate fixture",
                    "intake_state": "accepted",
                    "current_phase": "triage",
                    "current_task": "seeded test",
                    "active_owner": "rdc-debugger",
                    "pending_requirements": [],
                    "blocking_issues": [],
                    "progress_summary": ["seeded"],
                    "next_actions": ["run intake gate"],
                    "last_updated": "2026-03-24T00:00:00Z",
                    "intent_gate": {
                        "classifier_version": 1,
                        "judged_by": "rdc-debugger",
                        "clarification_rounds": 0,
                        "normalized_user_goal": "validate fixture",
                        "primary_completion_question": "why is the render wrong",
                        "dominant_operation": "diagnose",
                        "requested_artifact": "debugger_verdict",
                        "ab_role": "evidence_method",
                        "scores": {"debugger": 9, "analyst": 0, "optimizer": 0},
                        "decision": intent_decision,
                        "confidence": "high",
                        "hard_signals": {
                            "debugger_positive": [],
                            "analyst_positive": [],
                            "optimizer_positive": [],
                            "disqualifiers": [],
                        },
                        "rationale": "fixture",
                        "redirect_target": "",
                    },
                    "hypotheses": [],
                }
            },
            sort_keys=False,
            allow_unicode=True,
        ),
    )
    return run_root


def _action_chain_path(root: Path) -> Path:
    return root / "common" / "knowledge" / "library" / "sessions" / "sess_fixture_001" / "action_chain.jsonl"


def _append_events(root: Path, events: list[dict]) -> None:
    path = _action_chain_path(root)
    existing = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []
    existing.extend(events)
    _write(path, "\n".join(json.dumps(event, ensure_ascii=False) for event in existing) + "\n")


class CodexRuntimeGuardTests(unittest.TestCase):
    def _load_guard(self):
        return _load_module(GUARD_PATH, f"codex_runtime_guard_{id(self)}")

    def test_preflight_blocks_missing_common_and_tools(self) -> None:
        root = _prepare_platform_root(with_common=False, with_tools=False)
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()

        payload = guard.run_preflight(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["blocking_codes"], ["BLOCKED_BINDING_NOT_READY"])

    def test_preflight_passes_for_valid_platform_payload(self) -> None:
        root = _prepare_platform_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()

        payload = guard.run_preflight(root)

        self.assertEqual(payload["status"], "passed")

    def test_entry_gate_reuses_shared_blocker_codes(self) -> None:
        root = _prepare_platform_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        case_root = root / "workspace" / "cases" / "case_001"
        capture = case_root / "incoming" / "sample.rdc"
        _write(capture, "fixture")

        caps_path = root / "common" / "config" / "platform_capabilities.json"
        caps = json.loads(caps_path.read_text(encoding="utf-8-sig"))
        caps["platforms"]["codex"]["remote_support"] = "unsupported"
        caps_path.write_text(json.dumps(caps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        payload = guard.run_entry_gate(
            root,
            case_root,
            platform="codex",
            entry_mode="cli",
            backend="remote",
            capture_paths=[str(capture)],
            remote_transport="adb_android",
        )

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("BLOCKED_PLATFORM_MODE_UNSUPPORTED", {item["code"] for item in payload["blockers"]})

    def test_dispatch_readiness_blocks_before_intake_gate(self) -> None:
        root = _prepare_platform_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        run_root = _seed_case(root)
        case_root = run_root.parent.parent

        guard.run_entry_gate(
            root,
            case_root,
            platform="codex",
            entry_mode="cli",
            backend="local",
            capture_paths=[
                str((case_root / "inputs" / "captures" / "broken.rdc").resolve()),
                str((case_root / "inputs" / "captures" / "good.rdc").resolve()),
            ],
        )

        payload = guard.run_dispatch_readiness(root, run_root, platform="codex")

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("BLOCKED_INTAKE_GATE_REQUIRED", payload["blocking_codes"])
        self.assertIn("BLOCKED_RUNTIME_TOPOLOGY_REQUIRED", payload["blocking_codes"])

    def test_dispatch_readiness_blocks_orchestrator_overreach(self) -> None:
        root = _prepare_platform_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        run_root = _seed_case(root)
        case_root = run_root.parent.parent

        guard.run_entry_gate(
            root,
            case_root,
            platform="codex",
            entry_mode="cli",
            backend="local",
            capture_paths=[
                str((case_root / "inputs" / "captures" / "broken.rdc").resolve()),
                str((case_root / "inputs" / "captures" / "good.rdc").resolve()),
            ],
        )
        guard.run_intake_gate(root, run_root)
        guard.run_runtime_topology(root, run_root, platform="codex")

        _append_events(
            root,
            [
                {
                    "schema_version": "2",
                    "event_id": "evt-waiting",
                    "ts_ms": 1772537599950,
                    "run_id": "run_01",
                    "session_id": "sess_fixture_001",
                    "agent_id": "rdc-debugger",
                    "event_type": "workflow_stage_transition",
                    "status": "entered",
                    "duration_ms": 0,
                    "refs": [],
                    "payload": {"workflow_stage": "waiting_for_specialist_brief"},
                },
                {
                    "schema_version": "2",
                    "event_id": "evt-overreach",
                    "ts_ms": 1772537599960,
                    "run_id": "run_01",
                    "session_id": "sess_fixture_001",
                    "agent_id": "rdc-debugger",
                    "event_type": "tool_execution",
                    "status": "ok",
                    "duration_ms": 30,
                    "refs": [],
                    "payload": _rt_payload(tool_name="rd.pipeline.get_state"),
                },
            ],
        )

        payload = guard.run_dispatch_readiness(root, run_root, platform="codex")

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["blocking_codes"], ["PROCESS_DEVIATION_MAIN_AGENT_OVERREACH"])
        action_chain = [json.loads(line) for line in _action_chain_path(root).read_text(encoding="utf-8").splitlines() if line.strip()]
        process_deviations = [event for event in action_chain if event.get("event_type") == "process_deviation"]
        self.assertTrue(process_deviations)
        self.assertEqual(process_deviations[-1]["payload"]["deviation_code"], "PROCESS_DEVIATION_MAIN_AGENT_OVERREACH")

    def test_specialist_feedback_timeout_blocks(self) -> None:
        root = _prepare_platform_root()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        guard = self._load_guard()
        run_root = _seed_case(root)
        case_root = run_root.parent.parent

        guard.run_entry_gate(
            root,
            case_root,
            platform="codex",
            entry_mode="cli",
            backend="local",
            capture_paths=[
                str((case_root / "inputs" / "captures" / "broken.rdc").resolve()),
                str((case_root / "inputs" / "captures" / "good.rdc").resolve()),
            ],
        )
        guard.run_intake_gate(root, run_root)
        guard.run_runtime_topology(root, run_root, platform="codex")
        _append_events(
            root,
            [
                {
                    "schema_version": "2",
                    "event_id": "evt-dispatch-pixel",
                    "ts_ms": 1000,
                    "run_id": "run_01",
                    "session_id": "sess_fixture_001",
                    "agent_id": "rdc-debugger",
                    "event_type": "dispatch",
                    "status": "sent",
                    "duration_ms": 10,
                    "refs": [],
                    "payload": _rt_payload(target_agent="pixel_forensics_agent", objective="inspect the hotspot"),
                }
            ],
        )

        payload = guard.run_specialist_feedback(root, run_root, timeout_seconds=300, now_ms=302000)

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["blocking_codes"], ["BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT"])

    def test_final_audit_delegates_to_shared_writer(self) -> None:
        guard = self._load_guard()
        root = Path(tempfile.mkdtemp())
        run_root = root / "workspace" / "cases" / "case_001" / "runs" / "run_01"
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        expected = {"status": "passed", "paths": {"action_chain": "dummy"}}

        with mock.patch.object(guard, "write_run_audit_artifact", return_value=expected) as mocked:
            payload = guard.run_final_audit(root, run_root, platform="codex")

        self.assertIs(payload, expected)
        mocked.assert_called_once_with(root, run_root.resolve(), "codex")

    def test_codex_truth_stays_runtime_owner_and_non_hooks_based(self) -> None:
        capabilities = json.loads((DEBUGGER_ROOT / "common" / "config" / "platform_capabilities.json").read_text(encoding="utf-8-sig"))
        compliance = json.loads((DEBUGGER_ROOT / "common" / "config" / "framework_compliance.json").read_text(encoding="utf-8-sig"))
        codex = capabilities["platforms"]["codex"]

        self.assertEqual(codex["enforcement_layer"], "runtime_owner")
        self.assertFalse(codex["capabilities"]["hooks"]["supported"])
        self.assertEqual(compliance["platforms"]["codex"]["enforcement_mode"], "runtime_owner_gate_loop")
        self.assertIn("platforms/codex/.codex/runtime_guard.py", codex["required_paths"])
        self.assertIn("platforms/codex/.codex/agents/rdc-debugger.toml", codex["required_paths"])


if __name__ == "__main__":
    unittest.main()
