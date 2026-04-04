#!/usr/bin/env python3
"""
Complete PPTX information extractor using direct XML parsing.
More reliable than python-pptx for extracting themes, fonts, and layouts.
"""

import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
import json
import re


@dataclass
class ThemeColor:
    name: str
    hex_value: str
    type: str  # 'srgb' or 'system'


@dataclass
class FontInfo:
    name: str
    font_type: str  # 'latin', 'ea' (east asian), 'cs' (complex script)
    slide_numbers: List[int] = field(default_factory=list)


@dataclass
class SlideLayout:
    name: str
    layout_id: str
    slide_numbers: List[int] = field(default_factory=list)


@dataclass
class ShapeInfo:
    shape_type: str
    x: float  # EMU
    y: float
    width: float
    height: float
    text: str = ""
    fill_color: Optional[str] = None
    line_color: Optional[str] = None
    font_name: Optional[str] = None
    font_size: Optional[int] = None
    font_color: Optional[str] = None


@dataclass
class SlideInfo:
    number: int
    layout_name: str
    shapes: List[ShapeInfo]
    background_color: Optional[str] = None
    title: str = ""


@dataclass
class DeckInfo:
    slide_count: int
    width_emu: int
    height_emu: int
    width_inches: float
    height_inches: float
    themes: Dict[str, List[ThemeColor]]
    fonts: List[FontInfo]
    layouts: List[SlideLayout]
    slides: List[SlideInfo]
    global_colors: List[Tuple[str, int]]
    global_fonts: Set[str]


# Constants
EMU_PER_INCH = 914400
SYSTEM_COLOR_MAP = {
    "window": "#FFFFFF",
    "windowText": "#000000",
    "btnFace": "#F0F0F0",
    "btnText": "#000000",
    "highlight": "#0078D4",
    "highlightText": "#FFFFFF",
    "caption": "#909090",
    "infoText": "#000000",
}


def parse_hex_color(value: str) -> Optional[str]:
    """Parse hex color value, handling different formats."""
    if not value:
        return None
    value = value.strip().upper()
    if not value.startswith("#"):
        value = "#" + value
    return value


def parseEMU(value: str) -> float:
    """Parse EMU (English Metric Units) value."""
    try:
        return float(value) if value else 0.0
    except (ValueError, TypeError):
        return 0.0


