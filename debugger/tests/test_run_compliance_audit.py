from __future__ import annotations

import json
import shutil
import subprocess
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
AUDIT_SCRIPT = DEBUGGER_ROOT / "common" / "hooks" / "utils" / "run_compliance_audit.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_base(root: Path) -> None:
    for rel in (
        Path("common/config/framework_compliance.json"),
        Path("common/config/platform_capabilities.json"),
        Path("common/knowledge/spec/README.md"),
        Path("common/knowledge/spec/registry/active_manifest.yaml"),
        Path("common/knowledge/spec/registry/spec_registry.yaml"),
        Path("common/knowledge/spec/policy/evolution_policy.yaml"),
        Path("common/knowledge/spec/negative_memory.yaml"),
        Path("common/knowledge/spec/ledger/evolution_ledger.jsonl"),
        Path("common/knowledge/spec/objects/sops/SOP-CATALOG@1.yaml"),
        Path("common/knowledge/spec/objects/sops/SOP-CATALOG@1.payload.yaml"),
        Path("common/knowledge/spec/objects/invariants/INVARIANT-CATALOG@1.yaml"),
        Path("common/knowledge/spec/objects/invariants/INVARIANT-CATALOG@1.payload.yaml"),
        Path("common/knowledge/spec/objects/taxonomy/SYMPTOM-TAXONOMY@1.yaml"),
        Path("common/knowledge/spec/objects/taxonomy/SYMPTOM-TAXONOMY@1.payload.yaml"),
        Path("common/knowledge/spec/objects/taxonomy/TRIGGER-TAXONOMY@1.yaml"),
        Path("common/knowledge/spec/objects/taxonomy/TRIGGER-TAXONOMY@1.payload.yaml"),
    ):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DEBUGGER_ROOT / rel, target)


