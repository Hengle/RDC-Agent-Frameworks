from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUGGER_ROOT = REPO_ROOT / "debugger"

BANNED_MARKERS = (
    "concurrent" + "_team",
    "single_agent" + "_by_user",
    "runtime_" + "topology",
    "runtime_" + "baton",
    "runtime_" + "lock",
    "capability_" + "token",
    "team_" + "agents",
    "multi_" + "context_",
)

SCAN_ROOTS = (
    DEBUGGER_ROOT / "common" / "docs",
    DEBUGGER_ROOT / "common" / "hooks",
    DEBUGGER_ROOT / "platforms",
    DEBUGGER_ROOT / "scripts",
    DEBUGGER_ROOT / "README.md",
)


def _iter_text_files():
    for item in SCAN_ROOTS:
        if item.is_file():
            yield item
            continue
        for path in item.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.name == "tool_catalog.snapshot.json":
                continue
            yield path


class RepoBaselineValidationTests(unittest.TestCase):
    def test_core_docs_reference_runtime_broker_artifacts(self) -> None:
        for path in [
            DEBUGGER_ROOT / "common" / "AGENT_CORE.md",
            DEBUGGER_ROOT / "common" / "docs" / "runtime-coordination-model.md",
            DEBUGGER_ROOT / "platforms" / "codex" / "AGENTS.md",
        ]:
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("runtime_session.yaml", text)
            self.assertIn("runtime_snapshot.yaml", text)
            self.assertIn("ownership_lease.yaml", text)
            self.assertIn("runtime_failure.yaml", text)

    def test_repo_wrappers_do_not_reintroduce_removed_runtime_contract_terms(self) -> None:
        offenders: list[str] = []
        for path in _iter_text_files():
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            for marker in BANNED_MARKERS:
                if marker in text:
                    offenders.append(f"{path}: {marker}")
        self.assertFalse(offenders, "\n".join(offenders[:50]))


if __name__ == "__main__":
    unittest.main()
