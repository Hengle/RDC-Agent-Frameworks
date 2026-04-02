#!/usr/bin/env python3
"""Shared cross-platform harness enforcement core."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
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
    print("missing dependency 'PyYAML'", file=sys.stderr)
    raise SystemExit(2)


def _debugger_root(default: Path | None = None) -> Path:
    return default.resolve() if default else Path(__file__).resolve().parents[3]


COMMON_UTILS = Path(__file__).resolve().parent
COMMON_VALIDATORS = Path(__file__).resolve().parents[1] / "validators"
COMMON_CONFIG = Path(__file__).resolve().parents[2] / "config"
for path in (COMMON_UTILS, COMMON_VALIDATORS, COMMON_CONFIG):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from entry_gate import run_entry_gate as shared_run_entry_gate  # noqa: E402
from hypothesis_board_validator import validate_hypothesis_board  # noqa: E402
from intake_gate import build_intake_gate_payload, run_intake_gate as shared_run_intake_gate  # noqa: E402
from run_compliance_audit import ACTION_CHAIN_SCHEMA, ACTION_SPECIALISTS, load_action_chain_events, specialist_handoff_path_ok, workflow_stage_overreach_issues, write_run_audit_artifact  # noqa: E402
from runtime_broker import acquire_lease, close_runtime, load_ownership_lease, load_runtime_failure, load_runtime_session, load_runtime_snapshot, ownership_lease_path, release_lease, runtime_failure_path, runtime_session_path, runtime_snapshot_path, start_runtime, validate_lease  # noqa: E402
from validate_binding import validate_binding  # noqa: E402
from validate_tool_contract_runtime import validate_runtime_tool_contract  # noqa: E402


GUARD_SCHEMA = "3"
FREEZE_STATE_SCHEMA = "1"
FINALIZATION_RECEIPT_SCHEMA = "1"
DISPATCH_FEEDBACK_EVENT_TYPES = {"artifact_write", "quality_check", "counterfactual_reviewed", "conflict_resolved"}
SPECIALIST_AGENTS = ACTION_SPECIALISTS | {"skeptic_agent", "curator_agent"}
DEFAULT_LEASE_TTL_SECONDS = 1800
NOTE_FILE_BY_AGENT = {
    "triage_agent": "triage.md",
    "capture_repro_agent": "capture_repro.md",
    "pass_graph_pipeline_agent": "pass_graph_pipeline.md",
    "pixel_forensics_agent": "pixel_forensics.md",
    "shader_ir_agent": "shader_ir.md",
    "driver_device_agent": "driver_device.md",
    "skeptic_agent": "skeptic.md",
    "curator_agent": "curator.md",
}


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _norm(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _status_ok(value: str) -> bool:
    return str(value or "").strip() in {"passed", "ready", "not_applicable", "issued"}


def _sanitize_token(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "-" for ch in str(value or "").strip())
    return text.strip("-_") or "unknown"


def _extract_session_id(root: Path, run_root: Path) -> str:
    run_yaml = run_root / "run.yaml"
    run_data = _read_yaml(run_yaml) if run_yaml.is_file() else {}
    if not isinstance(run_data, dict):
        run_data = {}
    for value in (run_data.get("session_id"), (run_data.get("runtime") or {}).get("session_id") if isinstance(run_data.get("runtime"), dict) else None):
        if isinstance(value, str) and value.strip():
            return value.strip()
    marker = root / "common" / "knowledge" / "library" / "sessions" / ".current_session"
    if marker.is_file():
        value = marker.read_text(encoding="utf-8").lstrip("\ufeff").strip()
        if value and value != "session-unset":
            return value
    return ""


def _action_chain_path(root: Path, run_root: Path) -> Path:
    session_id = _extract_session_id(root, run_root)
    base = root / "common" / "knowledge" / "library" / "sessions"
    return base / session_id / "action_chain.jsonl" if session_id else base / "action_chain.jsonl"


def _action_chain_events(root: Path, run_root: Path) -> list[dict[str, Any]]:
    path = _action_chain_path(root, run_root)
    return load_action_chain_events(path) if path.is_file() else []


def _append_event(path: Path, event: dict[str, Any]) -> None:
    payload = json.dumps(event, ensure_ascii=False)
    existing = _read_text(path) if path.exists() else ""
    if payload in existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8', newline='\n') as handle:
        if existing and not existing.endswith('\n'):
            handle.write('\n')
        handle.write(payload)
        handle.write('\n')


def _run_id(run_root: Path) -> str:
    run_yaml = run_root / "run.yaml"
    if not run_yaml.is_file():
        return run_root.name
    data = _read_yaml(run_yaml)
    if not isinstance(data, dict):
        return run_root.name
    return str(data.get("run_id") or run_root.name).strip() or run_root.name


def _guard_payload(*, stage: str, status: str, blockers: list[dict[str, Any]], paths: dict[str, str] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": GUARD_SCHEMA,
        "generated_by": "harness_guard",
        "generated_at": _now_iso(),
        "guard_stage": stage,
        "status": status,
        "blocking_codes": [str(item.get("code") or "").strip() for item in blockers if str(item.get("code") or "").strip()],
        "blockers": blockers,
        **({"paths": paths} if paths else {}),
        **(extra or {}),
    }


def _write_guard_artifact(run_root: Path, name: str, payload: dict[str, Any]) -> Path:
    path = run_root / "artifacts" / name
    _dump_yaml(path, payload)
    return path


def _runtime_fields(run_root: Path) -> dict[str, Any]:
    session = load_runtime_session(run_root)
    snapshot = load_runtime_snapshot(run_root)
    return {
        "entry_mode": str(session.get("entry_mode") or "cli").strip() or "cli",
        "backend": str(session.get("backend") or "local").strip() or "local",
        "runtime_generation": int(session.get("runtime_generation") or 1),
        "snapshot_rev": int(snapshot.get("snapshot_rev") or 0),
        "owner_agent_id": str(session.get("active_owner_agent_id") or "rdc-debugger").strip() or "rdc-debugger",
        "lease_epoch": int(session.get("lease_epoch") or 0),
        "continuity_status": str(session.get("continuity_status") or "fresh_start").strip() or "fresh_start",
    }


def _emit_quality_check(root: Path, run_root: Path, *, stage: str, payload: dict[str, Any], artifact_path: Path) -> None:
    _append_event(
        _action_chain_path(root, run_root),
        {
            "schema_version": ACTION_CHAIN_SCHEMA,
            "event_id": f"evt-harness-{stage}-{_now_ms()}",
            "ts_ms": _now_ms(),
            "run_id": _run_id(run_root),
            "session_id": _extract_session_id(root, run_root),
            "agent_id": "rdc-debugger",
            "event_type": "quality_check",
            "status": "pass" if payload["status"] == "passed" else "fail",
            "duration_ms": 0,
            "refs": [],
            "payload": {"validator": "harness_guard", "path": _norm(artifact_path), "action_request_id": f"ar-harness-{stage}-{_now_ms()}", **_runtime_fields(run_root)},
        },
    )


def _freeze_state_path(run_root: Path) -> Path:
    return run_root / "artifacts" / "freeze_state.yaml"


def _finalization_receipt_path(run_root: Path) -> Path:
    return run_root / "artifacts" / "finalization_receipt.yaml"


def _freeze_blockers(run_root: Path) -> list[dict[str, Any]]:
    path = _freeze_state_path(run_root)
    if not path.is_file():
        return []
    data = _read_yaml(path)
    # 修正：只有当data是dict且status明确等于"frozen"时才返回blocker
    if isinstance(data, dict) and str(data.get("status") or "").strip() == "frozen":
        return [{"code": "BLOCKED_FREEZE_STATE_ACTIVE", "reason": "run is frozen until deviation is resolved", "refs": [_norm(path)]}]
    return []


def freeze_run(run_root: Path, *, blocking_codes: list[str], reason: str, refs: list[str] | None = None) -> dict[str, Any]:
    payload = {"schema_version": FREEZE_STATE_SCHEMA, "generated_by": "harness_guard", "generated_at": _now_iso(), "status": "frozen", "blocking_codes": list(blocking_codes), "reason": reason, "refs": list(refs or [])}
    _dump_yaml(_freeze_state_path(run_root), payload)
    return payload


def _default_reference_contract(capture_roles: list[str]) -> tuple[str, dict[str, Any]]:
    if "baseline" in capture_roles:
        return "cross_device", {"source_kind": "capture_baseline", "source_refs": ["capture:baseline"], "verification_mode": "device_parity", "probe_set": {"pixels": [{"name": "intake_probe", "x": 0, "y": 0}]}, "acceptance": {"fallback_only": True, "max_channel_delta": 0.05}, "readiness_status": "strict_ready"}
    return "single", {"source_kind": "mixed", "source_refs": ["capture:anomalous"], "verification_mode": "visual_comparison", "probe_set": {"pixels": [{"name": "intake_probe", "x": 0, "y": 0}]}, "acceptance": {"fallback_only": True, "max_channel_delta": 0.05}, "readiness_status": "strict_ready"}


def _default_hypothesis_board(session_id: str, user_goal: str, symptom_summary: str) -> dict[str, Any]:
    return {"hypothesis_board": {"session_id": session_id, "entry_skill": "rdc-debugger", "user_goal": user_goal, "intake_state": "handoff_ready", "current_phase": "intake", "current_task": symptom_summary, "active_owner": "rdc-debugger", "pending_requirements": [], "blocking_issues": [], "progress_summary": ["accepted intake complete"], "next_actions": ["run triage before specialist dispatch"], "last_updated": _now_iso(), "intent_gate": {"classifier_version": 1, "judged_by": "rdc-debugger", "clarification_rounds": 0, "normalized_user_goal": user_goal, "primary_completion_question": "why is the render wrong", "dominant_operation": "diagnose", "requested_artifact": "debugger_verdict", "ab_role": "evidence_method", "scores": {"debugger": 9, "analyst": 0, "optimizer": 0}, "decision": "debugger", "confidence": "high", "hard_signals": {"debugger_positive": [], "analyst_positive": [], "optimizer_positive": [], "disqualifiers": []}, "rationale": symptom_summary, "redirect_target": ""}, "hypotheses": []}}


def _next_run_id(case_root: Path) -> str:
    runs_root = case_root / "runs"
    existing = {path.name for path in runs_root.iterdir()} if runs_root.is_dir() else set()
    index = 1
    while True:
        candidate = f"run_{index:03d}"
        if candidate not in existing:
            return candidate
        index += 1
def _resolve_case_id(case_root: Path, case_id: str | None = None) -> str:
    if case_id and str(case_id).strip():
        return str(case_id).strip()
    return case_root.name or "case_001"


def _resolve_session_id(case_id: str, run_id: str, session_id: str | None = None) -> str:
    if session_id and str(session_id).strip():
        return str(session_id).strip()
    return f"sess_{_sanitize_token(case_id)}_{_sanitize_token(run_id)}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _capture_tokens(case_root: Path, capture_paths: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    roles: list[str] = []
    captures_root = case_root / "inputs" / "captures"
    captures_root.mkdir(parents=True, exist_ok=True)
    total = len(capture_paths)
    for index, raw in enumerate(capture_paths):
        source_path = Path(raw).resolve()
        role = "anomalous" if index == 0 else ("baseline" if index == 1 and total >= 2 else "fixed")
        capture_id = f"cap-{role}-{index + 1:03d}"
        dest_path = captures_root / source_path.name
        shutil.copy2(source_path, dest_path)
        entries.append({"capture_id": capture_id, "capture_role": role, "file_name": source_path.name, "source": "historical_good" if role == "baseline" else "user_supplied", "import_mode": "path", "imported_at": _now_iso(), "sha256": _sha256(dest_path), "source_path": _norm(source_path)})
        refs.append({"capture_id": capture_id, "capture_role": role, "file_name": source_path.name})
        roles.append(role)
    return entries, refs, roles


def run_preflight(root: Path, *, case_root: Path | None = None) -> dict[str, Any]:
    binding_findings = validate_binding(root)
    try:
        tool_findings = validate_runtime_tool_contract(root)
        tool_refs = []
        for path, tools in sorted(tool_findings.unknown_tools.items()):
            tool_refs.append(f"{path}: {', '.join(sorted(tools))}")
        tool_refs.extend(tool_findings.missing_prerequisite_examples)
        tool_refs.extend(tool_findings.banned_snippets)
    except Exception as exc:  # noqa: BLE001
        tool_refs = [str(exc)]
    blockers: list[dict[str, Any]] = []
    if binding_findings:
        blockers.append({"code": "BLOCKED_ENTRY_PREFLIGHT", "reason": "binding validation failed", "refs": binding_findings[:12]})
    if tool_refs:
        blockers.append({"code": "BLOCKED_ENTRY_PREFLIGHT", "reason": "runtime tool contract validation failed", "refs": tool_refs[:12]})
    payload = _guard_payload(stage="preflight", status="passed" if not blockers else "blocked", blockers=blockers, paths={"root": _norm(root), **({"case_root": _norm(case_root)} if case_root else {})})
    if case_root:
        _dump_yaml(case_root / "artifacts" / "preflight.yaml", payload)
    return payload


def run_entry_gate(root: Path, case_root: Path, *, platform: str, entry_mode: str, backend: str, capture_paths: list[str] | None = None, mcp_configured: bool = False, remote_transport: str = "", fix_reference_status: str = "strict_ready") -> dict[str, Any]:
    return shared_run_entry_gate(root, case_root.resolve(), platform=platform, entry_mode=entry_mode, backend=backend, capture_paths=capture_paths, mcp_configured=mcp_configured, remote_transport=remote_transport, fix_reference_status=fix_reference_status)


def run_accept_intake(root: Path, case_root: Path, *, platform: str, entry_mode: str, backend: str, capture_paths: list[str], case_id: str = "", run_id: str = "", session_id: str = "", mcp_configured: bool = False, remote_transport: str = "", user_goal: str = "", symptom_summary: str = "") -> dict[str, Any]:
    case_root = case_root.resolve()
    capture_paths = [str(item or "").strip() for item in (capture_paths or []) if str(item or "").strip()]
    entry_payload = run_entry_gate(root, case_root, platform=platform, entry_mode=entry_mode, backend=backend, capture_paths=capture_paths, mcp_configured=mcp_configured, remote_transport=remote_transport, fix_reference_status="strict_ready")
    if entry_payload["status"] != "passed":
        return _guard_payload(stage="accept_intake", status="blocked", blockers=list(entry_payload.get("blockers") or []), paths={"case_root": _norm(case_root), "entry_gate": _norm(case_root / "artifacts" / "entry_gate.yaml")})

    case_id = _resolve_case_id(case_root, case_id)
    run_id = str(run_id or "").strip() or _next_run_id(case_root)
    run_root = case_root / "runs" / run_id
    if (run_root / "run.yaml").is_file():
        return _guard_payload(stage="accept_intake", status="blocked", blockers=[{"code": "BLOCKED_RUN_ALREADY_INITIALIZED", "reason": "run_root already contains run.yaml", "refs": [_norm(run_root)]}], paths={"run_root": _norm(run_root)})

    session_id = _resolve_session_id(case_id, run_id, session_id)
    user_goal = str(user_goal or "").strip() or "locate the rendering root cause"
    symptom_summary = str(symptom_summary or "").strip() or "user supplied debugger capture"
    capture_entries, capture_refs, capture_roles = _capture_tokens(case_root, capture_paths)
    session_mode, reference_contract = _default_reference_contract(capture_roles)
    case_input = {"schema_version": "1", "case_id": case_id, "session": {"mode": session_mode, "goal": user_goal}, "symptom": {"summary": symptom_summary}, "captures": [{"capture_id": item["capture_id"], "role": item["capture_role"], "file_name": item["file_name"], "source": item["source"], "provenance": {"source_path": item["source_path"]}} for item in capture_entries], "environment": {"api": "unknown"}, "reference_contract": reference_contract, "hints": {}, "project": {"engine": "unknown"}}
    _dump_yaml(case_root / "case.yaml", {"case_id": case_id, "current_run": run_id})
    _dump_yaml(case_root / "case_input.yaml", case_input)
    _dump_yaml(case_root / "inputs" / "captures" / "manifest.yaml", {"captures": capture_entries})
    _dump_yaml(case_root / "inputs" / "references" / "manifest.yaml", {"references": [{"reference_id": "reference_contract_intake", "source_kind": reference_contract["source_kind"], "source_refs": list(reference_contract["source_refs"]), "verification_mode": reference_contract["verification_mode"]}]})
    _dump_yaml(run_root / "run.yaml", {"run_id": run_id, "session_id": session_id, "platform": platform, "coordination_mode": "staged_handoff", "runtime": {"coordination_mode": "staged_handoff", "orchestration_mode": "multi_agent", "backend": backend, "entry_mode": entry_mode, "session_id": session_id, "workflow_stage": "accepted_intake_initialized"}})
    _dump_yaml(run_root / "capture_refs.yaml", {"captures": capture_refs})
    _dump_yaml(run_root / "notes" / "hypothesis_board.yaml", _default_hypothesis_board(session_id, user_goal, symptom_summary))
    marker = root / "common" / "knowledge" / "library" / "sessions" / ".current_session"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{session_id}\n", encoding="utf-8")
    intake_payload = run_intake_gate(root, run_root)
    runtime_payload = start_runtime(run_root, session_id=session_id, entry_mode=entry_mode, backend=backend)
    blockers: list[dict[str, Any]] = []
    if intake_payload["status"] != "passed":
        blockers.append({"code": "BLOCKED_INTAKE_GATE_REQUIRED", "reason": "accepted intake did not satisfy the run-level intake gate", "refs": [_norm(run_root / "artifacts" / "intake_gate.yaml")]})
    if runtime_payload["status"] != "passed":
        blockers.append({"code": "BLOCKED_RUNTIME_SESSION_REQUIRED", "reason": "accepted intake did not bootstrap runtime broker artifacts", "refs": [_norm(runtime_session_path(run_root)), _norm(runtime_snapshot_path(run_root)), _norm(ownership_lease_path(run_root)), _norm(runtime_failure_path(run_root))]})
    payload = _guard_payload(stage="accept_intake", status="passed" if not blockers else "blocked", blockers=blockers, paths={"case_root": _norm(case_root), "run_root": _norm(run_root), "entry_gate": _norm(case_root / "artifacts" / "entry_gate.yaml"), "intake_gate": _norm(run_root / "artifacts" / "intake_gate.yaml"), "runtime_session": _norm(runtime_session_path(run_root)), "runtime_snapshot": _norm(runtime_snapshot_path(run_root)), "ownership_lease": _norm(ownership_lease_path(run_root)), "runtime_failure": _norm(runtime_failure_path(run_root))})
    _write_guard_artifact(run_root, "accept_intake.yaml", payload)
    return payload


def run_intake_gate(root: Path, run_root: Path) -> dict[str, Any]:
    return shared_run_intake_gate(root, run_root.resolve())


def validate_ownership_lease(run_root: Path, *, lease_ref: str, owner_agent_id: str, action_class: str, workflow_stage: str = "waiting_for_specialist_brief") -> dict[str, Any]:
    return validate_lease(run_root, lease_ref=lease_ref, owner_agent_id=owner_agent_id, action_class=action_class, workflow_stage=workflow_stage)


def check_execution_lock(run_root: Path, *, agent_id: str, workflow_stage: str = "") -> dict[str, Any]:
    """检查当前workflow_stage是否处于锁定状态。

    如果是锁定状态且agent是rdc-debugger，阻止tool_execution等操作。
    返回锁定状态和阻断码。
    """
    # 定义需要锁定的workflow_stage列表
    LOCKED_STAGES = {"waiting_for_specialist_brief"}

    # 检查当前stage是否处于锁定状态
    is_locked = workflow_stage in LOCKED_STAGES

    # 只有rdc-debugger在锁定状态下会被阻止
    if is_locked and agent_id == "rdc-debugger":
        return {
            "locked": True,
            "blocking_code": "BLOCKED_EXECUTION_LOCK_ACTIVE",
            "reason": f"workflow_stage '{workflow_stage}' is locked for rdc-debugger",
            "workflow_stage": workflow_stage,
        }

    return {
        "locked": False,
        "blocking_code": None,
        "reason": None,
        "workflow_stage": workflow_stage,
    }


def run_dispatch_readiness(root: Path, run_root: Path, *, platform: str) -> dict[str, Any]:
    run_root = run_root.resolve()
    # 修正：在现有检查之前添加execution_lock检查
    runtime_session = load_runtime_session(run_root)
    current_stage = str(runtime_session.get("workflow_stage") or "").strip()
    owner_agent_id = str(runtime_session.get("active_owner_agent_id") or "rdc-debugger").strip() or "rdc-debugger"
    lock_check = check_execution_lock(run_root, agent_id=owner_agent_id, workflow_stage=current_stage)
    if lock_check.get("locked"):
        blockers = [{"code": lock_check["blocking_code"], "reason": lock_check["reason"], "refs": [_norm(run_root)]}]
        return _guard_payload(stage="dispatch_readiness", status="blocked", blockers=blockers, paths={"run_root": _norm(run_root)})
    freeze_blockers = _freeze_blockers(run_root)
    if freeze_blockers:
        return _guard_payload(stage="dispatch_readiness", status="blocked", blockers=freeze_blockers, paths={"run_root": _norm(run_root), "freeze_state": _norm(_freeze_state_path(run_root))})
    blockers: list[dict[str, Any]] = []
    case_root = run_root.parent.parent
    entry_gate = _read_yaml(case_root / "artifacts" / "entry_gate.yaml") if (case_root / "artifacts" / "entry_gate.yaml").is_file() else {}
    intake_gate = _read_yaml(run_root / "artifacts" / "intake_gate.yaml") if (run_root / "artifacts" / "intake_gate.yaml").is_file() else {}
    runtime_session = load_runtime_session(run_root)
    runtime_failure = load_runtime_failure(run_root)
    ownership_lease = load_ownership_lease(run_root)
    if str((entry_gate or {}).get("status") or "").strip() != "passed":
        blockers.append({"code": "BLOCKED_ENTRY_GATE_REQUIRED", "reason": "entry_gate.yaml must be passed before specialist dispatch", "refs": [_norm(case_root / "artifacts" / "entry_gate.yaml")]})
    recomputed_intake = build_intake_gate_payload(root, run_root)
    if str((intake_gate or {}).get("status") or "").strip() != "passed" or any(item.get("result") != "pass" for item in recomputed_intake.get("checks", [])):
        blockers.append({"code": "BLOCKED_INTAKE_GATE_REQUIRED", "reason": "intake_gate.yaml must stay valid before staged handoff", "refs": [_norm(run_root / "artifacts" / "intake_gate.yaml")]})
    if str(runtime_session.get("status") or "").strip() != "active":
        blockers.append({"code": "BLOCKED_RUNTIME_SESSION_REQUIRED", "reason": "runtime_session.yaml must stay active before staged handoff", "refs": [_norm(runtime_session_path(run_root))]})
    if str(runtime_failure.get("status") or "clear").strip() == "blocked":
        blockers.append({"code": str(runtime_failure.get("blocking_code") or "BLOCKED_RUNTIME_FAILURE_OPEN"), "reason": "runtime_failure.yaml contains an unresolved blocked runtime failure", "refs": [_norm(runtime_failure_path(run_root))]})
    if str(ownership_lease.get("status") or "released").strip() == "active":
        blockers.append({"code": "BLOCKED_ACTIVE_OWNERSHIP_LEASE", "reason": "ownership_lease.yaml must be released before a new dispatch", "refs": [_norm(ownership_lease_path(run_root))]})
    board_path = run_root / "notes" / "hypothesis_board.yaml"
    board = _read_yaml(board_path) if board_path.is_file() else {}
    board_issues = validate_hypothesis_board(board) if board else ["hypothesis_board missing"]
    if board_issues:
        blockers.append({"code": "BLOCKED_REQUIRED_ARTIFACT_MISSING", "reason": "hypothesis_board.yaml must satisfy the shared schema before staged handoff", "refs": [_norm(board_path), *board_issues[:8]]})
    overreach = workflow_stage_overreach_issues(_action_chain_events(root, run_root), coordination_mode="staged_handoff")
    if overreach:
        blockers = [{"code": "PROCESS_DEVIATION_MAIN_AGENT_OVERREACH", "reason": "rdc-debugger attempted live investigation while waiting_for_specialist_brief", "refs": overreach[:8]}]
    payload = _guard_payload(stage="dispatch_readiness", status="passed" if not blockers else "blocked", blockers=blockers, paths={"run_root": _norm(run_root), "entry_gate": _norm(case_root / "artifacts" / "entry_gate.yaml"), "intake_gate": _norm(run_root / "artifacts" / "intake_gate.yaml"), "runtime_session": _norm(runtime_session_path(run_root)), "ownership_lease": _norm(ownership_lease_path(run_root)), "runtime_failure": _norm(runtime_failure_path(run_root))}, extra={"platform": platform, "coordination_mode": "staged_handoff", "orchestration_mode": "multi_agent"})
    artifact_path = _write_guard_artifact(run_root, "dispatch_readiness.yaml", payload)
    if blockers:
        _emit_quality_check(root, run_root, stage="dispatch-readiness", payload=payload, artifact_path=artifact_path)
    return payload
def run_dispatch_specialist(root: Path, run_root: Path, *, platform: str, target_agent: str, objective: str, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS) -> dict[str, Any]:
    run_root = run_root.resolve()
    readiness = run_dispatch_readiness(root, run_root, platform=platform)
    if readiness["status"] != "passed":
        return readiness
    if target_agent not in SPECIALIST_AGENTS:
        payload = _guard_payload(stage="dispatch_specialist", status="blocked", blockers=[{"code": "BLOCKED_UNKNOWN_SPECIALIST", "reason": "dispatch target must be a known specialist, skeptic, or curator agent", "refs": [target_agent]}], paths={"run_root": _norm(run_root)})
        _write_guard_artifact(run_root, "dispatch_specialist.yaml", payload)
        return payload
    lease_result = acquire_lease(run_root, owner_agent_id=target_agent, workflow_stage="waiting_for_specialist_brief", allowed_action_classes=["broker_action", "artifact_write", "submit_brief"], handoff_from="rdc-debugger", ttl_seconds=ttl_seconds)
    if lease_result["status"] != "passed":
        payload = _guard_payload(stage="dispatch_specialist", status="blocked", blockers=[{"code": str(lease_result.get("blocking_code") or "BLOCKED_ACTIVE_OWNERSHIP_LEASE"), "reason": str(lease_result.get("reason") or "lease acquisition failed"), "refs": [str(lease_result.get("path") or _norm(ownership_lease_path(run_root)))]}], paths={"run_root": _norm(run_root)})
        _write_guard_artifact(run_root, "dispatch_specialist.yaml", payload)
        return payload
    lease = lease_result["lease"]
    runtime = _runtime_fields(run_root)
    dispatch_event_id = f"evt-dispatch-{_sanitize_token(target_agent)}-{_now_ms()}"
    _append_event(_action_chain_path(root, run_root), {"schema_version": ACTION_CHAIN_SCHEMA, "event_id": dispatch_event_id, "ts_ms": _now_ms(), "run_id": _run_id(run_root), "session_id": _extract_session_id(root, run_root), "agent_id": "rdc-debugger", "event_type": "dispatch", "status": "sent", "duration_ms": 0, "refs": [], "payload": {"target_agent": target_agent, "objective": objective, "ownership_lease_ref": lease["path"], "action_request_id": f"ar-dispatch-{_sanitize_token(target_agent)}-{_now_ms()}", **runtime}})
    _append_event(_action_chain_path(root, run_root), {"schema_version": ACTION_CHAIN_SCHEMA, "event_id": f"evt-stage-waiting-{_sanitize_token(target_agent)}-{_now_ms()}", "ts_ms": _now_ms(), "run_id": _run_id(run_root), "session_id": _extract_session_id(root, run_root), "agent_id": "rdc-debugger", "event_type": "workflow_stage_transition", "status": "entered", "duration_ms": 0, "refs": [dispatch_event_id], "payload": {"workflow_stage": "waiting_for_specialist_brief", "required_artifacts_before_transition": [f"notes/{NOTE_FILE_BY_AGENT.get(target_agent, f'{target_agent}.md')}"]}})
    payload = _guard_payload(stage="dispatch_specialist", status="passed", blockers=[], paths={"run_root": _norm(run_root), "action_chain": _norm(_action_chain_path(root, run_root)), "ownership_lease": lease["path"]}, extra={"target_agent": target_agent, "objective": objective, "ownership_lease": lease})
    _write_guard_artifact(run_root, "dispatch_specialist.yaml", payload)
    return payload


def run_specialist_feedback(root: Path, run_root: Path, *, timeout_seconds: int = 300, now_ms: int | None = None) -> dict[str, Any]:
    run_root = run_root.resolve()
    freeze_blockers = _freeze_blockers(run_root)
    if freeze_blockers:
        return _guard_payload(stage="specialist_feedback", status="blocked", blockers=freeze_blockers, paths={"run_root": _norm(run_root), "freeze_state": _norm(_freeze_state_path(run_root))})
    blockers: list[dict[str, Any]] = []
    if str(load_runtime_session(run_root).get("status") or "").strip() != "active":
        blockers.append({"code": "BLOCKED_RUNTIME_SESSION_REQUIRED", "reason": "specialist feedback requires an active runtime_session.yaml", "refs": [_norm(runtime_session_path(run_root))]})
    events = _action_chain_events(root, run_root)
    now_value = int(now_ms if now_ms is not None else _now_ms())
    timeout_ms = int(timeout_seconds) * 1000
    pending: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("agent_id") or "").strip() != "rdc-debugger" or str(event.get("event_type") or "").strip() != "dispatch":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        target_agent = str(payload.get("target_agent") or "").strip()
        if target_agent not in ACTION_SPECIALISTS:
            continue
        dispatch_ts = int(event.get("ts_ms") or 0)
        feedback = next((candidate for candidate in events if int(candidate.get("ts_ms") or 0) >= dispatch_ts and str(candidate.get("agent_id") or "").strip() == target_agent and ((str(candidate.get("event_type") or "").strip() == "artifact_write" and specialist_handoff_path_ok(str(((candidate.get("payload") or {}).get("path") or "")), run_root)) or str(candidate.get("event_type") or "").strip() in DISPATCH_FEEDBACK_EVENT_TYPES - {"artifact_write"})), None)
        if feedback is not None:
            if str(load_ownership_lease(run_root).get("status") or "").strip() == "active":
                release_lease(run_root, reason="feedback_recorded")
            continue
        age_ms = now_value - dispatch_ts
        if age_ms > timeout_ms:
            pending.append({"target_agent": target_agent, "dispatch_event_id": str(event.get("event_id") or "").strip() or "?", "age_ms": age_ms})
    if pending:
        blockers.append({"code": "BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT", "reason": "a dispatched specialist exceeded the feedback budget without writing a handoff artifact or review event", "refs": [f"{item['target_agent']}@{item['dispatch_event_id']} age_ms={item['age_ms']}" for item in pending[:8]]})
    payload = _guard_payload(stage="specialist_feedback", status="passed" if not blockers else "blocked", blockers=blockers, paths={"run_root": _norm(run_root), "runtime_session": _norm(runtime_session_path(run_root)), "ownership_lease": _norm(ownership_lease_path(run_root)), "action_chain": _norm(_action_chain_path(root, run_root))}, extra={"timeout_seconds": int(timeout_seconds), "pending_dispatches": pending})
    artifact_path = _write_guard_artifact(run_root, "specialist_feedback.yaml", payload)
    if blockers:
        _emit_quality_check(root, run_root, stage="specialist-feedback", payload=payload, artifact_path=artifact_path)
        freeze_run(run_root, blocking_codes=["BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT"], reason="specialist feedback timeout froze the run", refs=[f"{item['target_agent']}@{item['dispatch_event_id']}" for item in pending[:8]])
    return payload


def run_final_audit(root: Path, run_root: Path, *, platform: str) -> dict[str, Any]:
    return write_run_audit_artifact(root, run_root.resolve(), platform)


def run_render_user_verdict(root: Path, run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    freeze_blockers = _freeze_blockers(run_root)
    if freeze_blockers:
        return _guard_payload(stage="user_verdict", status="blocked", blockers=freeze_blockers, paths={"run_root": _norm(run_root), "freeze_state": _norm(_freeze_state_path(run_root))})
    blockers: list[dict[str, Any]] = []
    compliance_path = run_root / "artifacts" / "run_compliance.yaml"
    report_md = run_root / "reports" / "report.md"
    visual_report = run_root / "reports" / "visual_report.html"
    fix_verification = run_root / "artifacts" / "fix_verification.yaml"
    compliance = _read_yaml(compliance_path) if compliance_path.is_file() else {}
    if not compliance_path.is_file() or str((compliance or {}).get("status") or "").strip() != "passed":
        blockers.append({"code": "BLOCKED_RUN_COMPLIANCE_NOT_PASSED", "reason": "render_user_verdict requires artifacts/run_compliance.yaml status=passed", "refs": [_norm(compliance_path)]})
    for path, code in ((report_md, "BLOCKED_REPORT_MISSING"), (visual_report, "BLOCKED_REPORT_MISSING"), (fix_verification, "BLOCKED_FIX_VERIFICATION_MISSING"), (runtime_session_path(run_root), "BLOCKED_RUNTIME_SESSION_REQUIRED"), (runtime_snapshot_path(run_root), "BLOCKED_RUNTIME_SNAPSHOT_REQUIRED"), (ownership_lease_path(run_root), "BLOCKED_OWNERSHIP_LEASE_REQUIRED"), (runtime_failure_path(run_root), "BLOCKED_RUNTIME_FAILURE_REQUIRED")):
        if not path.is_file():
            blockers.append({"code": code, "reason": f"missing required artifact: {_norm(path)}", "refs": [_norm(path)]})
    if str(load_ownership_lease(run_root).get("status") or "released").strip() == "active":
        blockers.append({"code": "BLOCKED_ACTIVE_OWNERSHIP_LEASE", "reason": "render_user_verdict requires ownership_lease.yaml to be released", "refs": [_norm(ownership_lease_path(run_root))]})
    failure = load_runtime_failure(run_root)
    if str(failure.get("status") or "clear").strip() == "blocked":
        blockers.append({"code": str(failure.get("blocking_code") or "BLOCKED_RUNTIME_FAILURE_OPEN"), "reason": "render_user_verdict requires runtime_failure.yaml to be cleared or recovered", "refs": [_norm(runtime_failure_path(run_root))]})
    if blockers:
        return _guard_payload(stage="user_verdict", status="blocked", blockers=blockers, paths={"run_root": _norm(run_root), "run_compliance": _norm(compliance_path), "runtime_session": _norm(runtime_session_path(run_root)), "ownership_lease": _norm(ownership_lease_path(run_root)), "runtime_failure": _norm(runtime_failure_path(run_root))})
    receipt = {"schema_version": FINALIZATION_RECEIPT_SCHEMA, "generated_by": "harness_guard", "generated_at": _now_iso(), "status": "issued", "run_compliance": _norm(compliance_path), "report_md": _norm(report_md), "visual_report_html": _norm(visual_report), "fix_verification": _norm(fix_verification), "runtime_session": _norm(runtime_session_path(run_root)), "runtime_snapshot": _norm(runtime_snapshot_path(run_root)), "ownership_lease": _norm(ownership_lease_path(run_root)), "runtime_failure": _norm(runtime_failure_path(run_root))}
    _dump_yaml(_finalization_receipt_path(run_root), receipt)
    close_runtime(run_root)
    fix_data = _read_yaml(fix_verification) if fix_verification.is_file() else {}
    if not isinstance(fix_data, dict):
        fix_data = {}
    verdict = str(fix_data.get("verdict") or (fix_data.get("overall_result") or {}).get("verdict") or "").strip()
    overall_status = str((fix_data.get("overall_result") or {}).get("status") or "").strip()
    payload = {"schema_version": GUARD_SCHEMA, "generated_by": "harness_guard", "generated_at": _now_iso(), "guard_stage": "user_verdict", "status": "passed", "run_id": _run_id(run_root), "session_id": _extract_session_id(root, run_root), "verdict": verdict, "verification_status": overall_status, "response_lines": ["DEBUGGER_USER_VERDICT", "", f"- verdict: {verdict or 'unknown'}", f"- verification_status: {overall_status or 'unknown'}", f"- reports: {_norm(report_md.relative_to(run_root))}, {_norm(visual_report.relative_to(run_root))}", f"- run_compliance: {_norm(compliance_path.relative_to(run_root))} = passed", f"- finalization_receipt: {_norm(_finalization_receipt_path(run_root).relative_to(run_root))}"], "paths": {"report_md": _norm(report_md), "visual_report_html": _norm(visual_report), "run_compliance": _norm(compliance_path), "fix_verification": _norm(fix_verification), "finalization_receipt": _norm(_finalization_receipt_path(run_root))}}
    _write_guard_artifact(run_root, "user_verdict.yaml", payload)
    return payload


def _print_yaml(payload: dict[str, Any]) -> None:
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), end="")


def main() -> int:
    parser = argparse.ArgumentParser(description="Shared cross-platform harness guard")
    parser.add_argument("--root", type=Path, default=None, help="debugger root override")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--case-root", type=Path, default=None)
    entry = subparsers.add_parser("entry-gate")
    entry.add_argument("--case-root", type=Path, required=True)
    entry.add_argument("--platform", required=True)
    entry.add_argument("--entry-mode", required=True, choices=("cli", "mcp"))
    entry.add_argument("--backend", required=True, choices=("local", "remote"))
    entry.add_argument("--capture-path", action="append", default=[])
    entry.add_argument("--mcp-configured", action="store_true")
    entry.add_argument("--remote-transport", default="")
    entry.add_argument("--fix-reference-status", default="strict_ready")
    accept = subparsers.add_parser("accept-intake")
    accept.add_argument("--case-root", type=Path, required=True)
    accept.add_argument("--platform", required=True)
    accept.add_argument("--entry-mode", required=True, choices=("cli", "mcp"))
    accept.add_argument("--backend", required=True, choices=("local", "remote"))
    accept.add_argument("--capture-path", action="append", default=[])
    accept.add_argument("--case-id", default="")
    accept.add_argument("--run-id", default="")
    accept.add_argument("--session-id", default="")
    accept.add_argument("--mcp-configured", action="store_true")
    accept.add_argument("--remote-transport", default="")
    accept.add_argument("--user-goal", default="")
    accept.add_argument("--symptom-summary", default="")
    intake = subparsers.add_parser("intake-gate")
    intake.add_argument("--run-root", type=Path, required=True)
    dispatch_ready = subparsers.add_parser("dispatch-readiness")
    dispatch_ready.add_argument("--run-root", type=Path, required=True)
    dispatch_ready.add_argument("--platform", required=True)
    dispatch = subparsers.add_parser("dispatch-specialist")
    dispatch.add_argument("--run-root", type=Path, required=True)
    dispatch.add_argument("--platform", required=True)
    dispatch.add_argument("--target-agent", required=True)
    dispatch.add_argument("--objective", required=True)
    dispatch.add_argument("--ttl-seconds", type=int, default=DEFAULT_LEASE_TTL_SECONDS)
    feedback = subparsers.add_parser("specialist-feedback")
    feedback.add_argument("--run-root", type=Path, required=True)
    feedback.add_argument("--timeout-seconds", type=int, default=300)
    feedback.add_argument("--now-ms", type=int, default=None)
    final = subparsers.add_parser("final-audit")
    final.add_argument("--run-root", type=Path, required=True)
    final.add_argument("--platform", required=True)
    verdict = subparsers.add_parser("render-user-verdict")
    verdict.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    root = _debugger_root(args.root)
    try:
        if args.command == "preflight":
            payload = run_preflight(root, case_root=args.case_root.resolve() if args.case_root else None)
        elif args.command == "entry-gate":
            payload = run_entry_gate(root, args.case_root.resolve(), platform=str(args.platform or "").strip(), entry_mode=args.entry_mode, backend=args.backend, capture_paths=list(args.capture_path or []), mcp_configured=bool(args.mcp_configured), remote_transport=str(args.remote_transport or "").strip(), fix_reference_status=str(args.fix_reference_status or "").strip())
        elif args.command == "accept-intake":
            payload = run_accept_intake(root, args.case_root.resolve(), platform=str(args.platform or "").strip(), entry_mode=args.entry_mode, backend=args.backend, capture_paths=list(args.capture_path or []), case_id=str(args.case_id or "").strip(), run_id=str(args.run_id or "").strip(), session_id=str(args.session_id or "").strip(), mcp_configured=bool(args.mcp_configured), remote_transport=str(args.remote_transport or "").strip(), user_goal=str(args.user_goal or "").strip(), symptom_summary=str(args.symptom_summary or "").strip())
        elif args.command == "intake-gate":
            payload = run_intake_gate(root, args.run_root.resolve())
        elif args.command == "dispatch-readiness":
            payload = run_dispatch_readiness(root, args.run_root.resolve(), platform=str(args.platform or "").strip())
        elif args.command == "dispatch-specialist":
            payload = run_dispatch_specialist(root, args.run_root.resolve(), platform=str(args.platform or "").strip(), target_agent=str(args.target_agent or "").strip(), objective=str(args.objective or "").strip(), ttl_seconds=int(args.ttl_seconds))
        elif args.command == "specialist-feedback":
            payload = run_specialist_feedback(root, args.run_root.resolve(), timeout_seconds=int(args.timeout_seconds), now_ms=args.now_ms)
        elif args.command == "final-audit":
            payload = run_final_audit(root, args.run_root.resolve(), platform=str(args.platform or "").strip())
        elif args.command == "render-user-verdict":
            payload = run_render_user_verdict(root, args.run_root.resolve())
        else:
            raise ValueError(f"unknown command: {args.command}")
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 2
    _print_yaml(payload)
    return 0 if _status_ok(str(payload.get("status") or "")) else 1


if __name__ == "__main__":
    raise SystemExit(main())