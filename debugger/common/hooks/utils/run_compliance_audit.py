#!/usr/bin/env python3
"""Audit whether a debugger run complies with the broker-owned runtime contract."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    import yaml
except ModuleNotFoundError:
    req = Path(__file__).resolve().parents[1] / "requirements.txt"
    print("missing dependency 'PyYAML'", file=sys.stderr)
    print(f"install with: python -m pip install -r {req}", file=sys.stderr)
    raise SystemExit(2)


ACTION_SPECIALISTS = {
    "triage_agent",
    "capture_repro_agent",
    "pass_graph_pipeline_agent",
    "pixel_forensics_agent",
    "shader_ir_agent",
    "driver_device_agent",
}
AGENT_IDS = ACTION_SPECIALISTS | {"rdc-debugger", "skeptic_agent", "curator_agent"}
ACTION_CHAIN_SCHEMA = "2"
RUN_COMPLIANCE_SCHEMA = "3"
REQUIRED_RUNTIME_FIELDS = {
    "runtime_generation",
    "snapshot_rev",
    "owner_agent_id",
    "lease_epoch",
    "continuity_status",
    "action_request_id",
}


def _debugger_root(default: Path | None = None) -> Path:
    return default.resolve() if default else Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _norm(path: Path) -> str:
    return str(path).replace("\\", "/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _infer_run_root(root: Path) -> Path:
    workspace = root / "workspace" / "cases"
    candidates = [p for p in workspace.glob("*/runs/*") if p.is_dir()] if workspace.is_dir() else []
    if not candidates:
        raise FileNotFoundError("no run directories found under workspace/cases")
    candidates.sort(key=lambda p: max((c.stat().st_mtime for c in p.rglob("*")), default=p.stat().st_mtime), reverse=True)
    return candidates[0]


def _load_action_chain(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(_text(path).splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"action_chain line {line_no} must be a JSON object")
        rows.append(obj)
    return rows


def load_action_chain_events(path: Path) -> list[dict[str, Any]]:
    return _load_action_chain(path)


def specialist_handoff_path_ok(path_value: str, run_root: Path) -> bool:
    if not str(path_value).strip():
        return False
    normalized = str(path_value).strip().replace("\\", "/")
    notes_root = _norm(run_root / "notes").rstrip("/")
    capture_refs = _norm(run_root / "capture_refs.yaml")
    return normalized == capture_refs or normalized.startswith(notes_root + "/") or normalized == notes_root


def workflow_stage_overreach_issues(events: list[dict[str, Any]], coordination_mode: str) -> list[str]:
    if coordination_mode != "staged_handoff":
        return []
    waiting_since = -1
    issues: list[str] = []
    for event in events:
        event_type = str(event.get("event_type") or "").strip()
        if event_type == "workflow_stage_transition":
            stage = str(((event.get("payload") or {}).get("workflow_stage")) or "").strip()
            if stage == "waiting_for_specialist_brief":
                waiting_since = int(event.get("ts_ms") or 0)
            elif stage and stage != "waiting_for_specialist_brief":
                waiting_since = -1
        if waiting_since >= 0 and event_type == "tool_execution" and str(event.get("agent_id") or "").strip() == "rdc-debugger":
            issues.append(str(event.get("event_id") or "").strip() or "tool_execution")
    return issues


def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, detail: str, *, path: Path | None = None, refs: list[str] | None = None) -> None:
    checks.append({"id": check_id, "result": "pass" if passed else "fail", "detail": detail, **({"path": _norm(path)} if path else {}), **({"refs": refs} if refs else {})})


def _append_event(path: Path, event: dict[str, Any]) -> None:
    payload = json.dumps(event, ensure_ascii=False)
    existing = _text(path) if path.exists() else ""
    if payload in existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(payload)
        handle.write("\n")


def _dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "event_count": len(events),
        "dispatch_count": sum(1 for event in events if str(event.get("event_type") or "") == "dispatch"),
        "tool_execution_count": sum(1 for event in events if str(event.get("event_type") or "") == "tool_execution"),
        "artifact_write_count": sum(1 for event in events if str(event.get("event_type") or "") == "artifact_write"),
    }


def run_audit(root: Path, run_root: Path, platform: str) -> dict[str, Any]:
    compliance_cfg = _read_json(root / "common" / "config" / "framework_compliance.json")
    caps = _read_json(root / "common" / "config" / "platform_capabilities.json")
    checks: list[dict[str, Any]] = []
    case_root = run_root.parent.parent
    case_yaml = case_root / "case.yaml"
    case_input = case_root / "case_input.yaml"
    entry_gate = case_root / "artifacts" / "entry_gate.yaml"
    captures_manifest = case_root / "inputs" / "captures" / "manifest.yaml"
    references_manifest = case_root / "inputs" / "references" / "manifest.yaml"
    run_yaml = run_root / "run.yaml"
    capture_refs = run_root / "capture_refs.yaml"
    intake_gate = run_root / "artifacts" / "intake_gate.yaml"
    runtime_session = run_root / "artifacts" / "runtime_session.yaml"
    runtime_snapshot = run_root / "artifacts" / "runtime_snapshot.yaml"
    ownership_lease = run_root / "artifacts" / "ownership_lease.yaml"
    runtime_failure = run_root / "artifacts" / "runtime_failure.yaml"
    fix_verification = run_root / "artifacts" / "fix_verification.yaml"
    report_md = run_root / "reports" / "report.md"
    visual_report = run_root / "reports" / "visual_report.html"
    hypothesis_board = run_root / "notes" / "hypothesis_board.yaml"
    session_marker = root / "common" / "knowledge" / "library" / "sessions" / ".current_session"
    run_data = _read_yaml(run_yaml) if run_yaml.is_file() else {}
    if not isinstance(run_data, dict):
        run_data = {}
    session_id = str(run_data.get("session_id") or session_marker.read_text(encoding="utf-8").lstrip("\ufeff").strip() if session_marker.is_file() else "").strip()
    session_evidence = root / "common" / "knowledge" / "library" / "sessions" / session_id / "session_evidence.yaml" if session_id else root / "common" / "knowledge" / "library" / "sessions" / "session_evidence.yaml"
    skeptic_signoff = root / "common" / "knowledge" / "library" / "sessions" / session_id / "skeptic_signoff.yaml" if session_id else root / "common" / "knowledge" / "library" / "sessions" / "skeptic_signoff.yaml"
    action_chain = root / "common" / "knowledge" / "library" / "sessions" / session_id / "action_chain.jsonl" if session_id else root / "common" / "knowledge" / "library" / "sessions" / "action_chain.jsonl"
    for path, label in ((case_yaml, "case_yaml"), (case_input, "case_input"), (entry_gate, "entry_gate_artifact"), (captures_manifest, "captures_manifest"), (references_manifest, "references_manifest"), (run_yaml, "run_yaml"), (capture_refs, "capture_refs"), (intake_gate, "intake_gate_artifact"), (runtime_session, "runtime_session_artifact"), (runtime_snapshot, "runtime_snapshot_artifact"), (ownership_lease, "ownership_lease_artifact"), (runtime_failure, "runtime_failure_artifact"), (fix_verification, "fix_verification"), (hypothesis_board, "hypothesis_board"), (report_md, "report_md"), (visual_report, "visual_report_html"), (session_evidence, "session_evidence"), (skeptic_signoff, "skeptic_signoff"), (action_chain, "action_chain")):
        _check(checks, label, path.is_file(), f"{label} must exist", path=path)

    platform_caps = (caps.get("platforms") or {}).get(platform) or {}
    platform_rules = (compliance_cfg.get("platforms") or {}).get(platform) or {}
    _check(checks, "platform_capability_alignment", str(platform_caps.get("coordination_mode") or "") == "staged_handoff" and str(platform_caps.get("orchestration_mode") or "") == "multi_agent", "platform_capabilities must resolve to staged_handoff + multi_agent")
    _check(checks, "framework_compliance_alignment", str(platform_rules.get("coordination_mode") or "") == "staged_handoff", "framework_compliance coordination_mode must be staged_handoff")
    _check(checks, "run_coordination_mode", str(run_data.get("coordination_mode") or "") == "staged_handoff", "run.yaml coordination_mode must be staged_handoff", path=run_yaml if run_yaml.is_file() else None)

    entry_gate_data = _read_yaml(entry_gate) if entry_gate.is_file() else {}
    intake_gate_data = _read_yaml(intake_gate) if intake_gate.is_file() else {}
    runtime_session_data = _read_yaml(runtime_session) if runtime_session.is_file() else {}
    runtime_snapshot_data = _read_yaml(runtime_snapshot) if runtime_snapshot.is_file() else {}
    ownership_lease_data = _read_yaml(ownership_lease) if ownership_lease.is_file() else {}
    runtime_failure_data = _read_yaml(runtime_failure) if runtime_failure.is_file() else {}
    _check(checks, "entry_gate_status", str((entry_gate_data or {}).get("status") or "") == "passed", "entry_gate.yaml must be passed", path=entry_gate if entry_gate.is_file() else None)
    _check(checks, "intake_gate_status", str((intake_gate_data or {}).get("status") or "") == "passed", "intake_gate.yaml must be passed", path=intake_gate if intake_gate.is_file() else None)
    _check(checks, "runtime_session_status", str((runtime_session_data or {}).get("status") or "") == "active", "runtime_session.yaml must stay active until finalization", path=runtime_session if runtime_session.is_file() else None)
    _check(checks, "runtime_failure_clear", str((runtime_failure_data or {}).get("status") or "clear") in {"clear", "recovered"}, "runtime_failure.yaml must be clear or recovered at finalization", path=runtime_failure if runtime_failure.is_file() else None)
    _check(checks, "ownership_lease_released", str((ownership_lease_data or {}).get("status") or "released") == "released", "ownership_lease.yaml must be released at finalization", path=ownership_lease if ownership_lease.is_file() else None)

    events = load_action_chain_events(action_chain) if action_chain.is_file() else []
    payload_issues: list[str] = []
    owner_mismatches: list[str] = []
    dispatch_ok = False
    skeptic_ok = False
    curator_ok = False
    for event in events:
        event_type = str(event.get("event_type") or "").strip()
        agent_id = str(event.get("agent_id") or "").strip()
        payload = _event_payload(event)
        if event_type == "dispatch" and agent_id == "rdc-debugger":
            dispatch_ok = True
        if agent_id == "skeptic_agent" and event_type in {"quality_check", "counterfactual_reviewed", "conflict_resolved", "artifact_write"}:
            skeptic_ok = True
        if agent_id == "curator_agent" and event_type == "artifact_write":
            curator_ok = True
        if event_type in {"dispatch", "tool_execution", "artifact_write", "quality_check"} and str(payload.get("validator") or "") != "intake_gate":
            missing = sorted(field for field in REQUIRED_RUNTIME_FIELDS if field not in payload)
            if missing:
                payload_issues.append(f"{event.get('event_id') or '?'} missing {', '.join(missing)}")
        if event_type == "tool_execution" and agent_id and str(payload.get("owner_agent_id") or "").strip() != agent_id:
            owner_mismatches.append(str(event.get("event_id") or "").strip() or "?")
    _check(checks, "action_chain_dispatch", dispatch_ok, "action_chain must contain a dispatch event from rdc-debugger", path=action_chain if action_chain.is_file() else None)
    _check(checks, "action_chain_runtime_payload", not payload_issues, "dispatch/tool_execution/artifact_write/quality_check payloads must carry runtime_generation/snapshot_rev/owner_agent_id/lease_epoch/continuity_status/action_request_id", path=action_chain if action_chain.is_file() else None, refs=payload_issues[:8] or None)
    _check(checks, "tool_execution_owner_alignment", not owner_mismatches, "tool_execution.agent_id must equal payload.owner_agent_id", path=action_chain if action_chain.is_file() else None, refs=owner_mismatches[:8] or None)
    _check(checks, "action_chain_skeptic", skeptic_ok, "action_chain must contain skeptic review activity", path=action_chain if action_chain.is_file() else None)
    _check(checks, "action_chain_curator", curator_ok, "action_chain must contain curator report artifact_write", path=action_chain if action_chain.is_file() else None)
    _check(checks, "workflow_stage_overreach", not workflow_stage_overreach_issues(events, coordination_mode="staged_handoff"), "rdc-debugger must not execute live tool work while waiting_for_specialist_brief", path=action_chain if action_chain.is_file() else None, refs=workflow_stage_overreach_issues(events, coordination_mode="staged_handoff")[:8] or None)
    _check(checks, "runtime_generation_recorded", int((runtime_session_data or {}).get("runtime_generation") or 0) >= 1 and int((runtime_snapshot_data or {}).get("runtime_generation") or 0) >= 1, "runtime_session.yaml and runtime_snapshot.yaml must carry runtime_generation", path=runtime_session if runtime_session.is_file() else None)
    _check(checks, "snapshot_revision_recorded", ((runtime_snapshot_data or {}).get("snapshot_rev") is not None) and int((runtime_snapshot_data or {}).get("snapshot_rev")) >= 0, "runtime_snapshot.yaml must carry snapshot_rev", path=runtime_snapshot if runtime_snapshot.is_file() else None)

    return {
        "schema_version": RUN_COMPLIANCE_SCHEMA,
        "platform": platform,
        "run_root": _norm(run_root),
        "generated_by": "run_compliance_audit",
        "generated_at": _now_iso(),
        "status": "passed" if all(item["result"] == "pass" for item in checks) else "failed",
        "session_id": session_id,
        "checks": checks,
        "summary": {"passed": sum(1 for item in checks if item["result"] == "pass"), "failed": sum(1 for item in checks if item["result"] == "fail")},
        "metrics": _metrics(events),
        "paths": {
            "case_yaml": _norm(case_yaml),
            "case_input": _norm(case_input),
            "entry_gate": _norm(entry_gate),
            "captures_manifest": _norm(captures_manifest),
            "references_manifest": _norm(references_manifest),
            "run_yaml": _norm(run_yaml),
            "capture_refs": _norm(capture_refs),
            "intake_gate": _norm(intake_gate),
            "runtime_session": _norm(runtime_session),
            "runtime_snapshot": _norm(runtime_snapshot),
            "ownership_lease": _norm(ownership_lease),
            "runtime_failure": _norm(runtime_failure),
            "fix_verification": _norm(fix_verification),
            "hypothesis_board": _norm(hypothesis_board),
            "session_evidence": _norm(session_evidence),
            "skeptic_signoff": _norm(skeptic_signoff),
            "action_chain": _norm(action_chain),
            "report_md": _norm(report_md),
            "visual_report_html": _norm(visual_report),
        },
    }


def write_run_audit_artifact(root: Path, run_root: Path, platform: str) -> dict[str, Any]:
    payload = run_audit(root, run_root, platform)
    action_chain_path = Path(payload["paths"]["action_chain"])
    session = _read_yaml(Path(payload["paths"]["runtime_session"])) if Path(payload["paths"]["runtime_session"]).is_file() else {}
    snapshot = _read_yaml(Path(payload["paths"]["runtime_snapshot"])) if Path(payload["paths"]["runtime_snapshot"]).is_file() else {}
    run_data = _read_yaml(run_root / "run.yaml") if (run_root / "run.yaml").is_file() else {}
    if not isinstance(run_data, dict):
        run_data = {}
    _append_event(action_chain_path, {"schema_version": ACTION_CHAIN_SCHEMA, "event_id": f"evt-audit-run-compliance-{payload['status']}", "ts_ms": _now_ms(), "run_id": str(run_data.get("run_id", "")).strip(), "session_id": payload["session_id"], "agent_id": "rdc-debugger", "event_type": "quality_check", "status": "pass" if payload["status"] == "passed" else "fail", "duration_ms": 0, "refs": [], "payload": {"validator": "run_compliance_audit", "summary": f"run compliance audit {payload['status']}", "path": _norm(run_root / "artifacts" / "run_compliance.yaml"), "runtime_generation": int((session or {}).get("runtime_generation") or 1), "snapshot_rev": int((snapshot or {}).get("snapshot_rev") or 0), "owner_agent_id": str((session or {}).get("active_owner_agent_id") or "rdc-debugger"), "lease_epoch": int((session or {}).get("lease_epoch") or 0), "continuity_status": str((session or {}).get("continuity_status") or "fresh_start"), "action_request_id": f"ar-run-compliance-{_now_ms()}"}})
    _dump_yaml(run_root / "artifacts" / "run_compliance.yaml", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit debugger run compliance")
    parser.add_argument("--platform", required=False)
    parser.add_argument("--run-root", type=Path, default=None)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = _debugger_root(args.root)
    run_root = args.run_root.resolve() if args.run_root else _infer_run_root(root)
    platform = args.platform or root.name
    try:
        payload = write_run_audit_artifact(root, run_root, platform)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 2
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), end="")
    if args.strict and payload["status"] != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())