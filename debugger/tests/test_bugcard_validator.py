from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATORS_ROOT = REPO_ROOT / "debugger" / "common" / "hooks" / "validators"
if str(VALIDATORS_ROOT) not in sys.path:
    sys.path.insert(0, str(VALIDATORS_ROOT))

from bugcard_validator import validate_bugcard  # noqa: E402


def _base_bugcard() -> dict:
    return {
        "bugcard_id": "BUG-PREC-999",
        "title": "Adreno 740 精度 lowering 触发头发黑化",
        "symptom_tags": ["blackout"],
        "trigger_tags": ["Adreno_GPU"],
        "violated_invariants": ["I-PREC-01"],
        "recommended_sop": "SOP-PREC-01",
        "causal_anchor_type": "first_bad_event",
        "causal_anchor_ref": "event:523",
        "causal_chain_summary": "目标像素在 Event#523 首次变坏，异常在该 drawcall 首次引入，而不是在后续 pass 首次可见。",
        "root_cause_summary": "在 MobileShadingModels.ush 中，half 计算经 Adreno 740 lowering 后产生异常负值并被错误钳零。",
        "fingerprint": {"pattern": "half KajiyaDiffuse = 1 - abs(dot(N, L));", "risk_category": "precision_lowering", "shader_stage": "PS"},
        "fix_verified": True,
        "verification": {
            "reference_contract_ref": "../workspace/cases/case-001/case_input.yaml#reference_contract",
            "structural": {"status": "passed", "artifact_ref": "../workspace/cases/case-001/runs/run-001/artifacts/fix_verification.yaml#structural_verification"},
            "semantic": {"status": "passed", "artifact_ref": "../workspace/cases/case-001/runs/run-001/artifacts/fix_verification.yaml#semantic_verification"},
        },
        "skeptic_signed": True,
        "bugcard_skeptic_signed": True,
    }


class BugCardValidatorTests(unittest.TestCase):
    def test_verification_object_passes(self) -> None:
        self.assertEqual(validate_bugcard(_base_bugcard()), [])

    def test_removed_fix_verification_data_rejected(self) -> None:
        data = _base_bugcard()
        data["fix_verification_data"] = {"pixel_before": {}, "pixel_after": {}}
        errors = validate_bugcard(data)
        self.assertTrue(any("fix_verification_data" in err for err in errors))

    def test_fix_verified_requires_passed_structural_and_semantic(self) -> None:
        data = _base_bugcard()
        data["verification"]["semantic"]["status"] = "fallback_only"
        errors = validate_bugcard(data)
        self.assertTrue(any("semantic.status" in err for err in errors))

    def test_verification_object_is_always_required(self) -> None:
        data = _base_bugcard()
        data["fix_verified"] = False
        data.pop("verification")
        errors = validate_bugcard(data)
        self.assertTrue(any("verification" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
