#!/usr/bin/env python3
"""Validate generated platform layout against repo baseline rules."""

from __future__ import annotations

import argparse
from pathlib import Path

import sync_platform_scaffolds


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTS = {".md", ".json", ".toml", ".txt", ".yaml", ".yml", ".py"}
FORBIDDEN_MARKERS = (
    "direct-reference",
    "".join(["depre", "cated"]),
    "transitional",
    "".join(["leg", "acy"]),
    "本目录直接引用仓库中的共享",
    "运行时共享文档统一直接引用仓库中的",
    "禁止复制或镜像 `common/` 内容",
)
BROKEN_MARKERS = ("\u0007rtifacts", "\u0007ction_chain")


def validate_layout(strict: bool = False) -> list[str]:
    findings: list[str] = []

    for artifact in (".claude", ".github", ".codex", ".agents"):
        path = ROOT / artifact
        if path.exists():
            findings.append(f"source root must not contain host artifact: {path}")

    ctx = sync_platform_scaffolds.load_context(ROOT)
    findings.extend(sync_platform_scaffolds.validate_source_tree(ctx))
    for platform_key in ctx["platform_capabilities"]["platforms"]:
        findings.extend(sync_platform_scaffolds.collect_findings(ctx, platform_key))

    platform_root = ROOT / "platforms"
    for file_path in platform_root.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in TEXT_EXTS:
            continue
        if "/common/" in file_path.as_posix():
            continue
        text = file_path.read_text(encoding="utf-8-sig", errors="ignore")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                findings.append(f"forbidden removed text in {file_path}: {marker}")
        for marker in BROKEN_MARKERS:
            if marker in text:
                findings.append(f"broken generated text in {file_path}: {marker}")
        if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in text):
            findings.append(f"control character found in generated text file: {file_path}")

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate debugger platform layout")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when findings exist")
    args = parser.parse_args(argv)

    findings = validate_layout(strict=args.strict)
    if findings:
        print("[platform layout findings]")
        for row in findings:
            print(f" - {row}")
        return 1 if args.strict else 0

    print("platform layout validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
