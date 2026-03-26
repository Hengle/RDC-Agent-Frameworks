#!/usr/bin/env python3
"""Run-level intake gate for debugger workspace cases."""

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

VALIDATORS_ROOT = Path(__file__).resolve().parents[1] / "validators"
if str(VALIDATORS_ROOT) not in sys.path:
    sys.path.insert(0, str(VALIDATORS_ROOT))

from intake_validator import validate_case_input  # noqa: E402


ACTION_CHAIN_SCHEMA = "2"
INTAKE_GATE_SCHEMA = "1"
INTAKE_GATE_CHECK_IDS = (
    "case_input",
    "case_input_schema",
    "captures_manifest",
    "captures_manifest_schema",
    "imported_capture_files",
    "capture_refs",
    "capture_refs_schema",
    "hypothesis_board",
    "intent_gate_acceptance",
)


def _debugger_root(default: Path | None = None) -> Path:
    return default.resolve() if default else Path(__file__).resolve().parents[3]


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _norm(path: Path) -> str:
    return str(path).replace("\\", "/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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


def _check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    detail: str,
    *,
    path: Path | None = None,
    refs: list[str] | None = None,
) -> None:
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
    existing = _read_text(path) if path.exists() else ""
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


def _case_root(run_root: Path) -> Path:
    return run_root.parent.parent


