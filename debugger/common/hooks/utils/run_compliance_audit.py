#!/usr/bin/env python3
"""Audit whether a debugger run complies with the hard-cut knowledge/hooks contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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

UTILS_ROOT = Path(__file__).resolve().parent
if str(UTILS_ROOT) not in sys.path:
    sys.path.insert(0, str(UTILS_ROOT))
VALIDATORS_ROOT = Path(__file__).resolve().parents[1] / "validators"
if str(VALIDATORS_ROOT) not in sys.path:
    sys.path.insert(0, str(VALIDATORS_ROOT))

from knowledge_evolution import default_promotion_metrics, upsert_candidate  # noqa: E402
from spec_store import active_spec_versions, load_active_sops, spec_snapshot_ref  # noqa: E402
from hypothesis_board_validator import validate_hypothesis_board  # noqa: E402
from entry_gate import build_entry_gate_payload  # noqa: E402
from intake_gate import build_intake_gate_payload  # noqa: E402
from intake_validator import validate_case_input  # noqa: E402
from runtime_topology import (  # noqa: E402
    DEGRADED_REASONS,
    DELEGATION_STATUSES,
    FALLBACK_EXECUTION_MODES,
    build_runtime_topology_payload,
)


ACTION_SPECIALISTS = {
    "triage_agent",
    "capture_repro_agent",
    "pass_graph_pipeline_agent",
    "pixel_forensics_agent",
    "shader_ir_agent",
    "driver_device_agent",
}
AGENT_IDS = ACTION_SPECIALISTS | {"rdc-debugger", "skeptic_agent", "curator_agent"}
HYPOTHESIS_STATES = ("OPEN", "ACTIVE", "CONFLICTED", "ARBITRATED", "VALIDATED", "REFUTED")
ACTION_CHAIN_SCHEMA = "2"
SESSION_EVIDENCE_SCHEMA = "2"
RUN_COMPLIANCE_SCHEMA = "2"
SESSION_RE = re.compile(r"\bsession_id\s*[:=]\s*([A-Za-z0-9._-]+)")
CAPTURE_FILE_RE = re.compile(r"\bcapture_file_id\s*[:=]\s*([A-Za-z0-9._-]+)")
EVENT_RE = re.compile(r"\bevent[_\s:=#-]*(\d+)\b", re.IGNORECASE)
FINAL_VERDICT_RE = re.compile(r"DEBUGGER_FINAL_VERDICT|final verdict|最终裁决|结案", re.IGNORECASE)
FIX_VERIFICATION_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "fix_verification_schema.yaml"
ALLOWED_FIX_VERDICTS = {
    "root_cause_localized_fix_unverified",
    "root_cause_probable_fix_unverified",
    "root_cause_validated_fix_verified",
    "root_cause_localized_remote_fix_path_blocked",
    "root_cause_localized_remote_runtime_inconsistent",
    "verification_blocked_remote_backend_capability",
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


def _event_index(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(event.get("event_id", "")).strip(): event for event in events if str(event.get("event_id", "")).strip()}


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _extract_session_id(run_data: dict[str, Any], session_marker: Path) -> str | None:
    for value in (
        run_data.get("session_id"),
        (run_data.get("debug") or {}).get("session_id") if isinstance(run_data.get("debug"), dict) else None,
        (run_data.get("runtime") or {}).get("session_id") if isinstance(run_data.get("runtime"), dict) else None,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    if session_marker.is_file():
        value = session_marker.read_text(encoding="utf-8").lstrip("\ufeff").strip()
        if value and value != "session-unset":
            return value
    return None


def _extract_matches(text: str, pattern: re.Pattern[str]) -> list[str]:
    return [match.strip() for match in pattern.findall(text or "") if str(match).strip()]


def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, detail: str, *, path: Path | None = None, refs: list[str] | None = None) -> None:
    checks.append(
        {
            "id": check_id,
            "result": "pass" if passed else "fail",
            "detail": detail,
            **({"path": _norm(path)} if path else {}),
            **({"refs": refs} if refs else {}),
        },
    )


def _append_event(path: Path, event: dict[str, Any]) -> None:
    serialized = json.dumps(event, ensure_ascii=False)
    existing = _text(path) if path.exists() else ""
    if serialized in existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(serialized)
        handle.write("\n")


def _dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _ensure_event_ref(ref: str, events: dict[str, dict[str, Any]], issues: list[str], prefix: str) -> None:
    event = events.get(ref)
    if event is None:
        issues.append(f"{prefix}{ref} does not resolve in action_chain")
    elif str(event.get("schema_version", "")).strip() != ACTION_CHAIN_SCHEMA:
        issues.append(f"{prefix}{ref} schema_version must be {ACTION_CHAIN_SCHEMA}")


def _path_ref_matches(ref: str, expected: Path) -> bool:
    normalized_ref = str(ref or "").strip().replace("\\", "/")
    normalized_expected = _norm(expected)
    if normalized_ref == normalized_expected or normalized_ref.endswith(normalized_expected):
        return True
    for marker in ("/workspace/", "/common/"):
        if marker in normalized_ref and marker in normalized_expected:
            if normalized_ref[normalized_ref.index(marker):] == normalized_expected[normalized_expected.index(marker):]:
                return True
        bare_marker = marker.strip("/")
        if bare_marker in normalized_ref and marker in normalized_expected:
            expected_suffix = normalized_expected[normalized_expected.index(marker) + 1 :]
            if normalized_ref.endswith(expected_suffix):
                return True
    return False


def _event_validator(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("validator", "")).strip()


def _event_path(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("path", "")).strip()


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _event_payload_str(event: dict[str, Any], key: str) -> str:
    return str(_event_payload(event).get(key) or "").strip()


def _event_payload_list(event: dict[str, Any], key: str) -> list[str]:
    value = _event_payload(event).get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalized_reason_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    elif isinstance(value, str) and value.strip():
        items = [value.strip()]
    else:
        items = []
    return sorted({item for item in items if item})


def _has_passed_intake_gate(events: list[dict[str, Any]]) -> bool:
    for event in events:
        if str(event.get("event_type", "")).strip() != "quality_check":
            continue
        if str(event.get("status", "")).strip() != "pass":
            continue
        if _event_validator(event) == "intake_gate":
            return True
    return False


def _delegation_execution_issues(
    events: list[dict[str, Any]],
    *,
    backend: str,
    topology_data: dict[str, Any],
) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    degraded_reasons = set(_normalized_reason_list((topology_data or {}).get("degraded_reasons")))
    delegation_status = str((topology_data or {}).get("delegation_status") or "").strip()
    fallback_execution_mode = str((topology_data or {}).get("fallback_execution_mode") or "").strip()
    orchestration_mode = str((topology_data or {}).get("orchestration_mode") or "").strip()
    single_agent_reason = str((topology_data or {}).get("single_agent_reason") or "").strip()

    if delegation_status and delegation_status not in DELEGATION_STATUSES:
        issues.append(f"runtime_topology.delegation_status must be one of {sorted(DELEGATION_STATUSES)}")
    if fallback_execution_mode and fallback_execution_mode not in FALLBACK_EXECUTION_MODES:
        issues.append(f"runtime_topology.fallback_execution_mode must be one of {sorted(FALLBACK_EXECUTION_MODES)}")
    invalid_reasons = [item for item in degraded_reasons if item not in DEGRADED_REASONS]
    if invalid_reasons:
        issues.append(f"runtime_topology.degraded_reasons contains invalid values: {', '.join(invalid_reasons)}")

    local_direct = fallback_execution_mode == "local_renderdoc_python" or any(
        _event_payload_str(event, "fallback_execution_mode") == "local_renderdoc_python" for event in events
    )
    dispatch_events = [
        event
        for event in events
        if str(event.get("event_type", "")).strip() == "dispatch"
        and str(event.get("agent_id", "")).strip() == "rdc-debugger"
        and _event_payload_str(event, "target_agent") in ACTION_SPECIALISTS
    ]
    specialist_events = [
        event
        for event in events
        if str(event.get("agent_id", "")).strip() in ACTION_SPECIALISTS | {"skeptic_agent", "curator_agent"}
        and str(event.get("event_type", "")).strip() in {"tool_execution", "artifact_write", "quality_check", "counterfactual_reviewed", "conflict_resolved"}
    ]

    if local_direct:
        degraded_reasons.add("WRAPPER_DEGRADED_LOCAL_DIRECT")
        if backend != "local":
            issues.append("local_renderdoc_python fallback is only allowed for local backend")

    if orchestration_mode not in {"multi_agent", "single_agent_by_user"}:
        issues.append("runtime_topology.orchestration_mode must be multi_agent or single_agent_by_user")
    elif orchestration_mode == "single_agent_by_user":
        if single_agent_reason != "user_requested":
            issues.append("single_agent_by_user requires single_agent_reason=user_requested")
        if dispatch_events:
            issues.append("single_agent_by_user runs must not dispatch specialist agents")
        if specialist_events:
            issues.append("single_agent_by_user runs must not emit specialist-owned execution or reporting events")
        if delegation_status != "single_agent_by_user":
            issues.append("single_agent_by_user runs must record delegation_status=single_agent_by_user")
    else:
        if delegation_status == "single_agent_by_user":
            issues.append("multi_agent runs must not record delegation_status=single_agent_by_user")

    return sorted(set(issues)), sorted(degraded_reasons)


def _resolve_runtime_baton_ref(run_root: Path, ref: str) -> Path | None:
    text = str(ref or "").strip()
    if not text:
        return None
    direct = Path(text)
    if direct.is_file():
        return direct
    if not direct.is_absolute():
        candidate = (run_root / text).resolve()
        if candidate.is_file():
            return candidate
        candidate = (run_root / "artifacts" / "runtime_batons" / direct.name).resolve()
        if candidate.is_file():
            return candidate
    return None


def _event_payload_contract_issues(events: list[dict[str, Any]], *, expected_entry_mode: str, expected_backend: str) -> list[str]:
    issues: list[str] = []
    required_event_types = {"dispatch", "tool_execution", "artifact_write", "quality_check"}
    for event in events:
        event_type = str(event.get("event_type", "")).strip()
        if event_type not in required_event_types:
            continue
        payload = _event_payload(event)
        event_id = str(event.get("event_id", "")).strip() or "?"
        for field in ("entry_mode", "backend", "context_id", "runtime_owner", "baton_ref", "context_binding_id", "capture_ref", "canonical_anchor_ref"):
            if field not in payload:
                issues.append(f"[event {event_id}] payload.{field} must be present for {event_type}")
        entry_mode = str(payload.get("entry_mode") or "").strip()
        backend = str(payload.get("backend") or "").strip()
        if expected_entry_mode and entry_mode and entry_mode != expected_entry_mode:
            issues.append(f"[event {event_id}] payload.entry_mode must match runtime topology ({expected_entry_mode})")
        if expected_backend and backend and backend != expected_backend:
            issues.append(f"[event {event_id}] payload.backend must match runtime topology ({expected_backend})")
    return issues


def _runtime_baton_issues(events: list[dict[str, Any]], run_root: Path) -> list[str]:
    issues: list[str] = []
    for event in events:
        payload = _event_payload(event)
        tool_name = str(payload.get("tool_name") or "").strip()
        baton_ref = str(payload.get("baton_ref") or "").strip()
        event_id = str(event.get("event_id", "")).strip() or "?"
        source_context_id = str(payload.get("source_context_id") or "").strip()
        target_context_id = str(payload.get("context_id") or "").strip()
        if baton_ref and _resolve_runtime_baton_ref(run_root, baton_ref) is None:
            issues.append(f"[event {event_id}] baton_ref does not resolve to runs/<run_id>/artifacts/runtime_batons/**")
        if tool_name in {"rd.session.resume", "rd.session.rehydrate_runtime_baton"} and not baton_ref:
            issues.append(f"[event {event_id}] {tool_name} must declare payload.baton_ref")
        if source_context_id and target_context_id and source_context_id != target_context_id and not baton_ref:
            issues.append(f"[event {event_id}] cross-context live transfer must declare payload.baton_ref")
    return issues


def _context_binding_projection(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        locator = item.get("session_locator") if isinstance(item.get("session_locator"), dict) else {}
        rows.append(
            {
                "context_binding_id": str(item.get("context_binding_id") or "").strip(),
                "context_id": str(item.get("context_id") or "").strip(),
                "owner_agent": str(item.get("owner_agent") or "").strip(),
                "capture_ref": str(item.get("capture_ref") or "").strip(),
                "canonical_anchor_ref": str(item.get("canonical_anchor_ref") or "").strip(),
                "task_scope": str(item.get("task_scope") or "").strip(),
                "status": str(item.get("status") or "").strip(),
                "session_locator": {
                    "session_id": str(locator.get("session_id") or "").strip(),
                    "frame_index": str(locator.get("frame_index") or "").strip(),
                    "active_event_id": str(locator.get("active_event_id") or "").strip(),
                    "rdc_path": str(locator.get("rdc_path") or "").strip(),
                },
            }
        )
    return sorted(rows, key=lambda item: (item["context_id"], item["owner_agent"], item["context_binding_id"]))


def _runtime_topology_issues(
    events: list[dict[str, Any]],
    *,
    coordination_mode: str,
    backend: str,
    applied_live_runtime_policy: str,
) -> list[str]:
    issues: list[str] = []
    tool_events = [event for event in events if str(event.get("event_type", "")).strip() == "tool_execution"]
    owner_set = {value for value in (_event_payload_str(event, "runtime_owner") for event in tool_events) if value}
    context_set = {value for value in (_event_payload_str(event, "context_id") for event in tool_events) if value}
    specialist_dispatches = []
    for event in events:
        if str(event.get("event_type", "")).strip() != "dispatch":
            continue
        payload = _event_payload(event)
        target_agent = str(payload.get("target_agent") or "").strip()
        if target_agent in ACTION_SPECIALISTS:
            specialist_dispatches.append(event)
    if any(str(event.get("agent_id", "")).strip() != _event_payload_str(event, "runtime_owner") for event in tool_events):
        issues.append("tool_execution.agent_id must equal payload.runtime_owner")
    if coordination_mode == "staged_handoff":
        invalid_dispatchers = {
            str(event.get("agent_id", "")).strip()
            for event in specialist_dispatches
            if str(event.get("agent_id", "")).strip() != "rdc-debugger"
        }
        if invalid_dispatchers:
            issues.append("staged_handoff runs must keep specialist dispatch in rdc-debugger hub-and-spoke flow")
    if backend == "remote" or applied_live_runtime_policy == "single_runtime_owner":
        if len(owner_set) > 1:
            issues.append("single-owner runs must keep a single runtime_owner across all tool_execution events")
    elif applied_live_runtime_policy == "multi_context_orchestrated":
        specialist_events = [event for event in tool_events if str(event.get("agent_id", "")).strip() in ACTION_SPECIALISTS]
        distinct_specialists = {str(event.get("agent_id", "")).strip() for event in specialist_events}
        context_to_agents: dict[str, set[str]] = {}
        for event in specialist_events:
            ctx = _event_payload_str(event, "context_id")
            agent_id = str(event.get("agent_id", "")).strip()
            if not ctx or not agent_id:
                continue
            context_to_agents.setdefault(ctx, set()).add(agent_id)
        if any(len(agent_ids) > 1 for agent_ids in context_to_agents.values()):
            issues.append("multi_context_orchestrated runs must place distinct live specialists on distinct context_id values")
        if len(distinct_specialists) > 1 and len({ctx for ctx in context_to_agents}) < len(distinct_specialists):
            issues.append("multi_context_orchestrated runs must place distinct live specialists on distinct context_id values")
    elif coordination_mode == "concurrent_team" and applied_live_runtime_policy == "multi_context_multi_owner":
        specialist_events = [event for event in tool_events if str(event.get("agent_id", "")).strip() in ACTION_SPECIALISTS]
        distinct_specialists = {str(event.get("agent_id", "")).strip() for event in specialist_events}
        if len(distinct_specialists) > 1 and len(context_set) < len(distinct_specialists):
            issues.append("concurrent_team local runs must place distinct live specialists on distinct context_id values")
    return issues


def _specialist_handoff_path_ok(path_value: str, run_root: Path) -> bool:
    if not path_value.strip():
        return False
    notes_root = run_root / "notes"
    capture_refs = run_root / "capture_refs.yaml"
    normalized = path_value.strip().replace("\\", "/")
    notes_norm = _norm(notes_root).rstrip("/")
    if _path_ref_matches(path_value, capture_refs) or normalized == notes_norm or normalized.startswith(notes_norm + "/"):
        return True
    if "/workspace/" in notes_norm:
        expected_suffix = notes_norm[notes_norm.index("/workspace/") + 1 :]
        if normalized == expected_suffix or normalized.startswith(expected_suffix + "/"):
            return True
    return False


def specialist_handoff_path_ok(path_value: str, run_root: Path) -> bool:
    return _specialist_handoff_path_ok(path_value, run_root)


def _dispatched_specialist_handoff_issues(events: list[dict[str, Any]], run_root: Path) -> list[str]:
    issues: list[str] = []
    dispatched: dict[str, list[str]] = {}
    for event in events:
        if str(event.get("agent_id", "")).strip() != "rdc-debugger":
            continue
        if str(event.get("event_type", "")).strip() != "dispatch":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        target = str(payload.get("target_agent", "")).strip()
        if target in ACTION_SPECIALISTS:
            dispatched.setdefault(target, []).append(str(event.get("event_id", "")).strip() or "?")
    for agent_id, refs in dispatched.items():
        matched = any(
            str(event.get("agent_id", "")).strip() == agent_id
            and str(event.get("event_type", "")).strip() == "artifact_write"
            and _specialist_handoff_path_ok(_event_path(event), run_root)
            for event in events
        )
        if not matched:
            issues.append(f"{agent_id} dispatched by rdc-debugger but did not write notes/** or capture_refs.yaml")
    return issues


def _intake_gate_order_issues(events: list[dict[str, Any]]) -> list[str]:
    gate_pass_index: int | None = None
    for index, event in enumerate(events):
        if str(event.get("event_type", "")).strip() != "quality_check":
            continue
        if _event_validator(event) != "intake_gate":
            continue
        if str(event.get("status", "")).strip() != "pass":
            continue
        gate_pass_index = index
        break
    if gate_pass_index is None:
        return ["action_chain must contain a passed intake_gate quality_check event before live analysis"]
    issues: list[str] = []
    for index, event in enumerate(events):
        if index >= gate_pass_index:
            break
        event_type = str(event.get("event_type", "")).strip()
        if event_type in {"dispatch", "tool_execution"}:
            issues.append(f"{event_type} occurred before intake_gate pass: {str(event.get('event_id', '')).strip() or '?'}")
    return issues


def intake_gate_order_issues(events: list[dict[str, Any]]) -> list[str]:
    return _intake_gate_order_issues(events)


def _fix_verification_issues(data: Any) -> list[str]:
    issues: list[str] = []
    schema = _read_yaml(FIX_VERIFICATION_SCHEMA)
    if not isinstance(data, dict):
        return ["fix_verification must be a YAML/JSON object"]
    if not isinstance(schema, dict):
        return [f"unable to load fix verification schema: {FIX_VERIFICATION_SCHEMA}"]

    for item in schema.get("required_fields", []) or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip()
        if not field:
            continue
        value = data.get(field)
        if value is None:
            issues.append(f"missing fix_verification field: {field}")
            continue
        if str(item.get("type", "")).strip() == "object" and not isinstance(value, dict):
            issues.append(f"fix_verification.{field} must be an object")
            continue
        for sub in item.get("required_subfields", []) or []:
            if not isinstance(value, dict) or sub not in value:
                issues.append(f"fix_verification.{field}.{sub} must be present")
                continue
            subvalue = value.get(sub)
            if subvalue is None or (isinstance(subvalue, str) and not subvalue.strip()):
                issues.append(f"fix_verification.{field}.{sub} must be present")

    structural = data.get("structural_verification") if isinstance(data.get("structural_verification"), dict) else {}
    semantic = data.get("semantic_verification") if isinstance(data.get("semantic_verification"), dict) else {}
    overall = data.get("overall_result") if isinstance(data.get("overall_result"), dict) else {}
    verdict = str(data.get("verdict", "")).strip()

    if structural.get("status") not in {"passed", "failed"}:
        issues.append("fix_verification.structural_verification.status must be passed or failed")
    if semantic.get("status") not in {"passed", "failed", "fallback_only"}:
        issues.append("fix_verification.semantic_verification.status must be passed, failed, or fallback_only")
    if overall.get("status") not in {"passed", "failed"}:
        issues.append("fix_verification.overall_result.status must be passed or failed")
    if not verdict:
        issues.append("fix_verification.verdict must be non-empty")
    elif verdict not in ALLOWED_FIX_VERDICTS:
        issues.append("fix_verification.verdict must be one of " + ", ".join(sorted(ALLOWED_FIX_VERDICTS)))
    if not _nonempty_str(data.get("verification_mode")):
        issues.append("fix_verification.verification_mode must be non-empty")
    if not _nonempty_str(data.get("verification_confidence")):
        issues.append("fix_verification.verification_confidence must be non-empty")
    for field in (
        "blocked_by_capability",
        "candidate_fix_prepared",
        "candidate_fix_live_applied",
        "candidate_fix_structurally_validated",
        "candidate_fix_semantically_validated",
    ):
        if not isinstance(data.get(field), bool):
            issues.append(f"fix_verification.{field} must be boolean")
    if not isinstance(data.get("blocked_capability_codes"), list):
        issues.append("fix_verification.blocked_capability_codes must be a list")
    if not isinstance(structural.get("blocked_by_capability"), bool):
        issues.append("fix_verification.structural_verification.blocked_by_capability must be boolean")
    if not isinstance(structural.get("blocked_capability_codes"), list):
        issues.append("fix_verification.structural_verification.blocked_capability_codes must be a list")
    if not isinstance(semantic.get("fallback_only"), bool):
        issues.append("fix_verification.semantic_verification.fallback_only must be boolean")

    if overall.get("status") == "passed":
        if structural.get("status") != "passed":
            issues.append("overall_result.status=passed requires structural_verification.status=passed")
        if semantic.get("status") != "passed":
            issues.append("overall_result.status=passed requires semantic_verification.status=passed")
        if bool(data.get("blocked_by_capability")):
            issues.append("overall_result.status=passed requires blocked_by_capability=false")
        if not bool(data.get("candidate_fix_live_applied")):
            issues.append("overall_result.status=passed requires candidate_fix_live_applied=true")

    if not isinstance(structural.get("probe_results"), list) or not structural.get("probe_results"):
        issues.append("fix_verification.structural_verification.probe_results must be a non-empty list")
    if not isinstance(semantic.get("probe_summary"), list) or not semantic.get("probe_summary"):
        issues.append("fix_verification.semantic_verification.probe_summary must be a non-empty list")
    if not isinstance(structural.get("anomaly_cleared"), bool):
        issues.append("fix_verification.structural_verification.anomaly_cleared must be boolean")
    if semantic.get("status") == "fallback_only" and overall.get("status") != "failed":
        issues.append("semantic_verification.status=fallback_only requires overall_result.status=failed")
    if bool(data.get("blocked_by_capability")) and overall.get("status") != "failed":
        issues.append("blocked_by_capability=true requires overall_result.status=failed")
    if overall and str(overall.get("verdict") or "").strip() != verdict:
        issues.append("fix_verification.overall_result.verdict must match fix_verification.verdict")
    if bool(data.get("blocked_by_capability")) and not list(data.get("blocked_capability_codes") or []):
        issues.append("blocked_by_capability=true requires blocked_capability_codes to be non-empty")
    if not bool(data.get("blocked_by_capability")) and verdict == "verification_blocked_remote_backend_capability":
        issues.append("verification_blocked_remote_backend_capability requires blocked_by_capability=true")
    if verdict == "root_cause_validated_fix_verified" and overall.get("status") != "passed":
        issues.append("root_cause_validated_fix_verified requires overall_result.status=passed")
    if verdict in {
        "root_cause_localized_remote_fix_path_blocked",
        "root_cause_localized_remote_runtime_inconsistent",
        "verification_blocked_remote_backend_capability",
    } and overall.get("status") != "failed":
        issues.append(f"{verdict} requires overall_result.status=failed")
    return issues


def _intent_gate_acceptance_issues(board_data: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(board_data, dict):
        return ["hypothesis_board must be a YAML object"]
    root = board_data.get("hypothesis_board")
    if not isinstance(root, dict):
        return ["hypothesis_board root object must exist"]
    intent_gate = root.get("intent_gate")
    if not isinstance(intent_gate, dict):
        return ["hypothesis_board.intent_gate must be an object"]

    if str(intent_gate.get("decision", "")).strip() != "debugger":
        issues.append("hypothesis_board.intent_gate.decision must be debugger for accepted debugger runs")
    if str(intent_gate.get("judged_by", "")).strip() != "rdc-debugger":
        issues.append("hypothesis_board.intent_gate.judged_by must be rdc-debugger")

    scores = intent_gate.get("scores")
    if not isinstance(scores, dict):
        issues.append("hypothesis_board.intent_gate.scores must be an object")
    else:
        for field in ("debugger", "analyst", "optimizer"):
            if not isinstance(scores.get(field), (int, float)):
                issues.append(f"hypothesis_board.intent_gate.scores.{field} must be numeric")

    rationale = intent_gate.get("rationale")
    if not _nonempty_str(rationale):
        issues.append("hypothesis_board.intent_gate.rationale must be non-empty")

    redirect_target = intent_gate.get("redirect_target")
    if str(redirect_target or "").strip():
        issues.append("hypothesis_board.intent_gate.redirect_target must be empty for accepted debugger runs")

    return issues


def _workflow_stage_overreach_issues(events: list[dict[str, Any]], *, coordination_mode: str) -> list[str]:
    if coordination_mode != "staged_handoff":
        return []
    issues: list[str] = []
    waiting_for_specialist_brief = False
    for event in events:
        event_type = str(event.get("event_type") or "").strip()
        if event_type == "workflow_stage_transition":
            stage = _event_payload_str(event, "workflow_stage")
            status = str(event.get("status") or "").strip()
            if stage == "waiting_for_specialist_brief" and status in {"entered", "blocked"}:
                waiting_for_specialist_brief = True
            elif stage and status == "entered" and stage != "waiting_for_specialist_brief":
                waiting_for_specialist_brief = False
            continue
        if not waiting_for_specialist_brief:
            continue
        if event_type == "tool_execution" and str(event.get("agent_id") or "").strip() == "rdc-debugger":
            event_id = str(event.get("event_id") or "").strip() or "?"
            tool_name = _event_payload_str(event, "tool_name") or "unknown_tool"
            issues.append(
                f"[event {event_id}] rdc-debugger must not execute live tool {tool_name} during waiting_for_specialist_brief",
            )
    return issues


def workflow_stage_overreach_issues(events: list[dict[str, Any]], *, coordination_mode: str) -> list[str]:
    return _workflow_stage_overreach_issues(events, coordination_mode=coordination_mode)


def _load_sops(root: Path) -> dict[str, dict[str, Any]]:
    data = load_active_sops(root)
    if not isinstance(data, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in data.get("sops", []) or []:
        if isinstance(item, dict):
            sop_id = str(item.get("id", "")).strip()
            if sop_id:
                result[sop_id] = item
    return result


def _combo_covered(sops: dict[str, dict[str, Any]], symptoms: list[str], triggers: list[str], invariants: list[str]) -> bool:
    signature = (tuple(sorted(symptoms)), tuple(sorted(triggers)), tuple(sorted(invariants)))
    for sop in sops.values():
        cond = sop.get("trigger_conditions") if isinstance(sop.get("trigger_conditions"), dict) else {}
        candidate = (
            tuple(sorted(str(x) for x in (cond.get("symptom_tags") or []) if str(x).strip())),
            tuple(sorted(str(x) for x in (cond.get("trigger_tags") or []) if str(x).strip())),
            tuple(sorted(str(x) for x in (sop.get("target_invariants") or []) if str(x).strip())),
        )
        if candidate == signature:
            return True
    return False


def _proposal_signature(kind: str, family: str, symptoms: list[str], triggers: list[str], invariants: list[str]) -> str:
    joined = "|".join([kind, family, ",".join(sorted(symptoms)), ",".join(sorted(triggers)), ",".join(sorted(invariants))])
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


def _snapshot_issues(snapshot: dict[str, Any], events: dict[str, dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    if str(snapshot.get("schema_version", "")).strip() != SESSION_EVIDENCE_SCHEMA:
        issues.append(f"session_evidence.schema_version must be {SESSION_EVIDENCE_SCHEMA}")
    if not isinstance(snapshot.get("snapshot_version"), int):
        issues.append("session_evidence.snapshot_version must be an integer")
    if not _nonempty_str(snapshot.get("spec_snapshot_ref")):
        issues.append("session_evidence.spec_snapshot_ref must be a non-empty string")
    active_versions = snapshot.get("active_spec_versions")
    if not isinstance(active_versions, dict):
        issues.append("session_evidence.active_spec_versions must be an object")
    else:
        for family in ("sop_catalog", "invariant_catalog", "symptom_taxonomy", "trigger_taxonomy"):
            if not isinstance(active_versions.get(family), int):
                issues.append(f"active_spec_versions.{family} must be an integer")

    contract = snapshot.get("store_contract")
    truth_roles = contract.get("truth_roles") if isinstance(contract, dict) else None
    if not isinstance(contract, dict):
        issues.append("session_evidence.store_contract must be an object")
    elif not isinstance(truth_roles, dict):
        issues.append("session_evidence.store_contract.truth_roles must be an object")
    else:
        if truth_roles.get("action_chain") != "append_only_ledger":
            issues.append("store_contract.truth_roles.action_chain must be append_only_ledger")
        if truth_roles.get("session_evidence") != "adjudicated_snapshot":
            issues.append("store_contract.truth_roles.session_evidence must be adjudicated_snapshot")
        if truth_roles.get("active_spec_snapshot") != "versioned_spec_pointer":
            issues.append("store_contract.truth_roles.active_spec_snapshot must be versioned_spec_pointer")
        if truth_roles.get("evolution_ledger") != "append_only_governance_ledger":
            issues.append("store_contract.truth_roles.evolution_ledger must be append_only_governance_ledger")
        if truth_roles.get("run_compliance") != "derived_audit":
            issues.append("store_contract.truth_roles.run_compliance must be derived_audit")

    anchor = snapshot.get("causal_anchor")
    if not isinstance(anchor, dict):
        issues.append("session_evidence.causal_anchor must be an object")
    else:
        for field in ("type", "ref", "established_by", "justification"):
            if not _nonempty_str(anchor.get(field)):
                issues.append(f"causal_anchor.{field} must be non-empty")
        refs = anchor.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            issues.append("causal_anchor.evidence_refs must be a non-empty list")
        else:
            for ref in refs:
                _ensure_event_ref(str(ref).strip(), events, issues, "causal_anchor.evidence_refs: ")

    reference_contract = snapshot.get("reference_contract")
    if not isinstance(reference_contract, dict):
        issues.append("session_evidence.reference_contract must be an object")
    else:
        for field in ("ref", "source_kind", "verification_mode"):
            if not _nonempty_str(reference_contract.get(field)):
                issues.append(f"reference_contract.{field} must be non-empty")
        if not isinstance(reference_contract.get("fallback_only"), bool):
            issues.append("reference_contract.fallback_only must be boolean")

    fix_verification = snapshot.get("fix_verification")
    if not isinstance(fix_verification, dict):
        issues.append("session_evidence.fix_verification must be an object")
    else:
        for field in ("ref", "structural_status", "semantic_status", "overall_status"):
            if not _nonempty_str(fix_verification.get(field)):
                issues.append(f"fix_verification.{field} must be non-empty")

    for ref in snapshot.get("evidence_refs", []) or []:
        _ensure_event_ref(str(ref).strip(), events, issues, "session_evidence.evidence_refs: ")

    hypotheses = snapshot.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        issues.append("session_evidence.hypotheses must be a non-empty list")
    else:
        for item in hypotheses:
            if not isinstance(item, dict):
                issues.append("hypotheses contains a non-object entry")
                continue
            hypothesis_id = str(item.get("hypothesis_id", "")).strip() or "?"
            if str(item.get("status", "")).strip() not in HYPOTHESIS_STATES:
                issues.append(f"hypothesis {hypothesis_id} has invalid status")
            if not isinstance(item.get("evidence_refs"), list):
                issues.append(f"hypothesis {hypothesis_id} evidence_refs must be a list")
            else:
                for ref in item["evidence_refs"]:
                    _ensure_event_ref(str(ref).strip(), events, issues, f"hypothesis {hypothesis_id} evidence_refs: ")

    conflicts = snapshot.get("conflicts")
    if not isinstance(conflicts, list):
        issues.append("session_evidence.conflicts must be a list")
    else:
        for item in conflicts:
            if not isinstance(item, dict):
                issues.append("conflicts contains a non-object entry")
                continue
            conflict_id = str(item.get("conflict_id", "")).strip() or "?"
            if str(item.get("status", "")).strip() not in {"OPEN", "ARBITRATED"}:
                issues.append(f"conflict {conflict_id} status must be OPEN or ARBITRATED")
            for field in ("opened_by_event", "resolved_by_event"):
                value = str(item.get(field, "")).strip()
                if value:
                    _ensure_event_ref(value, events, issues, f"conflict {conflict_id} {field}: ")
            for pos in item.get("positions", []) or []:
                if isinstance(pos, dict):
                    for ref in pos.get("evidence_refs", []) or []:
                        _ensure_event_ref(str(ref).strip(), events, issues, f"conflict {conflict_id} evidence_refs: ")

    reviews = snapshot.get("counterfactual_reviews")
    if not isinstance(reviews, list):
        issues.append("session_evidence.counterfactual_reviews must be a list")
    else:
        for item in reviews:
            if not isinstance(item, dict):
                issues.append("counterfactual_reviews contains a non-object entry")
                continue
            review_id = str(item.get("review_id", "")).strip() or "?"
            for field in ("submission_event_id", "review_event_id"):
                value = str(item.get(field, "")).strip()
                if not value:
                    issues.append(f"counterfactual review {review_id} missing {field}")
                else:
                    _ensure_event_ref(value, events, issues, f"counterfactual review {review_id} {field}: ")
            for ref in item.get("evidence_refs", []) or []:
                _ensure_event_ref(str(ref).strip(), events, issues, f"counterfactual review {review_id} evidence_refs: ")

    candidates = snapshot.get("knowledge_candidates")
    if not isinstance(candidates, list):
        issues.append("session_evidence.knowledge_candidates must be a list")
    else:
        for item in candidates:
            if isinstance(item, dict):
                ref = str(item.get("source_event_id", "")).strip()
                if ref:
                    _ensure_event_ref(ref, events, issues, "knowledge candidate source_event_id: ")

    return issues


def _counterfactual_issues(snapshot: dict[str, Any], events: dict[str, dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    hypotheses = {
        str(item.get("hypothesis_id", "")).strip(): str(item.get("status", "")).strip()
        for item in snapshot.get("hypotheses", []) or []
        if isinstance(item, dict)
    }
    unresolved_conflicts = {
        str(item.get("hypothesis_id", "")).strip()
        for item in snapshot.get("conflicts", []) or []
        if isinstance(item, dict) and str(item.get("status", "")).strip() != "ARBITRATED"
    }

    approved = 0
    reviews = snapshot.get("counterfactual_reviews", []) or []
    for item in reviews:
        if not isinstance(item, dict):
            continue
        review_id = str(item.get("review_id", "")).strip() or "?"
        prefix = f"[review {review_id}] "
        proposer = str(item.get("proposer_agent", "")).strip()
        reviewer = str(item.get("reviewer_agent", "")).strip()
        hypothesis_id = str(item.get("hypothesis_id", "")).strip()
        status = str(item.get("status", "")).strip()
        if proposer == reviewer and proposer:
            issues.append(f"{prefix}proposer_agent and reviewer_agent must differ")
        if hypothesis_id in unresolved_conflicts:
            issues.append(f"{prefix}hypothesis has unresolved conflict")
        if hypotheses.get(hypothesis_id) == "CONFLICTED":
            issues.append(f"{prefix}hypothesis is still CONFLICTED")
        submission = events.get(str(item.get("submission_event_id", "")).strip())
        review = events.get(str(item.get("review_event_id", "")).strip())
        if not isinstance(submission, dict) or not isinstance(review, dict):
            continue
        if str(submission.get("event_type", "")).strip() != "counterfactual_submitted":
            issues.append(f"{prefix}submission event type must be counterfactual_submitted")
        if str(review.get("event_type", "")).strip() != "counterfactual_reviewed":
            issues.append(f"{prefix}review event type must be counterfactual_reviewed")
        sp = submission.get("payload")
        rp = review.get("payload")
        if not isinstance(sp, dict) or not isinstance(rp, dict):
            issues.append(f"{prefix}submission/review payload must be objects")
            continue
        if str(sp.get("proposer_agent", "")).strip() != proposer:
            issues.append(f"{prefix}submission proposer_agent mismatch")
        if str(rp.get("reviewer_agent", "")).strip() != reviewer:
            issues.append(f"{prefix}review reviewer_agent mismatch")
        if not _nonempty_str(sp.get("reference_contract_ref")):
            issues.append(f"{prefix}submission reference_contract_ref must be non-empty")
        verification_mode = str(sp.get("verification_mode", "")).strip()
        if not _nonempty_str(verification_mode):
            issues.append(f"{prefix}submission verification_mode must be non-empty")
        baseline_source = sp.get("baseline_source")
        if not isinstance(baseline_source, dict):
            issues.append(f"{prefix}submission baseline_source must be an object")
        else:
            for field in ("kind", "ref"):
                if not _nonempty_str(baseline_source.get(field)):
                    issues.append(f"{prefix}baseline_source.{field} must be non-empty")
        probe_results = sp.get("probe_results")
        if not isinstance(probe_results, list) or not probe_results:
            issues.append(f"{prefix}submission probe_results must be a non-empty list")
        isolation = sp.get("isolation_checks")
        if not isinstance(isolation, dict):
            issues.append(f"{prefix}submission isolation_checks must be an object")
        else:
            for field in ("only_target_changed", "same_scene_same_input", "same_drawcall_count"):
                if not isinstance(isolation.get(field), bool):
                    issues.append(f"{prefix}isolation_checks.{field} must be boolean")
        measurements = sp.get("measurements")
        if not isinstance(measurements, dict):
            issues.append(f"{prefix}submission measurements must be an object")
        else:
            for field in ("pixel_before", "pixel_after", "pixel_baseline"):
                value = measurements.get(field)
                if not isinstance(value, dict) or not isinstance(value.get("rgba"), list) or len(value.get("rgba")) != 4:
                    issues.append(f"{prefix}measurements.{field}.rgba must be a 4-item list")
        scoring = sp.get("scoring")
        if not isinstance(scoring, dict):
            issues.append(f"{prefix}submission scoring must be an object")
        else:
            for field in ("pixel_recovery", "variable_isolation", "symptom_coverage", "total"):
                if not isinstance(scoring.get(field), (int, float)):
                    issues.append(f"{prefix}scoring.{field} must be numeric")
            if status == "approved" and float(scoring.get("total", 0.0)) < 0.80:
                issues.append(f"{prefix}approved review requires scoring.total >= 0.80")
        verdict = rp.get("isolation_verdict")
        if not isinstance(verdict, dict) or not _nonempty_str(verdict.get("verdict")) or not _nonempty_str(verdict.get("rationale")):
            issues.append(f"{prefix}review isolation_verdict must contain verdict and rationale")
        semantic_verdict = str(rp.get("semantic_verdict", "")).strip()
        if not _nonempty_str(semantic_verdict):
            issues.append(f"{prefix}review semantic_verdict must be non-empty")
        if verification_mode == "visual_comparison" and status == "approved":
            issues.append(f"{prefix}visual_comparison cannot be approved for strict finalization")
        if status == "approved" and semantic_verdict != "strict_pass":
            issues.append(f"{prefix}approved review requires semantic_verdict=strict_pass")
        if status == "approved":
            approved += 1

    if approved == 0:
        issues.append("at least one approved independent counterfactual review is required")
    return issues


def _skeptic_signed(data: Any) -> bool:
    if isinstance(data, dict):
        sign_off = data.get("sign_off")
        return isinstance(sign_off, dict) and sign_off.get("signed") is True
    if isinstance(data, list):
        return any(
            isinstance(item, dict)
            and item.get("message_type") == "SKEPTIC_SIGN_OFF"
            and isinstance(item.get("sign_off"), dict)
            and item["sign_off"].get("signed") is True
            for item in data
        )
    return False


def _metrics(events: list[dict[str, Any]], snapshot: dict[str, Any]) -> dict[str, Any]:
    per_agent: dict[str, dict[str, int]] = {}
    tool_total = tool_success = tool_failure = cf_submitted = cf_reviewed = 0
    cand_emitted = cand_updated = cand_replay = cand_shadow = cand_active = cand_rolled_back = 0
    for event in events:
        agent = str(event.get("agent_id", "")).strip() or "unknown"
        bucket = per_agent.setdefault(agent, {"events": 0, "duration_ms": 0})
        bucket["events"] += 1
        if isinstance(event.get("duration_ms"), (int, float)):
            bucket["duration_ms"] += int(event["duration_ms"])
        etype = str(event.get("event_type", "")).strip()
        status = str(event.get("status", "")).strip()
        if etype == "tool_execution":
            tool_total += 1
            if status == "ok":
                tool_success += 1
            elif status == "error":
                tool_failure += 1
        elif etype == "counterfactual_submitted":
            cf_submitted += 1
        elif etype == "counterfactual_reviewed" and status in {"approved", "rejected"}:
            cf_reviewed += 1
        elif etype == "knowledge_candidate_emitted":
            if status == "emitted":
                cand_emitted += 1
            elif status == "updated":
                cand_updated += 1
        elif etype == "knowledge_candidate_transition":
            if status == "replay_validated":
                cand_replay += 1
            elif status == "shadow_active":
                cand_shadow += 1
            elif status == "active":
                cand_active += 1
            elif status == "rolled_back":
                cand_rolled_back += 1

    state_counts = {state: 0 for state in HYPOTHESIS_STATES}
    for item in snapshot.get("hypotheses", []) or []:
        if isinstance(item, dict):
            state = str(item.get("status", "")).strip()
            if state in state_counts:
                state_counts[state] += 1

    latencies: list[int] = []
    total_conflicts = arbitrated = 0
    for item in snapshot.get("conflicts", []) or []:
        if not isinstance(item, dict):
            continue
        total_conflicts += 1
        if str(item.get("status", "")).strip() == "ARBITRATED":
            arbitrated += 1
            opened = item.get("opened_at_ms")
            resolved = item.get("resolved_at_ms")
            if isinstance(opened, (int, float)) and isinstance(resolved, (int, float)) and resolved >= opened:
                latencies.append(int(resolved - opened))

    return {
        "per_agent": per_agent,
        "tool_execution": {
            "total": tool_total,
            "success": tool_success,
            "failure": tool_failure,
            "failure_rate": round((tool_failure / tool_total), 4) if tool_total else 0.0,
        },
        "hypotheses": state_counts,
        "conflicts": {
            "total": total_conflicts,
            "arbitrated": arbitrated,
            "avg_arbitration_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        },
        "counterfactual_reviews": {
            "submitted": cf_submitted,
            "independently_reviewed": cf_reviewed,
            "independent_review_coverage": round((cf_reviewed / cf_submitted), 4) if cf_submitted else 0.0,
        },
        "knowledge_candidates": {
            "emitted": cand_emitted,
            "updated": cand_updated,
            "replay_validated": cand_replay,
            "shadow_active": cand_shadow,
            "activated": cand_active,
            "rolled_back": cand_rolled_back,
        },
    }


def _emit_candidates(root: Path, run_data: dict[str, Any], snapshot: dict[str, Any], session_id: str, run_id: str, action_chain: Path, events: list[dict[str, Any]]) -> None:
    ctx = run_data.get("knowledge_context") if isinstance(run_data.get("knowledge_context"), dict) else {}
    if not ctx:
        return
    symptoms = sorted(str(x) for x in (ctx.get("symptom_tags") or []) if str(x).strip())
    triggers = sorted(str(x) for x in (ctx.get("trigger_tags") or []) if str(x).strip())
    invariants = sorted(str(x) for x in (ctx.get("resolved_invariants") or []) if str(x).strip())
    matched_sop = str(ctx.get("matched_sop_id", "")).strip()
    adherence = ctx.get("sop_adherence_score")
    invariant_explains = bool(ctx.get("invariant_explains_verdict", True))
    sops = _load_sops(root)
    no_match = not (matched_sop and matched_sop in sops)
    low_adherence = isinstance(adherence, (int, float)) and float(adherence) < 0.75
    new_combo = bool(symptoms or triggers or invariants) and not _combo_covered(sops, symptoms, triggers, invariants)
    invariant_gap = (not invariants) or (not invariant_explains)
    review_refs = sorted(
        {
            str(item.get("submission_event_id", "")).strip()
            for item in (snapshot.get("counterfactual_reviews") or [])
            if isinstance(item, dict) and str(item.get("submission_event_id", "")).strip()
        }
        | {
            str(item.get("review_event_id", "")).strip()
            for item in (snapshot.get("counterfactual_reviews") or [])
            if isinstance(item, dict) and str(item.get("review_event_id", "")).strip()
        },
    )
    approved_reviews = [
        item
        for item in (snapshot.get("counterfactual_reviews") or [])
        if isinstance(item, dict) and str(item.get("status", "")).strip() == "approved"
    ]
    approved_rate = 1.0 if approved_reviews else 0.0
    active_versions = active_spec_versions(root)

    def upsert(kind: str, family: str, spec_id: str, reasons: dict[str, bool], summary: str, patch_mode: str) -> None:
        if not any(reasons.values()):
            return
        sig = _proposal_signature(kind, family, symptoms, triggers, invariants)
        proposal_id = f"{'CAND-SOP' if kind == 'sop_candidate' else 'CAND-INV' if kind == 'invariant_candidate' else 'CAND-TAX'}-{sig}"
        metrics = dict(default_promotion_metrics())
        incoming_metrics = ctx.get("promotion_metrics") if isinstance(ctx.get("promotion_metrics"), dict) else {}
        metrics.update(incoming_metrics)
        metrics["counterfactual_approved_rate"] = max(float(metrics.get("counterfactual_approved_rate", 0.0) or 0.0), approved_rate)
        distinct_device_groups = ctx.get("distinct_device_groups")
        if not isinstance(distinct_device_groups, int):
            device_groups = ctx.get("device_groups")
            if isinstance(device_groups, list):
                distinct_device_groups = len({str(item).strip() for item in device_groups if str(item).strip()})
            else:
                distinct_device_groups = 1

        payload = {
            "schema_version": "2",
            "proposal_id": proposal_id,
            "proposal_type": kind,
            "family": family,
            "spec_id": spec_id,
            "canonical_id": spec_id,
            "status": "candidate",
            "title": (
                f"SOP candidate for {', '.join(symptoms) or 'unclassified symptoms'}"
                if kind == "sop_candidate"
                else f"Invariant candidate for {', '.join(symptoms) or 'unclassified symptoms'}"
                if kind == "invariant_candidate"
                else f"Taxonomy candidate for {', '.join(symptoms + triggers) or 'unclassified signals'}"
            ),
            "summary": summary,
            "base_version": int(active_versions.get(family, 1) or 1),
            "candidate_version": int(active_versions.get(family, 1) or 1) + 1,
            "confidence_score": round(float(ctx.get("confidence_score", 0.75 if kind == "sop_candidate" else 0.7)), 4),
            "trigger_reasons": [name for name, enabled in reasons.items() if enabled],
            "match_signature": {
                "symptom_tags": symptoms,
                "trigger_tags": triggers,
                "resolved_invariants": invariants,
            },
            "proposed_patch": {
                "mode": patch_mode,
                "matched_sop_id": matched_sop,
                "matched_invariants": invariants,
                "summary": summary,
            },
            "negative_evidence_summary": str(ctx.get("negative_evidence_summary", "no durable negative evidence captured yet")).strip(),
            "dedupe_group": f"{family}:{sig}",
            "dedupe_targets": [],
            "distinct_device_groups": int(distinct_device_groups or 1),
            "promotion_metrics": metrics,
            "validation_stage": "candidate",
            "source_refs": {"session_ids": [session_id], "run_ids": [run_id], "event_ids": review_refs},
        }
        promotion_target = ctx.get("promotion_target")
        if isinstance(promotion_target, dict):
            payload["promotion_target"] = promotion_target
        upsert_candidate(root, payload, action_chain_path=action_chain, run_id=run_id, session_id=session_id, refs=review_refs)

    upsert(
        "sop_candidate",
        "sop_catalog",
        "SOP-CATALOG",
        {"no_active_sop_match": no_match, "low_sop_adherence": low_adherence, "new_symptom_trigger_invariant_combo": new_combo},
        "由合规 run 自动提出；当前 active SOP 覆盖不足、遵循度偏低，或新组合需要更短有效路径。",
        "candidate_stub",
    )
    upsert(
        "invariant_candidate",
        "invariant_catalog",
        "INVARIANT-CATALOG",
        {"invariant_gap": invariant_gap},
        "由合规 run 自动提出；当前 active invariant 无法完整解释最终裁决，需要补足最小解释约束。",
        "candidate_stub",
    )
    taxonomy_gap = bool(ctx.get("taxonomy_gaps")) or ("unclassified" in symptoms) or ("unclassified" in triggers)
    taxonomy_scope = str(ctx.get("taxonomy_scope", "symptom_taxonomy")).strip() or "symptom_taxonomy"
    if taxonomy_gap:
        upsert(
            "taxonomy_candidate",
            taxonomy_scope,
            "SYMPTOM-TAXONOMY" if taxonomy_scope == "symptom_taxonomy" else "TRIGGER-TAXONOMY",
            {"taxonomy_gap": True},
            "由合规 run 自动提出；当前 taxonomy 需要新增稳定标签、alias 归并或高混淆标签拆分。",
            "taxonomy_stub",
        )


def run_audit(root: Path, run_root: Path, platform: str) -> dict[str, Any]:
    compliance = _read_json(root / "common" / "config" / "framework_compliance.json")
    caps = _read_json(root / "common" / "config" / "platform_capabilities.json")
    platform_rules = (compliance.get("platforms") or {}).get(platform)
    platform_caps = (caps.get("platforms") or {}).get(platform)
    if not isinstance(platform_rules, dict):
        raise KeyError(f"unknown platform in framework_compliance.json: {platform}")
    if not isinstance(platform_caps, dict):
        raise KeyError(f"unknown platform in platform_capabilities.json: {platform}")

    checks: list[dict[str, Any]] = []
    case_root = run_root.parent.parent
    case_yaml = case_root / "case.yaml"
    case_input = case_root / "case_input.yaml"
    entry_gate = case_root / "artifacts" / "entry_gate.yaml"
    captures_manifest = case_root / "inputs" / "captures" / "manifest.yaml"
    references_manifest = case_root / "inputs" / "references" / "manifest.yaml"
    run_yaml = run_root / "run.yaml"
    capture_refs = run_root / "capture_refs.yaml"
    fix_verification = run_root / "artifacts" / "fix_verification.yaml"
    intake_gate = run_root / "artifacts" / "intake_gate.yaml"
    runtime_topology = run_root / "artifacts" / "runtime_topology.yaml"
    hypothesis_board = run_root / "notes" / "hypothesis_board.yaml"
    report_md = run_root / "reports" / "report.md"
    visual_report = run_root / "reports" / "visual_report.html"
    session_marker = root / "common" / "knowledge" / "library" / "sessions" / ".current_session"

    run_data = _read_yaml(run_yaml) if run_yaml.is_file() else {}
    if not isinstance(run_data, dict):
        run_data = {}
    run_id = str(run_data.get("run_id", "")).strip()
    expected_coordination = str(platform_rules.get("coordination_mode", "")).strip()
    session_id = _extract_session_id(run_data, session_marker)

    _check(checks, "case_yaml", case_yaml.is_file(), "case.yaml must exist", path=case_yaml)
    _check(checks, "case_input", case_input.is_file(), "case_input.yaml must exist", path=case_input)
    _check(checks, "entry_gate_artifact", entry_gate.is_file(), "workspace/cases/<case_id>/artifacts/entry_gate.yaml must exist", path=entry_gate)
    _check(checks, "captures_manifest", captures_manifest.is_file(), "inputs/captures/manifest.yaml must exist", path=captures_manifest)
    _check(checks, "references_manifest", references_manifest.is_file(), "inputs/references/manifest.yaml must exist", path=references_manifest)
    _check(checks, "run_yaml", run_yaml.is_file(), "run.yaml must exist", path=run_yaml)
    _check(checks, "capture_refs", capture_refs.is_file(), "runs/<run_id>/capture_refs.yaml must exist", path=capture_refs)
    _check(checks, "fix_verification", fix_verification.is_file(), "artifacts/fix_verification.yaml must exist", path=fix_verification)
    _check(checks, "intake_gate_artifact", intake_gate.is_file(), "artifacts/intake_gate.yaml must exist", path=intake_gate)
    _check(checks, "runtime_topology_artifact", runtime_topology.is_file(), "artifacts/runtime_topology.yaml must exist", path=runtime_topology)
    _check(checks, "hypothesis_board", hypothesis_board.is_file(), "notes/hypothesis_board.yaml must exist", path=hypothesis_board)
    _check(checks, "report_md", report_md.is_file(), "reports/report.md must exist", path=report_md)
    _check(checks, "visual_report_html", visual_report.is_file(), "reports/visual_report.html must exist", path=visual_report)

    run_platform = str(run_data.get("platform", "") or (run_data.get("debug") or {}).get("platform", "")).strip()
    _check(checks, "platform_match", (not run_platform) or (run_platform == platform), f"run platform should match requested platform ({platform})", path=run_yaml if run_yaml.is_file() else None)
    run_coordination = str(run_data.get("coordination_mode", "") or (run_data.get("runtime") or {}).get("coordination_mode", "")).strip()
    _check(checks, "coordination_mode", run_coordination == expected_coordination, f"coordination_mode must be {expected_coordination}", path=run_yaml if run_yaml.is_file() else None)
    _check(checks, "platform_capability_alignment", str(platform_caps.get("coordination_mode", "")).strip() == expected_coordination, "framework_compliance coordination_mode must match platform_capabilities")

    if session_id:
        session_dir = root / "common" / "knowledge" / "library" / "sessions" / session_id
        session_evidence = session_dir / "session_evidence.yaml"
        skeptic_signoff = session_dir / "skeptic_signoff.yaml"
        action_chain = session_dir / "action_chain.jsonl"
        _check(checks, "session_id", True, f"resolved session_id={session_id}", refs=[session_id])
    else:
        session_dir = root / "common" / "knowledge" / "library" / "sessions"
        session_evidence = session_dir / "session_evidence.yaml"
        skeptic_signoff = session_dir / "skeptic_signoff.yaml"
        action_chain = session_dir / "action_chain.jsonl"
        _check(checks, "session_id", False, "session_id could not be resolved from run.yaml or .current_session", path=run_yaml if run_yaml.is_file() else session_marker)

    _check(checks, "session_evidence", session_evidence.is_file(), "session_evidence.yaml must exist", path=session_evidence)
    _check(checks, "skeptic_signoff", skeptic_signoff.is_file(), "skeptic_signoff.yaml must exist", path=skeptic_signoff)
    _check(checks, "action_chain", action_chain.is_file(), "action_chain.jsonl must exist", path=action_chain)

    snapshot = _read_yaml(session_evidence) if session_evidence.is_file() else {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    skeptic_data = _read_yaml(skeptic_signoff) if skeptic_signoff.is_file() else {}
    case_input_data = _read_yaml(case_input) if case_input.is_file() else {}
    entry_gate_data = _read_yaml(entry_gate) if entry_gate.is_file() else {}
    references_manifest_data = _read_yaml(references_manifest) if references_manifest.is_file() else {}
    fix_verification_data = _read_yaml(fix_verification) if fix_verification.is_file() else {}
    intake_gate_data = _read_yaml(intake_gate) if intake_gate.is_file() else {}
    runtime_topology_data = _read_yaml(runtime_topology) if runtime_topology.is_file() else {}
    hypothesis_board_data = _read_yaml(hypothesis_board) if hypothesis_board.is_file() else {}
    events = _load_action_chain(action_chain) if action_chain.is_file() else []
    indexed = _event_index(events)
    active_manifest = root / "common" / "knowledge" / "spec" / "registry" / "active_manifest.yaml"
    computed_entry_gate = build_entry_gate_payload(
        root,
        case_root,
        platform=platform,
        entry_mode=str((entry_gate_data or {}).get("entry_mode") or (platform_caps.get("default_entry_mode") or "cli")).strip() or "cli",
        backend=str((entry_gate_data or {}).get("backend") or "local").strip() or "local",
        capture_paths=list(((entry_gate_data or {}).get("request") or {}).get("capture_paths") or []),
        mcp_configured=bool(((entry_gate_data or {}).get("request") or {}).get("mcp_configured")),
        remote_transport=str(((entry_gate_data or {}).get("request") or {}).get("remote_transport") or "").strip(),
    )
    computed_intake_gate = build_intake_gate_payload(root, run_root)
    computed_runtime_topology = build_runtime_topology_payload(root, run_root, platform=platform)

    _check(checks, "action_chain_nonempty", bool(events), "action_chain.jsonl must contain at least one event", path=action_chain if action_chain.is_file() else None)
    expected_snapshot = spec_snapshot_ref(root)
    _check(
        checks,
        "spec_snapshot_ref",
        (not snapshot) or (str(snapshot.get("spec_snapshot_ref", "")).strip() == expected_snapshot),
        "session_evidence must point at the current active spec snapshot",
        path=session_evidence if session_evidence.is_file() else active_manifest,
        refs=[expected_snapshot] if expected_snapshot else None,
    )

    schema_issues: list[str] = []
    for event in events:
        event_id = str(event.get("event_id", "")).strip() or "?"
        prefix = f"[event {event_id}] "
        for field in ("schema_version", "event_id", "ts_ms", "run_id", "session_id", "agent_id", "event_type", "status", "duration_ms", "refs", "payload"):
            if field not in event:
                schema_issues.append(f"{prefix}missing field: {field}")
        if str(event.get("schema_version", "")).strip() != ACTION_CHAIN_SCHEMA:
            schema_issues.append(f"{prefix}schema_version must be {ACTION_CHAIN_SCHEMA}")
        if str(event.get("run_id", "")).strip() != run_id:
            schema_issues.append(f"{prefix}run_id must match run.yaml")
        if session_id and str(event.get("session_id", "")).strip() != session_id:
            schema_issues.append(f"{prefix}session_id must match resolved session_id")
        if str(event.get("agent_id", "")).strip() not in AGENT_IDS:
            schema_issues.append(f"{prefix}agent_id is invalid")
        if not isinstance(event.get("refs"), list):
            schema_issues.append(f"{prefix}refs must be a list")
        if not isinstance(event.get("payload"), dict):
            schema_issues.append(f"{prefix}payload must be an object")
        elif str(event.get("event_type", "")).strip() in {"dispatch", "tool_execution", "artifact_write", "quality_check"}:
            for field in ("entry_mode", "backend", "context_id", "runtime_owner", "baton_ref"):
                if field not in event["payload"]:
                    schema_issues.append(f"{prefix}payload.{field} must be present")
    _check(checks, "action_chain_schema", not schema_issues, "action_chain events must follow schema_version=2", path=action_chain if action_chain.is_file() else None, refs=schema_issues[:8] or None)

    case_input_issues = validate_case_input(case_input_data) if case_input.is_file() else ["case_input missing"]
    _check(checks, "case_input_schema", not case_input_issues, "case_input.yaml must satisfy intake schema", path=case_input if case_input.is_file() else None, refs=case_input_issues[:8] or None)

    entry_gate_issues: list[str] = []
    if not isinstance(entry_gate_data, dict):
        entry_gate_issues.append("entry_gate artifact must be a YAML object")
    else:
        if str(entry_gate_data.get("status", "")).strip() != "passed":
            entry_gate_issues.append("entry_gate.status must be passed")
        if str(entry_gate_data.get("platform", "")).strip() and str(entry_gate_data.get("platform", "")).strip() != platform:
            entry_gate_issues.append("entry_gate.platform must match the audited platform")
    if str(computed_entry_gate.get("status", "")).strip() != "passed":
        entry_gate_issues.append("recomputed entry_gate blocks the audited case state")
    _check(
        checks,
        "entry_gate_status",
        not entry_gate_issues,
        "entry_gate.yaml must exist and record a passed platform/mode preflight",
        path=entry_gate if entry_gate.is_file() else None,
        refs=entry_gate_issues[:8] or None,
    )

    intake_gate_failures = [item["id"] for item in computed_intake_gate.get("checks", []) if item.get("result") != "pass"]
    _check(
        checks,
        "capture_manifest_integrity",
        "captures_manifest_schema" not in intake_gate_failures,
        "inputs/captures/manifest.yaml must be structurally valid",
        path=captures_manifest if captures_manifest.is_file() else None,
        refs=intake_gate_failures or None,
    )
    _check(
        checks,
        "capture_imported_files",
        "imported_capture_files" not in intake_gate_failures,
        "inputs/captures/manifest.yaml must resolve to imported .rdc files on disk",
        path=captures_manifest if captures_manifest.is_file() else None,
        refs=intake_gate_failures or None,
    )
    _check(
        checks,
        "capture_refs_integrity",
        "capture_refs_schema" not in intake_gate_failures,
        "capture_refs.yaml must reference imported captures from inputs/captures/manifest.yaml",
        path=capture_refs if capture_refs.is_file() else None,
        refs=intake_gate_failures or None,
    )

    references_issues: list[str] = []
    if not isinstance(references_manifest_data, dict):
        references_issues.append("references manifest must be a YAML object")
    elif not isinstance(references_manifest_data.get("references"), list):
        references_issues.append("references manifest must contain references list")
    _check(checks, "references_manifest_schema", not references_issues, "inputs/references/manifest.yaml must be well-formed", path=references_manifest if references_manifest.is_file() else None, refs=references_issues[:8] or None)

    hypothesis_board_issues = validate_hypothesis_board(hypothesis_board_data) if hypothesis_board.is_file() else ["hypothesis_board missing"]
    _check(
        checks,
        "hypothesis_board_schema",
        not hypothesis_board_issues,
        "notes/hypothesis_board.yaml must satisfy panel/orchestration schema",
        path=hypothesis_board if hypothesis_board.is_file() else None,
        refs=hypothesis_board_issues[:8] or None,
    )
    intent_gate_issues = _intent_gate_acceptance_issues(hypothesis_board_data) if hypothesis_board.is_file() else ["hypothesis_board missing"]
    _check(
        checks,
        "intent_gate_acceptance",
        not intent_gate_issues,
        "accepted debugger runs must carry an intent_gate from rdc-debugger",
        path=hypothesis_board if hypothesis_board.is_file() else None,
        refs=intent_gate_issues[:8] or None,
    )

    intake_gate_artifact_issues: list[str] = []
    if not isinstance(intake_gate_data, dict):
        intake_gate_artifact_issues.append("intake_gate artifact must be a YAML object")
    else:
        if str(intake_gate_data.get("status", "")).strip() != "passed":
            intake_gate_artifact_issues.append("intake_gate.status must be passed")
        if str(intake_gate_data.get("workflow_stage", "")).strip() != "intake_gate_passed":
            intake_gate_artifact_issues.append("intake_gate.workflow_stage must be intake_gate_passed")
        if str(intake_gate_data.get("run_root", "")).strip() and str(intake_gate_data.get("run_root", "")).strip() != _norm(run_root):
            intake_gate_artifact_issues.append("intake_gate.run_root must match the audited run_root")
    if str(computed_intake_gate.get("status", "")).strip() != "passed":
        intake_gate_artifact_issues.append("recomputed intake_gate fails for the audited workspace state")
    _check(
        checks,
        "intake_gate_status",
        not intake_gate_artifact_issues,
        "intake_gate.yaml must exist and record a passed intake gate for this run",
        path=intake_gate if intake_gate.is_file() else None,
        refs=intake_gate_artifact_issues[:8] or None,
    )

    runtime_topology_issues: list[str] = []
    if not isinstance(runtime_topology_data, dict):
        runtime_topology_issues.append("runtime_topology artifact must be a YAML object")
    else:
        if str(runtime_topology_data.get("status", "")).strip() != "passed":
            runtime_topology_issues.append("runtime_topology.status must be passed")
        if str(runtime_topology_data.get("entry_mode", "")).strip() != str(computed_runtime_topology.get("entry_mode", "")).strip():
            runtime_topology_issues.append("runtime_topology.entry_mode must match the recomputed topology")
        if str(runtime_topology_data.get("backend", "")).strip() != str(computed_runtime_topology.get("backend", "")).strip():
            runtime_topology_issues.append("runtime_topology.backend must match the recomputed topology")
        for field in (
            "workflow_stage",
            "orchestration_mode",
            "single_agent_reason",
            "sub_agent_mode",
            "peer_communication",
            "agent_description_mode",
            "dispatch_topology",
            "specialist_dispatch_requirement",
            "host_delegation_policy",
            "host_delegation_fallback",
            "runtime_parallelism_ceiling",
            "applied_live_runtime_policy",
            "delegation_status",
            "fallback_execution_mode",
            "remote_context_locality",
            "remote_handle_origin_context",
            "remote_handle_reuse_policy",
        ):
            if str(runtime_topology_data.get(field, "")).strip() != str(computed_runtime_topology.get(field, "")).strip():
                runtime_topology_issues.append(f"runtime_topology.{field} must match the recomputed topology")
        actual_degraded_reasons = _normalized_reason_list(runtime_topology_data.get("degraded_reasons"))
        expected_degraded_reasons = _normalized_reason_list(computed_runtime_topology.get("degraded_reasons"))
        if actual_degraded_reasons != expected_degraded_reasons:
            runtime_topology_issues.append("runtime_topology.degraded_reasons must match the recomputed topology")
        actual_bindings = _context_binding_projection(list(runtime_topology_data.get("context_bindings") or []))
        expected_bindings = _context_binding_projection(list(computed_runtime_topology.get("context_bindings") or []))
        if not actual_bindings:
            runtime_topology_issues.append("runtime_topology.context_bindings must not be empty")
        elif json.dumps(actual_bindings, ensure_ascii=False, sort_keys=True) != json.dumps(expected_bindings, ensure_ascii=False, sort_keys=True):
            runtime_topology_issues.append("runtime_topology.context_bindings must match the recomputed topology")
        actual_remote_gate = dict(runtime_topology_data.get("remote_gate_status") or {})
        expected_remote_gate = dict(computed_runtime_topology.get("remote_gate_status") or {})
        if json.dumps(actual_remote_gate, ensure_ascii=False, sort_keys=True) != json.dumps(expected_remote_gate, ensure_ascii=False, sort_keys=True):
            runtime_topology_issues.append("runtime_topology.remote_gate_status must match the recomputed topology")
        actual_remote_capability_matrix = dict(runtime_topology_data.get("remote_capability_matrix") or {})
        expected_remote_capability_matrix = dict(computed_runtime_topology.get("remote_capability_matrix") or {})
        if json.dumps(actual_remote_capability_matrix, ensure_ascii=False, sort_keys=True) != json.dumps(expected_remote_capability_matrix, ensure_ascii=False, sort_keys=True):
            runtime_topology_issues.append("runtime_topology.remote_capability_matrix must match the recomputed topology")
        actual_blocked_capability_codes = sorted(
            str(item).strip() for item in (runtime_topology_data.get("blocked_capability_codes") or []) if str(item).strip()
        )
        expected_blocked_capability_codes = sorted(
            str(item).strip() for item in (computed_runtime_topology.get("blocked_capability_codes") or []) if str(item).strip()
        )
        if actual_blocked_capability_codes != expected_blocked_capability_codes:
            runtime_topology_issues.append("runtime_topology.blocked_capability_codes must match the recomputed topology")
        actual_recovery_policy = dict(runtime_topology_data.get("recovery_policy") or {})
        expected_recovery_policy = dict(computed_runtime_topology.get("recovery_policy") or {})
        if json.dumps(actual_recovery_policy, ensure_ascii=False, sort_keys=True) != json.dumps(expected_recovery_policy, ensure_ascii=False, sort_keys=True):
            runtime_topology_issues.append("runtime_topology.recovery_policy must match the recomputed topology")
    if str(computed_runtime_topology.get("status", "")).strip() != "passed":
        runtime_topology_issues.append("recomputed runtime_topology fails for the audited run state")
    _check(
        checks,
        "runtime_topology_status",
        not runtime_topology_issues,
        "runtime_topology.yaml must exist and describe the run topology for this action chain",
        path=runtime_topology if runtime_topology.is_file() else None,
        refs=runtime_topology_issues[:8] or None,
    )
    audited_backend = str(
        (runtime_topology_data or {}).get("backend")
        or (computed_runtime_topology or {}).get("backend")
        or entry_gate_data.get("backend")
        or "local"
    ).strip()
    remote_artifact_checks = {
        "remote_prerequisite_gate_artifact": run_root / "artifacts" / "remote_prerequisite_gate.yaml",
        "remote_capability_gate_artifact": run_root / "artifacts" / "remote_capability_gate.yaml",
        "remote_recovery_decision_artifact": run_root / "artifacts" / "remote_recovery_decision.yaml",
        "remote_planning_brief_artifact": run_root / "notes" / "remote_planning_brief.yaml",
        "remote_runtime_inconsistency_artifact": run_root / "notes" / "remote_runtime_inconsistency.yaml",
    }
    for check_id, path in remote_artifact_checks.items():
        _check(
            checks,
            check_id,
            audited_backend != "remote" or path.is_file(),
            f"{path.name} must exist for remote finalization",
            path=path,
        )
    board_root = hypothesis_board_data.get("hypothesis_board") if isinstance(hypothesis_board_data, dict) else {}
    blocking_issue_refs = []
    if isinstance(board_root, dict):
        blocking_issue_refs = [str(item).strip() for item in (board_root.get("blocking_issues") or []) if str(item).strip()]
    _check(
        checks,
        "hypothesis_board_blockers",
        not blocking_issue_refs,
        "hypothesis_board.yaml must not carry unresolved blocking_issues at finalization",
        path=hypothesis_board if hypothesis_board.is_file() else None,
        refs=blocking_issue_refs[:8] or None,
    )

    fix_verification_issues = _fix_verification_issues(fix_verification_data) if fix_verification.is_file() else ["fix_verification missing"]
    _check(checks, "fix_verification_schema", not fix_verification_issues, "fix_verification.yaml must be structurally valid", path=fix_verification if fix_verification.is_file() else None, refs=fix_verification_issues[:8] or None)
    overall_status = str((fix_verification_data or {}).get("overall_result", {}).get("status", "")).strip()
    _check(checks, "fix_verification_pass", overall_status == "passed", "fix_verification overall_result.status must be passed for finalization", path=fix_verification if fix_verification.is_file() else None)

    snapshot_issues = _snapshot_issues(snapshot, indexed)
    _check(checks, "snapshot_refs", not snapshot_issues, "session_evidence must resolve all structured refs into action_chain", path=session_evidence if session_evidence.is_file() else None, refs=snapshot_issues[:8] or None)

    snapshot_contract_issues: list[str] = []
    if isinstance(snapshot.get("reference_contract"), dict) and case_input.is_file():
        ref = str(snapshot["reference_contract"].get("ref", "")).strip()
        if not _path_ref_matches(ref.split("#", 1)[0], case_input):
            snapshot_contract_issues.append("session_evidence.reference_contract.ref must point to case_input.yaml")
    if isinstance(snapshot.get("fix_verification"), dict) and fix_verification.is_file():
        ref = str(snapshot["fix_verification"].get("ref", "")).strip()
        if not _path_ref_matches(ref, fix_verification):
            snapshot_contract_issues.append("session_evidence.fix_verification.ref must point to fix_verification.yaml")
        if str(snapshot["fix_verification"].get("overall_status", "")).strip() != str((fix_verification_data or {}).get("overall_result", {}).get("status", "")).strip():
            snapshot_contract_issues.append("session_evidence.fix_verification.overall_status must match fix_verification.yaml")
    if isinstance(snapshot.get("reference_contract"), dict) and snapshot["reference_contract"].get("fallback_only") is True:
        snapshot_contract_issues.append("fallback_only reference_contract cannot pass strict finalization")
    _check(checks, "snapshot_workspace_contract", not snapshot_contract_issues, "session_evidence must point to workspace verification artifacts", path=session_evidence if session_evidence.is_file() else None, refs=snapshot_contract_issues[:8] or None)

    conflicted = [str(item.get("hypothesis_id", "")).strip() for item in (snapshot.get("hypotheses") or []) if isinstance(item, dict) and str(item.get("status", "")).strip() == "CONFLICTED"]
    unresolved = [str(item.get("conflict_id", "")).strip() for item in (snapshot.get("conflicts") or []) if isinstance(item, dict) and str(item.get("status", "")).strip() != "ARBITRATED"]
    _check(checks, "conflict_block", not conflicted, "no hypothesis may remain CONFLICTED at finalization", path=session_evidence if session_evidence.is_file() else None, refs=conflicted or None)
    _check(checks, "conflict_arbitration", not unresolved, "all conflicts must be ARBITRATED before finalization", path=session_evidence if session_evidence.is_file() else None, refs=unresolved or None)

    cf_issues = _counterfactual_issues(snapshot, indexed)
    _check(checks, "counterfactual_review", not cf_issues, "counterfactual reviews must be independently approved and structurally complete", path=session_evidence if session_evidence.is_file() else None, refs=cf_issues[:8] or None)
    _check(checks, "skeptic_signoff_status", _skeptic_signed(skeptic_data), "skeptic_signoff artifact must contain a signed approval", path=skeptic_signoff if skeptic_signoff.is_file() else None)

    topology_entry_mode = str((runtime_topology_data or {}).get("entry_mode") or (computed_runtime_topology or {}).get("entry_mode") or "").strip()
    topology_backend = str((runtime_topology_data or {}).get("backend") or (computed_runtime_topology or {}).get("backend") or "").strip()
    topology_live_policy = str((runtime_topology_data or {}).get("applied_live_runtime_policy") or (computed_runtime_topology or {}).get("applied_live_runtime_policy") or "").strip()
    orchestration_mode = str((runtime_topology_data or {}).get("orchestration_mode") or (computed_runtime_topology or {}).get("orchestration_mode") or "multi_agent").strip()
    topology_contract = runtime_topology_data if isinstance(runtime_topology_data, dict) and runtime_topology_data else computed_runtime_topology
    degraded_reasons = set(_normalized_reason_list((computed_runtime_topology or {}).get("degraded_reasons")))
    degraded_reasons.update(_normalized_reason_list((runtime_topology_data or {}).get("degraded_reasons")))
    dispatch_ok = any(str(e.get("event_type", "")).strip() == "dispatch" and str(e.get("agent_id", "")).strip() == "rdc-debugger" for e in events)
    live_tool_ok = any(str(e.get("event_type", "")).strip() == "tool_execution" for e in events)
    specialist_tool_ok = any(str(e.get("event_type", "")).strip() == "tool_execution" and str(e.get("agent_id", "")).strip() in ACTION_SPECIALISTS for e in events)
    intake_gate_order_issues = _intake_gate_order_issues(events)
    payload_contract_issues = _event_payload_contract_issues(events, expected_entry_mode=topology_entry_mode, expected_backend=topology_backend)
    runtime_owner_issues = _runtime_topology_issues(
        events,
        coordination_mode=expected_coordination,
        backend=topology_backend or "local",
        applied_live_runtime_policy=topology_live_policy or "single_runtime_owner",
    )
    degraded_execution_issues, normalized_degraded_reasons = _delegation_execution_issues(
        events,
        backend=topology_backend or "local",
        topology_data=topology_contract if isinstance(topology_contract, dict) else {},
    )
    degraded_reasons.update(normalized_degraded_reasons)
    runtime_baton_issues = _runtime_baton_issues(events, run_root)
    specialist_handoff_issues = _dispatched_specialist_handoff_issues(events, run_root)
    process_deviation_events = [
        event for event in events if str(event.get("event_type", "")).strip() == "process_deviation"
    ]
    workflow_stage_overreach_issues = _workflow_stage_overreach_issues(events, coordination_mode=expected_coordination)
    skeptic_ok = any(str(e.get("agent_id", "")).strip() == "skeptic_agent" and str(e.get("event_type", "")).strip() in {"conflict_resolved", "counterfactual_reviewed", "quality_check"} for e in events)
    native_curator_ok = any(
        str(e.get("agent_id", "")).strip() == "curator_agent"
        and str(e.get("event_type", "")).strip() == "artifact_write"
        and _path_ref_matches(_event_path(e), report_md)
        for e in events
    )
    single_agent_report_ok = any(
        str(e.get("agent_id", "")).strip() == "rdc-debugger"
        and str(e.get("event_type", "")).strip() == "artifact_write"
        and _path_ref_matches(_event_path(e), report_md)
        for e in events
    )
    curator_ok = native_curator_ok if orchestration_mode != "single_agent_by_user" else single_agent_report_ok
    _check(
        checks,
        "action_chain_dispatch",
        dispatch_ok if orchestration_mode != "single_agent_by_user" else True,
        "multi_agent runs must contain a dispatch event from rdc-debugger",
        path=action_chain if action_chain.is_file() else None,
    )
    _check(
        checks,
        "action_chain_live_execution",
        live_tool_ok,
        "action_chain must contain live tool_execution evidence",
        path=action_chain if action_chain.is_file() else None,
    )
    _check(
        checks,
        "action_chain_specialist",
        specialist_tool_ok if orchestration_mode != "single_agent_by_user" and expected_coordination == "concurrent_team" and (topology_backend or "local") == "local" else True,
        "multi_agent concurrent_team local runs must contain at least one specialist-owned tool_execution",
        path=action_chain if action_chain.is_file() else None,
    )
    _check(
        checks,
        "intake_gate_before_analysis",
        not intake_gate_order_issues,
        "intake_gate pass must appear in action_chain before any dispatch or tool_execution",
        path=action_chain if action_chain.is_file() else None,
        refs=intake_gate_order_issues[:8] or None,
    )
    _check(
        checks,
        "action_chain_runtime_payload",
        not payload_contract_issues,
        "dispatch/tool_execution/artifact_write/quality_check payloads must carry entry_mode/backend/context_id/runtime_owner/baton_ref/context_binding_id/capture_ref/canonical_anchor_ref",
        path=action_chain if action_chain.is_file() else None,
        refs=payload_contract_issues[:8] or None,
    )
    _check(
        checks,
        "runtime_owner_topology",
        not runtime_owner_issues,
        "runtime owner and context usage must match the run coordination mode and backend",
        path=action_chain if action_chain.is_file() else None,
        refs=runtime_owner_issues[:8] or None,
    )
    _check(
        checks,
        "delegation_execution_contract",
        not degraded_execution_issues,
        "delegation mode and direct-runtime fallback semantics must match the platform contract",
        path=runtime_topology if runtime_topology.is_file() else action_chain if action_chain.is_file() else None,
        refs=degraded_execution_issues[:8] or None,
    )
    _check(
        checks,
        "runtime_baton_contract",
        not runtime_baton_issues,
        "runtime baton refs must resolve and live resume operations must declare baton_ref",
        path=action_chain if action_chain.is_file() else None,
        refs=runtime_baton_issues[:8] or None,
    )
    _check(
        checks,
        "staged_handoff_artifacts",
        not specialist_handoff_issues if orchestration_mode != "single_agent_by_user" else True,
        "each dispatched specialist must leave a handoff artifact in runs/<run_id>/notes/** or capture_refs.yaml",
        path=action_chain if action_chain.is_file() else None,
        refs=specialist_handoff_issues[:8] or None,
    )
    _check(
        checks,
        "workflow_stage_overreach",
        not workflow_stage_overreach_issues,
        "rdc-debugger must not execute live tool work while waiting_for_specialist_brief in staged_handoff runs",
        path=action_chain if action_chain.is_file() else None,
        refs=workflow_stage_overreach_issues[:8] or None,
    )
    _check(
        checks,
        "action_chain_skeptic",
        skeptic_ok if orchestration_mode != "single_agent_by_user" else True,
        "multi_agent runs must contain skeptic review activity",
        path=action_chain if action_chain.is_file() else None,
    )
    _check(
        checks,
        "action_chain_curator",
        curator_ok,
        "multi_agent runs require curator_agent report artifact_write; single_agent_by_user runs require rdc-debugger report artifact_write",
        path=action_chain if action_chain.is_file() else None,
    )
    skeptic_index = next(
        (
            idx
            for idx, event in enumerate(events)
            if str(event.get("agent_id", "")).strip() == "skeptic_agent"
            and str(event.get("event_type", "")).strip() in {"conflict_resolved", "counterfactual_reviewed", "quality_check"}
        ),
        -1,
    )
    curator_index = next(
        (
            idx
            for idx, event in enumerate(events)
            if str(event.get("agent_id", "")).strip() == ("rdc-debugger" if orchestration_mode == "single_agent_by_user" else "curator_agent")
            and str(event.get("event_type", "")).strip() == "artifact_write"
            and _path_ref_matches(_event_path(event), report_md)
        ),
        -1,
    )
    _check(
        checks,
        "skeptic_before_curator",
        curator_index < 0 or skeptic_index < 0 or skeptic_index < curator_index or orchestration_mode == "single_agent_by_user",
        "skeptic review must occur before curator final report artifact_write in multi_agent runs",
        path=action_chain if action_chain.is_file() else None,
    )
    _check(
        checks,
        "process_deviation_clear",
        not process_deviation_events,
        "finalization requires no unresolved process_deviation events in action_chain",
        path=action_chain if action_chain.is_file() else None,
        refs=[str(_event_payload(event).get("deviation_code") or "") for event in process_deviation_events][:8] or None,
    )

    report_text = "\n".join(_text(path) for path in (report_md, visual_report) if path.is_file())
    report_session_ids = _extract_matches(report_text, SESSION_RE)
    report_capture_ids = _extract_matches(report_text, CAPTURE_FILE_RE)
    report_events = _extract_matches(report_text, EVENT_RE)
    run_text = json.dumps(run_data, ensure_ascii=False)
    snapshot_text = json.dumps(snapshot, ensure_ascii=False)
    action_text = "\n".join(json.dumps(event, ensure_ascii=False) for event in events)
    _check(checks, "report_session_mapping", (not report_session_ids) or (session_id in report_session_ids), "report session_id references must map to the resolved session artifact", path=report_md if report_md.is_file() else None, refs=report_session_ids or None)
    _check(checks, "report_capture_mapping", (not report_capture_ids) or all(token in (run_text + snapshot_text + action_text) for token in report_capture_ids), "report capture_file_id references must map to run/session data", path=report_md if report_md.is_file() else None, refs=report_capture_ids or None)
    _check(checks, "report_event_mapping", (not report_events) or all((f"event:{eid}" in snapshot_text) or (f"event {eid}" in report_text.lower()) for eid in report_events), "report event references must map to the snapshot or event ledger", path=report_md if report_md.is_file() else None, refs=report_events or None)
    bug_refs = re.findall(r"BUG-[A-Z0-9-]+", report_text, re.IGNORECASE)
    _check(checks, "final_refs", bool(bug_refs) or bool(FINAL_VERDICT_RE.search(report_text)), "report must reference BugCard/BugFull or include DEBUGGER_FINAL_VERDICT", path=report_md if report_md.is_file() else None, refs=bug_refs or None)

    emit_issues: list[str] = []
    if all(item["result"] == "pass" for item in checks) and action_chain.is_file():
        try:
            _emit_candidates(root, run_data, snapshot, session_id or "", run_id, action_chain, events)
            events = _load_action_chain(action_chain)
        except Exception as exc:  # noqa: BLE001
            emit_issues.append(str(exc))
    _check(checks, "knowledge_candidates_emit", not emit_issues, "knowledge candidate emission must succeed when compliant run triggers it", path=action_chain if action_chain.is_file() else None, refs=emit_issues or None)

    return {
        "schema_version": RUN_COMPLIANCE_SCHEMA,
        "platform": platform,
        "run_root": _norm(run_root),
        "generated_by": "run_compliance_audit",
        "generated_at": _now_iso(),
        "status": "passed" if all(item["result"] == "pass" for item in checks) else "failed",
        "session_id": session_id or "",
        "degraded_reasons": sorted(reason for reason in degraded_reasons if reason in DEGRADED_REASONS),
        "checks": checks,
        "summary": {
            "passed": sum(1 for item in checks if item["result"] == "pass"),
            "failed": sum(1 for item in checks if item["result"] == "fail"),
        },
        "metrics": _metrics(events, snapshot),
        "paths": {
            "case_yaml": _norm(case_yaml),
            "case_input": _norm(case_input),
            "entry_gate": _norm(entry_gate),
            "captures_manifest": _norm(captures_manifest),
            "references_manifest": _norm(references_manifest),
            "run_yaml": _norm(run_yaml),
            "capture_refs": _norm(capture_refs),
            "fix_verification": _norm(fix_verification),
            "intake_gate": _norm(intake_gate),
            "runtime_topology": _norm(runtime_topology),
            "hypothesis_board": _norm(hypothesis_board),
            "session_evidence": _norm(session_evidence),
            "skeptic_signoff": _norm(skeptic_signoff),
            "action_chain": _norm(action_chain),
            "active_manifest": _norm(active_manifest),
            "report_md": _norm(report_md),
            "visual_report_html": _norm(visual_report),
        },
    }


def write_run_audit_artifact(root: Path, run_root: Path, platform: str) -> dict[str, Any]:
    payload = run_audit(root, run_root, platform)
    action_chain_path = Path(payload["paths"]["action_chain"])
    runtime_topology_path = run_root / "artifacts" / "runtime_topology.yaml"
    runtime_topology_data = _read_yaml(runtime_topology_path) if runtime_topology_path.is_file() else {}
    if not isinstance(runtime_topology_data, dict):
        runtime_topology_data = {}
    run_data = _read_yaml(run_root / "run.yaml") if (run_root / "run.yaml").is_file() else {}
    if not isinstance(run_data, dict):
        run_data = {}
    context_bindings = list(runtime_topology_data.get("context_bindings") or [])
    owners = list(runtime_topology_data.get("owners") or [])
    contexts = list(runtime_topology_data.get("contexts") or [])
    _append_event(
        action_chain_path,
        {
            "schema_version": ACTION_CHAIN_SCHEMA,
            "event_id": f"evt-audit-run-compliance-{payload['status']}",
            "ts_ms": _now_ms(),
            "run_id": str(run_data.get("run_id", "")).strip(),
            "session_id": payload["session_id"],
            "agent_id": "rdc-debugger",
            "event_type": "quality_check",
            "status": "pass" if payload["status"] == "passed" else "fail",
            "duration_ms": 0,
            "refs": [],
            "payload": {
                "validator": "run_compliance_audit",
                "summary": f"run compliance audit {payload['status']}",
                "path": _norm(run_root / "artifacts" / "run_compliance.yaml"),
                "entry_mode": str(runtime_topology_data.get("entry_mode", "cli")).strip() or "cli",
                "backend": str(runtime_topology_data.get("backend", "local")).strip() or "local",
                "context_id": str((contexts or ["default"])[0]),
                "runtime_owner": str((owners or ["rdc-debugger"])[0]),
                "baton_ref": "",
                "context_binding_id": str(((context_bindings or [{}])[0].get("context_binding_id") or "ctxbind-default")),
                "capture_ref": str(((context_bindings or [{}])[0].get("capture_ref") or "")),
                "canonical_anchor_ref": str(((context_bindings or [{}])[0].get("canonical_anchor_ref") or "")),
                "delegation_status": str(runtime_topology_data.get("delegation_status", "none")).strip() or "none",
                "fallback_execution_mode": str(runtime_topology_data.get("fallback_execution_mode", "wrapper")).strip() or "wrapper",
                "degraded_reasons": list(runtime_topology_data.get("degraded_reasons") or []),
            },
        },
    )
    _dump_yaml(run_root / "artifacts" / "run_compliance.yaml", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit debugger run compliance")
    parser.add_argument("--platform", required=False, help="platform key")
    parser.add_argument("--run-root", type=Path, default=None, help="workspace run root")
    parser.add_argument("--root", type=Path, default=None, help="debugger root override")
    parser.add_argument("--strict", action="store_true", help="return non-zero on failure")
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

