#!/usr/bin/env python3
"""Package-local tool contract validator for runtime hooks."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".jsonl", ".py", ".toml"}
TOOL_PATTERN = r"(?<![A-Za-z0-9_\.])(?P<tool>rd\.[A-Za-z0-9_]+\.[A-Za-z0-9_\.]+)"
TOOL_RE = re.compile(TOOL_PATTERN)
CALL_RE = re.compile(TOOL_PATTERN + r"\s*\(([^)]*)\)")
EXPECTED_TOOLS_ROOT = "tools"
EXPECTED_RUNTIME_MODE = "worker_staged"
BANNED_SNIPPETS = {
    "--connect": "legacy CLI connect flag removed; CLI is always daemon-backed",
    "error_message": "use canonical error.message instead of legacy error_message",
    "直接本地 runtime": "framework docs must not describe direct runtime ownership",
    "__CONFIGURE_TOOLS_ROOT__": "legacy configurable tools_root flow removed; use the package-local tools/ source payload",
    "配置 `paths.tools_root`": "legacy manual tools_root configuration removed; use the package-local tools/ source payload",
    "configure `paths.tools_root`": "legacy manual tools_root configuration removed; use the package-local tools/ source payload",
}


@dataclass
class Findings:
    unknown_tools: dict[str, set[str]] = field(default_factory=dict)
    missing_prerequisite_examples: list[str] = field(default_factory=list)
    banned_snippets: list[str] = field(default_factory=list)

    def has_issues(self) -> bool:
        return any([self.unknown_tools, self.missing_prerequisite_examples, self.banned_snippets])


def _root(default: Path | None = None) -> Path:
    return default.resolve() if default else Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg} (line {exc.lineno}, column {exc.colno}).") from exc


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _resolve_tools_root(root: Path) -> Path:
    adapter = _read_json(root / "common" / "config" / "platform_adapter.json")
    raw_root = str((adapter.get("paths") or {}).get("tools_source_root", "")).strip()
    if raw_root != EXPECTED_TOOLS_ROOT:
        raise ValueError(
            f"platform_adapter.json must keep paths.tools_source_root='{EXPECTED_TOOLS_ROOT}' and treat tools/ as a package-local source payload"
        )
    runtime_mode = str((adapter.get("runtime") or {}).get("mode", "")).strip()
    if runtime_mode != EXPECTED_RUNTIME_MODE:
        raise ValueError(
            f"platform_adapter.json must keep runtime.mode='{EXPECTED_RUNTIME_MODE}' for daemon-owned worker staging"
        )
    tools_root = (root / EXPECTED_TOOLS_ROOT).resolve()
    required_paths = [
        str(item).strip()
        for item in (adapter.get("validation") or {}).get("required_paths", [])
        if str(item).strip()
    ]
    if not required_paths:
        raise ValueError("platform_adapter.json missing validation.required_paths")
    missing = [rel for rel in required_paths if not (tools_root / rel).is_file()]
    if missing:
        paths = ", ".join(str(tools_root / rel) for rel in missing)
        raise ValueError(f"package-local tools source payload validation failed: missing {paths}")
    return tools_root


def _load_catalog(root: Path) -> tuple[set[str], dict[str, list[dict[str, str]]]]:
    payload = _read_json(_resolve_tools_root(root) / "spec" / "tool_catalog.json")
    names = {str(item.get("name", "")).strip() for item in payload.get("tools", []) if str(item.get("name", "")).strip()}
    prerequisites = {
        str(item.get("name", "")).strip(): [
            {
                "requires": str(pr.get("requires", "")).strip(),
                "when": str(pr.get("when", "")).strip(),
            }
            for pr in item.get("prerequisites", [])
            if isinstance(pr, dict) and str(pr.get("requires", "")).strip()
        ]
        for item in payload.get("tools", [])
        if str(item.get("name", "")).strip()
    }
    return names, prerequisites


def _iter_files(root: Path) -> list[Path]:
    bases = [
        root / name
        for name in ("common", "agents", "skills", "hooks", "references", "workflows", ".claude", ".github", ".agents", ".codex")
        if (root / name).exists()
    ]
    files: list[Path] = []
    for base in bases:
        for path in ([base] if base.is_file() else base.rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT_EXTS:
                files.append(path)
    return files


def _should_scan_banned_snippets(path: Path) -> bool:
    if path.name == "tool_catalog.snapshot.json":
        return False
    if path.suffix.lower() == ".py":
        return False
    return True


def _tool_refs(text: str) -> set[str]:
    return {match.group("tool") for match in TOOL_RE.finditer(text)}


def _looks_like_field_path(ref: str, known_tools: set[str]) -> bool:
    return any(ref.startswith(tool + ".") for tool in known_tools)


def validate_runtime_tool_contract(root: Path | None = None) -> Findings:
    package_root = _root(root)
    known_tools, prerequisites = _load_catalog(package_root)
    findings = Findings()

    for path in _iter_files(package_root):
        text = _read_text(path)
        unknown = sorted(
            {
                ref
                for ref in _tool_refs(text)
                if ref not in known_tools and not _looks_like_field_path(ref, known_tools)
            }
        )
        if unknown:
            findings.unknown_tools[str(path)] = set(unknown)
        if _should_scan_banned_snippets(path):
            for snippet, reason in BANNED_SNIPPETS.items():
                if snippet in text:
                    findings.banned_snippets.append(f"{path}: banned snippet `{snippet}` ({reason})")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in CALL_RE.finditer(line):
                tool = match.group("tool")
                arg_text = match.group(2)
                for prereq in prerequisites.get(tool, []):
                    required = prereq.get("requires", "")
                    when = prereq.get("when", "")
                    if when == "options.remote_id_present" and "remote_id" not in arg_text:
                        continue
                    if required == "session_id" and "session_id" not in arg_text:
                        findings.missing_prerequisite_examples.append(
                            f"{path}:{lineno}: {tool}(...) missing session_id prerequisite in example"
                        )
                    if required == "capture_file_id" and "capture_file_id" not in arg_text:
                        findings.missing_prerequisite_examples.append(
                            f"{path}:{lineno}: {tool}(...) missing capture_file_id prerequisite in example"
                        )
                    if required == "remote_id" and ("remote_id" not in arg_text and "options.remote_id" not in arg_text):
                        findings.missing_prerequisite_examples.append(
                            f"{path}:{lineno}: {tool}(...) missing remote_id prerequisite in example"
                        )

    return findings


def _print_findings(findings: Findings) -> None:
    if findings.unknown_tools:
        print("[unknown rd.* references]")
        for file_path in sorted(findings.unknown_tools):
            print(f" - {file_path}: {', '.join(sorted(findings.unknown_tools[file_path]))}")
    if findings.missing_prerequisite_examples:
        print("[example calls missing prerequisites]")
        for row in findings.missing_prerequisite_examples:
            print(f" - {row}")
    if findings.banned_snippets:
        print("[banned legacy snippets]")
        for row in findings.banned_snippets:
            print(f" - {row}")


def main() -> int:
    try:
        findings = validate_runtime_tool_contract()
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 2

    if findings.has_issues():
        _print_findings(findings)
        return 1

    print("runtime tool contract validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
