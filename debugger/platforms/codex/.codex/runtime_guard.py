#!/usr/bin/env python3
"""Codex workspace-native runtime guard for validator-driven enforcement."""

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
    print("missing dependency 'PyYAML'", file=sys.stderr)
    raise SystemExit(2)


def _platform_root(default: Path | None = None) -> Path:
    return default.resolve() if default else Path(__file__).resolve().parents[1]


def _shared_debugger_root() -> Path:
    for candidate in (_platform_root(), *_platform_root().parents):
        common_root = candidate / "common" / "hooks" / "utils" / "entry_gate.py"
        if common_root.is_file():
            return candidate
    raise FileNotFoundError("unable to resolve shared debugger root for Codex runtime guard")


SHARED_DEBUGGER_ROOT = _shared_debugger_root()
COMMON_UTILS = SHARED_DEBUGGER_ROOT / "common" / "hooks" / "utils"
COMMON_VALIDATORS = SHARED_DEBUGGER_ROOT / "common" / "hooks" / "validators"
COMMON_CONFIG = SHARED_DEBUGGER_ROOT / "common" / "config"
for path in (COMMON_UTILS, COMMON_VALIDATORS, COMMON_CONFIG):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from entry_gate import run_entry_gate as shared_run_entry_gate  # noqa: E402
from hypothesis_board_validator import validate_hypothesis_board  # noqa: E402
from intake_gate import build_intake_gate_payload, run_intake_gate as shared_run_intake_gate  # noqa: E402
from run_compliance_audit import (  # noqa: E402
    ACTION_CHAIN_SCHEMA,
    ACTION_SPECIALISTS,
    load_action_chain_events,
    specialist_handoff_path_ok,
    workflow_stage_overreach_issues,
    write_run_audit_artifact,
)
from runtime_topology import (  # noqa: E402
    build_runtime_topology_payload,
    run_runtime_topology as shared_run_runtime_topology,
)
from validate_binding import validate_binding  # noqa: E402
from validate_tool_contract_runtime import validate_runtime_tool_contract  # noqa: E402


