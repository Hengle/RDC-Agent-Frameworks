from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUGGER_ROOT = REPO_ROOT / "debugger"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


class ConfigConsistencyTests(unittest.TestCase):
    def test_platform_keys_and_cursor_alignment(self) -> None:
        compliance = _read_json(DEBUGGER_ROOT / "common" / "config" / "framework_compliance.json")
        capabilities = _read_json(DEBUGGER_ROOT / "common" / "config" / "platform_capabilities.json")
        routing = _read_json(DEBUGGER_ROOT / "common" / "config" / "model_routing.json")

        capability_platforms = set((capabilities.get("platforms") or {}).keys())
        compliance_platforms = set((compliance.get("platforms") or {}).keys())
        self.assertEqual(capability_platforms, compliance_platforms)
        self.assertIn("cursor", capability_platforms)

        class_members = {
            platform
            for members in (routing.get("platform_classes") or {}).values()
            for platform in members
        }
        self.assertEqual(capability_platforms, class_members)

        for profile in (routing.get("profiles") or {}).values():
            rendered = set((profile.get("platform_rendering") or {}).keys())
            self.assertEqual(capability_platforms, rendered)


if __name__ == "__main__":
    unittest.main()
