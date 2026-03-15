#!/usr/bin/env python3
"""Causal anchor gate validator for RenderDoc/RDC GPU Debug."""

from __future__ import annotations

import json
import sys
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
    print("Missing dependency 'PyYAML'; cannot parse YAML.")
    print(f"Install dependencies with: python3 -m pip install -r {req}")
    sys.exit(2)

ANSI_RED = "\033[91m"
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RESET = "\033[0m"
ALLOWED_TYPES = {"first_bad_event", "first_divergence_event", "root_drawcall", "root_expression"}
ACTION_CHAIN_SCHEMA = "2"
SESSION_EVIDENCE_SCHEMA = "2"


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _load_action_chain(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"action_chain line {line_no} must be a JSON object")
        rows.append(obj)
    return rows


def _index_events(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = str(row.get("event_id", "")).strip()
        if event_id:
            index[event_id] = row
    return index


def validate_causal_anchor(data: dict[str, Any], events: dict[str, dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not isinstance(data, dict):
        return False, ["session evidence must be a YAML/JSON object"]
    if str(data.get("schema_version", "")).strip() != SESSION_EVIDENCE_SCHEMA:
        issues.append(f"session_evidence.schema_version must be {SESSION_EVIDENCE_SCHEMA}")

    anchor = data.get("causal_anchor")
    if not isinstance(anchor, dict):
        return False, ["missing causal_anchor object"]

    if anchor.get("type") not in ALLOWED_TYPES:
        issues.append(f"invalid causal_anchor.type: {anchor.get('type')!r}; allowed: {sorted(ALLOWED_TYPES)}")
    if not _nonempty_str(anchor.get("ref")):
        issues.append("causal_anchor.ref must not be empty")
    if not _nonempty_str(anchor.get("established_by")):
        issues.append("causal_anchor.established_by must not be empty")
    if not _nonempty_str(anchor.get("justification")):
        issues.append("causal_anchor.justification must not be empty")

    refs = anchor.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        issues.append("causal_anchor.evidence_refs must be a non-empty list")
        return False, issues

    resolved_tool_events = 0
    for ref in refs:
        ref_id = str(ref).strip()
        if not ref_id:
            issues.append("causal_anchor.evidence_refs contains an empty reference")
            continue
        event = events.get(ref_id)
        if event is None:
            issues.append(f"causal_anchor.evidence_refs contains unknown event_id: {ref_id}")
            continue
        if str(event.get("schema_version", "")).strip() != ACTION_CHAIN_SCHEMA:
            issues.append(f"{ref_id}: action_chain schema_version must be {ACTION_CHAIN_SCHEMA}")
        if str(event.get("event_type", "")).strip() == "tool_execution":
            resolved_tool_events += 1

    if resolved_tool_events == 0:
        issues.append("causal_anchor.evidence_refs must include at least one tool_execution event")

    return (not issues), issues


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 causal_anchor_validator.py <session_evidence.yaml>")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"{ANSI_RED}Error: file not found - {path}{ANSI_RESET}")
        return 2

    action_chain = path.with_name("action_chain.jsonl")
    if not action_chain.exists():
        print(f"{ANSI_RED}Error: sibling action_chain missing - {action_chain}{ANSI_RESET}")
        return 2

    try:
        data = _load_yaml(path)
        rows = _load_action_chain(action_chain)
        events = _index_events(rows)
    except Exception as exc:  # noqa: BLE001
        print(f"{ANSI_RED}Error: parse failed - {exc}{ANSI_RESET}")
        return 2

    ok, issues = validate_causal_anchor(data, events)
    if ok:
        anchor = data.get("causal_anchor", {})
        print(f"{ANSI_GREEN}OK causal anchor - {anchor.get('type')} / {anchor.get('ref')}{ANSI_RESET}")
        return 0

    print(f"{ANSI_RED}FAIL causal anchor gate{ANSI_RESET}\n")
    for issue in issues:
        print(f"  - {issue}")
    print(f"\n{ANSI_YELLOW}Add a causal anchor or re-anchor the investigation before finalization.{ANSI_RESET}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
