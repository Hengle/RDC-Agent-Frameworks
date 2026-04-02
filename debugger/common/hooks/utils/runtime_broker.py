#!/usr/bin/env python3
"""Shared broker-owned runtime contract for debugger runs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


RUNTIME_SESSION_SCHEMA = "1"
RUNTIME_SNAPSHOT_SCHEMA = "1"
OWNERSHIP_LEASE_SCHEMA = "1"
RUNTIME_FAILURE_SCHEMA = "1"

LEASE_ACTION_CLASSES = {
    "broker_action",
    "artifact_write",
    "submit_brief",
    "skeptic_review",
    "curator_finalize",
}
CONTINUITY_STATUSES = {
    "fresh_start",
    "reattached_equivalent",
    "reattached_shifted",
    "reattach_failed",
}
FAILURE_CLASSES = {
    "TOOL_CONTRACT_VIOLATION",
    "TOOL_RUNTIME_FAILURE",
    "TOOL_CAPABILITY_LIMIT",
    "INVESTIGATION_INCONCLUSIVE",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _run_id(run_root: Path) -> str:
    run_yaml = run_root / "run.yaml"
    if not run_yaml.is_file():
        return run_root.name
    data = _read_yaml(run_yaml)
    if not isinstance(data, dict):
        return run_root.name
    return str(data.get("run_id") or run_root.name).strip() or run_root.name


def runtime_session_path(run_root: Path) -> Path:
    return run_root / "artifacts" / "runtime_session.yaml"


def runtime_snapshot_path(run_root: Path) -> Path:
    return run_root / "artifacts" / "runtime_snapshot.yaml"


def ownership_lease_path(run_root: Path) -> Path:
    return run_root / "artifacts" / "ownership_lease.yaml"


def runtime_failure_path(run_root: Path) -> Path:
    return run_root / "artifacts" / "runtime_failure.yaml"


def load_runtime_session(run_root: Path) -> dict[str, Any]:
    path = runtime_session_path(run_root)
    data = _read_yaml(path) if path.is_file() else {}
    return data if isinstance(data, dict) else {}


def load_runtime_snapshot(run_root: Path) -> dict[str, Any]:
    path = runtime_snapshot_path(run_root)
    data = _read_yaml(path) if path.is_file() else {}
    return data if isinstance(data, dict) else {}


def load_ownership_lease(run_root: Path) -> dict[str, Any]:
    path = ownership_lease_path(run_root)
    data = _read_yaml(path) if path.is_file() else {}
    return data if isinstance(data, dict) else {}


def load_runtime_failure(run_root: Path) -> dict[str, Any]:
    path = runtime_failure_path(run_root)
    data = _read_yaml(path) if path.is_file() else {}
    return data if isinstance(data, dict) else {}


def _default_session(run_root: Path, *, session_id: str, entry_mode: str, backend: str) -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_SESSION_SCHEMA,
        "generated_by": "runtime_broker",
        "generated_at": _now_iso(),
        "status": "active",
        "run_id": _run_id(run_root),
        "entry_mode": entry_mode,
        "backend": backend,
        "runtime_generation": 1,
        "process_status": "alive",
        "session_id": session_id,
        "context_id": "ctx-runtime-001",
        "active_owner_agent_id": "rdc-debugger",
        "lease_epoch": 0,
        "continuity_status": "fresh_start",
    }


def _default_snapshot(run_root: Path, *, generation: int) -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_SNAPSHOT_SCHEMA,
        "generated_by": "runtime_broker",
        "generated_at": _now_iso(),
        "status": "active",
        "run_id": _run_id(run_root),
        "runtime_generation": generation,
        "snapshot_rev": 0,
        "active_event_id": 0,
        "selected_resource": "",
        "pipeline_stage": "",
        "view_intent": "intake",
        "last_successful_action": "start_runtime",
        "last_action_request_id": "ar-start-runtime",
    }


def _default_lease(run_root: Path) -> dict[str, Any]:
    return {
        "schema_version": OWNERSHIP_LEASE_SCHEMA,
        "generated_by": "runtime_broker",
        "generated_at": _now_iso(),
        "status": "released",
        "run_id": _run_id(run_root),
        "owner_agent_id": "",
        "lease_epoch": 0,
        "issued_at": "",
        "expires_at": "",
        "handoff_from": "",
        "workflow_stage": "",
        "allowed_action_classes": [],
        "path": str(ownership_lease_path(run_root)).replace("\\", "/"),
    }


def _default_failure(run_root: Path, *, generation: int) -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_FAILURE_SCHEMA,
        "generated_by": "runtime_broker",
        "generated_at": _now_iso(),
        "status": "clear",
        "run_id": _run_id(run_root),
        "failure_class": "",
        "recovery_attempted": False,
        "runtime_generation_before": generation,
        "runtime_generation_after": generation,
        "continuity_status": "fresh_start",
        "blocking_code": "",
        "notes": "",
    }


def start_runtime(run_root: Path, *, session_id: str, entry_mode: str, backend: str) -> dict[str, Any]:
    run_root = run_root.resolve()
    session = _default_session(run_root, session_id=session_id, entry_mode=entry_mode, backend=backend)
    snapshot = _default_snapshot(run_root, generation=1)
    lease = _default_lease(run_root)
    failure = _default_failure(run_root, generation=1)
    _dump_yaml(runtime_session_path(run_root), session)
    _dump_yaml(runtime_snapshot_path(run_root), snapshot)
    _dump_yaml(ownership_lease_path(run_root), lease)
    _dump_yaml(runtime_failure_path(run_root), failure)
    return {
        "status": "passed",
        "runtime_session": session,
        "runtime_snapshot": snapshot,
        "ownership_lease": lease,
        "runtime_failure": failure,
    }


def acquire_lease(
    run_root: Path,
    *,
    owner_agent_id: str,
    workflow_stage: str,
    allowed_action_classes: list[str] | None = None,
    handoff_from: str = "rdc-debugger",
    ttl_seconds: int = 1800,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    session = load_runtime_session(run_root)
    lease = load_ownership_lease(run_root)
    if not session:
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_RUNTIME_SESSION_REQUIRED",
            "reason": "runtime_session.yaml must exist before lease acquisition",
            "path": str(runtime_session_path(run_root)).replace("\\", "/"),
        }
    if str(session.get("process_status") or "").strip() != "alive":
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_RUNTIME_PROCESS_NOT_ALIVE",
            "reason": "runtime session process must be alive before lease acquisition",
            "path": str(runtime_session_path(run_root)).replace("\\", "/"),
        }
    if str(lease.get("status") or "").strip() == "active":
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_ACTIVE_OWNERSHIP_LEASE",
            "reason": "an active ownership lease already exists",
            "path": str(ownership_lease_path(run_root)).replace("\\", "/"),
        }

    next_epoch = int(session.get("lease_epoch") or 0) + 1
    issued_at = _now()
    expires_at = issued_at + timedelta(seconds=int(ttl_seconds))
    normalized_actions = [
        item
        for item in (str(value).strip() for value in (allowed_action_classes or ["broker_action", "artifact_write", "submit_brief"]))
        if item
    ]
    invalid_actions = [item for item in normalized_actions if item not in LEASE_ACTION_CLASSES]
    if invalid_actions:
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_OWNERSHIP_LEASE_ACTION_INVALID",
            "reason": f"invalid action classes: {', '.join(invalid_actions)}",
            "path": str(ownership_lease_path(run_root)).replace("\\", "/"),
        }

    session["generated_at"] = _now_iso()
    session["active_owner_agent_id"] = owner_agent_id
    session["lease_epoch"] = next_epoch
    _dump_yaml(runtime_session_path(run_root), session)

    payload = {
        "schema_version": OWNERSHIP_LEASE_SCHEMA,
        "generated_by": "runtime_broker",
        "generated_at": _now_iso(),
        "status": "active",
        "run_id": _run_id(run_root),
        "owner_agent_id": owner_agent_id,
        "lease_epoch": next_epoch,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "handoff_from": handoff_from,
        "workflow_stage": workflow_stage,
        "allowed_action_classes": normalized_actions,
        "path": str(ownership_lease_path(run_root)).replace("\\", "/"),
    }
    _dump_yaml(ownership_lease_path(run_root), payload)
    return {"status": "passed", "lease": payload}


def validate_lease(
    run_root: Path,
    *,
    lease_ref: str,
    owner_agent_id: str,
    action_class: str,
    workflow_stage: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    lease_path = Path(lease_ref)
    if not lease_path.is_absolute():
        lease_path = (run_root / lease_ref).resolve()
    if not lease_path.is_file():
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_OWNERSHIP_LEASE_REQUIRED",
            "reason": "ownership lease file is missing",
            "path": str(lease_path).replace("\\", "/"),
        }
    lease = _read_yaml(lease_path)
    if not isinstance(lease, dict):
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_OWNERSHIP_LEASE_INVALID",
            "reason": "ownership lease payload must be a YAML object",
            "path": str(lease_path).replace("\\", "/"),
        }
    if str(lease.get("status") or "").strip() != "active":
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_OWNERSHIP_LEASE_INACTIVE",
            "reason": "ownership lease is not active",
            "path": str(lease_path).replace("\\", "/"),
        }
    if str(lease.get("owner_agent_id") or "").strip() != owner_agent_id:
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_OWNERSHIP_LEASE_OWNER_MISMATCH",
            "reason": "ownership lease owner_agent_id does not match caller",
            "path": str(lease_path).replace("\\", "/"),
        }
    if workflow_stage and str(lease.get("workflow_stage") or "").strip() != workflow_stage:
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_OWNERSHIP_LEASE_STAGE_MISMATCH",
            "reason": "ownership lease workflow_stage does not match caller context",
            "path": str(lease_path).replace("\\", "/"),
        }
    if action_class not in [str(item).strip() for item in (lease.get("allowed_action_classes") or []) if str(item).strip()]:
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_OWNERSHIP_LEASE_ACTION_MISMATCH",
            "reason": "ownership lease does not allow the requested action class",
            "path": str(lease_path).replace("\\", "/"),
        }
    expires_at = str(lease.get("expires_at") or "").strip()
    current = now or _now()
    if not expires_at or current > datetime.fromisoformat(expires_at):
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_OWNERSHIP_LEASE_EXPIRED",
            "reason": "ownership lease has expired",
            "path": str(lease_path).replace("\\", "/"),
        }
    session = load_runtime_session(run_root)
    if not session:
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_RUNTIME_SESSION_REQUIRED",
            "reason": "runtime_session.yaml must exist before lease validation",
            "path": str(runtime_session_path(run_root)).replace("\\", "/"),
        }
    if str(session.get("active_owner_agent_id") or "").strip() != owner_agent_id:
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_RUNTIME_OWNER_MISMATCH",
            "reason": "runtime_session active_owner_agent_id does not match caller",
            "path": str(runtime_session_path(run_root)).replace("\\", "/"),
        }
    if int(session.get("lease_epoch") or 0) != int(lease.get("lease_epoch") or -1):
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_OWNERSHIP_LEASE_EPOCH_MISMATCH",
            "reason": "runtime_session lease_epoch does not match ownership lease",
            "path": str(runtime_session_path(run_root)).replace("\\", "/"),
        }
    return {
        "status": "passed",
        "lease_epoch": int(lease.get("lease_epoch") or 0),
        "path": str(lease_path).replace("\\", "/"),
    }


def release_lease(run_root: Path, *, reason: str = "feedback_recorded") -> dict[str, Any]:
    run_root = run_root.resolve()
    lease = load_ownership_lease(run_root)
    if not lease:
        return _default_lease(run_root)
    lease["status"] = "released"
    lease["released_at"] = _now_iso()
    lease["release_reason"] = reason
    _dump_yaml(ownership_lease_path(run_root), lease)
    session = load_runtime_session(run_root)
    if session:
        session["generated_at"] = _now_iso()
        session["active_owner_agent_id"] = "rdc-debugger"
        _dump_yaml(runtime_session_path(run_root), session)
    return lease


def update_snapshot(
    run_root: Path,
    *,
    action_request_id: str,
    view_intent: str,
    last_successful_action: str,
    active_event_id: int | None = None,
    selected_resource: str | None = None,
    pipeline_stage: str | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    session = load_runtime_session(run_root)
    snapshot = load_runtime_snapshot(run_root)
    if not session or not snapshot:
        raise FileNotFoundError("runtime session/snapshot must exist before snapshot update")
    snapshot["generated_at"] = _now_iso()
    snapshot["runtime_generation"] = int(session.get("runtime_generation") or 1)
    snapshot["snapshot_rev"] = int(snapshot.get("snapshot_rev") or 0) + 1
    snapshot["view_intent"] = view_intent
    snapshot["last_successful_action"] = last_successful_action
    snapshot["last_action_request_id"] = action_request_id
    if active_event_id is not None:
        snapshot["active_event_id"] = int(active_event_id)
    if selected_resource is not None:
        snapshot["selected_resource"] = selected_resource
    if pipeline_stage is not None:
        snapshot["pipeline_stage"] = pipeline_stage
    _dump_yaml(runtime_snapshot_path(run_root), snapshot)
    return snapshot


def run_action(
    run_root: Path,
    *,
    lease_ref: str,
    owner_agent_id: str,
    action_request_id: str,
    action_class: str,
    workflow_stage: str,
    view_intent: str,
    last_successful_action: str,
) -> dict[str, Any]:
    validation = validate_lease(
        run_root,
        lease_ref=lease_ref,
        owner_agent_id=owner_agent_id,
        action_class=action_class,
        workflow_stage=workflow_stage,
    )
    if validation["status"] != "passed":
        return validation
    snapshot = update_snapshot(
        run_root,
        action_request_id=action_request_id,
        view_intent=view_intent,
        last_successful_action=last_successful_action,
    )
    return {"status": "passed", "snapshot": snapshot, "lease_epoch": validation["lease_epoch"]}


def record_failure(
    run_root: Path,
    *,
    failure_class: str,
    continuity_status: str,
    blocking_code: str,
    recovery_attempted: bool,
    status: str,
    notes: str = "",
) -> dict[str, Any]:
    if failure_class and failure_class not in FAILURE_CLASSES:
        raise ValueError(f"invalid failure_class: {failure_class}")
    if continuity_status not in CONTINUITY_STATUSES:
        raise ValueError(f"invalid continuity_status: {continuity_status}")
    run_root = run_root.resolve()
    session = load_runtime_session(run_root)
    before_generation = int(session.get("runtime_generation") or 1) if session else 1
    existing = load_runtime_failure(run_root)
    after_generation = int(existing.get("runtime_generation_after") or before_generation)
    payload = {
        "schema_version": RUNTIME_FAILURE_SCHEMA,
        "generated_by": "runtime_broker",
        "generated_at": _now_iso(),
        "status": status,
        "run_id": _run_id(run_root),
        "failure_class": failure_class,
        "recovery_attempted": bool(recovery_attempted),
        "runtime_generation_before": before_generation,
        "runtime_generation_after": after_generation,
        "continuity_status": continuity_status,
        "blocking_code": blocking_code,
        "notes": notes,
    }
    _dump_yaml(runtime_failure_path(run_root), payload)
    return payload


def recover_runtime(run_root: Path, *, failure_class: str, continuity_status: str, notes: str = "") -> dict[str, Any]:
    if failure_class != "TOOL_RUNTIME_FAILURE":
        raise ValueError("recover_runtime only supports TOOL_RUNTIME_FAILURE")
    if continuity_status not in {"reattached_equivalent", "reattached_shifted", "reattach_failed"}:
        raise ValueError("invalid continuity_status for recover_runtime")
    run_root = run_root.resolve()
    session = load_runtime_session(run_root)
    failure = load_runtime_failure(run_root)
    if not session:
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_RUNTIME_SESSION_REQUIRED",
            "reason": "runtime_session.yaml must exist before recovery",
            "path": str(runtime_session_path(run_root)).replace("\\", "/"),
        }
    if bool(failure.get("recovery_attempted")):
        payload = record_failure(
            run_root,
            failure_class="TOOL_RUNTIME_FAILURE",
            continuity_status="reattach_failed",
            blocking_code="BLOCKED_RUNTIME_RECOVERY_EXHAUSTED",
            recovery_attempted=True,
            status="blocked",
            notes="runtime recovery budget exhausted",
        )
        return {"status": "blocked", "runtime_failure": payload}

    previous_generation = int(session.get("runtime_generation") or 1)
    if continuity_status == "reattach_failed":
        payload = record_failure(
            run_root,
            failure_class="TOOL_RUNTIME_FAILURE",
            continuity_status=continuity_status,
            blocking_code="BLOCKED_RUNTIME_CONTINUITY_UNPROVEN",
            recovery_attempted=True,
            status="blocked",
            notes=notes,
        )
        return {"status": "blocked", "runtime_failure": payload}

    next_generation = previous_generation + 1
    session["generated_at"] = _now_iso()
    session["runtime_generation"] = next_generation
    session["process_status"] = "alive"
    session["context_id"] = f"ctx-runtime-{next_generation:03d}"
    session["continuity_status"] = continuity_status
    session["active_owner_agent_id"] = "rdc-debugger"
    _dump_yaml(runtime_session_path(run_root), session)

    snapshot = load_runtime_snapshot(run_root)
    if snapshot:
        snapshot["generated_at"] = _now_iso()
        snapshot["runtime_generation"] = next_generation
        snapshot["snapshot_rev"] = int(snapshot.get("snapshot_rev") or 0) + 1
        snapshot["view_intent"] = "recovery"
        snapshot["last_successful_action"] = "recover_runtime"
        snapshot["last_action_request_id"] = "ar-recover-runtime"
        _dump_yaml(runtime_snapshot_path(run_root), snapshot)

    payload = {
        "schema_version": RUNTIME_FAILURE_SCHEMA,
        "generated_by": "runtime_broker",
        "generated_at": _now_iso(),
        "status": "recovered",
        "run_id": _run_id(run_root),
        "failure_class": failure_class,
        "recovery_attempted": True,
        "runtime_generation_before": previous_generation,
        "runtime_generation_after": next_generation,
        "continuity_status": continuity_status,
        "blocking_code": "",
        "notes": notes,
    }
    _dump_yaml(runtime_failure_path(run_root), payload)
    release_lease(run_root, reason="runtime_recovered")
    return {"status": "passed", "runtime_failure": payload, "runtime_session": session}


def close_runtime(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    session = load_runtime_session(run_root)
    if not session:
        return {
            "status": "blocked",
            "blocking_code": "BLOCKED_RUNTIME_SESSION_REQUIRED",
            "reason": "runtime_session.yaml must exist before close_runtime",
            "path": str(runtime_session_path(run_root)).replace("\\", "/"),
        }
    release_lease(run_root, reason="close_runtime")
    session["generated_at"] = _now_iso()
    session["process_status"] = "closed"
    session["active_owner_agent_id"] = "rdc-debugger"
    _dump_yaml(runtime_session_path(run_root), session)
    return {"status": "passed", "runtime_session": session}