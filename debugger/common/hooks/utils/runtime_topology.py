#!/usr/bin/env python3
"""Run-level runtime topology artifact builder."""

from __future__ import annotations

import argparse
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


RUNTIME_TOPOLOGY_SCHEMA = "2"
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.-]+")
ACTION_SPECIALISTS = {
    "triage_agent",
    "capture_repro_agent",
    "pass_graph_pipeline_agent",
    "pixel_forensics_agent",
    "shader_ir_agent",
    "driver_device_agent",
}
DELEGATION_STATUSES = {"native_dispatch", "single_agent_by_user", "none"}
FALLBACK_EXECUTION_MODES = {"wrapper", "local_renderdoc_python"}
DEGRADED_REASONS = {
    "WRAPPER_DEGRADED_LOCAL_DIRECT",
}


def _debugger_root(default: Path | None = None) -> Path:
    return default.resolve() if default else Path(__file__).resolve().parents[3]


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _norm(path: Path) -> str:
    return str(path).replace("\\", "/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_action_chain(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _read_text(path).splitlines():
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _extract_session_id(run_data: dict[str, Any], session_marker: Path) -> str:
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
    return ""


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return dict(payload) if isinstance(payload, dict) else {}


def _payload_str(event: dict[str, Any], key: str) -> str:
    return str(_payload(event).get(key) or "").strip()


def _payload_list(event: dict[str, Any], key: str) -> list[str]:
    value = _payload(event).get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _mode_key(entry_mode: str, backend: str) -> str:
    if backend == "remote":
        return "remote_mcp" if entry_mode == "mcp" else "remote_daemon"
    return "local_mcp" if entry_mode == "mcp" else "local_cli"


def _safe_token(value: str, fallback: str = "default") -> str:
    text = _SAFE_TOKEN_RE.sub("-", str(value or "").strip()).strip("-._")
    return text or fallback


def _read_capture_ref_paths(case_root: Path, run_root: Path) -> dict[str, str]:
    capture_refs_path = run_root / "capture_refs.yaml"
    capture_refs = _read_yaml(capture_refs_path) if capture_refs_path.is_file() else {}
    if not isinstance(capture_refs, dict):
        capture_refs = {}
    mapping: dict[str, str] = {}
    for item in capture_refs.get("captures") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("capture_role") or item.get("role") or "").strip()
        file_name = str(item.get("file_name") or "").strip()
        capture_id = str(item.get("capture_id") or "").strip()
        if not file_name:
            continue
        path = case_root / "inputs" / "captures" / file_name
        if role:
            mapping[f"capture:{role}"] = _norm(path)
        if capture_id:
            mapping[f"capture_id:{capture_id}"] = _norm(path)
    return mapping


def _has_passed_intake_gate(events: list[dict[str, Any]]) -> bool:
    for event in events:
        if str(event.get("event_type") or "").strip() != "quality_check":
            continue
        if str(event.get("status") or "").strip() != "pass":
            continue
        if _payload_str(event, "validator") == "intake_gate":
            return True
    return False


def _runtime_delegation_summary(
    events: list[dict[str, Any]],
    *,
    backend: str,
    orchestration_mode: str,
) -> tuple[str, str, list[str], list[str]]:
    degraded_reasons: set[str] = set()
    native_dispatch = False
    fallback_execution_mode = "wrapper"
    issues: list[str] = []

    for event in events:
        event_type = str(event.get("event_type") or "").strip()
        agent_id = str(event.get("agent_id") or "").strip()
        payload = _payload(event)
        delegation_status = str(payload.get("delegation_status") or "").strip()
        if delegation_status:
            if delegation_status not in DELEGATION_STATUSES:
                issues.append(f"invalid delegation_status in action_chain: {delegation_status}")
            if delegation_status == "native_dispatch":
                native_dispatch = True
            elif delegation_status == "single_agent_by_user" and orchestration_mode != "single_agent_by_user":
                issues.append("single_agent_by_user delegation_status requires orchestration_mode=single_agent_by_user")
        fallback_mode = str(payload.get("fallback_execution_mode") or "").strip()
        if fallback_mode:
            if fallback_mode not in FALLBACK_EXECUTION_MODES:
                issues.append(f"invalid fallback_execution_mode in action_chain: {fallback_mode}")
            elif fallback_mode == "local_renderdoc_python":
                fallback_execution_mode = fallback_mode
        for reason in _payload_list(event, "degraded_reasons"):
            if reason not in DEGRADED_REASONS:
                issues.append(f"invalid degraded_reason in action_chain: {reason}")
                continue
            degraded_reasons.add(reason)
        target_agent = str(payload.get("target_agent") or "").strip()
        if event_type == "dispatch" and agent_id == "rdc-debugger" and target_agent in ACTION_SPECIALISTS:
            native_dispatch = True
        if event_type == "tool_execution" and agent_id in ACTION_SPECIALISTS:
            native_dispatch = True
    if orchestration_mode == "single_agent_by_user":
        delegation_status = "single_agent_by_user"
        if native_dispatch:
            issues.append("single_agent_by_user runs must not dispatch specialist agents")
    elif native_dispatch:
        delegation_status = "native_dispatch"
    else:
        delegation_status = "none"

    if fallback_execution_mode == "local_renderdoc_python":
        degraded_reasons.add("WRAPPER_DEGRADED_LOCAL_DIRECT")
        if backend != "local":
            issues.append("local_renderdoc_python fallback is only allowed for local backend")

    return delegation_status, fallback_execution_mode, sorted(degraded_reasons), issues


