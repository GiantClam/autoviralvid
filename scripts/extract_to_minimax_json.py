#!/usr/bin/env python3
"""
Extract PPT information to minimax JSON format for comparison.
"""

import zipfile
import xml.etree.ElementTree as ET
import json
import re
import base64
import posixpath
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import PurePosixPath


@dataclass
class TextElement:
    type: str = "text"
    content: str = ""
    top: float = 0.0
    left: float = 0.0
    width: float = 0.0
    height: float = 0.0
    font_size: int = 0  # Font size in points
    font_name: str = ""
    font_color: str = ""
    bold: bool = False
    italic: bool = False
    align: str = ""
    z_index: int = 0


@dataclass
class ShapeElement:
    type: str = "shape"  # shape, rectangle, roundRect, etc.
    subtype: str = ""
    top: float = 0.0
    left: float = 0.0
    width: float = 0.0
    height: float = 0.0
    rotation: float = 0.0
    z_index: int = 0
    fill_color: str = ""
    fill_transparency: float = 0.0
    line_color: str = ""
    line_width_pt: float = 0.0
    line_transparency: float = 0.0
    line_dash: str = ""
    has_text: bool = False
    text_content: str = ""
    image_base64: str = ""
    image_ext: str = ""
    media_path: str = ""
    media_rid: str = ""


@dataclass
class VisualInfo:
    shapes: List[ShapeElement] = None
    images: int = 0
    background_color: str = ""
    has_gradient_bg: bool = False

    def __post_init__(self):
        if self.shapes is None:
            self.shapes = []


@dataclass
class Block:
    block_type: str
    type: str
    card_id: str = ""
    id: str = ""
    content: str = ""
    label: str = ""
    emphasis: List[str] = None

    def __post_init__(self):
        if self.emphasis is None:
            self.emphasis = []


@dataclass
class Slide:
    page_number: int
    slide_id: str
    id: str
    slide_type: str
    title: str = ""
    blocks: List[Block] = None
    elements: List[TextElement] = None
    shapes: List[ShapeElement] = None
    visual: VisualInfo = None
    slide_layout_path: str = ""
    slide_layout_name: str = ""
    slide_master_path: str = ""
    slide_theme_path: str = ""
    media_refs: List[Dict[str, str]] = None

    def __post_init__(self):
        if self.blocks is None:
            self.blocks = []
        if self.elements is None:
            self.elements = []
        if self.shapes is None:
            self.shapes = []
        if self.visual is None:
            self.visual = VisualInfo()
        if self.media_refs is None:
            self.media_refs = []


@dataclass
class Theme:
    palette: str = "custom"
    style: str = "sharp"
    primary: str = ""
    secondary: str = ""
    accent: str = ""
    bg: str = "FFFFFF"


# Constants
EMU_PER_INCH = 914400
EMU_PER_POINT = 12700
SYSTEM_COLOR_MAP = {
    "window": "FFFFFF",
    "windowText": "000000",
    "btnFace": "F0F0F0",
    "highlight": "0078D4",
}
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
    ".wmf",
    ".emf",
    ".svg",
}

_EXTRA_TEMPLATE_KEYWORDS: Dict[str, List[str]] = {
    "pm_government_blue_light": [
        "government",
        "government affairs",
        "policy",
        "international",
        "diplomacy",
        "security",
        "strategy",
        "government_blue",
        "鏀垮姟",
        "鏀垮簻",
        "鏀跨瓥",
        "鍥介檯鍏崇郴",
        "澶栦氦",
        "鍗辨満",
        "娴峰场",
        "鍦扮紭",
        "瀹夊叏",
        "鎴樼暐",
    ],
    "pm_government_red_light": [
        "government",
        "party building",
        "authoritative",
        "government_red",
        "鍏氬缓",
        "鍏氭斂",
        "鏀跨瓥",
        "鏀垮姟",
    ],
    "pm_academic_defense_light": [
        "academic",
        "defense",
        "research",
        "thesis",
        "璇惧爞",
        "鏁欏",
        "瀛︽湳",
        "璁烘枃",
        "绛旇京",
    ],
    "pm_chongqing_university_light": [
        "university",
        "academic",
        "defense",
        "楂樻牎",
        "澶у",
        "鐮旂┒",
        "瀛︽湳",
    ],
    "pm_mckinsey_light": [
        "consulting",
        "strategy",
        "structured",
        "executive presentation",
        "鍜ㄨ",
        "鎴樼暐",
        "鍒嗘瀽",
    ],
}


