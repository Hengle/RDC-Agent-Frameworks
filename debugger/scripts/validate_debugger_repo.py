#!/usr/bin/env python3
"""Repository-level debugger validator."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _print_proc(proc: subprocess.CompletedProcess[str]) -> None:
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)


def _surface_supported(platform_caps: dict, surface: str) -> bool:
    if surface == "workflow":
        return bool(platform_caps.get("coordination_mode") == "workflow_stage" or platform_caps.get("degradation_mode") == "workflow-package")
    if surface == "agents":
        surface = "custom_agents"
    caps = platform_caps.get("capabilities") or {}
    slot = caps.get(surface) or {}
    return bool(slot.get("supported"))


def _frontmatter_string(path: Path, field: str) -> str | None:
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    match = re.search(rf"^{re.escape(field)}:\s*\"?([^\r\n\"]+)\"?\s*$", parts[1], re.MULTILINE)
    return match.group(1).strip() if match else None


def _toml_string(path: Path, key: str) -> str | None:
    text = path.read_text(encoding="utf-8-sig")
    match = re.search(rf"^{re.escape(key)}\s*=\s*\"([^\r\n\"]+)\"\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _platform_renders_per_agent_model(platform_caps: dict) -> bool:
    slot = (platform_caps.get("capabilities") or {}).get("per_agent_model") or {}
    rendered = str(slot.get("rendered", "")).strip()
    return bool(slot.get("supported")) and rendered not in {"inherit", "workflow-level", "not-supported"}


def _platform_is_inherit_only(platform_caps: dict) -> bool:
    slot = (platform_caps.get("capabilities") or {}).get("per_agent_model") or {}
    rendered = str(slot.get("rendered", "")).strip()
    return (not bool(slot.get("supported"))) or rendered in {"inherit", "workflow-level", "not-supported"}


def _expected_rendered_model(root: Path, platform_key: str, agent_id: str) -> tuple[Path, str] | None:
    manifest = _read_json(root / "common" / "config" / "role_manifest.json")
    routing = _read_json(root / "common" / "config" / "model_routing.json")
    role_profiles = routing.get("role_profiles") or {}
    profiles = routing.get("profiles") or {}
    roles = {row["agent_id"]: row for row in manifest.get("roles") or []}
    role = roles.get(agent_id)
    if not role:
        return None
    platform_file = (role.get("platform_files") or {}).get(platform_key)
    if not platform_file:
        return None
    profile_name = role_profiles.get(agent_id)
    profile = profiles.get(profile_name) or {}
    expected_model = ((profile.get("platform_rendering") or {}).get(platform_key) or "").strip()
    if platform_key == "code-buddy":
        path = root / "platforms" / platform_key / "agents" / platform_file
    elif platform_key == "claude-code":
        path = root / "platforms" / platform_key / ".claude" / "agents" / platform_file
    elif platform_key == "copilot-cli":
        path = root / "platforms" / platform_key / "agents" / platform_file
    elif platform_key == "copilot-ide":
        path = root / "platforms" / platform_key / ".github" / "agents" / platform_file
    elif platform_key == "codex":
        path = root / "platforms" / platform_key / ".codex" / "agents" / f"{platform_file}.toml"
    else:
        return None
    return path, expected_model


def _model_routing_findings(root: Path) -> list[str]:
    findings: list[str] = []
    routing = _read_json(root / "common" / "config" / "model_routing.json")
    role_policy = _read_json(root / "common" / "config" / "role_policy.json")
    caps = _read_json(root / "common" / "config" / "platform_capabilities.json")
    manifest = _read_json(root / "common" / "config" / "role_manifest.json")

    cap_platforms = caps.get("platforms") or {}
    routing_profiles = routing.get("profiles") or {}
    role_profiles = routing.get("role_profiles") or {}
    policy_profiles = role_policy.get("model_profiles") or {}
    policy_roles = role_policy.get("roles") or {}
    manifest_roles = {row["agent_id"]: row for row in manifest.get("roles") or []}
    declared_classes = routing.get("platform_classes") or {}

    if "global_requirements" not in routing:
        findings.append("model_routing.json missing global_requirements")

    class_members: set[str] = set()
    for class_name, platforms in declared_classes.items():
        if not isinstance(platforms, list):
            findings.append(f"model_routing.json platform_classes.{class_name} must be a list")
            continue
        class_members.update(str(item) for item in platforms)
    if class_members and class_members != set(cap_platforms):
        findings.append("model_routing.json platform_classes do not cover exactly the platform_capabilities platforms")

    for profile_name, profile in sorted(policy_profiles.items()):
        if "platform_models" in profile:
            findings.append(f"role_policy.json model_profiles.{profile_name} still contains platform_models")

    if set(role_profiles) != set(manifest_roles):
        findings.append("model_routing.json role_profiles keys differ from role_manifest roles")
    if set(policy_roles) != set(manifest_roles):
        findings.append("role_policy.json role keys differ from role_manifest roles")

    for agent_id, profile_name in sorted(role_profiles.items()):
        if profile_name not in routing_profiles:
            findings.append(f"model_routing.json missing profile '{profile_name}' for role {agent_id}")
            continue
        if agent_id not in policy_roles:
            findings.append(f"role_policy.json missing role policy for {agent_id}")
            continue
        policy_profile = str(policy_roles[agent_id].get("model_profile", "")).strip()
        if policy_profile != profile_name:
            findings.append(f"{agent_id}: role_policy model_profile mismatch ({policy_profile} != {profile_name})")

    for profile_name, profile in sorted(routing_profiles.items()):
        routing_map = profile.get("platform_rendering") or {}
        if set(routing_map) != set(cap_platforms):
            findings.append(f"{profile_name}: platform_rendering keys differ from platform_capabilities platforms")
            continue
        for platform_key, platform_caps in sorted(cap_platforms.items()):
            routed_model = str(routing_map.get(platform_key, "")).strip()
            if _platform_is_inherit_only(platform_caps):
                if routed_model != "inherit":
                    findings.append(f"{profile_name}: inherit-only platform {platform_key} must route to inherit, got '{routed_model}'")
            elif not routed_model or routed_model == "inherit":
                findings.append(f"{profile_name}: platform {platform_key} must have an explicit rendered model")

    rendered_platforms = ["code-buddy", "claude-code", "copilot-cli", "copilot-ide", "codex"]
    for platform_key in rendered_platforms:
        platform_caps = cap_platforms.get(platform_key) or {}
        if not _platform_renders_per_agent_model(platform_caps):
            findings.append(f"{platform_key}: expected rendered per-agent model support is missing from platform_capabilities")
            continue
        for agent_id in sorted(manifest_roles):
            expected = _expected_rendered_model(root, platform_key, agent_id)
            if expected is None:
                continue
            path, expected_model = expected
            if not path.exists():
                findings.append(f"{platform_key}: rendered agent file missing: {path}")
                continue
            if platform_key == "codex":
                actual_model = _toml_string(path, "model")
            else:
                actual_model = _frontmatter_string(path, "model")
            if actual_model != expected_model:
                findings.append(f"{platform_key}: {agent_id} rendered model mismatch ({actual_model} != {expected_model})")

    codex_root = root / "platforms" / "codex" / ".codex" / "config.toml"
    codex_team_lead = _expected_rendered_model(root, "codex", "team_lead")
    if codex_team_lead is not None and codex_root.exists():
        _, expected_team_lead_model = codex_team_lead
        actual_root_model = _toml_string(codex_root, "model")
        if actual_root_model != expected_team_lead_model:
            findings.append(f"codex root model mismatch ({actual_root_model} != {expected_team_lead_model})")

    return findings


def _compliance_findings(root: Path) -> list[str]:
    findings: list[str] = []
    compliance = _read_json(root / "common" / "config" / "framework_compliance.json")
    caps = _read_json(root / "common" / "config" / "platform_capabilities.json")
    platforms = compliance.get("platforms") or {}
    cap_platforms = caps.get("platforms") or {}

    if set(platforms) != set(cap_platforms):
        findings.append("framework_compliance.json and platform_capabilities.json platform keys differ")

    for key, rules in sorted(platforms.items()):
        platform_caps = cap_platforms.get(key)
        if not isinstance(platform_caps, dict):
            findings.append(f"missing platform_capabilities entry for {key}")
            continue

        expected_mode = str(rules.get("coordination_mode", "")).strip()
        actual_mode = str(platform_caps.get("coordination_mode", "")).strip()
        if expected_mode != actual_mode:
            findings.append(f"{key}: coordination_mode mismatch ({expected_mode} != {actual_mode})")

        for surface in rules.get("required_surfaces") or []:
            if not _surface_supported(platform_caps, str(surface)):
                findings.append(f"{key}: required surface '{surface}' is not supported by platform_capabilities")

        for rel in platform_caps.get("required_paths") or []:
            path = root / rel
            if not path.exists():
                findings.append(f"{key}: required path missing: {path}")

        if rules.get("workflow_required") and actual_mode != "workflow_stage":
            findings.append(f"{key}: workflow_required=true but coordination_mode is not workflow_stage")

    live_sessions = root / "common" / "knowledge" / "library" / "sessions"
    allowed = set(compliance["runtime_artifact_contract"]["allowed_live_library_session_entries"])
    if live_sessions.is_dir():
        for child in live_sessions.iterdir():
            if child.name in allowed:
                continue
            if child.is_dir() and not any(child.iterdir()):
                continue
            if child.name not in allowed:
                findings.append(f"live library sessions contains example or unexpected entry: {child}")

    return findings


def _spec_store_findings(root: Path) -> list[str]:
    findings: list[str] = []
    spec_root = root / "common" / "knowledge" / "spec"
    required = [
        spec_root / "README.md",
        spec_root / "registry" / "active_manifest.yaml",
        spec_root / "registry" / "spec_registry.yaml",
        spec_root / "policy" / "evolution_policy.yaml",
        spec_root / "negative_memory.yaml",
        spec_root / "ledger" / "evolution_ledger.jsonl",
    ]
    forbidden = [
        spec_root / "skills",
        spec_root / "invariants",
        spec_root / "taxonomy",
        root / "common" / "docs" / "sop_extraction_guide.md",
    ]

    for path in required:
        if not path.exists():
            findings.append(f"missing versioned spec store path: {path}")

    for path in forbidden:
        if path.exists():
            findings.append(f"legacy spec path must not exist: {path}")

    if findings:
        return findings

    manifest = _read_yaml(spec_root / "registry" / "active_manifest.yaml")
    registry = _read_yaml(spec_root / "registry" / "spec_registry.yaml")
    families = manifest.get("families") or {}
    registry_families = registry.get("families") or {}
    if set(families) != set(registry_families):
        findings.append("active_manifest and spec_registry family keys differ")
        return findings

    for family, entry in sorted(families.items()):
        if not isinstance(entry, dict):
            findings.append(f"active_manifest family entry must be an object: {family}")
            continue
        object_path = root / str(entry.get("object_path", "")).replace("/", "\\")
        if not object_path.is_file():
            findings.append(f"{family}: active object missing: {object_path}")
            continue
        obj = _read_yaml(object_path)
        if not isinstance(obj, dict):
            findings.append(f"{family}: active object must be a YAML object")
            continue
        payload_path = root / str(obj.get("payload_path", "")).replace("/", "\\")
        if not payload_path.is_file():
            findings.append(f"{family}: active payload missing: {payload_path}")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate debugger repo")
    parser.add_argument("--strict", action="store_true", help="return non-zero when findings exist")
    args = parser.parse_args()

    root = _root()
    commands = [
        [sys.executable, str(root / "scripts" / "sync_platform_scaffolds.py"), "--check"],
        [sys.executable, str(root / "scripts" / "validate_platform_layout.py"), "--strict"],
        [sys.executable, str(root / "scripts" / "validate_tool_contract.py"), "--mode", "source", "--strict"],
    ]

    findings: list[str] = []
    for command in commands:
        proc = _run(command, root.parent)
        _print_proc(proc)
        if proc.returncode != 0:
            findings.append(f"command failed: {' '.join(command)}")

    findings.extend(_compliance_findings(root))
    findings.extend(_spec_store_findings(root))
    findings.extend(_model_routing_findings(root))

    if findings:
        print("[debugger repo findings]")
        for row in findings:
            print(f" - {row}")
        return 1 if args.strict else 0

    print("debugger repo validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