class PPTXExtractor:
    """Extract complete information from PPTX files using direct XML parsing."""

    def __init__(self, pptx_path: str):
        self.pptx_path = pptx_path
        self.zip_file = zipfile.ZipFile(pptx_path, "r")
        self.ns = {
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "sl": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }

    def extract_all(self) -> DeckInfo:
        """Extract all information from the PPTX file."""
        slides = self._extract_slides()
        themes = self._extract_themes()
        fonts = self._extract_fonts()
        layouts = self._extract_layouts()
        dimensions = self._get_dimensions()

        # Collect global colors
        color_counter = Counter()
        for slide in slides:
            for shape in slide.shapes:
                if shape.fill_color:
                    color_counter[shape.fill_color] += 1
                if shape.font_color:
                    color_counter[shape.font_color] += 1
                if shape.line_color:
                    color_counter[shape.line_color] += 1

        # Also include theme colors
        for theme_colors in themes.values():
            for tc in theme_colors:
                color_counter[tc.hex_value] += 1

        global_colors = color_counter.most_common(20)

        return DeckInfo(
            slide_count=len(slides),
            width_emu=dimensions[0],
            height_emu=dimensions[1],
            width_inches=dimensions[0] / EMU_PER_INCH,
            height_inches=dimensions[1] / EMU_PER_INCH,
            themes=themes,
            fonts=fonts,
            layouts=layouts,
            slides=slides,
            global_colors=global_colors,
            global_fonts=set(f.name for f in fonts),
        )

    def _get_dimensions(self) -> Tuple[int, int]:
        """Get slide dimensions from presentation.xml."""
        try:
            content = self.zip_file.read("ppt/presentation.xml")
            root = ET.fromstring(content)

            # Get slide size
            for elem in root.iter():
                if "sldSz" in elem.tag:
                    cx = int(elem.get("cx", 0))
                    cy = int(elem.get("cy", 0))
                    return cx, cy
        except Exception:
            pass
        return (12192000, 6858000)  # Default 13.33 x 7.5 inches

    def _extract_themes(self) -> Dict[str, List[ThemeColor]]:
        """Extract all theme colors from theme files."""
        themes = {}

        theme_files = [
            f for f in self.zip_file.namelist() if "theme" in f and f.endswith(".xml")
        ]

        for theme_file in theme_files:
            theme_name = theme_file.split("/")[-1].replace(".xml", "")
            colors = []

            try:
                content = self.zip_file.read(theme_file)
                root = ET.fromstring(content)

                for elem in root.iter():
                    if "clrScheme" in elem.tag:
                        for clr in elem:
                            tag = clr.tag.split("}")[1] if "}" in clr.tag else clr.tag

                            # Check for srgbClr
                            srgb = clr.find(
                                ".//{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr"
                            )
                            if srgb is not None:
                                val = srgb.get("val")
                                if val:
                                    colors.append(ThemeColor(tag, f"#{val}", "srgb"))
                                    continue

                            # Check for sysClr
                            sys_clr = clr.find(
                                ".//{http://schemas.openxmlformats.org/drawingml/2006/main}sysClr"
                            )
                            if sys_clr is not None:
                                val = sys_clr.get("val")
                                if val:
                                    mapped = SYSTEM_COLOR_MAP.get(
                                        val.lower(), "#808080"
                                    )
                                    colors.append(ThemeColor(tag, mapped, "system"))

                themes[theme_name] = colors
            except Exception as e:
                print(f"Error parsing {theme_file}: {e}")

        return themes

    def _extract_fonts(self) -> List[FontInfo]:
        """Extract fonts used in the presentation."""
        font_map = {}  # font_name -> FontInfo

        slide_files = [
            f
            for f in self.zip_file.namelist()
            if f.endswith(".xml") and "slides/slide" in f
        ]

        for slide_file in slide_files:
            slide_num = int(re.search(r"slide(\d+)", slide_file).group(1))

            try:
                content = self.zip_file.read(slide_file)
                root = ET.fromstring(content)

                # Find font runs
                for elem in root.iter():
                    # Latin font
                    if elem.tag.endswith("}latin") or "latin" in elem.tag:
                        font = elem.get("typeface")
                        if font and font != "+none":
                            if font not in font_map:
                                font_map[font] = FontInfo(font, "latin")
                            if slide_num not in font_map[font].slide_numbers:
                                font_map[font].slide_numbers.append(slide_num)

                    # East Asian font
                    if elem.tag.endswith("}ea") or (
                        elem.tag.endswith("}font") and "ea" in elem.tag
                    ):
                        font = elem.get("typeface")
                        if font and font != "+none":
                            if font not in font_map:
                                font_map[font] = FontInfo(font, "ea")
                            if slide_num not in font_map[font].slide_numbers:
                                font_map[font].slide_numbers.append(slide_num)
            except Exception as e:
                print(f"Error parsing {slide_file}: {e}")

        return list(font_map.values())

    def _extract_layouts(self) -> List[SlideLayout]:
        """Extract slide layouts."""
        layouts = []

        layout_files = [
            f
            for f in self.zip_file.namelist()
            if "slideLayout" in f and f.endswith(".xml")
        ]

        for layout_file in layout_files:
            layout_name = layout_file.split("/")[-1].replace(".xml", "")
            layout_id = re.search(r"slideLayout(\d+)", layout_file)
            lid = layout_id.group(1) if layout_id else "0"

            layouts.append(SlideLayout(layout_name, lid, []))

        # Map slides to layouts
        slide_files = [
            f
            for f in self.zip_file.namelist()
            if f.endswith(".xml") and "slides/slide" in f
        ]

        for slide_file in slide_files:
            slide_num = int(re.search(r"slide(\d+)", slide_file).group(1))

            try:
                content = self.zip_file.read(slide_file)
                root = ET.fromstring(content)

                # Find layout reference
                for elem in root.iter():
                    if "layout" in elem.tag.lower():
                        ref = elem.get(
                            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                        )
                        if ref:
                            # Find corresponding layout file
                            for layout in layouts:
                                if layout.layout_id in ref:
                                    layout.slide_numbers.append(slide_num)
                                    break
            except Exception:
                pass

        return layouts

    def _extract_slides(self) -> List[SlideInfo]:
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

                shapes = []
                texts = []

                for elem in root.iter():
                    if "sp" in elem.tag or "grpSp" in elem.tag:
                        shape = self._parse_shape(elem, slide_num)
                        if shape:
                            shapes.append(shape)
                            if shape.text:
                                texts.append(shape.text)

                slide_info = SlideInfo(
                    number=slide_num,
                    layout_name="",
                    shapes=shapes,
                    title=texts[0] if texts else "",
                )
                slides.append(slide_info)

            except Exception as e:
                print(f"Error parsing slide {slide_num}: {e}")

        return slides

    def _parse_shape(self, elem, slide_num: int) -> Optional[ShapeInfo]:
        """Parse a shape element."""
        try:
            # Get shape type and name
            shape_type = "unknown"
            tx_body = None

            for child in elem.iter():
                if "prstGeom" in child.tag:
                    shape_type = child.get("prst", "rect")
                if "txBody" in child.tag:
                    tx_body = child

            # Get position and size
            x = y = w = h = 0
            for child in elem.iter():
                if "xfrm" in child.tag:
                    for xfrm_child in child:
                        if "off" in xfrm_child.tag:
                            x = parseEMU(xfrm_child.get("x", "0"))
                            y = parseEMU(xfrm_child.get("y", "0"))
                        elif "ext" in xfrm_child.tag:
                            w = parseEMU(xfrm_child.get("cx", "0"))
                            h = parseEMU(xfrm_child.get("cy", "0"))

            # Get text
            text = ""
            if tx_body is not None:
                text_parts = []
                for t in tx_body.iter():
                    if "t" in t.tag and t.text:
                        text_parts.append(t.text)
                text = " ".join(text_parts).strip()

            # Get fill color
            fill_color = None
            for child in elem.iter():
                if "solidFill" in child.tag:
                    for sf_child in child:
                        if "srgbClr" in sf_child.tag:
                            val = sf_child.get("val")
                            if val:
                                fill_color = f"#{val}"
                            break

            return ShapeInfo(
                shape_type=shape_type,
                x=x,
                y=y,
                width=w,
                height=h,
                text=text,
                fill_color=fill_color,
            )
        except Exception:
            return None

    def close(self):
        """Close the zip file."""
        self.zip_file.close()


