#!/usr/bin/env python3
"""Candidate lifecycle helpers for the versioned debugger knowledge store."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

UTILS_ROOT = Path(__file__).resolve().parent
if str(UTILS_ROOT) not in sys.path:
    sys.path.insert(0, str(UTILS_ROOT))

from spec_store import (
    append_evolution_ledger,
    append_jsonl,
    debugger_root,
    load_active_manifest,
    load_evolution_policy,
    load_negative_memory,
    load_spec_registry,
    write_yaml,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _proposal_suffix(match_signature: dict[str, Any], proposal_type: str, family: str) -> str:
    fingerprint = json.dumps(
        {
            "proposal_type": proposal_type,
            "family": family,
            "match_signature": match_signature,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]


def _policy_slot(policy: dict[str, Any], proposal_type: str) -> dict[str, Any]:
    slot = (policy.get("candidates") or {}).get(proposal_type) or {}
    if not isinstance(slot, dict):
        raise ValueError(f"invalid policy slot for {proposal_type}")
    return slot


def default_promotion_metrics() -> dict[str, Any]:
    return {
        "counterfactual_approved_rate": 0.0,
        "median_steps_to_anchor_improvement": 0.0,
        "route_precision_improvement": 0.0,
        "false_route_rate_delta": 0.0,
        "critical_regression_streak": 0,
        "shadow_run_count": 0,
        "shadow_no_critical_regression_runs": 0,
        "explanatory_gap_closure_rate": 0.0,
        "cluster_purity": 0.0,
    }


def evaluate_transition(candidate: dict[str, Any], policy: dict[str, Any]) -> str | None:
    status = str(candidate.get("status", "")).strip()
    proposal_type = str(candidate.get("proposal_type", "")).strip()
    thresholds = _policy_slot(policy, proposal_type)
    metrics = candidate.get("promotion_metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}

    support_runs = int(candidate.get("support_runs", 0) or 0)
    distinct_sessions = int(candidate.get("distinct_sessions", 0) or 0)
    distinct_device_groups = int(candidate.get("distinct_device_groups", 0) or 0)
    counterfactual_rate = float(metrics.get("counterfactual_approved_rate", 0.0) or 0.0)
    route_precision = float(metrics.get("route_precision_improvement", 0.0) or 0.0)
    step_gain = float(metrics.get("median_steps_to_anchor_improvement", 0.0) or 0.0)
    false_route_delta = float(metrics.get("false_route_rate_delta", 0.0) or 0.0)
    shadow_runs = int(metrics.get("shadow_run_count", 0) or 0)
    shadow_clean = int(metrics.get("shadow_no_critical_regression_runs", 0) or 0)
    critical_regression = int(metrics.get("critical_regression_streak", 0) or 0)
    gap_closure = float(metrics.get("explanatory_gap_closure_rate", 0.0) or 0.0)
    purity = float(metrics.get("cluster_purity", 0.0) or 0.0)

    replay_rules = thresholds.get("replay_thresholds") or {}
    shadow_rules = thresholds.get("shadow_thresholds") or {}
    rollback_rules = thresholds.get("rollback_thresholds") or {}

    replay_ok = (
        support_runs >= int(replay_rules.get("support_runs", 0) or 0)
        and distinct_sessions >= int(replay_rules.get("distinct_sessions", 0) or 0)
        and distinct_device_groups >= int(replay_rules.get("distinct_device_groups", 0) or 0)
        and counterfactual_rate >= float(replay_rules.get("counterfactual_approved_rate_min", 0.0) or 0.0)
    )

    if proposal_type == "sop_candidate":
        replay_ok = replay_ok and (
            step_gain >= float(replay_rules.get("median_steps_to_anchor_improvement_min", 0.0) or 0.0)
            or route_precision >= float(replay_rules.get("route_precision_improvement_min", 0.0) or 0.0)
        )
    elif proposal_type == "invariant_candidate":
        replay_ok = replay_ok and gap_closure >= float(replay_rules.get("explanatory_gap_closure_rate_min", 0.0) or 0.0)
    elif proposal_type == "taxonomy_candidate":
        replay_ok = replay_ok and purity >= float(replay_rules.get("cluster_purity_min", 0.0) or 0.0) and route_precision >= float(replay_rules.get("route_precision_improvement_floor", 0.0) or 0.0)

    if status == "candidate" and replay_ok:
        return "replay_validated"

    if status in {"candidate", "replay_validated"} and shadow_runs > 0:
        return "shadow_active"

    if status in {"replay_validated", "shadow_active"}:
        activation_target = candidate.get("promotion_target")
        if (
            isinstance(activation_target, dict)
            and shadow_clean >= int(shadow_rules.get("no_critical_regression_runs", 0) or 0)
            and false_route_delta <= float(shadow_rules.get("false_route_rate_delta_max", 999.0) or 999.0)
            and critical_regression == 0
        ):
            return "active"

    if status == "active":
        if critical_regression >= int(rollback_rules.get("critical_regression_streak", 999) or 999):
            return "rolled_back"
        if false_route_delta > float(rollback_rules.get("false_route_rate_delta_max", 999.0) or 999.0):
            return "rolled_back"
        if counterfactual_rate < float(rollback_rules.get("counterfactual_approved_rate_floor", 0.0) or 0.0):
            return "rolled_back"

    return None


def _candidate_file(root: Path, proposal_id: str) -> Path:
    return root / "common" / "knowledge" / "proposals" / f"{proposal_id}.yaml"


def _ledger_event(kind: str, proposal_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "event_id": f"evolution-{kind}-{proposal_id}-{_now_ms()}",
        "ts_ms": _now_ms(),
        "event_type": kind,
        "proposal_id": proposal_id,
        "payload": payload,
    }


def _merge_source_refs(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for key in ("session_ids", "run_ids", "event_ids"):
        prior = existing.get(key) if isinstance(existing, dict) else []
        current = incoming.get(key) if isinstance(incoming, dict) else []
        merged[key] = sorted({str(item).strip() for item in (prior or []) + (current or []) if str(item).strip()})
    return merged


def _update_registry_active(root: Path, candidate: dict[str, Any]) -> None:
    activation = candidate.get("promotion_target")
    if not isinstance(activation, dict):
        return

    family = str(candidate.get("family", "")).strip()
    object_path = str(activation.get("object_path", "")).strip()
    if not family or not object_path:
        return

    manifest_path = root / "common" / "knowledge" / "spec" / "registry" / "active_manifest.yaml"
    registry_path = root / "common" / "knowledge" / "spec" / "registry" / "spec_registry.yaml"
    manifest = load_active_manifest(root)
    registry = load_spec_registry(root)

    families = manifest.get("families") or {}
    if not isinstance(families, dict):
        families = {}
    family_entry = families.get(family) if isinstance(families.get(family), dict) else {}
    previous_object_path = str(family_entry.get("object_path", "")).strip() or None
    previous_version = family_entry.get("version")
    family_entry.update(
        {
            "spec_id": candidate.get("spec_id"),
            "version": candidate.get("candidate_version"),
            "canonical_id": candidate.get("canonical_id", candidate.get("spec_id")),
            "object_path": object_path,
            "activated_at": _now_iso(),
        }
    )
    families[family] = family_entry
    manifest["snapshot_id"] = f"spec-snapshot-{_now_ms()}"
    manifest["generated_at"] = _now_iso()
    manifest["families"] = families
    write_yaml(manifest_path, manifest)

    registry_families = registry.get("families") or {}
    if not isinstance(registry_families, dict):
        registry_families = {}
    registry_entry = registry_families.get(family) if isinstance(registry_families.get(family), dict) else {"versions": []}
    versions = registry_entry.get("versions")
    if not isinstance(versions, list):
        versions = []
    matched = False
    for item in versions:
        if not isinstance(item, dict):
            continue
        if int(item.get("version", -1)) == int(candidate.get("candidate_version", -1)):
            item["status"] = "active"
            item["object_path"] = object_path
            item["rollback_target"] = previous_object_path
            matched = True
        elif item.get("status") == "active":
            item["status"] = "superseded"
    if not matched:
        versions.append(
            {
                "spec_id": candidate.get("spec_id"),
                "family": family,
                "version": candidate.get("candidate_version"),
                "status": "active",
                "object_path": object_path,
                "parent_version": candidate.get("base_version"),
                "rollback_target": previous_object_path,
                "dedupe_group": candidate.get("dedupe_group"),
                "canonical_id": candidate.get("canonical_id", candidate.get("spec_id")),
            }
        )
    registry_entry["spec_id"] = candidate.get("spec_id")
    registry_entry["family"] = family
    registry_entry["active_version"] = candidate.get("candidate_version")
    registry_entry["active_object_path"] = object_path
    registry_entry["rollback_target"] = previous_object_path
    registry_entry["previous_version"] = previous_version
    registry_entry["versions"] = versions
    registry_families[family] = registry_entry
    registry["families"] = registry_families
    write_yaml(registry_path, registry)


def _record_negative_memory(root: Path, candidate: dict[str, Any]) -> None:
    memory_path = root / "common" / "knowledge" / "spec" / "negative_memory.yaml"
    negative_memory = load_negative_memory(root)
    entries = negative_memory.get("entries")
    if not isinstance(entries, list):
        entries = []
    entries.append(
        {
            "captured_at": _now_iso(),
            "spec_id": candidate.get("spec_id"),
            "family": candidate.get("family"),
            "candidate_version": candidate.get("candidate_version"),
            "trigger": "automatic_rollback",
            "summary": candidate.get("negative_evidence_summary", "rollback-triggered negative evidence"),
            "fingerprint": candidate.get("dedupe_group"),
        }
    )
    negative_memory["entries"] = entries
    write_yaml(memory_path, negative_memory)


def upsert_candidate(
    root: Path | None,
    payload: dict[str, Any],
    *,
    action_chain_path: Path | None = None,
    run_id: str = "",
    session_id: str = "",
    refs: list[str] | None = None,
) -> tuple[Path, dict[str, Any], str]:
    repo_root = debugger_root(root)
    policy = load_evolution_policy(repo_root)
    candidate = dict(payload)

    proposal_id = str(candidate.get("proposal_id", "")).strip()
    if not proposal_id:
        family = str(candidate.get("family", "")).strip()
        proposal_type = str(candidate.get("proposal_type", "")).strip()
        suffix = _proposal_suffix(candidate.get("match_signature") or {}, proposal_type, family)
        prefix = {"sop_candidate": "CAND-SOP", "invariant_candidate": "CAND-INV", "taxonomy_candidate": "CAND-TAX"}[proposal_type]
        proposal_id = f"{prefix}-{suffix}"
        candidate["proposal_id"] = proposal_id

    path = _candidate_file(repo_root, proposal_id)
    prior = yaml.safe_load(path.read_text(encoding="utf-8-sig")) if path.exists() else None
    prior = prior if isinstance(prior, dict) else {}

    source_refs = _merge_source_refs(prior.get("source_refs") or {}, candidate.get("source_refs") or {})
    candidate["source_refs"] = source_refs
    candidate["support_runs"] = len(source_refs["run_ids"])
    candidate["distinct_sessions"] = len(source_refs["session_ids"])

    metrics = dict(default_promotion_metrics())
    incoming_metrics = candidate.get("promotion_metrics")
    if isinstance(prior.get("promotion_metrics"), dict):
        metrics.update(prior["promotion_metrics"])
    if isinstance(incoming_metrics, dict):
        metrics.update(incoming_metrics)
    candidate["promotion_metrics"] = metrics

    if not isinstance(candidate.get("distinct_device_groups"), int):
        candidate["distinct_device_groups"] = int(metrics.get("distinct_device_groups", 0) or 0) or 1

    candidate.setdefault("status", "candidate")
    candidate.setdefault("created_at", prior.get("created_at") or _now_iso())
    candidate["updated_at"] = _now_iso()

    transition = evaluate_transition(candidate, policy)
    if transition:
        candidate["status"] = transition

    write_yaml(path, candidate)
    append_evolution_ledger(
        repo_root,
        _ledger_event(
            "candidate_upserted",
            proposal_id,
            {
                "path": str(path.relative_to(repo_root)).replace("\\", "/"),
                "status": candidate.get("status"),
                "run_id": run_id,
                "session_id": session_id,
            },
        ),
    )

    if action_chain_path is not None:
        event_type = "knowledge_candidate_emitted"
        status = "emitted" if not prior else "updated"
        if transition:
            event_type = "knowledge_candidate_transition"
            status = transition
        append_jsonl(
            action_chain_path,
            {
                "schema_version": "2",
                "event_id": f"evt-candidate-{proposal_id.lower()}-{_now_ms()}",
                "ts_ms": _now_ms(),
                "run_id": run_id,
                "session_id": session_id,
                "agent_id": "curator_agent",
                "event_type": event_type,
                "status": status,
                "duration_ms": 0,
                "refs": refs or [],
                "payload": {
                    "proposal_id": proposal_id,
                    "proposal_type": candidate.get("proposal_type"),
                    "path": str(path.relative_to(repo_root)).replace("\\", "/"),
                },
            },
        )

    if candidate.get("status") == "active":
        _update_registry_active(repo_root, candidate)
        append_evolution_ledger(
            repo_root,
            _ledger_event(
                "spec_activated",
                proposal_id,
                {
                    "family": candidate.get("family"),
                    "candidate_version": candidate.get("candidate_version"),
                },
            ),
        )
    elif candidate.get("status") == "rolled_back":
        _record_negative_memory(repo_root, candidate)
        append_evolution_ledger(
            repo_root,
            _ledger_event(
                "spec_rolled_back",
                proposal_id,
                {
                    "family": candidate.get("family"),
                    "candidate_version": candidate.get("candidate_version"),
                },
            ),
        )

    return path, candidate, transition or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Advance debugger knowledge candidates")
    parser.add_argument("--root", type=Path, default=None, help="debugger root override")
    parser.add_argument("--candidate", type=Path, default=None, help="candidate yaml path")
    args = parser.parse_args()

    repo_root = debugger_root(args.root)
    if args.candidate:
        payload = yaml.safe_load(args.candidate.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            print(f"invalid candidate payload: {args.candidate}")
            return 2
        _, candidate, transition = upsert_candidate(repo_root, payload)
        print(yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False), end="")
        if transition:
            print(f"transition={transition}")
        return 0

    proposals_root = repo_root / "common" / "knowledge" / "proposals"
    for candidate_path in sorted(proposals_root.glob("CAND-*.yaml")):
        payload = yaml.safe_load(candidate_path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            continue
        upsert_candidate(repo_root, payload)
    print("knowledge candidate sweep complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