def _parse_hex_rgb(color: str) -> Optional[Tuple[int, int, int]]:
    raw = str(color or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        return None
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _is_dark_hex(color: str) -> bool:
    rgb = _parse_hex_rgb(color)
    if not rgb:
        return False
    r, g, b = rgb
    # Relative luminance approximation on sRGB.
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return luminance < 128


def _should_count_keyword(token: str) -> bool:
    t = str(token or "").strip().lower()
    if not t:
        return False
    if re.fullmatch(r"[a-z0-9]+", t):
        return len(t) >= 4
    if re.search(r"[\u4e00-\u9fff]", t):
        return len(t) >= 2
    return len(t) >= 3


def parse_hex_color(value: str) -> str:
    """Parse hex color value."""
    if not value:
        return ""
    value = value.strip().upper().lstrip("#")
    return value


def emu_to_inches(emu: int) -> float:
    """Convert EMU to inches."""
    return emu / EMU_PER_INCH


def emu_to_points(emu: int) -> float:
    """Convert EMU to points."""
    return emu / EMU_PER_POINT


def _dedupe_texts(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        key = re.sub(r"\s+", " ", text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _pick_emphasis_tokens(text: str, fallback: str = "primary") -> List[str]:
    source = str(text or "")
    if not source.strip():
        return [fallback]

    numeric_hits = re.findall(r"\d+(?:\.\d+)?%?", source)
    if numeric_hits:
        return numeric_hits[:2]

    words = [
        w.strip() for w in re.split(r"[\s,锛屻€傦紱;:锛?)锛堬級/]+", source) if w.strip()
    ]
    for word in words:
        if len(word) >= 2:
            return [word[:14]]
    return [fallback]


class PPTXMinimaxExtractor:
    """Extract PPTX information in minimax JSON format."""

    def __init__(self, pptx_path: str):
        self.pptx_path = pptx_path
        self.zip_file = zipfile.ZipFile(pptx_path, "r")
        self.theme_color_map: Dict[str, str] = {}
        self.ns = {
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }

    def extract_all(self) -> Dict[str, Any]:
        """Extract all information and return as minimax JSON dict."""
        dimensions = self._get_dimensions()
        theme = self._extract_theme()
        theme_manifest = self._extract_theme_manifest()
        master_layout_manifest = self._extract_master_layout_manifest()
        media_manifest = self._extract_media_manifest()
        slides = self._extract_slides()
        fonts = self._extract_unique_fonts()

        # Determine slide types based on content
        for slide in slides:
            self._infer_slide_type(slide)
        template_profile = self._infer_template_profile(slides=slides, theme=theme)

        return {
            "title": self._extract_title_from_first_slide(slides),
            "author": "Extracted from PPT",
            "source_pptx_path": str(Path(self.pptx_path).resolve()),
            "theme": asdict(theme),
            "theme_color_map": dict(self.theme_color_map),
            "theme_manifest": theme_manifest,
            "master_layout_manifest": master_layout_manifest,
            "media_manifest": media_manifest,
            "template_family": template_profile["template_family"],
            "template_id": template_profile["template_id"],
            "skill_profile": template_profile["skill_profile"],
            "hardness_profile": "balanced",
            "schema_profile": "auto",
            "contract_profile": "default",
            "quality_profile": "default",
            "design_spec": {
                "colors": {
                    "primary": theme.primary,
                    "secondary": theme.secondary,
                    "accent": theme.accent,
                    "background": theme.bg,
                },
                "typography": {
                    "fonts": list(fonts)[:5],
                },
                "spacing": {},
                "visual": {
                    "style_recipe": theme.style,
                    "visual_priority": True,
                    "visual_density": "balanced",
                },
            },
            "visual_priority": True,
            "visual_preset": "executive_brief",
            "visual_density": "balanced",
            "dimensions": {
                "width_inches": emu_to_inches(dimensions[0]),
                "height_inches": emu_to_inches(dimensions[1]),
            },
            "fonts": list(fonts),
            "slides": [asdict(s) for s in slides],
        }

    def _infer_template_profile(
        self,
        *,
        slides: List[Slide],
        theme: Theme,
    ) -> Dict[str, str]:
        """Infer template hints from extracted deck content."""
        fallback = {
            "template_family": "auto",
            "template_id": "auto",
            "skill_profile": "auto",
        }
        catalog_path = (
            Path(__file__).resolve().parents[1]
            / "agent"
            / "src"
            / "ppt_specs"
            / "template-catalog.json"
        )
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except Exception:
            return fallback

        templates = (
            catalog.get("templates") if isinstance(catalog.get("templates"), dict) else {}
        )
        keyword_rules = (
            catalog.get("keyword_rules") if isinstance(catalog.get("keyword_rules"), list) else []
        )
        if not templates:
            return fallback

        keywords_by_template: Dict[str, List[str]] = {}
        for row in keyword_rules:
            if not isinstance(row, dict):
                continue
            template_id = str(row.get("template") or "").strip().lower()
            keywords = row.get("keywords")
            if not template_id or not isinstance(keywords, list):
                continue
            words = keywords_by_template.setdefault(template_id, [])
            for kw in keywords:
                token = str(kw or "").strip()
                if token:
                    words.append(token)

        blob_parts: List[str] = []
        blob_parts.append(str(Path(self.pptx_path).stem or ""))
        blob_parts.append(str(Path(self.pptx_path).name or ""))
        blob_parts.append(self._extract_title_from_first_slide(slides))
        for slide in slides:
            blob_parts.extend(
                [
                    str(slide.title or ""),
                    str(slide.slide_layout_name or ""),
                    str(slide.slide_layout_path or ""),
                    str(slide.slide_master_path or ""),
                    str(slide.slide_theme_path or ""),
                ]
            )
            for block in slide.blocks or []:
                blob_parts.append(str(block.content or ""))
                blob_parts.append(str(block.label or ""))
                for emphasis in block.emphasis or []:
                    blob_parts.append(str(emphasis or ""))
            for element in slide.elements or []:
                blob_parts.append(str(element.content or ""))
        blob = " ".join(part.strip().lower() for part in blob_parts if str(part).strip())

        prefers_dark = _is_dark_hex(theme.bg) and _is_dark_hex(theme.primary)
        best_template = ""
        best_score = 0.0
        for template_id, template_row_raw in templates.items():
            template = str(template_id or "").strip().lower()
            if not template:
                continue
            template_row = template_row_raw if isinstance(template_row_raw, dict) else {}
            words = list(keywords_by_template.get(template, []))
            words.extend(_EXTRA_TEMPLATE_KEYWORDS.get(template, []))
            score = 0.0
            matched = 0
            seen: set[str] = set()
            for kw in words:
                token = str(kw or "").strip().lower()
                if not _should_count_keyword(token):
                    continue
                if token in seen:
                    continue
                seen.add(token)
                if token in blob:
                    matched += 1
            score += float(matched)
            tone = str(template_row.get("tone") or "").strip().lower()
            if tone in {"light", "dark"}:
                if prefers_dark and tone == "dark":
                    score += 0.25
                elif (not prefers_dark) and tone == "light":
                    score += 0.25
            if str(template_row.get("source_pack") or "").strip().lower() == "ppt-master":
                score += 0.1
            if score > best_score:
                best_score = score
                best_template = template

        if not best_template or best_score < 1.0:
            return fallback

        chosen = templates.get(best_template) if isinstance(templates.get(best_template), dict) else {}
        return {
            "template_family": best_template,
            "template_id": best_template,
            "skill_profile": str(chosen.get("skill_profile") or "general-content"),
        }

    def _get_dimensions(self) -> Tuple[int, int]:
        """Get slide dimensions from presentation.xml."""
        try:
            content = self.zip_file.read("ppt/presentation.xml")
            root = ET.fromstring(content)
            for elem in root.iter():
                if "sldSz" in elem.tag:
                    cx = int(elem.get("cx", 0))
                    cy = int(elem.get("cy", 0))
                    return cx, cy
        except Exception:
            pass
        return (12192000, 6858000)  # Default 13.33 x 7.5 inches

    def _extract_theme(self) -> Theme:
        """Extract theme colors from theme files.

        Note: PPTX can have multiple themes. theme2.xml often contains the red/orange theme.
        """
        theme = Theme()

        # Try theme2.xml first (contains red #C0504D in accent2)
        theme_files_to_try = [
            "ppt/theme/theme2.xml",  # Red theme
            "ppt/theme/theme1.xml",  # Blue theme (fallback)
        ]

        for theme_file in theme_files_to_try:
            try:
                if theme_file not in self.zip_file.namelist():
                    continue

                content = self.zip_file.read(theme_file)
                root = ET.fromstring(content)

                for elem in root.iter():
                    if "clrScheme" in elem.tag:
                        theme_colors = {}
                        for clr in elem:
                            tag = clr.tag.split("}")[1] if "}" in clr.tag else clr.tag

                            # Get srgbClr value
                            srgb = clr.find(
                                ".//{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr"
                            )
                            if srgb is not None:
                                val = srgb.get("val", "")
                                if val:
                                    theme_colors[tag] = val
                            else:
                                # Get sysClr lastClr value
                                sys_clr = clr.find(
                                    ".//{http://schemas.openxmlformats.org/drawingml/2006/main}sysClr"
                                )
                                if sys_clr is not None:
                                    last_clr = sys_clr.get("lastClr", "")
                                    if last_clr:
                                        theme_colors[tag] = last_clr

                        # Map to theme fields
                        # For this PPT: RED (#C0504D) is the main accent color, WHITE is background
                        # In theme2: accent2 = red, lt1 = white
                        # We map: accent2 -> primary (red), lt1 -> bg (white)
                        accent1 = theme_colors.get("accent1", "")  # Blue
                        accent2 = theme_colors.get("accent2", "")  # Red
                        lt1 = theme_colors.get("lt1", "FFFFFF")  # White
                        lt2 = theme_colors.get("lt2", "EEECE1")  # Light gray/cream

                        # Use red (#C0504D) as primary if available, otherwise use accent1
                        if accent2 and accent2.upper() in [
                            "C0504D",
                            "B10F2E",
                            "C00000",
                        ]:
                            theme.primary = accent2  # Red
                            theme.secondary = accent1 if accent1 else lt2
                        else:
                            theme.primary = accent1 if accent1 else accent2
                            theme.secondary = accent2 if accent2 else lt2

                        theme.accent = lt2  # Light accent
                        theme.bg = lt1  # Background (white)
                        self.theme_color_map = {
                            k: v.upper()
                            for k, v in theme_colors.items()
                            if isinstance(v, str) and v
                        }
                        # Resolve common scheme aliases used in shapes/runs.
                        # In most PPT themes: tx1->dk1, bg1->lt1, tx2->dk2, bg2->lt2.
                        if "tx1" not in self.theme_color_map and "dk1" in self.theme_color_map:
                            self.theme_color_map["tx1"] = self.theme_color_map["dk1"]
                        if "bg1" not in self.theme_color_map and "lt1" in self.theme_color_map:
                            self.theme_color_map["bg1"] = self.theme_color_map["lt1"]
                        if "tx2" not in self.theme_color_map and "dk2" in self.theme_color_map:
                            self.theme_color_map["tx2"] = self.theme_color_map["dk2"]
                        if "bg2" not in self.theme_color_map and "lt2" in self.theme_color_map:
                            self.theme_color_map["bg2"] = self.theme_color_map["lt2"]

                        print(f"  浣跨敤涓婚鏂囦欢: {theme_file}")
                        print(f"  璇嗗埆鐨勪富鑹?绾㈣壊): #{theme.primary}")
                        print(f"  璇嗗埆鐨勮儗鏅?鐧借壊): #{theme.bg}")

                        # If we found valid colors, use this theme
                        if theme.primary and theme.secondary:
                            return theme
            except Exception as e:
                print(f"Error parsing {theme_file}: {e}")

        return theme

    def _extract_unique_fonts(self) -> set:
        """Extract unique fonts used in the presentation."""
        fonts = set()

        slide_files = [
            f
            for f in self.zip_file.namelist()
            if f.endswith(".xml") and "slides/slide" in f
        ]

        for slide_file in slide_files:
            try:
                content = self.zip_file.read(slide_file)
                root = ET.fromstring(content)

                for elem in root.iter():
                    if elem.tag.endswith("}latin") or "latin" in elem.tag:
                        font = elem.get("typeface")
                        if font and font != "+none":
                            fonts.add(font)
                    if elem.tag.endswith("}ea"):
                        font = elem.get("typeface")
                        if font and font != "+none":
                            fonts.add(font)
            except Exception:
                pass

        return fonts

    def _resolve_rel_target(self, source_part: str, target: str) -> str:
        src = PurePosixPath(source_part)
        resolved = str((src.parent / target).as_posix())
        normalized = posixpath.normpath(resolved)
        if normalized.startswith("/"):
            normalized = normalized[1:]
        return normalized

    def _load_relationship_entries_for_part(self, source_part: str) -> Dict[str, Dict[str, str]]:
        rels_file = f"{PurePosixPath(source_part).parent.as_posix()}/_rels/{PurePosixPath(source_part).name}.rels"
        if rels_file not in self.zip_file.namelist():
            return {}
        entries: Dict[str, Dict[str, str]] = {}
        try:
            content = self.zip_file.read(rels_file)
            root = ET.fromstring(content)
            for rel in root.iter():
                if not rel.tag.endswith("Relationship"):
                    continue
                rid = str(rel.get("Id", "") or "").strip()
                target = str(rel.get("Target", "") or "").strip()
                rel_type = str(rel.get("Type", "") or "").strip()
                if not rid or not target:
                    continue
                entries[rid] = {
                    "target": self._resolve_rel_target(source_part, target),
                    "type": rel_type,
                }
        except Exception:
            return {}
        return entries

    def _load_slide_relationships(self, slide_num: int) -> Dict[str, str]:
        source_part = f"ppt/slides/slide{slide_num}.xml"
        entries = self._load_relationship_entries_for_part(source_part)
        return {
            rid: row.get("target", "")
            for rid, row in entries.items()
            if str(row.get("target", "")).strip()
        }

    def _extract_media_manifest(self) -> List[Dict[str, Any]]:
        manifest: List[Dict[str, Any]] = []
        names = sorted(
            name
            for name in self.zip_file.namelist()
            if name.startswith("ppt/media/") and not name.endswith("/")
        )
        for name in names:
            try:
                raw = self.zip_file.read(name)
            except Exception:
                continue
            ext = Path(name).suffix.lower()
            mime_type = mimetypes.types_map.get(ext, "application/octet-stream")
            kind = "image" if ext in IMAGE_EXTENSIONS else "binary"
            manifest.append(
                {
                    "path": name,
                    "filename": Path(name).name,
                    "ext": ext.lstrip("."),
                    "mime_type": mime_type,
                    "kind": kind,
                    "size": len(raw),
                    "base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        return manifest

    def _extract_theme_manifest(self) -> List[Dict[str, Any]]:
        manifest: List[Dict[str, Any]] = []
        names = sorted(
            name
            for name in self.zip_file.namelist()
            if name.startswith("ppt/theme/") and name.endswith(".xml")
        )
        for name in names:
            try:
                raw = self.zip_file.read(name)
            except Exception:
                continue
            if not raw:
                continue
            manifest.append(
                {
                    "path": name,
                    "filename": Path(name).name,
                    "size": len(raw),
                    "base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        return manifest

    def _extract_master_layout_manifest(self) -> List[Dict[str, Any]]:
        manifest: List[Dict[str, Any]] = []
        prefixes = (
            "ppt/slideMasters/",
            "ppt/slideLayouts/",
        )
        names = sorted(
            name
            for name in self.zip_file.namelist()
            if any(name.startswith(prefix) for prefix in prefixes) and not name.endswith("/")
        )
        for name in names:
            try:
                raw = self.zip_file.read(name)
            except Exception:
                continue
            if not raw:
                continue
            manifest.append(
                {
                    "path": name,
                    "filename": Path(name).name,
                    "size": len(raw),
                    "base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        return manifest

    def _extract_slide_binding(self, slide_num: int) -> Dict[str, str]:
        source_part = f"ppt/slides/slide{slide_num}.xml"
        entries = self._load_relationship_entries_for_part(source_part)
        out = {
            "slide_layout_path": "",
            "slide_layout_name": "",
            "slide_master_path": "",
            "slide_theme_path": "",
        }
        layout_path = ""
        for row in entries.values():
            rel_type = str(row.get("type", "") or "").lower()
            if rel_type.endswith("/slidelayout"):
                layout_path = str(row.get("target", "") or "").strip()
                break
        if not layout_path:
            return out
        out["slide_layout_path"] = layout_path

        if layout_path in self.zip_file.namelist():
            try:
                layout_root = ET.fromstring(self.zip_file.read(layout_path))
                c_sld = layout_root.find(".//p:cSld", self.ns)
                if c_sld is not None:
                    name = str(c_sld.get("name", "") or "").strip()
                    out["slide_layout_name"] = name or Path(layout_path).stem
                else:
                    out["slide_layout_name"] = Path(layout_path).stem
            except Exception:
                out["slide_layout_name"] = Path(layout_path).stem

        layout_entries = self._load_relationship_entries_for_part(layout_path)
        master_path = ""
        for row in layout_entries.values():
            rel_type = str(row.get("type", "") or "").lower()
            if rel_type.endswith("/slidemaster"):
                master_path = str(row.get("target", "") or "").strip()
                break
        out["slide_master_path"] = master_path
        if not master_path:
            return out

        master_entries = self._load_relationship_entries_for_part(master_path)
        for row in master_entries.values():
            rel_type = str(row.get("type", "") or "").lower()
            if rel_type.endswith("/theme"):
                out["slide_theme_path"] = str(row.get("target", "") or "").strip()
                break
        return out

    def _extract_color_from_container(self, node) -> str:
        if node is None:
            return ""
        try:
            srgb = node.find(".//a:srgbClr", self.ns)
            if srgb is not None:
                return parse_hex_color(str(srgb.get("val", "") or ""))
            sys_clr = node.find(".//a:sysClr", self.ns)
            if sys_clr is not None:
                return parse_hex_color(str(sys_clr.get("lastClr", "") or ""))
            scheme = node.find(".//a:schemeClr", self.ns)
            if scheme is not None:
                key = str(scheme.get("val", "") or "").strip()
                if key and key in self.theme_color_map:
                    return parse_hex_color(self.theme_color_map.get(key, ""))
                if key:
                    return f"scheme:{key}"
        except Exception:
            return ""
        return ""

    def _extract_slide_background(self, slide_root) -> Tuple[str, bool]:
        bg_color = ""
        has_gradient = False
        try:
            bg_pr = slide_root.find(".//p:bg/p:bgPr", self.ns)
            if bg_pr is None:
                return bg_color, has_gradient
            bg_color = self._extract_color_from_container(bg_pr)
            if bg_pr.find(".//a:gradFill", self.ns) is not None:
                has_gradient = True
        except Exception:
            return "", False
        return bg_color, has_gradient

    def _extract_slide_media_refs(
        self, rel_entries: Dict[str, Dict[str, str]]
    ) -> List[Dict[str, str]]:
        refs: List[Dict[str, str]] = []
        for rid, row in rel_entries.items():
            target = str(row.get("target", "") or "").strip()
            rel_type = str(row.get("type", "") or "").strip()
            if not target.startswith("ppt/media/"):
                continue
            refs.append(
                {
                    "rid": rid,
                    "path": target,
                    "type": rel_type,
                }
            )
        return refs

    def _parse_picture_element(
        self, elem, rels_map: Dict[str, str], z_index: int = 0
    ) -> Optional[ShapeElement]:
        try:
            x = y = w = h = 0
            rotation = 0.0
            embed_rid = ""
            for child in elem.iter():
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "xfrm":
                    rot_raw = child.get("rot")
                    if rot_raw:
                        try:
                            rotation = float(rot_raw) / 60000.0
                        except ValueError:
                            rotation = 0.0
                    for xfrm_child in child:
                        sub_tag = (
                            xfrm_child.tag.split("}")[-1]
                            if "}" in xfrm_child.tag
                            else xfrm_child.tag
                        )
                        if sub_tag == "off":
                            x = int(xfrm_child.get("x", "0"))
                            y = int(xfrm_child.get("y", "0"))
                        elif sub_tag == "ext":
                            w = int(xfrm_child.get("cx", "0"))
                            h = int(xfrm_child.get("cy", "0"))
                elif tag == "blip":
                    embed_rid = (
                        child.get(
                            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed",
                            "",
                        )
                        or child.get("embed", "")
                    )

            width_inch = emu_to_inches(w)
            height_inch = emu_to_inches(h)
            if width_inch < 0.05 or height_inch < 0.05:
                return None

            image_base64 = ""
            image_ext = ""
            media_path = ""
            if embed_rid and embed_rid in rels_map:
                media_path = rels_map[embed_rid]
                if media_path in self.zip_file.namelist():
                    raw = self.zip_file.read(media_path)
                    image_base64 = base64.b64encode(raw).decode("ascii")
                    image_ext = Path(media_path).suffix.lstrip(".").lower()

            return ShapeElement(
                type="image",
                subtype="image",
                top=emu_to_inches(y),
                left=emu_to_inches(x),
                width=width_inch,
                height=height_inch,
                rotation=rotation,
                z_index=int(z_index),
                fill_color="",
                line_color="",
                has_text=False,
                text_content="",
                image_base64=image_base64,
                image_ext=image_ext,
                media_path=media_path,
                media_rid=embed_rid,
            )
        except Exception:
            return None

    def _extract_slides(self) -> List[Slide]:
        """Extract information from all slides."""
        slides = []

        slide_files = sorted(
            [
                f
                for f in self.zip_file.namelist()
                if f.endswith(".xml") and "slides/slide" in f
            ],
            key=lambda x: int(re.search(r"slide(\d+)", x).group(1)),
        )

        for slide_file in slide_files:
            slide_num = int(re.search(r"slide(\d+)", slide_file).group(1))

            try:
                content = self.zip_file.read(slide_file)
                root = ET.fromstring(content)
                rel_entries = self._load_relationship_entries_for_part(slide_file)
                rels_map = self._load_slide_relationships(slide_num)
                slide_binding = self._extract_slide_binding(slide_num)

                slide_elements, slide_shapes, slide_image_count = self._extract_visual_from_root(
                    root,
                    rels_map=rels_map,
                    z_base=0,
                    include_placeholders=True,
                )
                layout_elements, layout_shapes, layout_image_count = self._extract_visual_from_part(
                    str(slide_binding.get("slide_layout_path", "") or ""),
                    z_base=-10000,
                    include_placeholders=False,
                )
                master_elements, master_shapes, master_image_count = self._extract_visual_from_part(
                    str(slide_binding.get("slide_master_path", "") or ""),
                    z_base=-20000,
                    include_placeholders=False,
                )

                # Keep render order (master -> layout -> slide) via z_index; for block parsing use position sort.
                elements = master_elements + layout_elements + slide_elements
                shapes = master_shapes + layout_shapes + slide_shapes
                image_count = slide_image_count + layout_image_count + master_image_count
                block_elements = sorted(elements, key=lambda e: (e.top, e.left))

                # Get texts in visual order
                texts = [e.content for e in block_elements if e.content]

                # Create blocks from texts
                blocks = self._create_blocks(texts, slide_num, block_elements)

                # Determine the main title - for cover slide, it's usually the largest/first prominent text
                title = self._extract_main_title(elements, slide_num)
                bg_color, has_gradient_bg = self._extract_slide_background(root)
                media_refs = self._extract_slide_media_refs(rel_entries)

                # Create visual info
                visual = VisualInfo(
                    shapes=shapes,
                    images=image_count,
                    background_color=bg_color,
                    has_gradient_bg=has_gradient_bg,
                )

                slide = Slide(
                    page_number=slide_num,
                    slide_id=f"slide-{slide_num:03d}",
                    id=f"slide-{slide_num:03d}",
                    slide_type="content",  # Default, will be inferred later
                    title=title,
                    blocks=blocks,
                    elements=elements,
                    shapes=shapes,
                    visual=visual,
                    slide_layout_path=str(slide_binding.get("slide_layout_path", "") or ""),
                    slide_layout_name=str(slide_binding.get("slide_layout_name", "") or ""),
                    slide_master_path=str(slide_binding.get("slide_master_path", "") or ""),
                    slide_theme_path=str(slide_binding.get("slide_theme_path", "") or ""),
                    media_refs=media_refs,
                )
                slides.append(slide)

            except Exception as e:
                print(f"Error parsing slide {slide_num}: {e}")

        return slides

    def _is_placeholder_node(self, elem) -> bool:
        try:
            return elem.find(".//p:nvPr/p:ph", self.ns) is not None
        except Exception:
            return False

    def _extract_visual_from_part(
        self,
        part_path: str,
        *,
        z_base: int = 0,
        include_placeholders: bool = False,
    ) -> Tuple[List[TextElement], List[ShapeElement], int]:
        path = str(part_path or "").strip().replace("\\", "/")
        if not path or path not in self.zip_file.namelist():
            return [], [], 0
        try:
            root = ET.fromstring(self.zip_file.read(path))
        except Exception:
            return [], [], 0
        rel_entries = self._load_relationship_entries_for_part(path)
        rels_map = {
            rid: str(row.get("target", "") or "").strip()
            for rid, row in rel_entries.items()
            if isinstance(row, dict) and str(row.get("target", "") or "").strip()
        }
        return self._extract_visual_from_root(
            root,
            rels_map=rels_map,
            z_base=z_base,
            include_placeholders=include_placeholders,
        )

    def _extract_visual_from_root(
        self,
        root,
        *,
        rels_map: Dict[str, str],
        z_base: int = 0,
        include_placeholders: bool = True,
    ) -> Tuple[List[TextElement], List[ShapeElement], int]:
        elements: List[TextElement] = []
        shapes: List[ShapeElement] = []
        image_count = 0
        sp_tree = root.find(".//p:cSld/p:spTree", self.ns)
        ordered_nodes = list(sp_tree) if sp_tree is not None else []
        if not ordered_nodes:
            ordered_nodes = list(root.iter())

        for idx, elem in enumerate(ordered_nodes):
            local_tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local_tag not in {"sp", "pic"}:
                continue
            if (not include_placeholders) and self._is_placeholder_node(elem):
                continue
            z_idx = int(z_base + idx)
            if local_tag == "sp":
                text_elem = self._parse_text_shape(elem, z_index=z_idx)
                if text_elem:
                    elements.append(text_elem)
                else:
                    shape_elem = self._parse_shape_element(elem, z_index=z_idx)
                    if shape_elem:
                        shapes.append(shape_elem)
            elif local_tag == "pic":
                pic_elem = self._parse_picture_element(elem, rels_map, z_index=z_idx)
                if pic_elem:
                    shapes.append(pic_elem)
                    image_count += 1
        return elements, shapes, image_count

    def _extract_main_title(self, elements: List[TextElement], slide_num: int) -> str:
        """Extract the main title from slide elements.

        For cover slides (slide 1), the title is typically:
        - The largest text (by font size)
        - Located in the upper portion of the slide
        - Not a footer or small text
        """
        if not elements:
            return f"Slide {slide_num}"

        # Filter out very small texts and single characters
        substantial_texts = [
            e
            for e in elements
            if e.height > 0.3 and e.width > 1.0 and len(e.content) > 1
        ]

        if not substantial_texts:
            substantial_texts = [e for e in elements if len(e.content) > 1]

        if not substantial_texts:
            return f"Slide {slide_num}"

        # Sort by font size (largest first) - best indicator of title
        by_font_size = sorted(
            substantial_texts, key=lambda e: e.font_size, reverse=True
        )

        # For the first slide (cover), use the largest font text in upper portion
        if slide_num == 1:
            # Get texts in upper portion with largest fonts
            upper_texts = [e for e in by_font_size if e.top < 5.0]
            if upper_texts:
                return upper_texts[0].content
            return by_font_size[0].content

        # For other slides, use largest font text
        return by_font_size[0].content

    def _parse_text_shape(self, elem, z_index: int = 0) -> Optional[TextElement]:
        """Parse a shape element with text and extract text, position, and font size."""
        try:
            # Get position and size
            x = y = w = h = 0
            text = ""
            font_size = 0
            font_name = ""
            font_color = ""
            bold = False
            italic = False
            align = ""

            def _extract_color_token(node) -> str:
                if node is None:
                    return ""
                for color_node in node.iter():
                    tag = color_node.tag.split("}")[-1] if "}" in color_node.tag else color_node.tag
                    if tag == "srgbClr":
                        return parse_hex_color(color_node.get("val", ""))
                    if tag == "sysClr":
                        return parse_hex_color(color_node.get("lastClr", ""))
                    if tag == "schemeClr":
                        scheme_key = str(color_node.get("val", "") or "").strip()
                        if scheme_key and scheme_key in self.theme_color_map:
                            return parse_hex_color(self.theme_color_map.get(scheme_key, ""))
                        if scheme_key:
                            return f"scheme:{scheme_key}"
                return ""

            def _consume_rpr(rpr_node) -> None:
                nonlocal font_size, font_name, font_color, bold, italic
                if rpr_node is None:
                    return
                sz = rpr_node.get("sz")
                if sz:
                    try:
                        fs = int(sz) // 100
                        if fs > font_size:
                            font_size = fs
                    except ValueError:
                        pass
                if rpr_node.get("b") in {"1", "true", "True"}:
                    bold = True
                if rpr_node.get("i") in {"1", "true", "True"}:
                    italic = True
                latin = rpr_node.find(".//a:latin", self.ns)
                if latin is not None:
                    typeface = str(latin.get("typeface", "") or "").strip()
                    if typeface and not typeface.startswith("+"):
                        font_name = typeface
                color_token = _extract_color_token(rpr_node)
                if color_token:
                    font_color = color_token

            for child in elem.iter():
                if "xfrm" in child.tag:
                    for xfrm_child in child:
                        if "off" in xfrm_child.tag:
                            x = int(xfrm_child.get("x", "0"))
                            y = int(xfrm_child.get("y", "0"))
                        elif "ext" in xfrm_child.tag:
                            w = int(xfrm_child.get("cx", "0"))
                            h = int(xfrm_child.get("cy", "0"))

                if "txBody" in child.tag:
                    text_parts = []
                    paragraph_texts = []
                    for p in child.findall(".//a:p", self.ns):
                        p_text_parts = []
                        ppr = p.find("./a:pPr", self.ns)
                        if ppr is not None and not align:
                            align = str(ppr.get("algn", "") or "").strip()
                        def_rpr = p.find("./a:pPr/a:defRPr", self.ns)
                        _consume_rpr(def_rpr)
                        for run in p.findall("./a:r", self.ns):
                            t_node = run.find("./a:t", self.ns)
                            if t_node is not None and t_node.text:
                                p_text_parts.append(t_node.text)
                            _consume_rpr(run.find("./a:rPr", self.ns))
                        if p_text_parts:
                            line = "".join(p_text_parts).strip()
                            if line:
                                paragraph_texts.append(line)
                    if paragraph_texts:
                        text_parts.extend(paragraph_texts)
                    text = "\n".join(text_parts).strip()

            if text:
                # Convert EMU to inches for consistency with JSON format
                return TextElement(
                    type="text",
                    content=text,
                    top=emu_to_inches(y),
                    left=emu_to_inches(x),
                    width=emu_to_inches(w),
                    height=emu_to_inches(h),
                    font_size=font_size,
                    font_name=font_name,
                    font_color=font_color,
                    bold=bold,
                    italic=italic,
                    align=align,
                    z_index=int(z_index),
                )
        except Exception:
            pass
        return None

    def _parse_shape_element(self, elem, z_index: int = 0) -> Optional[ShapeElement]:
        """Parse a shape element and extract visual properties."""
        try:
            x = y = w = h = 0
            rotation = 0.0
            shape_type = "rectangle"
            fill_color = ""
            line_color = ""
            fill_transparency = 0.0
            line_transparency = 0.0
            line_width_pt = 0.0
            line_dash = ""
            has_fill = False
            has_text = False
            text_content = ""
            min_width = 0.1  # Minimum width in inches to be considered
            min_height = 0.05  # Minimum height in inches

            for child in elem.iter():
                # Get position and size
                if "xfrm" in child.tag:
                    rot_raw = child.get("rot")
                    if rot_raw:
                        try:
                            rotation = float(rot_raw) / 60000.0
                        except ValueError:
                            rotation = 0.0
                    for xfrm_child in child:
                        if "off" in xfrm_child.tag:
                            x = int(xfrm_child.get("x", "0"))
                            y = int(xfrm_child.get("y", "0"))
                        elif "ext" in xfrm_child.tag:
                            w = int(xfrm_child.get("cx", "0"))
                            h = int(xfrm_child.get("cy", "0"))

                # Get shape type
                if "prstGeom" in child.tag:
                    shape_type = child.get("prst", "rectangle")

                # Get fill color - check multiple color types
                if "solidFill" in child.tag:
                    has_fill = True  # Mark that this shape has fill
                    for sf in child:
                        sf_tag = sf.tag.split("}")[-1] if "}" in sf.tag else sf.tag
                        if "srgbClr" in sf_tag:
                            fill_color = sf.get("val", "")
                        elif "sysClr" in sf_tag:
                            fill_color = sf.get("lastClr", "")
                        elif "schemeClr" in sf_tag:
                            scheme_key = str(sf.get("val", "") or "").strip()
                            if scheme_key and scheme_key in self.theme_color_map:
                                fill_color = self.theme_color_map.get(scheme_key, "")
                            elif scheme_key:
                                fill_color = f"scheme:{scheme_key}"
                            else:
                                fill_color = "theme"
                        if "alpha" in sf_tag:
                            try:
                                fill_transparency = max(
                                    0.0, min(1.0, 1.0 - float(sf.get("val", "100000")) / 100000.0)
                                )
                            except ValueError:
                                fill_transparency = fill_transparency

                # Get line color
                if "ln" in child.tag:
                    ln = child
                    try:
                        if ln.get("w"):
                            line_width_pt = emu_to_points(int(ln.get("w", "0")))
                    except ValueError:
                        line_width_pt = line_width_pt
                    for ln_child in ln:
                        ln_tag = ln_child.tag.split("}")[-1] if "}" in ln_child.tag else ln_child.tag
                        if ln_tag in {"prstDash", "custDash"}:
                            line_dash = str(ln_child.get("val", "") or ln_tag)
                        if "solidFill" in ln_child.tag:
                            for sf in ln_child:
                                sf_tag = sf.tag.split("}")[-1] if "}" in sf.tag else sf.tag
                                if "srgbClr" in sf.tag:
                                    line_color = sf.get("val", "")
                                elif "sysClr" in sf.tag:
                                    line_color = sf.get("lastClr", "")
                                elif "schemeClr" in sf.tag:
                                    scheme_key = str(sf.get("val", "") or "").strip()
                                    if scheme_key and scheme_key in self.theme_color_map:
                                        line_color = self.theme_color_map.get(scheme_key, "")
                                    elif scheme_key:
                                        line_color = f"scheme:{scheme_key}"
                                if sf_tag == "alpha":
                                    try:
                                        line_transparency = max(
                                            0.0,
                                            min(
                                                1.0,
                                                1.0 - float(sf.get("val", "100000")) / 100000.0,
                                            ),
                                        )
                                    except ValueError:
                                        line_transparency = line_transparency

                # Check for text
                if "txBody" in child.tag:
                    has_text = True
                    text_parts = []
                    for t in child.iter():
                        if "t" in t.tag and t.text:
                            text_parts.append(t.text)
                    text_content = " ".join(text_parts)

            # Convert to inches
            width_inch = emu_to_inches(w)
            height_inch = emu_to_inches(h)

            # Only return if it has meaningful visual presence
            # - Has fill (any color type), or
            # - Has line color and reasonable size, or
            # - Is a named shape type (not generic rect)
            # - Has reasonable minimum size
            if (
                (has_fill or line_color or shape_type not in ["rect", "rectangle"])
                and width_inch >= min_width
                and height_inch >= min_height
            ):
                return ShapeElement(
                    type="shape",
                    subtype=shape_type,
                    top=emu_to_inches(y),
                    left=emu_to_inches(x),
                    width=width_inch,
                    height=height_inch,
                    rotation=rotation,
                    z_index=int(z_index),
                    fill_color=fill_color
                    if fill_color
                    else ("filled" if has_fill else ""),
                    fill_transparency=float(fill_transparency or 0.0),
                    line_color=line_color,
                    line_width_pt=float(line_width_pt or 0.0),
                    line_transparency=float(line_transparency or 0.0),
                    line_dash=line_dash,
                    has_text=has_text,
                    text_content=text_content[:50] if text_content else "",
                )
        except Exception:
            pass
        return None

    def _create_blocks(
        self, texts: List[str], slide_num: int, elements: List[TextElement]
    ) -> List[Block]:
        """Create blocks from extracted texts."""
        blocks = []

        if not elements:
            return blocks

        # Sort elements by font size (largest first) for title identification
        by_font = sorted(elements, key=lambda e: e.font_size, reverse=True)

        # Get title (largest font text)
        title_elem = by_font[0] if by_font else None
        title_text = title_elem.content if title_elem else ""

        # Get other elements (excluding title)
        other_elements = [e for e in elements if e != title_elem]

        unique_other_texts = _dedupe_texts([e.content for e in other_elements])

        subtitle_texts = []
        body_texts = []
        kpi_texts = []

        # Categorize other texts
        for text in unique_other_texts:
            if "%" in text or (text.isdigit() and len(text) <= 3):
                kpi_texts.append(text)
            elif len(text) < 30 and not any(c in text for c in "銆傦紝锛涳細"):
                subtitle_texts.append(text)
            else:
                body_texts.append(text)

        subtitle_texts = _dedupe_texts(subtitle_texts)
        body_texts = _dedupe_texts(body_texts)
        kpi_texts = _dedupe_texts(kpi_texts)

        # Add title block
        if title_text:
            blocks.append(
                Block(
                    block_type="title",
                    type="title",
                    card_id=f"card-{slide_num}-1",
                    id=f"title-{slide_num}",
                    content=title_text,
                )
            )

        # Add subtitle blocks (up to 2)
        for i, text in enumerate(subtitle_texts[:2], start=1):
            blocks.append(
                Block(
                    block_type="subtitle",
                    type="subtitle",
                    card_id=f"card-{slide_num}-{i + 1}",
                    id=f"subtitle-{slide_num}-{i}",
                    content=text,
                    emphasis=_pick_emphasis_tokens(text),
                )
            )

        # Add body/list block with combined content
        if body_texts:
            combined_body = "\n".join(body_texts[:6])  # Limit to 6 items
            blocks.append(
                Block(
                    block_type="list",
                    type="list",
                    card_id=f"card-{slide_num}-body",
                    id=f"list-{slide_num}",
                    content=combined_body,
                    emphasis=_pick_emphasis_tokens(combined_body),
                )
            )

        # Add KPI blocks
        for i, text in enumerate(kpi_texts[:2], start=1):
            blocks.append(
                Block(
                    block_type="kpi",
                    type="kpi",
                    card_id=f"card-{slide_num}-kpi-{i}",
                    id=f"kpi-{slide_num}-{i}",
                    content=text,
                    emphasis=_pick_emphasis_tokens(text),
                )
            )

        return blocks

        # Determine title - for cover slide, it's "2O2X" style
        # For content slides, it's the section title
        title_text = texts[0] if texts else ""
        subtitle_texts = []
        body_texts = []
        kpi_texts = []

        # Categorize texts
        for text in texts[1:] if len(texts) > 1 else []:
            if "%" in text or text.isdigit():
                kpi_texts.append(text)
            elif len(text) < 30 and not any(c in text for c in "銆傦紝锛涳細"):
                subtitle_texts.append(text)
            else:
                body_texts.append(text)

        # Add title block
        if title_text:
            blocks.append(
                Block(
                    block_type="title",
                    type="title",
                    card_id=f"card-{slide_num}-1",
                    id=f"title-{slide_num}",
                    content=title_text,
                )
            )

        # Add subtitle blocks
        for i, text in enumerate(subtitle_texts[:2], start=1):
            blocks.append(
                Block(
                    block_type="subtitle",
                    type="subtitle",
                    card_id=f"card-{slide_num}-{i + 1}",
                    id=f"subtitle-{slide_num}-{i}",
                    content=text,
                )
            )

        # Add body/list block with combined content
        if body_texts:
            combined_body = "\n".join(body_texts[:6])  # Limit to 6 items
            blocks.append(
                Block(
                    block_type="list",
                    type="list",
                    card_id=f"card-{slide_num}-body",
                    id=f"list-{slide_num}",
                    content=combined_body,
                )
            )

        # Add KPI blocks
        for i, text in enumerate(kpi_texts[:2], start=1):
            blocks.append(
                Block(
                    block_type="kpi",
                    type="kpi",
                    card_id=f"card-{slide_num}-kpi-{i}",
                    id=f"kpi-{slide_num}-{i}",
                    content=text,
                )
            )

        return blocks

    def _infer_slide_type(self, slide: Slide):
        """Infer slide type based on content."""
        title = slide.title.lower() if slide.title else ""

        if slide.page_number == 1:
            slide.slide_type = "cover"
        elif "目录" in title or "contents" in title.lower():
            slide.slide_type = "toc"
        elif "总结" in title or "结束" in title or "thanks" in title.lower():
            slide.slide_type = "summary"
        elif "part" in title or "绗竴" in title or "绗簩" in title:
            slide.slide_type = "divider"
        else:
            slide.slide_type = "content"

    def _extract_title_from_first_slide(self, slides: List[Slide]) -> str:
        """Extract the main title from the first slide."""
        if slides and slides[0].blocks:
            for block in slides[0].blocks:
                if block.block_type == "title" and block.content:
                    return block.content
        return "Untitled Presentation"

    def close(self):
        """Close the zip file."""
        self.zip_file.close()


def color_distance(c1: str, c2: str) -> float:
    """Calculate Euclidean distance between two hex colors."""
    try:
        h1 = c1.upper().lstrip("#")
        h2 = c2.upper().lstrip("#")
        if len(h1) == 3:
            h1 = "".join(c * 2 for c in h1)
        if len(h2) == 3:
            h2 = "".join(c * 2 for c in h2)
        r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
        r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
        return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
    except:
        return 999


def compare_minimax_json(ref_json: Dict, gen_json: Dict) -> Dict:
    """Compare two minimax JSON files and return similarity scores."""
    results = {
        "overall_score": 0.0,
        "title_match": False,
        "slide_count_match": False,
        "theme_colors_match": 0.0,
        "content_match": 0.0,
        "details": {},
    }

    # 1. Title match
    ref_title = ref_json.get("title", "").strip()
    gen_title = gen_json.get("title", "").strip()
    results["title_match"] = ref_title == gen_title
    results["details"]["ref_title"] = ref_title
    results["details"]["gen_title"] = gen_title

    # 2. Slide count match (allow 卤2 difference)
    ref_slides = len(ref_json.get("slides", []))
    gen_slides = len(gen_json.get("slides", []))
    slide_diff = abs(ref_slides - gen_slides)
    results["slide_count_match"] = slide_diff <= 2
    results["details"]["ref_slide_count"] = ref_slides
    results["details"]["gen_slide_count"] = gen_slides
    results["details"]["slide_diff"] = slide_diff

    # 3. Theme colors match (use color distance for similarity)
    # Reference has colors in theme, target has colors in design_spec.colors
    ref_theme = ref_json.get("theme", {})
    ref_colors = ref_json.get("design_spec", {}).get("colors", ref_theme)

    # Target JSON may have colors in design_spec.colors or theme
    gen_design_spec = gen_json.get("design_spec", {})
    gen_colors = gen_design_spec.get("colors", gen_json.get("theme", {}))

    # Map color keys (target uses 'background' instead of 'bg')
    color_key_map = {
        "primary": "primary",
        "secondary": "secondary",
        "accent": "accent",
        "bg": "background",  # ref uses bg, target uses background
    }

    color_scores = []
    color_details = []
    for ref_key, gen_key in color_key_map.items():
        ref_color = str(ref_colors.get(ref_key, "")).upper().lstrip("#")
        gen_color = str(gen_colors.get(gen_key, "")).upper().lstrip("#")
        if ref_color and gen_color:
            dist = color_distance(ref_color, gen_color)
            # Convert distance to similarity (0-100)
            # Max possible distance is ~441 (sqrt(255^2 * 3))
            # More lenient: colors within distance 50 are considered similar
            if dist < 50:
                similarity = 100
            elif dist < 100:
                similarity = 80
            elif dist < 150:
                similarity = 60
            elif dist < 200:
                similarity = 40
            else:
                similarity = max(0, 100 - (dist / 441 * 100))
            color_scores.append(similarity)
            color_details.append(
                {
                    "key": ref_key,
                    "ref": f"#{ref_color}",
                    "gen": f"#{gen_color}",
                    "distance": round(dist, 1),
                    "similarity": round(similarity, 1),
                }
            )

    results["theme_colors_match"] = sum(color_scores) / max(len(color_scores), 1)
    results["details"]["color_comparison"] = color_details

    # 4. Content match (compare titles, allow partial match)
    ref_titles = [s.get("title", "") for s in ref_json.get("slides", [])]
    gen_titles = [s.get("title", "") for s in gen_json.get("slides", [])]

    title_matches = 0
    for rt in ref_titles:
        # Check for exact or substring match
        if rt in gen_titles or any(
            rt in gt or gt in rt for gt in gen_titles if rt and gt
        ):
            title_matches += 1

    results["content_match"] = (title_matches / max(len(ref_titles), 1)) * 100
    results["details"]["title_matches"] = title_matches
    results["details"]["ref_titles"] = ref_titles[:10]
    results["details"]["gen_titles"] = gen_titles[:10]

    # Overall score
    results["overall_score"] = (
        (1.0 if results["title_match"] else 0.0) * 15
        + (1.0 if results["slide_count_match"] else 0.0) * 15
        + results["theme_colors_match"] * 0.3
        + results["content_match"] * 0.4
    )

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="浠庡弬鑰働PT鎻愬彇淇℃伅骞跺彲閫変笌鐩爣JSON瀵规瘮"
    )
    parser.add_argument("--input", "-i", default="", help="鍙傝€働PT鏂囦欢璺緞 (蹇呭～)")
    parser.add_argument(
        "--output",
        "-o",
        default="extracted.json",
        help="杈撳嚭JSON鏂囦欢璺緞 (榛樿: extracted.json)",
    )
    parser.add_argument(
        "--target", "-t", default="", help="瀵规瘮鐩爣JSON鏂囦欢璺緞 (鍙€?"
    )
    parser.add_argument(
        "--no-compare", action="store_true", help="skip comparison with target JSON"
    )
    parser.add_argument(
        "--pages", default=None, help="鎻愬彇鐨勯〉鐮佽寖鍥达紝濡?'1-10' 鎴?'1,3,5'"
    )

    args = parser.parse_args()

    # Reference PPT path
    ref_path = args.input
    if not ref_path:
        parser.error("--input is required")

    print("=== 浠庡弬鑰働PT鎻愬彇淇℃伅 ===")
    print(f"杈撳叆鏂囦欢: {ref_path}")
    extractor = PPTXMinimaxExtractor(ref_path)
    ref_json = extractor.extract_all()
    extractor.close()

    # Handle page range filtering
    if args.pages:
        slides = ref_json.get("slides", [])
        page_ranges = args.pages.split(",")
        filtered_slides = []
        for r in page_ranges:
            if "-" in r:
                start, end = map(int, r.split("-"))
                filtered_slides.extend(slides[start - 1 : end])
            else:
                filtered_slides.append(slides[int(r) - 1])
        ref_json["slides"] = filtered_slides
        print(f"  (宸茶繃婊ら〉鐮? {args.pages})")

    # Save extracted JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ref_json, f, ensure_ascii=False, indent=2)

    print(f"宸蹭繚瀛樻彁鍙栫粨鏋滃埌: {output_path}")
    print(f"  鏍囬: {ref_json['title']}")
    print(f"  骞荤伅鐗囨暟: {len(ref_json['slides'])}")
    print(f"  涓婚棰滆壊:")
    print(f"    primary: #{ref_json['theme']['primary']}")
    print(f"    secondary: #{ref_json['theme']['secondary']}")
    print(f"    accent: #{ref_json['theme']['accent']}")
    print(f"    bg: #{ref_json['theme']['bg']}")
    print()

    # Load target JSON for comparison (unless --no-compare is set)
    if args.no_compare:
        print("=== 瀵规瘮宸茶烦杩?(--no-compare) ===")
        return

    if not str(args.target or "").strip():
        print("=== 鏈彁渚涘姣旂洰鏍囷紝璺宠繃瀵规瘮 ===")
        return

    target_path = Path(args.target)
    if not target_path.exists():
        print(f"=== 瀵规瘮鐩爣鏂囦欢涓嶅瓨鍦紝璺宠繃瀵规瘮 ===")
        print(f"  鐩爣璺緞: {target_path}")
        return

    with open(target_path, "r", encoding="utf-8") as f:
        target_json = json.load(f)

    print("=== 涓庣洰鏍嘕SON瀵规瘮 ===")
    comparison = compare_minimax_json(target_json, ref_json)

    print(f"鎬讳綋鍒嗘暟: {comparison['overall_score']:.1f}%")
    print(f"  title match: {'yes' if comparison['title_match'] else 'no'}")
    print(f"    鍙傝€冩爣棰? {comparison['details'].get('ref_title', '?')}")
    print(f"    鐩爣鏍囬: {comparison['details'].get('gen_title', '?')}")
    print(
        f"  slide count match: {'yes' if comparison['slide_count_match'] else 'no'} (allowed ±2)"
    )
    print(f"    鍙傝€? {comparison['details'].get('ref_slide_count', '?')}")
    print(f"    鐩爣: {comparison['details'].get('gen_slide_count', '?')}")
    print(f"  涓婚棰滆壊鍖归厤: {comparison['theme_colors_match']:.1f}%")
    for c in comparison["details"].get("color_comparison", []):
        print(f"    {c['key']}: {c['ref']} vs {c['gen']} (鐩镐技搴? {c['similarity']}%)")
    print(f"  content_match: {comparison['content_match']:.1f}%")
    print(f"    鍖归厤鏍囬鏁? {comparison['details'].get('title_matches', 0)}")
    print()
    print("鍙傝€働PT鏍囬:", comparison["details"].get("ref_titles", [])[:5])
    print("鐩爣JSON鏍囬:", comparison["details"].get("gen_titles", [])[:5])


if __name__ == "__main__":
    main()





