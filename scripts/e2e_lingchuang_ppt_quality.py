"""
Quality baseline harness for LingChuang PPT outputs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

try:
    from src.ppt_quality_gate import validate_deck, validate_layout_diversity
except Exception:  # pragma: no cover
    validate_deck = None
    validate_layout_diversity = None


PLACEHOLDER_PATTERNS = [
    re.compile(r"\b(?:xxxx|todo|tbd|placeholder)\b", re.IGNORECASE),
    re.compile(r"lorem ipsum", re.IGNORECASE),
    re.compile(r"\?\?\?"),
    re.compile(r"(待补充|请填写|占位符)"),
]


def _load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _slide_texts(slide: Dict[str, Any]) -> List[str]:
    texts: List[str] = []
    for key in ("title", "narration", "speaker_notes"):
        value = str(slide.get(key) or "").strip()
        if value:
            texts.append(value)
    for element in slide.get("elements") or []:
        if not isinstance(element, dict):
            continue
        if str(element.get("type") or "").lower() != "text":
            continue
        content = str(element.get("content") or "").strip()
        if content:
            texts.append(content)
    return texts


def _is_garbled(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    if "\ufffd" in s:
        return True
    mojibake_tokens = ("鈥", "锛", "鍙", "鐨", "銆", "闄")
    if sum(s.count(token) for token in mojibake_tokens) >= 2 and len(s) >= 6:
        return True
    q_ratio = s.count("?") / max(1, len(s))
    return s.count("?") >= 3 and q_ratio >= 0.15


def evaluate_quality(
    slides: List[Dict[str, Any]],
    keywords: List[str],
    min_slides: int,
    *,
    quality_profile: str = "default",
) -> Dict[str, Any]:
    joined = "\n".join("\n".join(_slide_texts(slide)) for slide in slides)
    joined_lower = joined.lower()

    keyword_hits = {kw: (kw.lower() in joined_lower) for kw in keywords if kw}
    missing_keywords = [kw for kw, hit in keyword_hits.items() if not hit]

    placeholder_hits: List[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(joined):
            placeholder_hits.append(pattern.pattern)

    garbled_samples: List[str] = []
    for slide in slides:
        for text in _slide_texts(slide):
            if _is_garbled(text):
                garbled_samples.append(text[:120])
            if len(garbled_samples) >= 5:
                break
        if len(garbled_samples) >= 5:
            break

    titles = [str(slide.get("title") or "").strip() for slide in slides]
    has_toc = any("目录" in t or "table of contents" in t.lower() for t in titles)
    has_cover = bool(titles and titles[0])

    checks = {
        "min_slides": len(slides) >= min_slides,
        "keywords": len(missing_keywords) == 0,
        "no_placeholder": len(placeholder_hits) == 0,
        "no_garbled": len(garbled_samples) == 0,
        "has_cover_title": has_cover,
        "has_toc_or_section": has_toc or len(slides) >= 8,
    }
    quality_gate = {"enabled": False, "ok": True, "issues": []}
    if callable(validate_deck) and callable(validate_layout_diversity):
        content_result = validate_deck(slides, profile=quality_profile)
        layout_result = validate_layout_diversity({"slides": slides}, profile=quality_profile)
        merged = [*content_result.issues, *layout_result.issues]
        quality_gate = {
            "enabled": True,
            "profile": quality_profile,
            "ok": len(merged) == 0,
            "issues": [
                {
                    "slide_id": issue.slide_id,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in merged[:50]
            ],
        }
        checks["quality_gate"] = quality_gate["ok"]
    ok = all(checks.values())
    return {
        "ok": ok,
        "checks": checks,
        "slide_count": len(slides),
        "min_slides": min_slides,
        "keyword_hits": keyword_hits,
        "missing_keywords": missing_keywords,
        "placeholder_hits": placeholder_hits,
        "garbled_samples": garbled_samples,
        "quality_gate": quality_gate,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="test_outputs/lingchuang_ppt")
    parser.add_argument(
        "--require-keywords",
        default="灵创智能,AI营销,数字人",
        help="Comma-separated keywords that must appear in generated slides.",
    )
    parser.add_argument("--min-slides", type=int, default=8)
    parser.add_argument("--quality-profile", default="default")
    parser.add_argument(
        "--report-path",
        default="test_reports/ppt/lingchuang_quality_baseline.json",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    slides = _load_json(input_dir / "slides.json", [])
    if not isinstance(slides, list):
        slides = []
    keywords = [item.strip() for item in str(args.require_keywords).split(",") if item.strip()]

    report = evaluate_quality(
        slides=slides,
        keywords=keywords,
        min_slides=args.min_slides,
        quality_profile=args.quality_profile,
    )
    report.update(
        {
            "input_dir": str(input_dir),
            "report_path": args.report_path,
        }
    )

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
