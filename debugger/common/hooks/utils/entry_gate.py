#!/usr/bin/env python3
"""Case-level entry gate for debugger platform/mode preflight."""

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


ENTRY_GATE_SCHEMA = "2"


def _debugger_root(default: Path | None = None) -> Path:
    return default.resolve() if default else Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _norm(path: Path) -> str:
    return str(path).replace("\\", "/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    detail: str,
    *,
    refs: list[str] | None = None,
    path: Path | None = None,
) -> None:
    checks.append(
        {
            "id": check_id,
            "result": "pass" if passed else "fail",
            "detail": detail,
            **({"refs": refs} if refs else {}),
            **({"path": _norm(path)} if path else {}),
        }
    )


def _mode_key(entry_mode: str, backend: str) -> str:
    normalized_entry = str(entry_mode or "").strip().lower()
    normalized_backend = str(backend or "").strip().lower()
    if normalized_backend == "remote":
        return "remote_mcp" if normalized_entry == "mcp" else "remote_daemon"
    return "local_mcp" if normalized_entry == "mcp" else "local_cli"


def _capture_candidates(paths: list[str]) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    for raw in paths:
        text = str(raw or "").strip()
        if not text:
            continue
        candidate = Path(text)
        if candidate.is_file() and candidate.suffix.lower() == ".rdc":
            valid.append(_norm(candidate.resolve()))
        else:
            invalid.append(text)
    return valid, invalid


def _blockers_from_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for item in checks:
        if item.get("result") == "pass":
            continue
        check_id = str(item.get("id") or "")
        if check_id == "capture_inputs":
            code = "BLOCKED_MISSING_CAPTURE"
        elif check_id == "fix_reference_status":
            code = "BLOCKED_MISSING_FIX_REFERENCE"
        elif check_id in {"mcp_preflight"}:
            code = "BLOCKED_ENTRY_PREFLIGHT"
        elif check_id in {"platform_known", "entry_mode_allowed", "backend_allowed", "platform_mode_support", "runtime_mode_truth", "platform_contract"}:
            code = "BLOCKED_PLATFORM_MODE_UNSUPPORTED"
        elif check_id == "remote_prerequisites":
            code = "BLOCKED_REMOTE_PREREQUISITE"
        else:
            continue
        blockers.append(
            {
                "code": code,
                "reason": str(item.get("detail") or ""),
                **({"refs": list(item.get("refs") or [])} if item.get("refs") else {}),
            }
        )
    return blockers


