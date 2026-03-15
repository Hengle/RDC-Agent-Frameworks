#!/usr/bin/env python3
"""Counterfactual review validator for RenderDoc/RDC GPU Debug."""

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
    print("错误：缺少依赖 'PyYAML'，无法解析 YAML。")
    print(f"请先安装依赖：python3 -m pip install -r {req}")
    sys.exit(2)

ANSI_RED = "\033[91m"
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RESET = "\033[0m"
ACTION_CHAIN_SCHEMA = "2"
SESSION_EVIDENCE_SCHEMA = "2"
REQUIRED_ISOLATION_FIELDS = ("only_target_changed", "same_scene_same_input", "same_drawcall_count")
REQUIRED_MEASUREMENT_FIELDS = ("pixel_before", "pixel_after", "pixel_baseline")
REQUIRED_SCORING_FIELDS = ("pixel_recovery", "variable_isolation", "symptom_coverage", "total")


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


def _validate_measurement_payload(measurements: Any, prefix: str) -> list[str]:
    issues: list[str] = []
    if not isinstance(measurements, dict):
        return [f"{prefix}measurements must be an object"]
    for field in REQUIRED_MEASUREMENT_FIELDS:
        value = measurements.get(field)
        if not isinstance(value, dict):
            issues.append(f"{prefix}measurements.{field} must be an object")
            continue
        rgba = value.get("rgba")
        if not isinstance(rgba, list) or len(rgba) != 4:
            issues.append(f"{prefix}measurements.{field}.rgba must be a 4-item list")
    return issues


def _validate_scoring_payload(scoring: Any, prefix: str) -> list[str]:
    issues: list[str] = []
    if not isinstance(scoring, dict):
        return [f"{prefix}scoring must be an object"]
    for field in REQUIRED_SCORING_FIELDS:
        value = scoring.get(field)
        if not isinstance(value, (int, float)):
            issues.append(f"{prefix}scoring.{field} must be numeric")
    total = scoring.get("total")
    if isinstance(total, (int, float)) and float(total) < 0.80:
        issues.append(f"{prefix}scoring.total must be >= 0.80 (got {float(total):.2f})")
    return issues