def _context_bindings(events: list[dict[str, Any]], *, run_data: dict[str, Any], case_root: Path, run_root: Path) -> list[dict[str, Any]]:
    runtime_data = run_data.get("runtime") if isinstance(run_data.get("runtime"), dict) else {}
    capture_ref_paths = _read_capture_ref_paths(case_root, run_root)
    bindings: dict[str, dict[str, Any]] = {}

    def ensure_binding(context_id: str) -> dict[str, Any]:
        binding = bindings.get(context_id)
        if isinstance(binding, dict):
            return binding
        run_session_id = str(runtime_data.get("session_id") or run_data.get("session_id") or "").strip()
        binding = {
            "context_binding_id": f"ctxbind-{_safe_token(context_id)}",
            "context_id": context_id,
            "owner_agent": str(runtime_data.get("runtime_owner") or run_data.get("runtime_owner") or "rdc-debugger").strip(),
            "capture_ref": "",
            "session_locator": {
                "session_id": run_session_id,
                "frame_index": _as_int(runtime_data.get("frame_index"), 0),
                "active_event_id": _as_int(runtime_data.get("active_event_id"), 0),
                "rdc_path": "",
            },
            "canonical_anchor_ref": "",
            "task_scope": "",
            "baton_refs": [],
            "status": "planned",
        }
        bindings[context_id] = binding
        return binding

    for event in events:
        payload = _payload(event)
        context_id = str(payload.get("context_id") or "").strip()
        if not context_id:
            continue
        binding = ensure_binding(context_id)
        owner_agent = str(payload.get("runtime_owner") or event.get("agent_id") or "").strip()
        if owner_agent:
            binding["owner_agent"] = owner_agent
        capture_ref = str(payload.get("capture_ref") or binding.get("capture_ref") or "").strip()
        if capture_ref:
            binding["capture_ref"] = capture_ref
        canonical_anchor_ref = str(payload.get("canonical_anchor_ref") or binding.get("canonical_anchor_ref") or "").strip()
        if canonical_anchor_ref:
            binding["canonical_anchor_ref"] = canonical_anchor_ref
        baton_ref = str(payload.get("baton_ref") or "").strip()
        if baton_ref and baton_ref not in binding["baton_refs"]:
            binding["baton_refs"].append(baton_ref)
        locator = dict(binding.get("session_locator") or {})
        locator["session_id"] = str(payload.get("session_id") or locator.get("session_id") or runtime_data.get("session_id") or run_data.get("session_id") or "").strip()
        locator["frame_index"] = _as_int(payload.get("frame_index"), _as_int(locator.get("frame_index"), 0))
        locator["active_event_id"] = _as_int(payload.get("active_event_id"), _as_int(locator.get("active_event_id"), 0))
        locator["rdc_path"] = str(payload.get("rdc_path") or locator.get("rdc_path") or capture_ref_paths.get(capture_ref, "") or "").strip()
        binding["session_locator"] = locator
        task_scope = str(payload.get("task_scope") or payload.get("objective") or payload.get("summary") or payload.get("tool_name") or binding.get("task_scope") or "").strip()
        if task_scope:
            binding["task_scope"] = task_scope
        event_type = str(event.get("event_type") or "").strip()
        if event_type == "tool_execution":
            binding["status"] = "active"
        elif event_type == "dispatch" and binding["status"] == "planned":
            binding["status"] = "dispatched"
        elif event_type == "artifact_write" and binding["status"] == "planned":
            binding["status"] = "captured"

    if not bindings:
        default_context_id = str(runtime_data.get("context_id") or run_data.get("context_id") or "default").strip() or "default"
        ensure_binding(default_context_id)

    return [bindings[key] for key in sorted(bindings)]