def build_entry_gate_payload(
    root: Path,
    case_root: Path,
    *,
    platform: str,
    entry_mode: str,
    backend: str,
    capture_paths: list[str] | None = None,
    mcp_configured: bool = False,
    remote_transport: str = "",
    fix_reference_status: str = "strict_ready",
) -> dict[str, Any]:
    platform_caps_path = root / "common" / "config" / "platform_capabilities.json"
    runtime_truth_path = root / "common" / "config" / "runtime_mode_truth.snapshot.json"
    platform_caps = _read_json(platform_caps_path)
    runtime_truth = _read_json(runtime_truth_path) if runtime_truth_path.is_file() else {"modes": {}}
    platforms = platform_caps.get("platforms") or {}
    platform_key = str(platform or "").strip()
    entry_mode_norm = str(entry_mode or "").strip().lower()
    backend_norm = str(backend or "").strip().lower()
    capture_paths = [str(item or "").strip() for item in (capture_paths or []) if str(item or "").strip()]
    valid_captures, invalid_captures = _capture_candidates(capture_paths)
    checks: list[dict[str, Any]] = []

    row = platforms.get(platform_key) if isinstance(platforms, dict) else None
    _check(checks, "platform_known", isinstance(row, dict), "platform must exist in platform_capabilities.json", refs=[platform_key] if platform_key else None, path=platform_caps_path)
    allowed_entry_modes = list((row or {}).get("supported_entry_modes") or (row or {}).get("allowed_entry_modes") or [])
    _check(
        checks,
        "entry_mode_allowed",
        entry_mode_norm in allowed_entry_modes,
        f"entry_mode must be one of {allowed_entry_modes or ['cli', 'mcp']}",
        refs=[entry_mode_norm] if entry_mode_norm else None,
        path=platform_caps_path,
    )
    supported_backends = list((row or {}).get("supported_backends") or ["local"])
    _check(
        checks,
        "backend_allowed",
        backend_norm in supported_backends,
        f"backend must be one of {supported_backends}",
        refs=[backend_norm] if backend_norm else None,
        path=platform_caps_path,
    )
    support_value = str((row or {}).get("remote_support" if backend_norm == "remote" else "local_support") or "unsupported").strip()
    _check(
        checks,
        "platform_mode_support",
        support_value != "unsupported",
        f"{backend_norm} support must not be unsupported for {platform_key}",
        refs=[support_value] if support_value else None,
        path=platform_caps_path,
    )
    _check(
        checks,
        "platform_contract",
        str((row or {}).get("coordination_mode") or "") == "staged_handoff"
        and str((row or {}).get("orchestration_mode") or "") == "multi_agent"
        and str((row or {}).get("live_runtime_policy") or "") == "single_runtime_single_context",
        "platform contract must be staged_handoff + multi_agent + single_runtime_single_context",
        path=platform_caps_path,
    )
    mode_key = _mode_key(entry_mode_norm, backend_norm)
    mode_truth = ((runtime_truth.get("modes") or {}).get(mode_key) or {}) if isinstance(runtime_truth, dict) else {}
    _check(
        checks,
        "runtime_mode_truth",
        isinstance(mode_truth, dict) and bool(mode_truth) and str(mode_truth.get("runtime_parallelism_ceiling") or "") == "single_runtime_single_context",
        f"runtime mode truth must define {mode_key} with single_runtime_single_context ceiling",
        refs=[mode_key],
        path=runtime_truth_path if runtime_truth_path.is_file() else None,
    )
    if entry_mode_norm == "mcp":
        _check(checks, "mcp_preflight", bool(mcp_configured), "MCP entry requires platform MCP server to be configured")
    else:
        _check(checks, "mcp_preflight", True, "CLI entry selected; MCP preflight not required")
    _check(
        checks,
        "capture_inputs",
        bool(valid_captures),
        "at least one accessible .rdc input path must be provided before accepted intake",
        refs=(valid_captures + invalid_captures)[:8] or None,
    )
    _check(
        checks,
        "fix_reference_status",
        str(fix_reference_status or "").strip() == "strict_ready",
        "fix reference must be strict_ready before accepted intake",
        refs=[str(fix_reference_status or "").strip()] if str(fix_reference_status or "").strip() else None,
    )
    if backend_norm == "remote":
        _check(
            checks,
            "remote_prerequisites",
            bool(str(remote_transport or "").strip()),
            "remote entry requires an explicit remote transport",
            refs=[str(remote_transport or "").strip()] if str(remote_transport or "").strip() else None,
        )
    else:
        _check(checks, "remote_prerequisites", True, "local backend selected; remote preflight not required")

    blockers = _blockers_from_checks(checks)
    status = "passed" if not blockers else "blocked"
    return {
        "schema_version": ENTRY_GATE_SCHEMA,
        "generated_by": "entry_gate",
        "generated_at": _now_iso(),
        "status": status,
        "workflow_stage": "entry_gate_passed" if status == "passed" else "preflight_pending",
        "platform": platform_key,
        "entry_mode": entry_mode_norm,
        "backend": backend_norm,
        "coordination_mode": "staged_handoff",
        "orchestration_mode": "multi_agent",
        "live_runtime_policy": "single_runtime_single_context",
        "mode_key": mode_key,
        "checks": checks,
        "blockers": blockers,
        "summary": {
            "passed": sum(1 for item in checks if item["result"] == "pass"),
            "failed": sum(1 for item in checks if item["result"] == "fail"),
        },
        "request": {
            "capture_paths": capture_paths,
            "valid_capture_paths": valid_captures,
            "mcp_configured": bool(mcp_configured),
            "remote_transport": str(remote_transport or "").strip(),
            "fix_reference_status": str(fix_reference_status or "").strip(),
        },
        "platform_contract": {
            "coordination_mode": "staged_handoff",
            "orchestration_mode": "multi_agent",
            "live_runtime_policy": "single_runtime_single_context",
            "specialist_dispatch_requirement": str((row or {}).get("specialist_dispatch_requirement") or ""),
            "host_delegation_policy": str((row or {}).get("host_delegation_policy") or ""),
            "hook_ssot": str((row or {}).get("hook_ssot") or "shared_harness"),
            "enforcement_layer": str((row or {}).get("enforcement_layer") or "shared_harness"),
        },
        "runtime_mode_truth": {
            "mode_key": mode_key,
            "status": str((mode_truth or {}).get("status") or ""),
            "runtime_parallelism_ceiling": str((mode_truth or {}).get("runtime_parallelism_ceiling") or ""),
            "host_coordination_gate": str((mode_truth or {}).get("host_coordination_gate") or ""),
        },
        "paths": {
            "case_root": _norm(case_root),
            "platform_capabilities": _norm(platform_caps_path),
            "runtime_mode_truth": _norm(runtime_truth_path),
        },
    }


def _dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


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
    fix_reference_status: str = "strict_ready",
) -> dict[str, Any]:
    payload = build_entry_gate_payload(
        root,
        case_root,
        platform=platform,
        entry_mode=entry_mode,
        backend=backend,
        capture_paths=capture_paths,
        mcp_configured=mcp_configured,
        remote_transport=remote_transport,
        fix_reference_status=fix_reference_status,
    )
    _dump_yaml(case_root / "artifacts" / "entry_gate.yaml", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate debugger entry gate")
    parser.add_argument("--case-root", type=Path, required=True, help="workspace case root")
    parser.add_argument("--platform", required=True, help="platform key")
    parser.add_argument("--entry-mode", required=True, choices=("cli", "mcp"))
    parser.add_argument("--backend", required=True, choices=("local", "remote"))
    parser.add_argument("--capture-path", action="append", default=[], help="accessible .rdc input path")
    parser.add_argument("--mcp-configured", action="store_true", help="mark MCP preflight as configured")
    parser.add_argument("--remote-transport", default="", help="remote transport hint")
    parser.add_argument("--fix-reference-status", default="strict_ready")
    parser.add_argument("--root", type=Path, default=None, help="debugger root override")
    parser.add_argument("--strict", action="store_true", help="return non-zero on blocked")
    args = parser.parse_args()

    payload = run_entry_gate(
        _debugger_root(args.root),
        args.case_root.resolve(),
        platform=args.platform,
        entry_mode=args.entry_mode,
        backend=args.backend,
        capture_paths=list(args.capture_path or []),
        mcp_configured=bool(args.mcp_configured),
        remote_transport=str(args.remote_transport or "").strip(),
        fix_reference_status=str(args.fix_reference_status or "").strip(),
    )
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), end="")
    if args.strict and payload["status"] != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())