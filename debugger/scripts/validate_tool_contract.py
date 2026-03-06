#!/usr/bin/env python3
"""Validate debugger tool references against the configured platform catalog.

Checks:
1) Unknown rd.* references in common/** and platforms/**
2) Action-chain tool calls:
   - unknown tool names
   - parameter key drift vs catalog param_names
   - missing session_id for tools that require it
3) Explicit call examples like rd.xxx.yyy(...) missing session_id for tools
   that require it
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Set

TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".jsonl", ".py"}
TOOL_RE = re.compile(r"rd\.[A-Za-z0-9_]+\.[A-Za-z0-9_\.]+")
CALL_RE = re.compile(r"(rd\.[A-Za-z0-9_]+\.[A-Za-z0-9_\.]+)\s*\(([^)]*)\)")
ENV_CATALOG = "DEBUGGER_PLATFORM_CATALOG"


@dataclass
class Findings:
    unknown_tools: Dict[str, Set[str]] = field(default_factory=dict)
    action_unknown_tools: Dict[str, Set[str]] = field(default_factory=dict)
    action_param_drift: List[str] = field(default_factory=list)
    missing_session_examples: List[str] = field(default_factory=list)

    def has_issues(self) -> bool:
        return any(
            [
                self.unknown_tools,
                self.action_unknown_tools,
                self.action_param_drift,
                self.missing_session_examples,
            ],
        )


def _debugger_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _framework_root(debugger_root: Path) -> Path:
    return debugger_root.parent


def _adapter_config_path(debugger_root: Path) -> Path:
    return debugger_root / "common" / "config" / "platform_adapter.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _resolve_from_framework_root(framework_root: Path, raw_path: str) -> Path:
    candidate = Path(str(raw_path).strip())
    if candidate.is_absolute():
        return candidate
    return (framework_root / candidate).resolve()


def _default_catalog(debugger_root: Path) -> Path:
    framework_root = _framework_root(debugger_root)
    env_override = os.environ.get(ENV_CATALOG, "").strip()
    if env_override:
        return Path(env_override).resolve()

    config_path = _adapter_config_path(debugger_root)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"missing adapter config: {config_path} (create common/config/platform_adapter.json or pass --catalog)",
        )

    payload = _read_json(config_path)
    raw_catalog = str(payload.get("paths", {}).get("catalog_path", "")).strip()
    if not raw_catalog:
        raise ValueError(
            f"adapter config missing paths.catalog_path: {config_path} (or set {ENV_CATALOG})",
        )
    return _resolve_from_framework_root(framework_root, raw_catalog)


def _load_catalog(catalog_path: Path) -> tuple[Set[str], Dict[str, Set[str]], Set[str]]:
    payload = _read_json(catalog_path)
    tools = payload.get("tools", [])
    names: Set[str] = set()
    param_names: Dict[str, Set[str]] = {}
    requires_session: Set[str] = set()
    for item in tools:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        names.add(name)
        params = {str(p).strip() for p in item.get("param_names", []) if str(p).strip()}
        param_names[name] = params
        if "session_id" in params:
            requires_session.add(name)
    return names, param_names, requires_session


def _iter_scan_files(debugger_root: Path) -> Iterable[Path]:
    for rel in ("common", "platforms"):
        base = debugger_root / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_EXTS:
                continue
            if "design" in path.parts:
                continue
            yield path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _check_unknown_tools(files: Iterable[Path], known_tools: Set[str]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for path in files:
        refs = set(TOOL_RE.findall(_read_text(path)))
        unknown = {ref for ref in refs if ref not in known_tools}
        if unknown:
            out[str(path)] = unknown
    return out


def _check_action_chains(
    debugger_root: Path,
    known_tools: Set[str],
    tool_params: Dict[str, Set[str]],
    requires_session: Set[str],
) -> tuple[Dict[str, Set[str]], List[str]]:
    action_unknown: Dict[str, Set[str]] = {}
    drift: List[str] = []
    traces_dir = debugger_root / "common" / "knowledge" / "traces" / "action_chains"
    if not traces_dir.is_dir():
        return action_unknown, drift

    for jsonl in sorted(traces_dir.glob("*.jsonl")):
        unknown_here: Set[str] = set()
        for idx, line in enumerate(_read_text(jsonl).splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                drift.append(f"{jsonl}:{idx}: invalid jsonl line: {exc}")
                continue
            steps = payload.get("steps", [])
            if not isinstance(steps, list):
                drift.append(f"{jsonl}:{idx}: steps must be a list")
                continue
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if step.get("action_type") != "tool_call":
                    continue
                tool = str(step.get("tool", "")).strip()
                params = step.get("params", {})
                if tool not in known_tools:
                    if tool:
                        unknown_here.add(tool)
                    continue
                if not isinstance(params, dict):
                    drift.append(f"{jsonl}:{idx}: tool {tool} params must be object")
                    continue
                allowed = tool_params.get(tool, set())
                extra = sorted(k for k in params.keys() if k not in allowed)
                if extra:
                    drift.append(
                        f"{jsonl}:{idx}: tool {tool} has unexpected params {extra}; allowed={sorted(allowed)}",
                    )
                if tool in requires_session and "session_id" not in params:
                    drift.append(f"{jsonl}:{idx}: tool {tool} missing required session_id")
        if unknown_here:
            action_unknown[str(jsonl)] = unknown_here
    return action_unknown, drift


def _check_session_examples(files: Iterable[Path], requires_session: Set[str]) -> List[str]:
    missing: List[str] = []
    for path in files:
        text = _read_text(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for tool, arg_text in CALL_RE.findall(line):
                if tool in requires_session and "session_id" not in arg_text:
                    missing.append(f"{path}:{lineno}: {tool}(...) missing session_id in example")
    return missing


def _print_findings(findings: Findings) -> None:
    if findings.unknown_tools:
        print("[unknown rd.* references]")
        for file_path in sorted(findings.unknown_tools):
            refs = ", ".join(sorted(findings.unknown_tools[file_path]))
            print(f"  - {file_path}: {refs}")
    if findings.action_unknown_tools:
        print("[action_chains unknown tools]")
        for file_path in sorted(findings.action_unknown_tools):
            refs = ", ".join(sorted(findings.action_unknown_tools[file_path]))
            print(f"  - {file_path}: {refs}")
    if findings.action_param_drift:
        print("[action_chains param drift]")
        for row in findings.action_param_drift:
            print(f"  - {row}")
    if findings.missing_session_examples:
        print("[example calls missing session_id]")
        for row in findings.missing_session_examples:
            print(f"  - {row}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate debugger tool contract")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help=f"Path to platform tool catalog (default: adapter config or {ENV_CATALOG})",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when findings exist",
    )
    args = parser.parse_args()

    debugger_root = _debugger_root()
    try:
        catalog = args.catalog.resolve() if args.catalog else _default_catalog(debugger_root)
    except Exception as exc:  # noqa: BLE001
        print(str(exc))
        return 2

    if not catalog.is_file():
        print(
            f"catalog not found: {catalog} (update common/config/platform_adapter.json, set {ENV_CATALOG}, or pass --catalog)",
        )
        return 2

    known_tools, tool_params, requires_session = _load_catalog(catalog)

    files = list(_iter_scan_files(debugger_root))
    findings = Findings()
    findings.unknown_tools = _check_unknown_tools(files, known_tools)
    findings.action_unknown_tools, findings.action_param_drift = _check_action_chains(
        debugger_root,
        known_tools,
        tool_params,
        requires_session,
    )
    findings.missing_session_examples = _check_session_examples(files, requires_session)

    if findings.has_issues():
        _print_findings(findings)
        return 1 if args.strict else 0

    print(f"tool contract validation passed ({catalog})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
