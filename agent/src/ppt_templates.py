"""
PPT 模板系统 — 商务/教育/创意 3套模板

借鉴 OpenMAIC 的 SlideTheme + 元素布局系统
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.schemas.ppt import SlideBackground, SlideElement


# ── 渐变背景 ────────────────────────────────────────────────────────


def gradient_bg(colors: List[Dict[str, Any]], rotate: int = 180) -> SlideBackground:
    return SlideBackground(
        type="gradient", gradient={"type": "linear", "colors": colors, "rotate": rotate}
    )


def solid_bg(color: str) -> SlideBackground:
    return SlideBackground(type="solid", color=color)


# ── 商务蓝模板 ──────────────────────────────────────────────────────

BUSINESS_BLUE = {
    "id": "business-blue",
    "name": "商务蓝",
    "primary": "#1e3a5f",
    "secondary": "#2563eb",
    "accent": "#38bdf8",
    "background": "#ffffff",
    "dark_bg": "#0f172a",
    "text": "#1e293b",
    "text_light": "#64748b",
    "heading_font": "Microsoft YaHei",
    "body_font": "Microsoft YaHei",
    "chart_colors": ["#2563eb", "#7c3aed", "#38bdf8", "#22c55e", "#f59e0b"],
}

# ── 科技深色模板 ────────────────────────────────────────────────────

TECH_DARK = {
    "id": "tech-dark",
    "name": "科技深蓝",
    "primary": "#38bdf8",
    "secondary": "#8b5cf6",
    "accent": "#22c55e",
    "background": "#0f172a",
    "dark_bg": "#020617",
    "text": "#e2e8f0",
    "text_light": "#94a3b8",
    "heading_font": "Microsoft YaHei",
    "body_font": "Microsoft YaHei",
    "chart_colors": ["#38bdf8", "#8b5cf6", "#22c55e", "#f59e0b", "#e2e8f0"],
}

# ── 清新教育模板 ────────────────────────────────────────────────────

EDUCATION_FRESH = {
    "id": "education-fresh",
    "name": "清新绿",
    "primary": "#166534",
    "secondary": "#16a34a",
    "accent": "#4ade80",
    "background": "#f0fdf4",
    "dark_bg": "#14532d",
    "text": "#14532d",
    "text_light": "#6b7280",
    "heading_font": "Microsoft YaHei",
    "body_font": "Microsoft YaHei",
    "chart_colors": ["#16a34a", "#0ea5e9", "#f59e0b", "#ef4444", "#8b5cf6"],
}

TEMPLATES = {
    "professional": BUSINESS_BLUE,
    "education": EDUCATION_FRESH,
    "creative": TECH_DARK,
}


# ── 页面布局生成器 ──────────────────────────────────────────────────


def make_cover_elements(
    title: str, subtitle: str, template: Dict
) -> List[SlideElement]:
    """封面页布局"""
    t = template
    return [
        SlideElement(
            type="text",
            left=120,
            top=280,
            width=1680,
            height=100,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 56,
                "fontFamily": t["heading_font"],
                "color": t["primary"],
                "bold": True,
                "align": "center",
            },
        ),
        SlideElement(
            type="text",
            left=120,
            top=400,
            width=1680,
            height=60,
            content=subtitle,
            style={
                "fontSize": 28,
                "fontFamily": t["body_font"],
                "color": t["text_light"],
                "align": "center",
            },
        ),
        SlideElement(
            type="shape",
            left=760,
            top=500,
            width=400,
            height=4,
            style={"backgroundColor": t["secondary"], "borderRadius": 2},
        ),
    ]


def make_title_content_layout(
    title: str, points: List[str], template: Dict, has_chart: bool = False
) -> List[SlideElement]:
    """标题+要点 布局 (左文右图)"""
    t = template
    elements = [
        # 标题栏
        SlideElement(
            type="shape",
            left=0,
            top=0,
            width=1920,
            height=100,
            style={"backgroundColor": t["primary"]},
        ),
        SlideElement(
            type="text",
            left=80,
            top=20,
            width=1600,
            height=70,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 36,
                "fontFamily": t["heading_font"],
                "color": "#ffffff",
                "bold": True,
            },
        ),
        # 左侧装饰条
        SlideElement(
            type="shape",
            left=80,
            top=140,
            width=6,
            height=min(len(points) * 55, 600),
            style={"backgroundColor": t["accent"], "borderRadius": 3},
        ),
    ]

    # 要点
    for i, point in enumerate(points[:10]):
        y = 140 + i * 55
        if y > 900:
            break
        elements.append(
            SlideElement(
                type="text",
                left=110,
                top=y,
                width=1000,
                height=45,
                content=f"• {point}",
                style={
                    "fontSize": 22,
                    "fontFamily": t["body_font"],
                    "color": t["text"],
                    "lineSpacing": 1.4,
                },
            )
        )

    # 右侧图表占位
    if has_chart:
        elements.append(
            SlideElement(
                type="chart",
                left=1150,
                top=160,
                width=700,
                height=500,
                chart_type="bar",
                chart_data={
                    "labels": ["指标A", "指标B", "指标C", "指标D", "指标E"],
                    "datasets": [{"label": "数据", "data": [85, 92, 78, 95, 88]}],
                },
                style={"colors": t["chart_colors"]},
            )
        )

    return elements


def make_comparison_layout(
    title: str,
    left_title: str,
    left_points: List[str],
    right_title: str,
    right_points: List[str],
    template: Dict,
) -> List[SlideElement]:
    """对比布局 (左右分栏)"""
    t = template
    elements = [
        SlideElement(
            type="shape",
            left=0,
            top=0,
            width=1920,
            height=100,
            style={"backgroundColor": t["primary"]},
        ),
        SlideElement(
            type="text",
            left=80,
            top=20,
            width=1600,
            height=70,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 36,
                "fontFamily": t["heading_font"],
                "color": "#ffffff",
                "bold": True,
            },
        ),
        # 左栏标题
        SlideElement(
            type="shape",
            left=80,
            top=130,
            width=860,
            height=60,
            style={"backgroundColor": t["secondary"], "borderRadius": 8},
        ),
        SlideElement(
            type="text",
            left=100,
            top=140,
            width=820,
            height=45,
            content=f"<b>{left_title}</b>",
            style={
                "fontSize": 24,
                "fontFamily": t["heading_font"],
                "color": "#ffffff",
                "bold": True,
            },
        ),
        # 右栏标题
        SlideElement(
            type="shape",
            left=980,
            top=130,
            width=860,
            height=60,
            style={"backgroundColor": t["accent"], "borderRadius": 8},
        ),
        SlideElement(
            type="text",
            left=1000,
            top=140,
            width=820,
            height=45,
            content=f"<b>{right_title}</b>",
            style={
                "fontSize": 24,
                "fontFamily": t["heading_font"],
                "color": "#ffffff",
                "bold": True,
            },
        ),
    ]
    # 左栏要点
    for i, p in enumerate(left_points[:8]):
        elements.append(
            SlideElement(
                type="text",
                left=100,
                top=220 + i * 50,
                width=800,
                height=40,
                content=f"✓ {p}",
                style={
                    "fontSize": 20,
                    "fontFamily": t["body_font"],
                    "color": t["text"],
                },
            )
        )
    # 右栏要点
    for i, p in enumerate(right_points[:8]):
        elements.append(
            SlideElement(
                type="text",
                left=1000,
                top=220 + i * 50,
                width=800,
                height=40,
                content=f"✓ {p}",
                style={
                    "fontSize": 20,
                    "fontFamily": t["body_font"],
                    "color": t["text"],
                },
            )
        )
    return elements


def make_table_layout(
    title: str, headers: List[str], rows: List[List[str]], template: Dict
) -> List[SlideElement]:
    """表格布局"""
    t = template
    elements = [
        SlideElement(
            type="shape",
            left=0,
            top=0,
            width=1920,
            height=100,
            style={"backgroundColor": t["primary"]},
        ),
        SlideElement(
            type="text",
            left=80,
            top=20,
            width=1600,
            height=70,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 36,
                "fontFamily": t["heading_font"],
                "color": "#ffffff",
                "bold": True,
            },
        ),
        SlideElement(
            type="table",
            left=80,
            top=140,
            width=1760,
            height=min(100 + len(rows) * 45, 800),
            table_rows=[headers] + rows,
            table_col_widths=[1760 / len(headers)] * len(headers),
            style={"fontSize": 16, "fontFamily": t["body_font"]},
        ),
    ]
    return elements


def make_section_divider(
    section_num: int, title: str, subtitle: str, template: Dict
) -> List[SlideElement]:
    """章节分隔页"""
    t = template
    return [
        SlideElement(
            type="shape",
            left=0,
            top=0,
            width=1920,
            height=1080,
            style={"backgroundColor": t["primary"]},
        ),
        SlideElement(
            type="shape",
            left=120,
            top=420,
            width=200,
            height=4,
            style={"backgroundColor": t["accent"], "borderRadius": 2},
        ),
        SlideElement(
            type="text",
            left=120,
            top=340,
            width=200,
            height=60,
            content=f"<b>PART {section_num}</b>",
            style={
                "fontSize": 24,
                "fontFamily": t["heading_font"],
                "color": t["accent"],
                "bold": True,
            },
        ),
        SlideElement(
            type="text",
            left=120,
            top=450,
            width=1680,
            height=80,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 48,
                "fontFamily": t["heading_font"],
                "color": "#ffffff",
                "bold": True,
            },
        ),
        SlideElement(
            type="text",
            left=120,
            top=550,
            width=1680,
            height=40,
            content=subtitle,
            style={
                "fontSize": 20,
                "fontFamily": t["body_font"],
                "color": t["text_light"],
            },
        ),
    ]


def make_contact_layout(
    company: str, contacts: Dict[str, str], template: Dict
) -> List[SlideElement]:
    """联系页布局"""
    t = template
    elements = [
        SlideElement(
            type="shape",
            left=0,
            top=0,
            width=1920,
            height=1080,
            style={"backgroundColor": t["primary"]},
        ),
        SlideElement(
            type="text",
            left=120,
            top=300,
            width=1680,
            height=80,
            content=f"<b>感谢聆听</b>",
            style={
                "fontSize": 56,
                "fontFamily": t["heading_font"],
                "color": "#ffffff",
                "bold": True,
                "align": "center",
            },
        ),
        SlideElement(
            type="text",
            left=120,
            top=400,
            width=1680,
            height=40,
            content=f"期待与您合作",
            style={
                "fontSize": 24,
                "fontFamily": t["body_font"],
                "color": t["accent"],
                "align": "center",
            },
        ),
    ]
    y = 520
    for label, value in contacts.items():
        elements.append(
            SlideElement(
                type="text",
                left=600,
                top=y,
                width=720,
                height=35,
                content=f"{label}: {value}",
                style={
                    "fontSize": 18,
                    "fontFamily": t["body_font"],
                    "color": "#e2e8f0",
                    "align": "center",
                },
            )
        )
        y += 40
    return elements


# ── 根据页面类型生成布局 ────────────────────────────────────────────


def apply_template_layout(
    slide_order: int,
    title: str,
    key_points: List[str],
    description: str,
    template_id: str = "professional",
    page_type: str = "auto",
) -> tuple[List[SlideElement], SlideBackground]:
    """
    根据模板和页面类型生成专业布局。

    Returns: (elements, background)
    """
    template = TEMPLATES.get(template_id, BUSINESS_BLUE)

    # 自动推断页面类型
    if page_type == "auto":
        if slide_order == 0 or "封面" in title or "cover" in title.lower():
            page_type = "cover"
        elif "联系" in title or "contact" in title.lower():
            page_type = "contact"
        elif "对比" in title or "vs" in title.lower():
            page_type = "comparison"
        elif any("表" in p for p in key_points) or len(key_points) > 6:
            page_type = "table"
        elif slide_order > 0 and len(key_points) <= 2:
            page_type = "section"
        else:
            page_type = "content"

    bg = solid_bg(template["background"])

    if page_type == "cover":
        subtitle = key_points[0] if key_points else description
        return make_cover_elements(title, subtitle, template), bg

    elif page_type == "section":
        section_num = max(1, slide_order)
        return make_section_divider(section_num, title, description, template), bg

    elif page_type == "contact":
        contacts = {
            kp.split(":")[0]: kp.split(":")[1] for kp in key_points if ":" in kp
        }
        if not contacts:
            contacts = {
                "公司": "灵创智能",
                "电话": "400-XXX-XXXX",
                "官网": "www.lingchuang.com",
            }
        return make_contact_layout(title, contacts, template), solid_bg(
            template["primary"]
        )

    elif page_type == "comparison":
        mid = len(key_points) // 2
        return make_comparison_layout(
            title, "优势一", key_points[:mid], "优势二", key_points[mid:], template
        ), bg

    elif page_type == "table":
        headers = ["项目", "详情"]
        rows = [[f"指标{i + 1}", p] for i, p in enumerate(key_points[:8])]
        return make_table_layout(title, headers, rows, template), bg

    else:  # content
        has_chart = (
            "chart" in description.lower()
            or "数据" in description
            or "增长" in description
        )
        return make_title_content_layout(title, key_points, template, has_chart), bg