def _base_action_chain(session_id: str, run_id: str, *, reviewer: str = "skeptic_agent") -> list[dict]:
    return [
        {
            "schema_version": "2",
            "event_id": "evt-0001-dispatch",
            "ts_ms": 1772537600000,
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": "team_lead",
            "event_type": "dispatch",
            "status": "sent",
            "duration_ms": 15,
            "refs": [],
            "payload": {"target_agent": "triage_agent", "objective": "triage precision issue"},
        },
        {
            "schema_version": "2",
            "event_id": "evt-0002-tool",
            "ts_ms": 1772537600500,
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": "pixel_forensics_agent",
            "event_type": "tool_execution",
            "status": "ok",
            "duration_ms": 120,
            "refs": ["evt-0001-dispatch"],
            "payload": {"tool_name": "rd.debug.pixel_history", "transport": "daemon"},
        },
        {
            "schema_version": "2",
            "event_id": "evt-0003-hypothesis",
            "ts_ms": 1772537600900,
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": "team_lead",
            "event_type": "hypothesis_transition",
            "status": "applied",
            "duration_ms": 20,
            "refs": ["evt-0002-tool"],
            "payload": {
                "hypothesis_id": "H-001",
                "from_state": "OPEN",
                "to_state": "ACTIVE",
                "reason": "anchor established",
            },
        },
        {
            "schema_version": "2",
            "event_id": "evt-0004-conflict-open",
            "ts_ms": 1772537601200,
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": "driver_device_agent",
            "event_type": "conflict_opened",
            "status": "open",
            "duration_ms": 18,
            "refs": ["H-001"],
            "payload": {
                "conflict_id": "CONFLICT-001",
                "hypothesis_id": "H-001",
                "positions": [
                    {"agent_id": "shader_ir_agent", "stance": "support", "evidence_refs": ["evt-0002-tool"]},
                    {"agent_id": "driver_device_agent", "stance": "refute", "evidence_refs": ["evt-0003-hypothesis"]},
                ],
            },
        },
        {
            "schema_version": "2",
            "event_id": "evt-0005-conflict-resolved",
            "ts_ms": 1772537601500,
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": "skeptic_agent",
            "event_type": "conflict_resolved",
            "status": "resolved",
            "duration_ms": 50,
            "refs": ["CONFLICT-001", "H-001"],
            "payload": {
                "conflict_id": "CONFLICT-001",
                "hypothesis_id": "H-001",
                "reviewer_agent": "skeptic_agent",
                "decision": "support_precision_hypothesis",
                "rationale": "structured evidence aligns",
            },
        },
        {
            "schema_version": "2",
            "event_id": "evt-0006-counterfactual-submit",
            "ts_ms": 1772537602200,
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": "shader_ir_agent",
            "event_type": "counterfactual_submitted",
            "status": "submitted",
            "duration_ms": 140,
            "refs": ["evt-0002-tool", "H-001"],
            "payload": {
                "review_id": "CF-001",
                "hypothesis_id": "H-001",
                "proposer_agent": "shader_ir_agent",
                "intervention": "half diffuse -> float diffuse",
                "target_variable": "shader precision",
                "isolation_checks": {
                    "only_target_changed": True,
                    "same_scene_same_input": True,
                    "same_drawcall_count": True,
                },
                "measurements": {
                    "pixel_before": {"x": 512, "y": 384, "rgba": [0.21, 0.19, 0.18, 1.0]},
                    "pixel_after": {"x": 512, "y": 384, "rgba": [0.37, 0.34, 0.32, 1.0]},
                    "pixel_baseline": {"x": 512, "y": 384, "rgba": [0.38, 0.35, 0.33, 1.0]},
                },
                "scoring": {
                    "pixel_recovery": 0.94,
                    "variable_isolation": 1.0,
                    "symptom_coverage": 1.0,
                    "total": 0.97,
                },
                "evidence_refs": ["evt-0002-tool", "evt-0005-conflict-resolved"],
            },
        },
        {
            "schema_version": "2",
            "event_id": "evt-0007-counterfactual-review",
            "ts_ms": 1772537602500,
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": reviewer,
            "event_type": "counterfactual_reviewed",
            "status": "approved",
            "duration_ms": 60,
            "refs": ["CF-001", "evt-0006-counterfactual-submit"],
            "payload": {
                "review_id": "CF-001",
                "hypothesis_id": "H-001",
                "reviewer_agent": reviewer,
                "isolation_verdict": {"verdict": "isolated", "rationale": "all isolation checks passed"},
                "evidence_refs": ["evt-0006-counterfactual-submit", "evt-0002-tool"],
            },
        },
        {
            "schema_version": "2",
            "event_id": "evt-0008-artifact",
            "ts_ms": 1772537602800,
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": "curator_agent",
            "event_type": "artifact_write",
            "status": "written",
            "duration_ms": 10,
            "refs": ["evt-0007-counterfactual-review"],
            "payload": {
                "path": f"common/knowledge/library/sessions/{session_id}/session_evidence.yaml",
                "artifact_role": "adjudicated_snapshot",
            },
        },
    ]