def validate_counterfactual(snapshot: dict[str, Any], events: dict[str, dict[str, Any]]) -> tuple[bool, list[str], dict[str, Any]]:
    issues: list[str] = []
    details: dict[str, Any] = {"approved_reviews": 0, "review_ids": []}

    if not isinstance(snapshot, dict):
        return False, ["session_evidence must be a YAML/JSON object"], details
    if str(snapshot.get("schema_version", "")).strip() != SESSION_EVIDENCE_SCHEMA:
        issues.append(f"session_evidence.schema_version must be {SESSION_EVIDENCE_SCHEMA}")

    hypotheses = snapshot.get("hypotheses")
    if not isinstance(hypotheses, list):
        issues.append("session_evidence.hypotheses must be a list")
        hypotheses = []
    hypothesis_states = {
        str(item.get("hypothesis_id", "")).strip(): str(item.get("status", "")).strip()
        for item in hypotheses
        if isinstance(item, dict)
    }
    conflicted = sorted(hid for hid, state in hypothesis_states.items() if state == "CONFLICTED")
    if conflicted:
        issues.append(f"unresolved conflicted hypotheses present: {', '.join(conflicted)}")

    conflicts = snapshot.get("conflicts")
    if not isinstance(conflicts, list):
        issues.append("session_evidence.conflicts must be a list")
        conflicts = []
    unresolved_conflicts = sorted(
        str(item.get("conflict_id", "")).strip()
        for item in conflicts
        if isinstance(item, dict) and str(item.get("status", "")).strip() != "ARBITRATED"
    )
    unresolved_conflicts = [cid for cid in unresolved_conflicts if cid]
    if unresolved_conflicts:
        issues.append(f"unresolved conflicts present: {', '.join(unresolved_conflicts)}")

    reviews = snapshot.get("counterfactual_reviews")
    if not isinstance(reviews, list) or not reviews:
        return False, issues + ["session_evidence.counterfactual_reviews must be a non-empty list"], details

    approved_reviews = 0
    for review in reviews:
        if not isinstance(review, dict):
            issues.append("counterfactual_reviews contains a non-object entry")
            continue
        review_id = str(review.get("review_id", "")).strip()
        prefix = f"[review {review_id or '?'}] "
        for field in ("review_id", "hypothesis_id", "proposer_agent", "reviewer_agent", "status", "submission_event_id", "review_event_id", "evidence_refs"):
            if field not in review:
                issues.append(f"{prefix}missing field: {field}")
        proposer = str(review.get("proposer_agent", "")).strip()
        reviewer = str(review.get("reviewer_agent", "")).strip()
        status = str(review.get("status", "")).strip()
        if not _nonempty_str(proposer):
            issues.append(f"{prefix}proposer_agent must be non-empty")
        if not _nonempty_str(reviewer):
            issues.append(f"{prefix}reviewer_agent must be non-empty")
        if proposer and reviewer and proposer == reviewer:
            issues.append(f"{prefix}proposer_agent and reviewer_agent must differ")
        if status not in {"approved", "rejected"}:
            issues.append(f"{prefix}status must be approved or rejected")
        submission_event_id = str(review.get("submission_event_id", "")).strip()
        review_event_id = str(review.get("review_event_id", "")).strip()
        submission_event = events.get(submission_event_id)
        review_event = events.get(review_event_id)
        if submission_event is None:
            issues.append(f"{prefix}submission_event_id does not resolve: {submission_event_id}")
            continue
        if review_event is None:
            issues.append(f"{prefix}review_event_id does not resolve: {review_event_id}")
            continue
        if str(submission_event.get("schema_version", "")).strip() != ACTION_CHAIN_SCHEMA:
            issues.append(f"{prefix}submission event schema_version must be {ACTION_CHAIN_SCHEMA}")
        if str(review_event.get("schema_version", "")).strip() != ACTION_CHAIN_SCHEMA:
            issues.append(f"{prefix}review event schema_version must be {ACTION_CHAIN_SCHEMA}")
        if str(submission_event.get("event_type", "")).strip() != "counterfactual_submitted":
            issues.append(f"{prefix}submission_event_id must reference counterfactual_submitted")
        if str(review_event.get("event_type", "")).strip() != "counterfactual_reviewed":
            issues.append(f"{prefix}review_event_id must reference counterfactual_reviewed")
        if str(review_event.get("status", "")).strip() != status:
            issues.append(f"{prefix}review event status must match snapshot status")

        submission_payload = submission_event.get("payload")
        review_payload = review_event.get("payload")
        if not isinstance(submission_payload, dict):
            issues.append(f"{prefix}submission payload must be an object")
            continue
        if not isinstance(review_payload, dict):
            issues.append(f"{prefix}review payload must be an object")
            continue

        if str(submission_payload.get("proposer_agent", "")).strip() != proposer:
            issues.append(f"{prefix}submission payload proposer_agent mismatch")
        if str(review_payload.get("reviewer_agent", "")).strip() != reviewer:
            issues.append(f"{prefix}review payload reviewer_agent mismatch")

        isolation = submission_payload.get("isolation_checks")
        if not isinstance(isolation, dict):
            issues.append(f"{prefix}submission isolation_checks must be an object")
        else:
            for field in REQUIRED_ISOLATION_FIELDS:
                if not isinstance(isolation.get(field), bool):
                    issues.append(f"{prefix}submission isolation_checks.{field} must be boolean")

        issues.extend(_validate_measurement_payload(submission_payload.get("measurements"), prefix))
        issues.extend(_validate_scoring_payload(submission_payload.get("scoring"), prefix))

        isolation_verdict = review_payload.get("isolation_verdict")
        if not isinstance(isolation_verdict, dict):
            issues.append(f"{prefix}review isolation_verdict must be an object")
        else:
            if not _nonempty_str(isolation_verdict.get("verdict")):
                issues.append(f"{prefix}review isolation_verdict.verdict must be non-empty")
            if not _nonempty_str(isolation_verdict.get("rationale")):
                issues.append(f"{prefix}review isolation_verdict.rationale must be non-empty")

        evidence_refs = review.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            issues.append(f"{prefix}evidence_refs must be a non-empty list")
        else:
            for ref in evidence_refs:
                ref_id = str(ref).strip()
                if not ref_id:
                    issues.append(f"{prefix}evidence_refs contains an empty item")
                elif ref_id not in events:
                    issues.append(f"{prefix}evidence_ref does not resolve: {ref_id}")

        if status == "approved":
            approved_reviews += 1
            details["review_ids"].append(review_id)

    if approved_reviews == 0:
        issues.append("no approved counterfactual review found")
    details["approved_reviews"] = approved_reviews
    return (not issues), issues, details


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：python3 counterfactual_validator.py <session_evidence.yaml>")
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"{ANSI_RED}错误：文件不存在 — {path}{ANSI_RESET}")
        sys.exit(2)

    action_chain = path.with_name("action_chain.jsonl")
    if not action_chain.exists():
        print(f"{ANSI_RED}错误：缺少同目录 action_chain.jsonl — {action_chain}{ANSI_RESET}")
        sys.exit(2)

    try:
        snapshot = _load_yaml(path)
        rows = _load_action_chain(action_chain)
        events = _index_events(rows)
    except Exception as exc:  # noqa: BLE001
        print(f"{ANSI_RED}错误：解析失败 — {exc}{ANSI_RESET}")
        sys.exit(2)

    print(f"\n{'═'*55}")
    print(f"  Debugger 反事实复核检查器 — {path.name}")
    print(f"  action events：{len(events)}")
    print(f"{'═'*55}")

    ok, issues, details = validate_counterfactual(snapshot, events)
    if ok:
        print(f"\n{ANSI_GREEN}✅ 反事实验证通过 — 找到 {details.get('approved_reviews', 0)} 条独立批准记录{ANSI_RESET}")
        for review_id in details.get("review_ids", []):
            print(f"   - {review_id}")
        sys.exit(0)

    print(f"\n{ANSI_RED}❌ 反事实验证不足 — 无法结案{ANSI_RESET}\n")
    for issue in issues:
        print(f"  • {issue}")
    print(f"\n{ANSI_YELLOW}⚠  请补充独立复核、量化数据或冲突仲裁后再提交裁决。{ANSI_RESET}\n")
    sys.exit(1)


if __name__ == "__main__":
    main()