GUARD_SCHEMA = "1"
QUALITY_CHECK_EVENT_TYPE = "quality_check"
PROCESS_DEVIATION_EVENT_TYPE = "process_deviation"
DISPATCH_FEEDBACK_EVENT_TYPES = {
    "artifact_write",
    "quality_check",
    "counterfactual_reviewed",
    "conflict_resolved",
}


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _norm(path: Path) -> str:
    return str(path).replace("\\", "/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _status_ok(value: str) -> bool:
    return str(value or "").strip() in {"passed", "ready", "not_applicable"}


def _extract_session_id(root: Path, run_root: Path) -> str:
    run_yaml = run_root / "run.yaml"
    run_data = _read_yaml(run_yaml) if run_yaml.is_file() else {}
    if not isinstance(run_data, dict):
        run_data = {}
    for value in (
        run_data.get("session_id"),
        (run_data.get("debug") or {}).get("session_id") if isinstance(run_data.get("debug"), dict) else None,
        (run_data.get("runtime") or {}).get("session_id") if isinstance(run_data.get("runtime"), dict) else None,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    session_marker = root / "common" / "knowledge" / "library" / "sessions" / ".current_session"
    if session_marker.is_file():
        value = session_marker.read_text(encoding="utf-8").lstrip("\ufeff").strip()
        if value and value != "session-unset":
            return value
    return ""


def _action_chain_path(root: Path, run_root: Path) -> Path:
    session_id = _extract_session_id(root, run_root)
    sessions_root = root / "common" / "knowledge" / "library" / "sessions"
    if session_id:
        return sessions_root / session_id / "action_chain.jsonl"
    return sessions_root / "action_chain.jsonl"


def _action_chain_events(root: Path, run_root: Path) -> list[dict[str, Any]]:
    path = _action_chain_path(root, run_root)
    return load_action_chain_events(path) if path.is_file() else []


def _append_event(path: Path, event: dict[str, Any]) -> None:
    serialized = json.dumps(event, ensure_ascii=False)
    existing = _read_text(path) if path.exists() else ""
    if serialized in existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(serialized)
        handle.write("\n")


def _runtime_fields(run_root: Path) -> dict[str, str]:
    topology_path = run_root / "artifacts" / "runtime_topology.yaml"
    topology = _read_yaml(topology_path) if topology_path.is_file() else {}
    if not isinstance(topology, dict):
        topology = {}
    bindings = list(topology.get("context_bindings") or [])
    first_binding = bindings[0] if bindings else {}
    contexts = list(topology.get("contexts") or [])
    owners = list(topology.get("owners") or [])
    return {
        "entry_mode": str(topology.get("entry_mode") or "cli").strip() or "cli",
        "backend": str(topology.get("backend") or "local").strip() or "local",
        "context_id": str((contexts or ["default"])[0]),
        "runtime_owner": str((owners or ["rdc-debugger"])[0]),
        "baton_ref": "",
        "context_binding_id": str(first_binding.get("context_binding_id") or "ctxbind-default"),
        "capture_ref": str(first_binding.get("capture_ref") or ""),
        "canonical_anchor_ref": str(first_binding.get("canonical_anchor_ref") or ""),
    }


def _run_id(run_root: Path) -> str:
    run_yaml = run_root / "run.yaml"
    if not run_yaml.is_file():
        return run_root.name
    data = _read_yaml(run_yaml)
    if not isinstance(data, dict):
        return run_root.name
    return str(data.get("run_id") or run_root.name).strip() or run_root.name


def _write_guard_artifact(run_root: Path, artifact_name: str, payload: dict[str, Any]) -> Path:
    path = run_root / "artifacts" / artifact_name
    _dump_yaml(path, payload)
    return path


def _guard_payload(
    *,
    stage: str,
    status: str,
    blockers: list[dict[str, Any]],
    refs: list[str] | None = None,
    paths: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": GUARD_SCHEMA,
        "generated_by": "codex_runtime_guard",
        "generated_at": _now_iso(),
        "guard_stage": stage,
        "status": status,
        "blocking_codes": [str(item.get("code") or "").strip() for item in blockers if str(item.get("code") or "").strip()],
        "blockers": blockers,
        **({"refs": refs} if refs else {}),
        **({"paths": paths} if paths else {}),
        **(extra or {}),
    }


def _emit_quality_check(root: Path, run_root: Path, *, stage: str, payload: dict[str, Any], artifact_path: Path) -> None:
    action_chain = _action_chain_path(root, run_root)
    runtime = _runtime_fields(run_root)
    _append_event(
        action_chain,
        {
            "schema_version": ACTION_CHAIN_SCHEMA,
            "event_id": f"evt-codex-runtime-guard-{stage}-{payload['status']}-{_now_ms()}",
            "ts_ms": _now_ms(),
            "run_id": _run_id(run_root),
            "session_id": _extract_session_id(root, run_root),
            "agent_id": "rdc-debugger",
            "event_type": QUALITY_CHECK_EVENT_TYPE,
            "status": "pass" if payload["status"] == "passed" else "fail",
            "duration_ms": 0,
            "refs": [],
            "payload": {
                "validator": "codex_runtime_guard",
                "guard_stage": stage,
                "summary": f"codex runtime guard {stage} {payload['status']}",
                "path": _norm(artifact_path),
                "blocking_codes": list(payload.get("blocking_codes") or []),
                **runtime,
            },
        },
    )


def _emit_process_deviation(
    root: Path,
    run_root: Path,
    *,
    deviation_code: str,
    summary: str,
    refs: list[str],
    artifact_path: Path,
) -> None:
    action_chain = _action_chain_path(root, run_root)
    runtime = _runtime_fields(run_root)
    _append_event(
        action_chain,
        {
            "schema_version": ACTION_CHAIN_SCHEMA,
            "event_id": f"evt-codex-process-deviation-{_now_ms()}",
            "ts_ms": _now_ms(),
            "run_id": _run_id(run_root),
            "session_id": _extract_session_id(root, run_root),
            "agent_id": "rdc-debugger",
            "event_type": PROCESS_DEVIATION_EVENT_TYPE,
            "status": "blocked",
            "duration_ms": 0,
            "refs": refs,
            "payload": {
                "deviation_code": deviation_code,
                "summary": summary,
                "path": _norm(artifact_path),
                **runtime,
            },
        },
    )


def _flatten_tool_contract_findings(root: Path) -> list[str]:
    try:
        findings = validate_runtime_tool_contract(root)
    except Exception as exc:  # noqa: BLE001
        return [str(exc)]
    rows: list[str] = []
    for path, tools in sorted(findings.unknown_tools.items()):
        rows.append(f"{path}: {', '.join(sorted(tools))}")
    rows.extend(findings.missing_prerequisite_examples)
    rows.extend(findings.banned_snippets)
    return rows


def run_preflight(root: Path, *, case_root: Path | None = None) -> dict[str, Any]:
    binding_findings = validate_binding(root)
    tool_contract_findings = _flatten_tool_contract_findings(root)
    blockers: list[dict[str, Any]] = []
    if binding_findings or tool_contract_findings:
        blockers.append(
            {
                "code": "BLOCKED_BINDING_NOT_READY",
                "reason": "binding validation and runtime tool contract must pass before Codex can enter debugger flow",
                "refs": (binding_findings + tool_contract_findings)[:20],
            }
        )
    payload = _guard_payload(
        stage="preflight",
        status="passed" if not blockers else "blocked",
        blockers=blockers,
        paths={"root": _norm(root), **({"case_root": _norm(case_root)} if case_root else {})},
        extra={
            "checks": {
                "binding_validation": "passed" if not binding_findings else "failed",
                "runtime_tool_contract": "passed" if not tool_contract_findings else "failed",
            }
        },
    )
    if case_root:
        artifact_path = case_root / "artifacts" / "codex_preflight.yaml"
        _dump_yaml(artifact_path, payload)
    return payload


def run_entry_gate(
    root: Path,
    case_root: Path,
    *,
    platform: str,
    entry_mode: str,
    backend: str,
    capture_paths: list[str] | None = None,
    mcp_configured: bool = False,
    remote_transport: str = "",
    single_agent_requested: bool = False,
) -> dict[str, Any]:
    return shared_run_entry_gate(
        root,
        case_root.resolve(),
        platform=platform,
        entry_mode=entry_mode,
        backend=backend,
        capture_paths=capture_paths,
        mcp_configured=mcp_configured,
        remote_transport=remote_transport,
        single_agent_requested=single_agent_requested,
    )


def run_intake_gate(root: Path, run_root: Path) -> dict[str, Any]:
    return shared_run_intake_gate(root, run_root.resolve())


def run_runtime_topology(root: Path, run_root: Path, *, platform: str) -> dict[str, Any]:
    run_root = run_root.resolve()
    payload = shared_run_runtime_topology(root, run_root, platform=platform)
    if not _status_ok(str(payload.get("status") or "")):
        _emit_quality_check(
            root,
            run_root,
            stage="runtime-topology",
            payload=_guard_payload(
                stage="runtime_topology",
                status="blocked",
                blockers=[
                    {
                        "code": "BLOCKED_RUNTIME_TOPOLOGY_FAILED",
                        "reason": "shared runtime_topology failed",
                        "refs": [
                            str(item.get("id") or "").strip()
                            for item in payload.get("checks", [])
                            if item.get("result") != "pass" and str(item.get("id") or "").strip()
                        ][:12],
                    }
                ],
                paths={"runtime_topology": _norm(run_root / "artifacts" / "runtime_topology.yaml")},
            ),
            artifact_path=run_root / "artifacts" / "runtime_topology.yaml",
        )
    return payload


def run_final_audit(root: Path, run_root: Path, *, platform: str) -> dict[str, Any]:
    return write_run_audit_artifact(root, run_root.resolve(), platform)


def run_dispatch_readiness(root: Path, run_root: Path, *, platform: str) -> dict[str, Any]:
    run_root = run_root.resolve()
    case_root = run_root.parent.parent
    entry_gate_path = case_root / "artifacts" / "entry_gate.yaml"
    intake_gate_path = run_root / "artifacts" / "intake_gate.yaml"
    topology_path = run_root / "artifacts" / "runtime_topology.yaml"
    hypothesis_board_path = run_root / "notes" / "hypothesis_board.yaml"

    entry_gate = _read_yaml(entry_gate_path) if entry_gate_path.is_file() else {}
    intake_gate = _read_yaml(intake_gate_path) if intake_gate_path.is_file() else {}
    runtime_topology = _read_yaml(topology_path) if topology_path.is_file() else {}
    hypothesis_board = _read_yaml(hypothesis_board_path) if hypothesis_board_path.is_file() else {}
    entry_gate = entry_gate if isinstance(entry_gate, dict) else {}
    intake_gate = intake_gate if isinstance(intake_gate, dict) else {}
    runtime_topology = runtime_topology if isinstance(runtime_topology, dict) else {}
    hypothesis_board = hypothesis_board if isinstance(hypothesis_board, dict) else {}

    blockers: list[dict[str, Any]] = []
    refs: list[str] = []

    if str(entry_gate.get("status") or "").strip() != "passed":
        blockers.append(
            {
                "code": "BLOCKED_REQUIRED_ARTIFACT_MISSING",
                "reason": "artifacts/entry_gate.yaml must exist and be passed before specialist dispatch",
                "refs": [_norm(entry_gate_path)],
            }
        )
    recomputed_intake = build_intake_gate_payload(root, run_root)
    intake_failures = [item for item in recomputed_intake.get("checks", []) if item.get("result") != "pass"]
    if str(intake_gate.get("status") or "").strip() != "passed" or intake_failures:
        blockers.append(
            {
                "code": "BLOCKED_INTAKE_GATE_REQUIRED",
                "reason": "artifacts/intake_gate.yaml must exist, be passed, and stay valid before specialist dispatch or live analysis",
                "refs": [
                    _norm(intake_gate_path),
                    *[str(item.get("id") or "").strip() for item in intake_failures if str(item.get("id") or "").strip()],
                ][:12],
            }
        )
    recomputed_topology = build_runtime_topology_payload(root, run_root, platform=platform)
    topology_failures = [item for item in recomputed_topology.get("checks", []) if item.get("result") != "pass"]
    if str(runtime_topology.get("status") or "").strip() != "passed" or topology_failures:
        blockers.append(
            {
                "code": "BLOCKED_RUNTIME_TOPOLOGY_REQUIRED",
                "reason": "artifacts/runtime_topology.yaml must exist, be passed, and stay valid before staged handoff",
                "refs": [
                    _norm(topology_path),
                    *[str(item.get("id") or "").strip() for item in topology_failures if str(item.get("id") or "").strip()],
                ][:12],
            }
        )
    board_issues = validate_hypothesis_board(hypothesis_board) if hypothesis_board else ["hypothesis_board missing"]
    if board_issues:
        blockers.append(
            {
                "code": "BLOCKED_REQUIRED_ARTIFACT_MISSING",
                "reason": "notes/hypothesis_board.yaml must exist and satisfy the shared schema before staged handoff",
                "refs": [_norm(hypothesis_board_path), *board_issues[:8]],
            }
        )
    orchestration_mode = str(
        runtime_topology.get("orchestration_mode")
        or recomputed_topology.get("orchestration_mode")
        or ""
    ).strip()
    if orchestration_mode == "single_agent_by_user":
        blockers.append(
            {
                "code": "BLOCKED_SINGLE_AGENT_MODE_NO_DISPATCH",
                "reason": "single_agent_by_user runs must not dispatch specialists",
            }
        )

    events = _action_chain_events(root, run_root)
    overreach = workflow_stage_overreach_issues(
        events,
        coordination_mode=str(recomputed_topology.get("coordination_mode") or runtime_topology.get("coordination_mode") or "staged_handoff"),
    )
    refs.extend(overreach)
    status = "passed"
    if overreach:
        status = "blocked"
        blockers = [
            {
                "code": "PROCESS_DEVIATION_MAIN_AGENT_OVERREACH",
                "reason": "rdc-debugger attempted live investigation while waiting_for_specialist_brief",
                "refs": overreach[:8],
            }
        ]
    elif blockers:
        status = "blocked"

    payload = _guard_payload(
        stage="dispatch_readiness",
        status=status,
        blockers=blockers,
        refs=refs[:12] or None,
        paths={
            "run_root": _norm(run_root),
            "entry_gate": _norm(entry_gate_path),
            "intake_gate": _norm(intake_gate_path),
            "runtime_topology": _norm(topology_path),
            "hypothesis_board": _norm(hypothesis_board_path),
            "action_chain": _norm(_action_chain_path(root, run_root)),
        },
        extra={
            "orchestration_mode": orchestration_mode,
            "recomputed_intake_status": str(recomputed_intake.get("status") or ""),
            "recomputed_runtime_topology_status": str(recomputed_topology.get("status") or ""),
        },
    )
    artifact_path = _write_guard_artifact(run_root, "codex_dispatch_readiness.yaml", payload)
    if overreach:
        _emit_process_deviation(
            root,
            run_root,
            deviation_code="PROCESS_DEVIATION_MAIN_AGENT_OVERREACH",
            summary="rdc-debugger attempted live investigation during waiting_for_specialist_brief",
            refs=overreach[:8],
            artifact_path=artifact_path,
        )
    elif blockers:
        _emit_quality_check(root, run_root, stage="dispatch-readiness", payload=payload, artifact_path=artifact_path)
    return payload


def run_specialist_feedback(
    root: Path,
    run_root: Path,
    *,
    timeout_seconds: int = 300,
    now_ms: int | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    topology_path = run_root / "artifacts" / "runtime_topology.yaml"
    runtime_topology = _read_yaml(topology_path) if topology_path.is_file() else {}
    runtime_topology = runtime_topology if isinstance(runtime_topology, dict) else {}
    blockers: list[dict[str, Any]] = []

    if str(runtime_topology.get("status") or "").strip() != "passed":
        blockers.append(
            {
                "code": "BLOCKED_RUNTIME_TOPOLOGY_REQUIRED",
                "reason": "specialist feedback guard requires a passed artifacts/runtime_topology.yaml",
                "refs": [_norm(topology_path)],
            }
        )

    events = _action_chain_events(root, run_root)
    now_value = int(now_ms if now_ms is not None else _now_ms())
    timeout_ms = int(timeout_seconds) * 1000
    pending: list[dict[str, Any]] = []

    for event in events:
        if str(event.get("agent_id") or "").strip() != "rdc-debugger":
            continue
        if str(event.get("event_type") or "").strip() != "dispatch":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        target_agent = str(payload.get("target_agent") or "").strip()
        if target_agent not in ACTION_SPECIALISTS:
            continue
        dispatch_ts = int(event.get("ts_ms") or 0)
        feedback = next(
            (
                candidate
                for candidate in events
                if int(candidate.get("ts_ms") or 0) >= dispatch_ts
                and str(candidate.get("agent_id") or "").strip() == target_agent
                and (
                    (
                        str(candidate.get("event_type") or "").strip() == "artifact_write"
                        and specialist_handoff_path_ok(str(((candidate.get("payload") or {}).get("path") or "")), run_root)
                    )
                    or str(candidate.get("event_type") or "").strip() in DISPATCH_FEEDBACK_EVENT_TYPES - {"artifact_write"}
                )
            ),
            None,
        )
        if feedback is not None:
            continue
        age_ms = now_value - dispatch_ts
        if age_ms > timeout_ms:
            pending.append(
                {
                    "target_agent": target_agent,
                    "dispatch_event_id": str(event.get("event_id") or "").strip() or "?",
                    "dispatch_ts_ms": dispatch_ts,
                    "age_ms": age_ms,
                }
            )

    if pending:
        blockers.append(
            {
                "code": "BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT",
                "reason": "a dispatched specialist exceeded the feedback budget without writing a handoff artifact or review event",
                "refs": [
                    f"{item['target_agent']}@{item['dispatch_event_id']} age_ms={item['age_ms']}"
                    for item in pending[:8]
                ],
            }
        )

    payload = _guard_payload(
        stage="specialist_feedback",
        status="passed" if not blockers else "blocked",
        blockers=blockers,
        paths={
            "run_root": _norm(run_root),
            "runtime_topology": _norm(topology_path),
            "action_chain": _norm(_action_chain_path(root, run_root)),
        },
        extra={
            "timeout_seconds": int(timeout_seconds),
            "now_ms": now_value,
            "pending_dispatches": pending,
        },
    )
    artifact_path = _write_guard_artifact(run_root, "codex_specialist_feedback.yaml", payload)
    if blockers:
        _emit_quality_check(root, run_root, stage="specialist-feedback", payload=payload, artifact_path=artifact_path)
    return payload


def _print_yaml(payload: dict[str, Any]) -> None:
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), end="")


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex validator-driven runtime guard")
    parser.add_argument("--root", type=Path, default=None, help="platform package root override")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="run binding and runtime tool contract preflight")
    preflight.add_argument("--case-root", type=Path, default=None, help="optional workspace case root for artifact output")

    entry = subparsers.add_parser("entry-gate", help="run shared entry gate")
    entry.add_argument("--case-root", type=Path, required=True)
    entry.add_argument("--platform", default="codex")
    entry.add_argument("--entry-mode", required=True, choices=("cli", "mcp"))
    entry.add_argument("--backend", required=True, choices=("local", "remote"))
    entry.add_argument("--capture-path", action="append", default=[])
    entry.add_argument("--mcp-configured", action="store_true")
    entry.add_argument("--remote-transport", default="")
    entry.add_argument("--single-agent-by-user", action="store_true")

    intake = subparsers.add_parser("intake-gate", help="run shared intake gate")
    intake.add_argument("--run-root", type=Path, required=True)

    dispatch = subparsers.add_parser("dispatch-readiness", help="validate Codex specialist dispatch preconditions")
    dispatch.add_argument("--run-root", type=Path, required=True)
    dispatch.add_argument("--platform", default="codex")

    feedback = subparsers.add_parser("specialist-feedback", help="check for specialist feedback timeout")
    feedback.add_argument("--run-root", type=Path, required=True)
    feedback.add_argument("--timeout-seconds", type=int, default=300)
    feedback.add_argument("--now-ms", type=int, default=None)

    topology = subparsers.add_parser("runtime-topology", help="run shared runtime topology builder")
    topology.add_argument("--run-root", type=Path, required=True)
    topology.add_argument("--platform", default="codex")

    final = subparsers.add_parser("final-audit", help="run shared final compliance audit")
    final.add_argument("--run-root", type=Path, required=True)
    final.add_argument("--platform", default="codex")

    args = parser.parse_args()
    root = _platform_root(args.root)

    try:
        if args.command == "preflight":
            payload = run_preflight(root, case_root=args.case_root.resolve() if args.case_root else None)
        elif args.command == "entry-gate":
            payload = run_entry_gate(
                root,
                args.case_root.resolve(),
                platform=str(args.platform or "codex").strip() or "codex",
                entry_mode=args.entry_mode,
                backend=args.backend,
                capture_paths=list(args.capture_path or []),
                mcp_configured=bool(args.mcp_configured),
                remote_transport=str(args.remote_transport or "").strip(),
                single_agent_requested=bool(args.single_agent_by_user),
            )
        elif args.command == "intake-gate":
            payload = run_intake_gate(root, args.run_root.resolve())
        elif args.command == "dispatch-readiness":
            payload = run_dispatch_readiness(root, args.run_root.resolve(), platform=str(args.platform or "codex").strip() or "codex")
        elif args.command == "specialist-feedback":
            payload = run_specialist_feedback(
                root,
                args.run_root.resolve(),
                timeout_seconds=int(args.timeout_seconds),
                now_ms=args.now_ms,
            )
        elif args.command == "runtime-topology":
            payload = run_runtime_topology(root, args.run_root.resolve(), platform=str(args.platform or "codex").strip() or "codex")
        elif args.command == "final-audit":
            payload = run_final_audit(root, args.run_root.resolve(), platform=str(args.platform or "codex").strip() or "codex")
        else:  # pragma: no cover
            raise ValueError(f"unknown command: {args.command}")
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 2

    _print_yaml(payload)
    if not _status_ok(str(payload.get("status") or "")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