def _seed_common_session(
    root: Path,
    session_id: str,
    run_id: str,
    *,
    reviewer: str = "skeptic_agent",
    conflict_status: str = "ARBITRATED",
    hypothesis_status: str = "VALIDATED",
    review_event_id: str = "evt-0007-counterfactual-review",
) -> None:
    sessions_root = root / "common" / "knowledge" / "library" / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)
    _write(sessions_root / ".current_session", f"{session_id}\n")

    action_chain = _base_action_chain(session_id, run_id, reviewer=reviewer)
    _write(
        sessions_root / session_id / "action_chain.jsonl",
        "\n".join(json.dumps(event, ensure_ascii=False) for event in action_chain) + "\n",
    )

    snapshot = {
        "schema_version": "2",
        "session_id": session_id,
        "snapshot_version": 1,
        "spec_snapshot_ref": "spec-snapshot-20260315-0001",
        "active_spec_versions": {
            "sop_catalog": 1,
            "invariant_catalog": 1,
            "symptom_taxonomy": 1,
            "trigger_taxonomy": 1,
        },
        "causal_anchor": {
            "type": "root_drawcall",
            "ref": "event:523",
            "established_by": "pixel_forensics_agent",
            "justification": "fixture anchor",
            "evidence_refs": ["evt-0002-tool"],
        },
        "hypotheses": [
            {
                "hypothesis_id": "H-001",
                "status": hypothesis_status,
                "title": "precision regression",
                "lead_agent": "shader_ir_agent",
                "evidence_refs": ["evt-0002-tool", "evt-0007-counterfactual-review"],
                "conflict_ids": ["CONFLICT-001"],
            }
        ],
        "conflicts": [
            {
                "conflict_id": "CONFLICT-001",
                "hypothesis_id": "H-001",
                "status": conflict_status,
                "opened_at_ms": 1772537601200,
                "resolved_at_ms": 1772537601500,
                "opened_by_event": "evt-0004-conflict-open",
                "resolved_by_event": "evt-0005-conflict-resolved",
                "positions": [
                    {"agent_id": "shader_ir_agent", "stance": "support", "evidence_refs": ["evt-0002-tool"]},
                    {"agent_id": "driver_device_agent", "stance": "refute", "evidence_refs": ["evt-0003-hypothesis"]},
                ],
                "arbitration": {
                    "reviewer_agent": "skeptic_agent",
                    "decision": "support_precision_hypothesis",
                    "rationale": "fixture arbitration",
                },
            }
        ],
        "counterfactual_reviews": [
            {
                "review_id": "CF-001",
                "hypothesis_id": "H-001",
                "proposer_agent": "shader_ir_agent",
                "reviewer_agent": reviewer,
                "status": "approved",
                "submission_event_id": "evt-0006-counterfactual-submit",
                "review_event_id": review_event_id,
                "evidence_refs": ["evt-0002-tool", "evt-0006-counterfactual-submit"],
            }
        ],
        "knowledge_candidates": [],
        "evidence_refs": ["evt-0002-tool", "evt-0005-conflict-resolved", "evt-0007-counterfactual-review"],
        "store_contract": {
            "ledger_artifact": "action_chain.jsonl",
            "snapshot_artifact": "session_evidence.yaml",
            "active_spec_snapshot_artifact": "common/knowledge/spec/registry/active_manifest.yaml",
            "governance_ledger_artifact": "common/knowledge/spec/ledger/evolution_ledger.jsonl",
            "derived_artifacts": ["run_compliance.yaml"],
            "truth_roles": {
                "action_chain": "append_only_ledger",
                "session_evidence": "adjudicated_snapshot",
                "active_spec_snapshot": "versioned_spec_pointer",
                "evolution_ledger": "append_only_governance_ledger",
                "run_compliance": "derived_audit",
            },
        },
    }
    _write(sessions_root / session_id / "session_evidence.yaml", yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True))

    signoff = [
        {
            "message_type": "SKEPTIC_SIGN_OFF",
            "from": "skeptic_agent",
            "to": "team_lead",
            "target_hypothesis": "H-001",
            "blade_review": [
                {"blade": "刀1: 相关性刀", "result": "pass", "note": "ok"},
                {"blade": "刀2: 覆盖性刀", "result": "pass", "note": "ok"},
                {"blade": "刀3: 反事实刀", "result": "pass", "note": "ok"},
                {"blade": "刀4: 工具证据刀", "result": "pass", "note": "ok"},
                {"blade": "刀5: 替代假设刀", "result": "pass", "note": "ok"},
            ],
            "sign_off": {"signed": True, "declaration": "evidence chain is sufficient"},
        }
    ]
    _write(sessions_root / session_id / "skeptic_signoff.yaml", yaml.safe_dump(signoff, sort_keys=False, allow_unicode=True))


