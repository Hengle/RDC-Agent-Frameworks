from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUGGER_ROOT = REPO_ROOT / "debugger"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class SpecStoreTests(unittest.TestCase):
    def test_active_manifest_reference_sets_are_resolvable(self) -> None:
        spec_store = _load_module(DEBUGGER_ROOT / "common" / "hooks" / "utils" / "spec_store.py", "spec_store_module")

        refs = spec_store.load_reference_sets(DEBUGGER_ROOT)
        versions = spec_store.active_spec_versions(DEBUGGER_ROOT)

        self.assertEqual(spec_store.spec_snapshot_ref(DEBUGGER_ROOT), "spec-snapshot-20260315-0001")
        self.assertEqual(versions["sop_catalog"], 1)
        self.assertIn("banding", refs["symptom_tags"])
        self.assertIn("Adreno_GPU", refs["trigger_tags"])
        self.assertIn("I-PREC-01", refs["violated_invariants"])
        self.assertIn("SOP-PREC-01", refs["recommended_sop"])

    def test_candidate_transition_policy_covers_replay_activate_and_rollback(self) -> None:
        spec_store = _load_module(DEBUGGER_ROOT / "common" / "hooks" / "utils" / "spec_store.py", "spec_store_module_for_policy")
        evolution = _load_module(DEBUGGER_ROOT / "common" / "hooks" / "utils" / "knowledge_evolution.py", "knowledge_evolution_module")

        policy = spec_store.load_evolution_policy(DEBUGGER_ROOT)

        candidate = {
            "proposal_type": "sop_candidate",
            "status": "candidate",
            "support_runs": 5,
            "distinct_sessions": 3,
            "distinct_device_groups": 2,
            "promotion_metrics": {
                **evolution.default_promotion_metrics(),
                "counterfactual_approved_rate": 1.0,
                "median_steps_to_anchor_improvement": 0.12,
            },
        }
        self.assertEqual(evolution.evaluate_transition(candidate, policy), "replay_validated")

        candidate["status"] = "shadow_active"
        candidate["promotion_target"] = {"object_path": "common/knowledge/spec/objects/sops/SOP-CATALOG@1.yaml"}
        candidate["promotion_metrics"]["shadow_run_count"] = 20
        candidate["promotion_metrics"]["shadow_no_critical_regression_runs"] = 20
        self.assertEqual(evolution.evaluate_transition(candidate, policy), "active")

        candidate["status"] = "active"
        candidate["promotion_metrics"]["critical_regression_streak"] = 3
        self.assertEqual(evolution.evaluate_transition(candidate, policy), "rolled_back")


if __name__ == "__main__":
    unittest.main()
