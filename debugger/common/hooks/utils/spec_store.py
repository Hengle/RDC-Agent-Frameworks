#!/usr/bin/env python3
"""Helpers for the versioned debugger spec store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(f"PyYAML is required for spec_store: {exc}")


MANIFEST_REL = Path("common/knowledge/spec/registry/active_manifest.yaml")
REGISTRY_REL = Path("common/knowledge/spec/registry/spec_registry.yaml")
POLICY_REL = Path("common/knowledge/spec/policy/evolution_policy.yaml")
NEGATIVE_MEMORY_REL = Path("common/knowledge/spec/negative_memory.yaml")
LEDGER_REL = Path("common/knowledge/spec/ledger/evolution_ledger.jsonl")


class SpecStoreError(RuntimeError):
    """Raised when the versioned spec store is incomplete or malformed."""


def debugger_root(default: Path | None = None) -> Path:
    return default.resolve() if default else Path(__file__).resolve().parents[3]


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if serialized in existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(serialized)
        handle.write("\n")


def _load_root_yaml(root: Path, rel: Path) -> dict[str, Any]:
    path = root / rel
    if not path.is_file():
        raise SpecStoreError(f"missing spec store file: {path}")
    payload = _read_yaml(path)
    if not isinstance(payload, dict):
        raise SpecStoreError(f"spec store file must be a YAML object: {path}")
    return payload


def load_active_manifest(root: Path | None = None) -> dict[str, Any]:
    return _load_root_yaml(debugger_root(root), MANIFEST_REL)


def load_spec_registry(root: Path | None = None) -> dict[str, Any]:
    return _load_root_yaml(debugger_root(root), REGISTRY_REL)


def load_evolution_policy(root: Path | None = None) -> dict[str, Any]:
    return _load_root_yaml(debugger_root(root), POLICY_REL)


def load_negative_memory(root: Path | None = None) -> dict[str, Any]:
    return _load_root_yaml(debugger_root(root), NEGATIVE_MEMORY_REL)


def evolution_ledger_path(root: Path | None = None) -> Path:
    return debugger_root(root) / LEDGER_REL


def append_evolution_ledger(root: Path | None, payload: dict[str, Any]) -> None:
    append_jsonl(evolution_ledger_path(root), payload)


def spec_snapshot_ref(root: Path | None = None) -> str:
    manifest = load_active_manifest(root)
    return str(manifest.get("snapshot_id", "")).strip()


def active_spec_versions(root: Path | None = None) -> dict[str, int]:
    manifest = load_active_manifest(root)
    families = manifest.get("families") or {}
    if not isinstance(families, dict):
        raise SpecStoreError("active_manifest.families must be an object")
    versions: dict[str, int] = {}
    for family, entry in families.items():
        if isinstance(entry, dict) and isinstance(entry.get("version"), int):
            versions[str(family)] = int(entry["version"])
    return versions


def load_active_object(root: Path | None, family: str) -> dict[str, Any]:
    repo_root = debugger_root(root)
    manifest = load_active_manifest(repo_root)
    families = manifest.get("families") or {}
    if not isinstance(families, dict):
        raise SpecStoreError("active_manifest.families must be an object")
    entry = families.get(family)
    if not isinstance(entry, dict):
        raise SpecStoreError(f"family not found in active manifest: {family}")
    object_path = repo_root / str(entry.get("object_path", "")).replace("/", "\\")
    if not object_path.is_file():
        raise SpecStoreError(f"active object missing for family {family}: {object_path}")
    obj = _read_yaml(object_path)
    if not isinstance(obj, dict):
        raise SpecStoreError(f"active object must be a YAML object: {object_path}")
    payload_path = repo_root / str(obj.get("payload_path", "")).replace("/", "\\")
    if not payload_path.is_file():
        raise SpecStoreError(f"active payload missing for family {family}: {payload_path}")
    payload = _read_yaml(payload_path)
    if not isinstance(payload, dict):
        raise SpecStoreError(f"active payload must be a YAML object: {payload_path}")
    result = dict(obj)
    result["payload"] = payload
    result["object_path"] = object_path
    result["payload_path"] = payload_path
    return result


def load_active_sops(root: Path | None = None) -> dict[str, Any]:
    return load_active_object(root, "sop_catalog")["payload"]


def load_active_invariants(root: Path | None = None) -> dict[str, Any]:
    return load_active_object(root, "invariant_catalog")["payload"]


def load_active_symptom_taxonomy(root: Path | None = None) -> dict[str, Any]:
    return load_active_object(root, "symptom_taxonomy")["payload"]


def load_active_trigger_taxonomy(root: Path | None = None) -> dict[str, Any]:
    return load_active_object(root, "trigger_taxonomy")["payload"]


def load_reference_sets(root: Path | None = None) -> dict[str, set[str]]:
    symptoms_payload = load_active_symptom_taxonomy(root)
    triggers_payload = load_active_trigger_taxonomy(root)
    invariants_payload = load_active_invariants(root)
    sops_payload = load_active_sops(root)

    symptom_tags = {
        str(item.get("tag", "")).strip()
        for item in (symptoms_payload.get("symptoms") or [])
        if isinstance(item, dict) and str(item.get("tag", "")).strip()
    }
    trigger_tags = {
        str(item.get("tag", "")).strip()
        for item in (triggers_payload.get("triggers") or [])
        if isinstance(item, dict) and str(item.get("tag", "")).strip()
    }
    invariant_ids = {
        str(item.get("id", "")).strip()
        for item in (invariants_payload.get("invariants") or [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    sop_ids = {
        str(item.get("id", "")).strip()
        for item in (sops_payload.get("sops") or [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }

    return {
        "symptom_tags": symptom_tags,
        "trigger_tags": trigger_tags,
        "violated_invariants": invariant_ids,
        "recommended_sop": sop_ids,
    }