def _seed_run(
    root: Path,
    case_id: str,
    run_id: str,
    platform: str,
    coordination_mode: str,
    *,
    knowledge_context: dict | None = None,
) -> Path:
    case_root = root / "workspace" / "cases" / case_id
    run_root = case_root / "runs" / run_id
    _write(case_root / "case.yaml", f"case_id: {case_id}\ncurrent_run: {run_id}\n")
    run_payload = {
        "case_id": case_id,
        "run_id": run_id,
        "platform": platform,
        "coordination_mode": coordination_mode,
        "session_id": "sess_fixture_001",
        "capture_file_id": "capf_fixture_001",
    }
    if knowledge_context is not None:
        run_payload["knowledge_context"] = knowledge_context
    _write(run_root / "run.yaml", yaml.safe_dump(run_payload, sort_keys=False, allow_unicode=True))
    _write(run_root / "notes" / "hypothesis_board.yaml", "hypothesis_board:\n  hypotheses: []\n")
    _write(
        run_root / "reports" / "report.md",
        "\n".join(
            [
                "# BUG-PREC-FIXTURE",
                "",
                "session_id = sess_fixture_001",
                "capture_file_id = capf_fixture_001",
                "event 523",
                "DEBUGGER_FINAL_VERDICT",
            ]
        )
        + "\n",
    )
    _write(run_root / "reports" / "visual_report.html", "<html><body><p>session_id = sess_fixture_001</p><p>event 523</p></body></html>\n")
    return run_root


