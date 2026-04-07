#!/usr/bin/env python3
"""Sync ppt-master template assets and expand local template catalog.

This script does two things:
1. Copy the upstream ppt-master skill folder into this repo vendor tree.
2. Expand ``agent/src/ppt_specs/template-catalog.json`` with ``pm_*`` families
   generated from ``layouts_index.json`` metadata.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PPT_MASTER_ROOT = Path(r"D:\private\test\ppt-master\skills\ppt-master")
DEFAULT_VENDOR_SKILL_DIR = REPO_ROOT / "vendor" / "minimax-skills" / "skills" / "ppt-master"
CATALOG_PATH = REPO_ROOT / "agent" / "src" / "ppt_specs" / "template-catalog.json"

_LAYOUT_ID_MAP: Dict[str, Dict[str, str]] = {
    "academic_defense": {"template_id": "pm_academic_defense_light", "source_key": "academic_defense"},
    "ai_ops": {"template_id": "pm_ai_ops_light", "source_key": "ai_ops"},
    "anthropic": {"template_id": "pm_anthropic_light", "source_key": "anthropic"},
    "exhibit": {"template_id": "pm_exhibit_dark", "source_key": "exhibit"},
    "google_style": {"template_id": "pm_google_style_light", "source_key": "google_style"},
    "government_blue": {"template_id": "pm_government_blue_light", "source_key": "government_blue"},
    "government_red": {"template_id": "pm_government_red_light", "source_key": "government_red"},
    "mckinsey": {"template_id": "pm_mckinsey_light", "source_key": "mckinsey"},
    "medical_university": {"template_id": "pm_medical_university_light", "source_key": "medical_university"},
    "pixel_retro": {"template_id": "pm_pixel_retro_dark", "source_key": "pixel_retro"},
    "psychology_attachment": {"template_id": "pm_psychology_attachment_light", "source_key": "psychology_attachment"},
    "smart_red": {"template_id": "pm_smart_red_light", "source_key": "smart_red"},
    "中国电建_常规": {"template_id": "pm_powerchina_standard_light", "source_key": "powerchina_standard"},
    "中国电建_现代": {"template_id": "pm_powerchina_modern_light", "source_key": "powerchina_modern"},
    "中汽研_商务": {"template_id": "pm_catarc_business_light", "source_key": "catarc_business"},
    "中汽研_常规": {"template_id": "pm_catarc_standard_light", "source_key": "catarc_standard"},
    "中汽研_现代": {"template_id": "pm_catarc_modern_light", "source_key": "catarc_modern"},
    "招商银行": {"template_id": "pm_cmb_finance_light", "source_key": "cmb_finance"},
    "科技蓝商务": {"template_id": "pm_tech_blue_business_light", "source_key": "tech_blue_business"},
    "重庆大学": {"template_id": "pm_chongqing_university_light", "source_key": "chongqing_university"},
}

_COMMON_BLOCK_TYPES = [
    "title",
    "subtitle",
    "body",
    "list",
    "quote",
    "icon_text",
    "image",
    "chart",
    "kpi",
    "table",
    "workflow",
    "diagram",
    "comparison",
]


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _contains_any(text: str, needles: List[str]) -> bool:
    source = str(text or "").lower()
    return any(n.lower() in source for n in needles)


def _pick_skill_profile(layout_name: str, summary: str, keywords: List[str]) -> str:
    hint = " ".join([layout_name, summary, " ".join(keywords)]).lower()
    if _contains_any(hint, ["mckinsey", "exhibit", "finance", "bank", "consulting", "strategy"]):
        return "consulting-recommendation"
    if _contains_any(hint, ["ai", "ops", "anthropic", "tech", "technology", "government"]):
        return "architecture-explainer"
    if _contains_any(hint, ["academic", "medical", "university", "psychology", "education"]):
        return "education-textbook"
    if _contains_any(hint, ["pixel", "retro", "creative"]):
        return "bento-showcase"
    return "general-content"


def _pick_quality_profile(layout_name: str, summary: str, keywords: List[str]) -> str:
    hint = " ".join([layout_name, summary, " ".join(keywords)]).lower()
    if _contains_any(hint, ["mckinsey", "exhibit", "ai", "ops", "government", "finance", "strategy"]):
        return "high_density_consulting"
    if _contains_any(hint, ["academic", "medical", "university", "psychology", "education"]):
        return "training_deck"
    return "default"


def _pick_contract_profile(layout_name: str, summary: str, keywords: List[str]) -> str:
    hint = " ".join([layout_name, summary, " ".join(keywords)]).lower()
    if _contains_any(hint, ["strategy", "comparison", "consulting"]):
        return "default"
    if _contains_any(hint, ["ai", "ops", "architecture", "process", "flow"]):
        return "hierarchy_blocks_required"
    if _contains_any(hint, ["academic", "medical", "university", "education"]):
        return "default"
    return "default"


def _pick_header_style(template_id: str, summary: str, tone: str) -> str:
    hint = f"{template_id} {summary}".lower()
    if "pixel" in hint:
        return "gradient"
    if "mckinsey" in hint or "google" in hint:
        return "underline-light"
    if tone == "dark":
        return "gradient"
    return "underline-light"


def _pick_density(template_id: str, summary: str) -> Dict[str, str]:
    hint = f"{template_id} {summary}".lower()
    if _contains_any(hint, ["ai_ops", "mckinsey", "exhibit", "government", "finance"]):
        return {"min": "balanced", "max": "dense", "recommended": "balanced"}
    if _contains_any(hint, ["academic", "medical", "psychology", "university"]):
        return {"min": "sparse", "max": "balanced", "recommended": "balanced"}
    return {"min": "balanced", "max": "dense", "recommended": "balanced"}


def _pick_tone(template_id: str) -> str:
    if str(template_id).endswith("_dark"):
        return "dark"
    return "light"


def _build_template_entry(layout_name: str, row: Dict[str, Any]) -> tuple[str, Dict[str, Any], List[str]]:
    mapped = _LAYOUT_ID_MAP.get(layout_name)
    if not mapped:
        return "", {}, []
    template_id = str(mapped.get("template_id") or "").strip()
    source_key = str(mapped.get("source_key") or "").strip() or layout_name
    if not template_id:
        return "", {}, []
    summary = str(row.get("summary") or "")
    keywords = [str(item).strip() for item in _as_list(row.get("keywords")) if str(item).strip()]
    tone = _pick_tone(template_id)
    density = _pick_density(template_id, summary)
    skill_profile = _pick_skill_profile(layout_name, summary, keywords)
    quality_profile = _pick_quality_profile(layout_name, summary, keywords)
    contract_profile = _pick_contract_profile(layout_name, summary, keywords)
    header_style = _pick_header_style(template_id, summary, tone)
    entry = {
        "skill_profile": skill_profile,
        "hardness_profile": "balanced",
        "schema_profile": f"ppt-template/v2-ppt-master-{source_key}",
        "contract_profile": contract_profile,
        "quality_profile": quality_profile,
        "header_style": header_style,
        "source_layout": source_key,
        "source_pack": "ppt-master",
        "tone": tone,
        "requires_keyword_match": True,
        "capabilities": {
            "supported_slide_types": ["cover", "toc", "divider", "content", "comparison", "data", "summary", "timeline"],
            "supported_layouts": ["hero_1", "split_2", "asymmetric_2", "grid_3", "grid_4", "timeline", "bento_5"],
            "supported_block_types": _COMMON_BLOCK_TYPES,
            "density_range": density,
            "visual_anchor_capacity": 2,
            "data_block_capacity": 2,
        },
    }
    all_keywords = [source_key, template_id] + keywords
    return template_id, entry, [w for w in all_keywords if str(w).strip()]


def _sync_vendor_skill(source_skill_dir: Path, vendor_skill_dir: Path) -> None:
    if not source_skill_dir.exists():
        raise FileNotFoundError(f"ppt-master source dir not found: {source_skill_dir}")
    vendor_skill_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_skill_dir, vendor_skill_dir, dirs_exist_ok=True)


def _sync_template_catalog(source_skill_dir: Path, catalog_path: Path) -> Dict[str, Any]:
    layouts_index_path = source_skill_dir / "templates" / "layouts" / "layouts_index.json"
    if not layouts_index_path.exists():
        raise FileNotFoundError(f"layouts_index.json not found: {layouts_index_path}")
    layouts_index = json.loads(layouts_index_path.read_text(encoding="utf-8"))

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    templates = _as_dict(catalog.get("templates"))
    keyword_rules = _as_list(catalog.get("keyword_rules"))

    # Remove stale imported pm_* keyword rules before rebuild.
    fresh_rules: List[Dict[str, Any]] = []
    for rule in keyword_rules:
        if not isinstance(rule, dict):
            continue
        target = str(rule.get("template") or "").strip()
        if target.startswith("pm_"):
            continue
        fresh_rules.append(rule)

    imported_count = 0
    imported_ids: List[str] = []
    for layout_name, row in sorted(_as_dict(layouts_index.get("layouts")).items(), key=lambda kv: str(kv[0])):
        if not isinstance(row, dict):
            continue
        template_id, entry, keywords = _build_template_entry(str(layout_name), row)
        if not template_id:
            continue
        templates[template_id] = entry
        fresh_rules.append({"template": template_id, "keywords": keywords})
        imported_count += 1
        imported_ids.append(template_id)

    catalog["templates"] = templates
    catalog["keyword_rules"] = fresh_rules
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "imported_count": imported_count,
        "imported_template_ids": imported_ids,
        "catalog_path": str(catalog_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync ppt-master templates into this repository")
    parser.add_argument(
        "--source-skill-dir",
        default=str(DEFAULT_PPT_MASTER_ROOT),
        help="Path to upstream ppt-master skill directory",
    )
    parser.add_argument(
        "--vendor-skill-dir",
        default=str(DEFAULT_VENDOR_SKILL_DIR),
        help="Destination vendor path inside this repository",
    )
    parser.add_argument(
        "--catalog",
        default=str(CATALOG_PATH),
        help="Path to template-catalog.json",
    )
    parser.add_argument(
        "--skip-copy",
        action="store_true",
        help="Only update template-catalog without copying vendor skill folder",
    )
    args = parser.parse_args()

    source_skill_dir = Path(args.source_skill_dir).resolve()
    vendor_skill_dir = Path(args.vendor_skill_dir).resolve()
    catalog_path = Path(args.catalog).resolve()

    if not args.skip_copy:
        _sync_vendor_skill(source_skill_dir, vendor_skill_dir)

    summary = _sync_template_catalog(source_skill_dir, catalog_path)
    summary["source_skill_dir"] = str(source_skill_dir)
    summary["vendor_skill_dir"] = str(vendor_skill_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
