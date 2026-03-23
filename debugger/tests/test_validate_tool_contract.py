from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "debugger" / "scripts" / "validate_tool_contract.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_tool_contract_module", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_tool_contract_module"] = module
    spec.loader.exec_module(module)
    return module


class ValidateToolContractTests(unittest.TestCase):
    def test_field_name_does_not_match_tool_reference(self) -> None:
        module = _load_module()
        text = "BugCard.verification.reference_contract_ref: value"

        self.assertEqual(module._tool_refs(text), set())

    def test_real_tool_call_is_still_detected(self) -> None:
        module = _load_module()
        text = "rd.capture.open_replay(capture_file_id=cap_001)"

        self.assertEqual(module._tool_refs(text), {"rd.capture.open_replay"})
        match = next(module.CALL_RE.finditer(text))
        self.assertEqual(match.group("tool"), "rd.capture.open_replay")
        self.assertIn("capture_file_id", match.group(2))


if __name__ == "__main__":
    unittest.main()