def build_runtime_topology_payload(root: Path, run_root: Path, platform: str | None = None) -> dict[str, Any]:
    run_yaml = run_root / "run.yaml"
    run_data = _read_yaml(run_yaml) if run_yaml.is_file() else {}
    if not isinstance(run_data, dict):
        run_data = {}
    case_root = run_root.parent.parent
    entry_gate = case_root / "artifacts" / "entry_gate.yaml"
    entry_data = _read_yaml(entry_gate) if entry_gate.is_file() else {}
    if not isinstance(entry_data, dict):
        entry_data = {}
    platform_caps_path = root / "common" / "config" / "platform_capabilities.json"
    runtime_truth_path = root / "common" / "config" / "runtime_mode_truth.snapshot.json"
    platform_caps = _read_json(platform_caps_path) if platform_caps_path.is_file() else {"platforms": {}}
    runtime_truth = _read_json(runtime_truth_path) if runtime_truth_path.is_file() else {"modes": {}}
    session_marker = root / "common" / "knowledge" / "library" / "sessions" / ".current_session"
    session_id = _extract_session_id(run_data, session_marker)
    action_chain = (
        root / "common" / "knowledge" / "library" / "sessions" / session_id / "action_chain.jsonl"
        if session_id
        else root / "common" / "knowledge" / "library" / "sessions" / "action_chain.jsonl"
    )
    events = _load_action_chain(action_chain) if action_chain.is_file() else []
    entry_mode = str(entry_data.get("entry_mode") or (run_data.get("debug") or {}).get("entry_mode") or "cli").strip()
    backend = str(entry_data.get("backend") or (run_data.get("runtime") or {}).get("backend") or "local").strip()
    coordination_mode = str(run_data.get("coordination_mode") or (run_data.get("runtime") or {}).get("coordination_mode") or "").strip()
    platform_key = str(platform or run_data.get("platform") or "").strip()
    platform_row = dict(((platform_caps.get("platforms") or {}).get(platform_key) or {}))
    orchestration_mode = str(
        entry_data.get("orchestration_mode")
        or (run_data.get("runtime") or {}).get("orchestration_mode")
        or "multi_agent"
    ).strip()
    single_agent_reason = str(
        entry_data.get("single_agent_reason")
        or (run_data.get("runtime") or {}).get("single_agent_reason")
        or ""
    ).strip()
    sub_agent_mode = str(platform_row.get("sub_agent_mode") or "").strip()
    peer_communication = str(platform_row.get("peer_communication") or "").strip()
    agent_description_mode = str(platform_row.get("agent_description_mode") or "").strip()
    dispatch_topology = str(platform_row.get("dispatch_topology") or "").strip()
    specialist_dispatch_requirement = str(platform_row.get("specialist_dispatch_requirement") or "").strip()
    host_delegation_policy = str(platform_row.get("host_delegation_policy") or "").strip()
    host_delegation_fallback = str(platform_row.get("host_delegation_fallback") or "").strip()
    local_live_runtime_policy = str(platform_row.get("local_live_runtime_policy") or "").strip()
    remote_live_runtime_policy = str(platform_row.get("remote_live_runtime_policy") or "").strip()
    mode_key = _mode_key(entry_mode, backend)
    mode_truth = dict(((runtime_truth.get("modes") or {}).get(mode_key) or {}))
    runtime_parallelism_ceiling = str(mode_truth.get("runtime_parallelism_ceiling") or "").strip()
    applied_live_runtime_policy = remote_live_runtime_policy if backend == "remote" else local_live_runtime_policy
    delegation_status, fallback_execution_mode, degraded_reasons, degradation_issues = _runtime_delegation_summary(
        events,
        backend=backend,
        orchestration_mode=orchestration_mode,
    )
    context_bindings = _context_bindings(events, run_data=run_data, case_root=case_root, run_root=run_root)
    contexts = [str(item.get("context_id") or "").strip() for item in context_bindings if str(item.get("context_id") or "").strip()]
    owners = sorted({str(item.get("owner_agent") or "").strip() for item in context_bindings if str(item.get("owner_agent") or "").strip()})
    baton_refs = sorted({ref for item in context_bindings for ref in (item.get("baton_refs") or []) if str(ref).strip()})
    checks = [
        {"id": "entry_mode", "result": "pass" if entry_mode in {"cli", "mcp"} else "fail", "detail": "entry_mode must be cli or mcp"},
        {"id": "backend", "result": "pass" if backend in {"local", "remote"} else "fail", "detail": "backend must be local or remote"},
        {"id": "coordination_mode", "result": "pass" if bool(coordination_mode) else "fail", "detail": "coordination_mode must be recorded in run.yaml"},
        {"id": "platform_contract", "result": "pass" if bool(platform_row) else "fail", "detail": "platform_capabilities.json must define the platform agentic profile"},
        {
            "id": "delegation_contract_surface",
            "result": "pass" if specialist_dispatch_requirement in {"required"} and host_delegation_policy in {"platform_managed"} and host_delegation_fallback in {"native", "none"} else "fail",
            "detail": "platform_capabilities.json must declare specialist dispatch and host delegation fallback semantics",
        },
        {
            "id": "orchestration_mode",
            "result": "pass" if orchestration_mode in {"multi_agent", "single_agent_by_user"} else "fail",
            "detail": "orchestration_mode must be multi_agent or single_agent_by_user",
        },
        {
            "id": "single_agent_reason",
            "result": "pass" if orchestration_mode == "multi_agent" or single_agent_reason == "user_requested" else "fail",
            "detail": "single_agent_by_user requires single_agent_reason=user_requested",
        },
        {"id": "runtime_mode_truth", "result": "pass" if bool(mode_truth) and bool(runtime_parallelism_ceiling) else "fail", "detail": "runtime_mode_truth.snapshot.json must define runtime_parallelism_ceiling for the selected mode"},
        {"id": "applied_live_runtime_policy", "result": "pass" if bool(applied_live_runtime_policy) else "fail", "detail": "platform_capabilities.json must define the applied live runtime policy for this backend"},
        {"id": "context_bindings", "result": "pass" if bool(context_bindings) else "fail", "detail": "runtime topology must contain at least one context binding", "refs": contexts[:8] or None},
        {
            "id": "delegation_execution_contract",
            "result": "pass" if not degradation_issues else "fail",
            "detail": "runtime topology must normalize orchestration mode and direct-runtime fallback semantics",
            "refs": degradation_issues[:8] or None,
        },
    ]
    status = "passed" if all(item["result"] == "pass" for item in checks) else "failed"
    return {
        "schema_version": RUNTIME_TOPOLOGY_SCHEMA,
        "generated_by": "runtime_topology",
        "generated_at": _now_iso(),
        "status": status,
        "platform": platform_key,
        "run_id": str(run_data.get("run_id") or "").strip(),
        "session_id": session_id,
        "coordination_mode": coordination_mode,
        "orchestration_mode": orchestration_mode,
        "single_agent_reason": single_agent_reason,
        "sub_agent_mode": sub_agent_mode,
        "peer_communication": peer_communication,
        "agent_description_mode": agent_description_mode,
        "dispatch_topology": dispatch_topology,
        "specialist_dispatch_requirement": specialist_dispatch_requirement,
        "host_delegation_policy": host_delegation_policy,
        "host_delegation_fallback": host_delegation_fallback,
        "entry_mode": entry_mode,
        "backend": backend,
        "runtime_parallelism_ceiling": runtime_parallelism_ceiling,
        "applied_live_runtime_policy": applied_live_runtime_policy,
        "delegation_status": delegation_status,
        "fallback_execution_mode": fallback_execution_mode,
        "degraded_reasons": degraded_reasons,
        "contexts": contexts,
        "context_bindings": context_bindings,
        "owners": owners,
        "baton_refs": baton_refs,
        "checks": checks,
        "paths": {
            "entry_gate": _norm(entry_gate),
            "action_chain": _norm(action_chain),
            "platform_capabilities": _norm(platform_caps_path),
            "runtime_mode_truth": _norm(runtime_truth_path),
            "run_root": _norm(run_root),
        },
    }


def _dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def run_runtime_topology(root: Path, run_root: Path, platform: str | None = None) -> dict[str, Any]:
    payload = build_runtime_topology_payload(root, run_root, platform=platform)
    _dump_yaml(run_root / "artifacts" / "runtime_topology.yaml", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build debugger runtime topology artifact")
    parser.add_argument("--run-root", type=Path, required=True, help="workspace run root")
    parser.add_argument("--platform", default=None, help="platform key override")
    parser.add_argument("--root", type=Path, default=None, help="debugger root override")
    parser.add_argument("--strict", action="store_true", help="return non-zero on failed topology")
    args = parser.parse_args()

    payload = run_runtime_topology(_debugger_root(args.root), args.run_root.resolve(), platform=args.platform)
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), end="")
    if args.strict and payload["status"] != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
