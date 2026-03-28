"""
Fail fast on non-UTF-8 files and high-confidence mojibake sequences.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_PATHS = ("agent/src", "agent/tests", "scripts", "src", ".github/workflows")
SCAN_EXTENSIONS = {
    ".py",
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".sh",
}
SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".next",
    "vendor",
    "test_outputs",
    "test_reports",
    "renders",
    "__pycache__",
}
HIGH_CONFIDENCE_MOJIBAKE = (
    "鈥?",
    "銆傦紒锛燂紱",
    "灏侀潰",
    "鎬荤粨",
    "鏆傛棤",
    "鏈〉",
    "鐩綍",
    "琛ㄦ牸",
    "鍐呭",
    "浠嬬粛",
)


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES or part.startswith(".tmp") for part in path.parts)


def iter_candidate_files(root: Path, paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        base = (root / raw).resolve()
        if not base.exists():
            continue
        if base.is_file():
            if base.suffix.lower() in SCAN_EXTENSIONS and not should_skip(base):
                files.append(base)
            continue
        for item in base.rglob("*"):
            if not item.is_file():
                continue
            if item.suffix.lower() not in SCAN_EXTENSIONS:
                continue
            if should_skip(item):
                continue
            files.append(item)
    return files


def scan_file(path: Path) -> list[str]:
    issues: list[str] = []
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        issues.append(f"{path}: non-utf8 ({exc})")
        return issues

    if "\ufffd" in text:
        issues.append(f"{path}: contains replacement character U+FFFD")

    if path.name == "check_encoding_hygiene.py":
        return issues

    for index, line in enumerate(text.splitlines(), start=1):
        if "encoding-hygiene: allow-mojibake-tokens" in line:
            continue
        for token in HIGH_CONFIDENCE_MOJIBAKE:
            if token in line:
                issues.append(f"{path}:{index}: suspicious mojibake token `{token}`")
                break
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paths",
        nargs="*",
        default=list(DEFAULT_PATHS),
        help="Relative paths to scan.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    files = iter_candidate_files(root, args.paths)
    issues: list[str] = []
    for file in files:
        issues.extend(scan_file(file))

    if issues:
        _safe_print("Encoding hygiene check failed:")
        for issue in issues:
            _safe_print(f"- {issue}")
        return 1

    _safe_print(f"Encoding hygiene check passed ({len(files)} files scanned).")
    return 0


def _safe_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        fallback = message.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8",
            errors="replace",
        )
        print(fallback)


if __name__ == "__main__":
    sys.exit(main())