def _captures_manifest_entries(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("captures", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _capture_refs_entries(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        captures = data.get("captures")
        if isinstance(captures, list):
            return [item for item in captures if isinstance(item, dict)]
        refs = data.get("refs")
        if isinstance(refs, list):
            return [item for item in refs if isinstance(item, dict)]
        if any(key in data for key in ("anomalous", "baseline", "fixed")):
            entries: list[dict[str, Any]] = []
            for role in ("anomalous", "baseline", "fixed"):
                payload = data.get(role)
                if isinstance(payload, dict):
                    item = dict(payload)
                    item.setdefault("capture_role", role)
                    entries.append(item)
            return entries
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _capture_entry_capture_id(entry: dict[str, Any]) -> str:
    return str(entry.get("capture_id") or entry.get("id") or "").strip()


def _capture_entry_role(entry: dict[str, Any]) -> str:
    return str(entry.get("capture_role") or entry.get("role") or "").strip()


def _capture_entry_file_name(entry: dict[str, Any]) -> str:
    raw = str(entry.get("file_name") or entry.get("path") or entry.get("rdc_path") or "").strip()
    if not raw:
        return ""
    return Path(raw.replace("\\", "/")).name


def _intent_gate_issues(board_data: Any) -> list[str]:
    if not isinstance(board_data, dict):
        return ["hypothesis_board must be a YAML object"]
    root = board_data.get("hypothesis_board")
    if not isinstance(root, dict):
        return ["hypothesis_board root object must exist"]
    intent_gate = root.get("intent_gate")
    if not isinstance(intent_gate, dict):
        return ["hypothesis_board.intent_gate must be an object"]
    issues: list[str] = []
    if str(intent_gate.get("decision", "")).strip() != "debugger":
        issues.append("hypothesis_board.intent_gate.decision must be debugger")
    return issues


def build_intake_gate_payload(root: Path, run_root: Path) -> dict[str, Any]:
    case_root = _case_root(run_root)
    case_input = case_root / "case_input.yaml"
    captures_manifest = case_root / "inputs" / "captures" / "manifest.yaml"
    captures_dir = case_root / "inputs" / "captures"
    capture_refs = run_root / "capture_refs.yaml"
    hypothesis_board = run_root / "notes" / "hypothesis_board.yaml"
    run_yaml = run_root / "run.yaml"
    session_marker = root / "common" / "knowledge" / "library" / "sessions" / ".current_session"
    run_data = _read_yaml(run_yaml) if run_yaml.is_file() else {}
    if not isinstance(run_data, dict):
        run_data = {}
    run_id = str(run_data.get("run_id") or "").strip()
    session_id = _extract_session_id(run_data, session_marker)

    checks: list[dict[str, Any]] = []

    case_input_data = _read_yaml(case_input) if case_input.is_file() else {}
    case_input_issues = validate_case_input(case_input_data) if case_input.is_file() else ["case_input missing"]
    _check(checks, "case_input", case_input.is_file(), "case_input.yaml must exist", path=case_input)
    _check(
        checks,
        "case_input_schema",
        not case_input_issues,
        "case_input.yaml must satisfy intake schema",
        path=case_input if case_input.is_file() else None,
        refs=case_input_issues[:8] or None,
    )

    captures_manifest_data = _read_yaml(captures_manifest) if captures_manifest.is_file() else {}
    manifest_entries = _captures_manifest_entries(captures_manifest_data)
    manifest_issues: list[str] = []
    imported_capture_paths: list[str] = []
    manifest_capture_ids: set[str] = set()
    manifest_capture_roles: set[str] = set()
    if not isinstance(captures_manifest_data, dict):
        manifest_issues.append("captures manifest must be a YAML object")
    elif not manifest_entries:
        manifest_issues.append("captures manifest must contain a non-empty captures list")
    else:
        for entry in manifest_entries:
            capture_id = _capture_entry_capture_id(entry)
            capture_role = _capture_entry_role(entry)
            file_name = _capture_entry_file_name(entry)
            if not capture_id:
                manifest_issues.append("captures manifest entries must include capture_id")
            if not capture_role:
                manifest_issues.append("captures manifest entries must include capture_role")
            if not file_name:
                manifest_issues.append("captures manifest entries must include file_name")
                continue
            file_path = captures_dir / file_name
            if file_path.is_file() and file_path.suffix.lower() == ".rdc":
                imported_capture_paths.append(_norm(file_path))
                if capture_id:
                    manifest_capture_ids.add(capture_id)
                if capture_role:
                    manifest_capture_roles.add(capture_role)
            else:
                manifest_issues.append(f"imported capture file missing: {file_name}")
    _check(
        checks,
        "captures_manifest",
        captures_manifest.is_file(),
        "inputs/captures/manifest.yaml must exist",
        path=captures_manifest,
    )
    _check(
        checks,
        "captures_manifest_schema",
        not manifest_issues,
        "inputs/captures/manifest.yaml must be well-formed",
        path=captures_manifest if captures_manifest.is_file() else None,
        refs=manifest_issues[:8] or None,
    )
    _check(
        checks,
        "imported_capture_files",
        bool(imported_capture_paths),
        "inputs/captures/ must contain at least one imported .rdc file referenced by manifest.yaml",
        path=captures_dir,
        refs=imported_capture_paths[:8] or None,
    )

    capture_refs_data = _read_yaml(capture_refs) if capture_refs.is_file() else {}
    capture_ref_entries = _capture_refs_entries(capture_refs_data)
    capture_refs_issues: list[str] = []
    if not capture_ref_entries:
        capture_refs_issues.append("capture_refs.yaml must contain at least one capture reference")
    for entry in capture_ref_entries:
        capture_id = _capture_entry_capture_id(entry)
        capture_role = _capture_entry_role(entry)
        if not capture_id and not capture_role:
            capture_refs_issues.append("capture_refs entries must include capture_id or capture_role")
            continue
        if capture_id and capture_id not in manifest_capture_ids:
            capture_refs_issues.append(f"capture_refs references unknown capture_id: {capture_id}")
        if capture_role and capture_role not in manifest_capture_roles:
            capture_refs_issues.append(f"capture_refs references unknown capture_role: {capture_role}")
    _check(checks, "capture_refs", capture_refs.is_file(), "runs/<run_id>/capture_refs.yaml must exist", path=capture_refs)
    _check(
        checks,
        "capture_refs_schema",
        capture_refs.is_file() and not capture_refs_issues,
        "capture_refs.yaml must reference imported captures from inputs/captures/manifest.yaml",
        path=capture_refs if capture_refs.is_file() else None,
        refs=capture_refs_issues[:8] or None,
    )

    hypothesis_board_data = _read_yaml(hypothesis_board) if hypothesis_board.is_file() else {}
    intent_gate_issues = _intent_gate_issues(hypothesis_board_data) if hypothesis_board.is_file() else ["hypothesis_board missing"]
    _check(checks, "hypothesis_board", hypothesis_board.is_file(), "notes/hypothesis_board.yaml must exist", path=hypothesis_board)
    _check(
        checks,
        "intent_gate_acceptance",
        not intent_gate_issues,
        "hypothesis_board.intent_gate.decision must be debugger",
        path=hypothesis_board if hypothesis_board.is_file() else None,
        refs=intent_gate_issues[:8] or None,
    )

    status = "passed" if all(item["result"] == "pass" for item in checks) else "failed"
    return {
        "schema_version": INTAKE_GATE_SCHEMA,
        "generated_by": "intake_gate",
        "generated_at": _now_iso(),
        "status": status,
        "run_root": _norm(run_root),
        "run_id": run_id,
        "session_id": session_id,
        "checks": checks,
        "summary": {
            "passed": sum(1 for item in checks if item["result"] == "pass"),
            "failed": sum(1 for item in checks if item["result"] == "fail"),
        },
        "paths": {
            "case_input": _norm(case_input),
            "captures_manifest": _norm(captures_manifest),
            "captures_dir": _norm(captures_dir),
            "capture_refs": _norm(capture_refs),
            "hypothesis_board": _norm(hypothesis_board),
        },
    }


def run_intake_gate(root: Path, run_root: Path) -> dict[str, Any]:
    payload = build_intake_gate_payload(root, run_root)
    output_path = run_root / "artifacts" / "intake_gate.yaml"
    _dump_yaml(output_path, payload)
    case_root = _case_root(run_root)
    entry_gate = _read_yaml(case_root / "artifacts" / "entry_gate.yaml") if (case_root / "artifacts" / "entry_gate.yaml").is_file() else {}
    run_data = _read_yaml(run_root / "run.yaml") if (run_root / "run.yaml").is_file() else {}
    if not isinstance(entry_gate, dict):
        entry_gate = {}
    if not isinstance(run_data, dict):
        run_data = {}
    action_chain = (
        root / "common" / "knowledge" / "library" / "sessions" / payload["session_id"] / "action_chain.jsonl"
        if str(payload.get("session_id") or "").strip()
        else root / "common" / "knowledge" / "library" / "sessions" / "action_chain.jsonl"
    )
    _append_event(
        action_chain,
        {
            "schema_version": ACTION_CHAIN_SCHEMA,
            "event_id": f"evt-intake-gate-{payload['status']}-{str(payload.get('run_id') or 'unknown')}",
            "ts_ms": _now_ms(),
            "run_id": str(payload.get("run_id") or ""),
            "session_id": str(payload.get("session_id") or ""),
            "agent_id": "rdc-debugger",
            "event_type": "quality_check",
            "status": "pass" if payload["status"] == "passed" else "fail",
            "duration_ms": 0,
            "refs": [],
            "payload": {
                "validator": "intake_gate",
                "summary": f"run intake gate {payload['status']}",
                "path": _norm(output_path),
                "entry_mode": str(entry_gate.get("entry_mode") or (run_data.get("debug") or {}).get("entry_mode") or "cli"),
                "backend": str(entry_gate.get("backend") or (run_data.get("runtime") or {}).get("backend") or "local"),
                "context_id": str((run_data.get("runtime") or {}).get("context_id") or run_data.get("context_id") or "default"),
                "runtime_owner": str((run_data.get("runtime") or {}).get("runtime_owner") or run_data.get("runtime_owner") or "rdc-debugger"),
                "baton_ref": "",
                "context_binding_id": "",
                "capture_ref": "",
                "canonical_anchor_ref": "",
            },
        },
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate debugger intake gate")
    parser.add_argument("--run-root", type=Path, required=True, help="workspace run root")
    parser.add_argument("--root", type=Path, default=None, help="debugger root override")
    parser.add_argument("--strict", action="store_true", help="return non-zero on failure")
    args = parser.parse_args()

    root = _debugger_root(args.root)
    payload = run_intake_gate(root, args.run_root.resolve())
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), end="")
    if args.strict and payload["status"] != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