def _run_audit(root: Path, platform: str, run_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--root", str(root), "--platform", platform, "--run-root", str(run_root), "--strict"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


class RunComplianceAuditTests(unittest.TestCase):
    def _temp_root(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_compliant_run_passes_emits_proposal_and_metrics(self) -> None:
        root = self._temp_root()
        _seed_base(root)
        _seed_common_session(root, "sess_fixture_001", "run_01")
        run_root = _seed_run(
            root,
            "case_001",
            "run_01",
            "code-buddy",
            "concurrent_team",
            knowledge_context={
                "matched_sop_id": "SOP-PREC-01",
                "sop_adherence_score": 0.62,
                "symptom_tags": ["banding"],
                "trigger_tags": ["Adreno_GPU"],
                "resolved_invariants": ["I-PREC-01"],
                "invariant_explains_verdict": True,
            },
        )

        proc = _run_audit(root, "code-buddy", run_root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        artifact = yaml.safe_load((run_root / "artifacts" / "run_compliance.yaml").read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "passed")
        self.assertEqual(artifact["metrics"]["tool_execution"]["success"], 1)
        self.assertEqual(artifact["metrics"]["conflicts"]["arbitrated"], 1)
        self.assertEqual(artifact["metrics"]["counterfactual_reviews"]["independent_review_coverage"], 1.0)
        self.assertEqual(artifact["metrics"]["knowledge_candidates"]["emitted"], 1)
        proposals = list((root / "common" / "knowledge" / "proposals").glob("CAND-SOP-*.yaml"))
        self.assertEqual(len(proposals), 1)
        proposal = yaml.safe_load(proposals[0].read_text(encoding="utf-8"))
        self.assertEqual(proposal["schema_version"], "2")
        self.assertEqual(proposal["status"], "candidate")

    def test_audit_only_platform_passes(self) -> None:
        root = self._temp_root()
        _seed_base(root)
        _seed_common_session(root, "sess_fixture_001", "run_01")
        run_root = _seed_run(root, "case_001", "run_01", "codex", "concurrent_team")

        proc = _run_audit(root, "codex", run_root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        artifact = yaml.safe_load((run_root / "artifacts" / "run_compliance.yaml").read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "passed")

    def test_same_proposer_and_reviewer_fails(self) -> None:
        root = self._temp_root()
        _seed_base(root)
        _seed_common_session(root, "sess_fixture_001", "run_01", reviewer="shader_ir_agent")
        run_root = _seed_run(root, "case_001", "run_01", "code-buddy", "concurrent_team")

        proc = _run_audit(root, "code-buddy", run_root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        artifact = yaml.safe_load((run_root / "artifacts" / "run_compliance.yaml").read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "failed")

    def test_unresolved_conflict_fails(self) -> None:
        root = self._temp_root()
        _seed_base(root)
        _seed_common_session(root, "sess_fixture_001", "run_01", conflict_status="OPEN", hypothesis_status="CONFLICTED")
        run_root = _seed_run(root, "case_001", "run_01", "code-buddy", "concurrent_team")

        proc = _run_audit(root, "code-buddy", run_root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        artifact = yaml.safe_load((run_root / "artifacts" / "run_compliance.yaml").read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "failed")
        self.assertEqual(artifact["metrics"]["conflicts"]["arbitrated"], 0)

    def test_missing_review_event_reference_fails(self) -> None:
        root = self._temp_root()
        _seed_base(root)
        _seed_common_session(root, "sess_fixture_001", "run_01", review_event_id="evt-missing-review")
        run_root = _seed_run(root, "case_001", "run_01", "code-buddy", "concurrent_team")

        proc = _run_audit(root, "code-buddy", run_root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        artifact = yaml.safe_load((run_root / "artifacts" / "run_compliance.yaml").read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "failed")

    def test_failed_run_does_not_emit_proposal(self) -> None:
        root = self._temp_root()
        _seed_base(root)
        _seed_common_session(root, "sess_fixture_001", "run_01", reviewer="shader_ir_agent")
        run_root = _seed_run(
            root,
            "case_001",
            "run_01",
            "code-buddy",
            "concurrent_team",
            knowledge_context={
                "matched_sop_id": "",
                "sop_adherence_score": 0.40,
                "symptom_tags": ["banding"],
                "trigger_tags": ["Adreno_GPU"],
                "resolved_invariants": ["I-PREC-01"],
                "invariant_explains_verdict": False,
            },
        )

        proc = _run_audit(root, "code-buddy", run_root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        proposals = list((root / "common" / "knowledge" / "proposals").glob("CAND-*.yaml"))
        self.assertEqual(proposals, [])

    def test_repeated_candidate_updates_existing_proposal(self) -> None:
        root = self._temp_root()
        _seed_base(root)
        knowledge_context = {
            "matched_sop_id": "SOP-PREC-01",
            "sop_adherence_score": 0.62,
            "symptom_tags": ["banding"],
            "trigger_tags": ["Adreno_GPU"],
            "resolved_invariants": ["I-PREC-01"],
            "invariant_explains_verdict": True,
        }

        _seed_common_session(root, "sess_fixture_001", "run_01")
        run_root_1 = _seed_run(root, "case_001", "run_01", "code-buddy", "concurrent_team", knowledge_context=knowledge_context)
        proc_1 = _run_audit(root, "code-buddy", run_root_1)
        self.assertEqual(proc_1.returncode, 0, proc_1.stdout + proc_1.stderr)

        _seed_common_session(root, "sess_fixture_002", "run_02")
        run_root_2 = _seed_run(root, "case_002", "run_02", "code-buddy", "concurrent_team", knowledge_context=knowledge_context)
        run_yaml_2 = yaml.safe_load((run_root_2 / "run.yaml").read_text(encoding="utf-8"))
        run_yaml_2["session_id"] = "sess_fixture_002"
        _write(run_root_2 / "run.yaml", yaml.safe_dump(run_yaml_2, sort_keys=False, allow_unicode=True))
        _write(
            run_root_2 / "reports" / "report.md",
            "\n".join(
                [
                    "# BUG-PREC-FIXTURE",
                    "",
                    "session_id = sess_fixture_002",
                    "capture_file_id = capf_fixture_001",
                    "event 523",
                    "DEBUGGER_FINAL_VERDICT",
                ]
            )
            + "\n",
        )
        _write(run_root_2 / "reports" / "visual_report.html", "<html><body><p>session_id = sess_fixture_002</p><p>event 523</p></body></html>\n")
        proc_2 = _run_audit(root, "code-buddy", run_root_2)
        self.assertEqual(proc_2.returncode, 0, proc_2.stdout + proc_2.stderr)

        proposals = list((root / "common" / "knowledge" / "proposals").glob("CAND-SOP-*.yaml"))
        self.assertEqual(len(proposals), 1)
        proposal = yaml.safe_load(proposals[0].read_text(encoding="utf-8"))
        self.assertEqual(proposal["support_runs"], 2)
        self.assertEqual(sorted(proposal["source_refs"]["run_ids"]), ["run_01", "run_02"])


if __name__ == "__main__":
    unittest.main()