def compare_decks(ref: DeckInfo, gen: DeckInfo, max_slides: int = 20) -> dict:
    """Compare two decks and return similarity scores."""

    # 1. Structure comparison
    ref_slide_count = min(ref.slide_count, max_slides)
    gen_slide_count = min(gen.slide_count, max_slides)
    slide_count_score = max(
        0, 100 - abs(ref_slide_count - gen_slide_count) / max(ref_slide_count, 1) * 200
    )

    # 2. Color comparison
    ref_colors = set(c[0] for c in ref.global_colors[:15])
    gen_colors = set(c[0] for c in gen.global_colors[:15])

    def color_distance(c1, c2):
        try:
            h1 = c1.lstrip("#")
            h2 = c2.lstrip("#")
            if len(h1) == 3:
                h1 = "".join(c * 2 for c in h1)
            if len(h2) == 3:
                h2 = "".join(c * 2 for c in h2)
            r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
            r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
            return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
        except:
            return 999

    color_matches = 0
    for rc in ref_colors:
        for gc in gen_colors:
            if color_distance(rc, gc) < 40:
                color_matches += 1
                break
    color_score = color_matches / max(len(ref_colors), 1) * 100

    # 3. Font comparison
    ref_fonts = ref.global_fonts
    gen_fonts = gen.global_fonts

    font_overlap = len(ref_fonts & gen_fonts) / max(len(ref_fonts | gen_fonts), 1) * 100

    # 4. Dimension comparison
    ref_ar = ref.width_emu / ref.height_emu if ref.height_emu else 1
    gen_ar = gen.width_emu / gen.height_emu if gen.height_emu else 1
    ar_diff = abs(ref_ar - gen_ar) / max(ref_ar, 0.01)
    dimension_score = max(0, 100 - ar_diff * 300)

    # Overall score
    overall = (
        0.20 * slide_count_score
        + 0.30 * color_score
        + 0.25 * font_overlap
        + 0.25 * dimension_score
    )

    return {
        "overall_score": round(overall, 1),
        "slide_count_score": round(slide_count_score, 1),
        "color_score": round(color_score, 1),
        "font_overlap": round(font_overlap, 1),
        "dimension_score": round(dimension_score, 1),
        "ref_slide_count": ref.slide_count,
        "gen_slide_count": gen.slide_count,
        "ref_colors": list(ref_colors)[:10],
        "gen_colors": list(gen_colors)[:10],
        "ref_fonts": list(ref_fonts),
        "gen_fonts": list(gen_fonts),
    }


def main():
    import sys

    ref_path = "C:/Users/liula/Downloads/ppt2/ppt2/1.pptx"
    gen_path = "output/regression/generated_v2.pptx"

    print("=== 提取参考PPT信息 ===")
    ref_extractor = PPTXExtractor(ref_path)
    ref_info = ref_extractor.extract_all()
    ref_extractor.close()

    print(f"幻灯片数量: {ref_info.slide_count}")
    print(f'尺寸: {ref_info.width_inches:.2f}" x {ref_info.height_inches:.2f}"')
    print(f"主题颜色数: {sum(len(v) for v in ref_info.themes.values())}")
    print(f"字体: {ref_info.global_fonts}")
    print(f"布局数: {len(ref_info.layouts)}")
    print()

    print("=== 提取生成PPT信息 ===")
    gen_extractor = PPTXExtractor(gen_path)
    gen_info = gen_extractor.extract_all()
    gen_extractor.close()

    print(f"幻灯片数量: {gen_info.slide_count}")
    print(f'尺寸: {gen_info.width_inches:.2f}" x {gen_info.height_inches:.2f}"')
    print(f"主题颜色数: {sum(len(v) for v in gen_info.themes.values())}")
    print(f"字体: {gen_info.global_fonts}")
    print(f"布局数: {len(gen_info.layouts)}")
    print()

    print("=== 对比结果 ===")
    result = compare_decks(ref_info, gen_info)
    print(f"总体分数: {result['overall_score']}%")
    print(f"  幻灯片数量: {result['slide_count_score']}%")
    print(f"  颜色匹配: {result['color_score']}%")
    print(f"  字体重叠: {result['font_overlap']}%")
    print(f"  尺寸匹配: {result['dimension_score']}%")
    print()
    print("参考PPT颜色:", result["ref_colors"][:5])
    print("生成PPT颜色:", result["gen_colors"][:5])
    print("参考PPT字体:", result["ref_fonts"])
    print("生成PPT字体:", result["gen_fonts"])


if __name__ == "__main__":
    main()
