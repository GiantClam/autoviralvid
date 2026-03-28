"""
PPTX 母版渲染引擎 — 用 python-pptx 填充预设模板

核心思想: 不让代码控制审美，让代码去填空
预设 6 种版式: cover, bullet_points, split_left_img, split_right_img, quote, comparison, big_number
"""

from __future__ import annotations

import io
import logging
import os
from typing import List, Optional

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from src.schemas.slide_v5 import SlideContentV5

logger = logging.getLogger("pptx_template")


# ════════════════════════════════════════════════════════════════════
# 配色方案
# ════════════════════════════════════════════════════════════════════

THEMES = {
    "professional": {
        "primary": RGBColor(0x1E, 0x3A, 0x5F),
        "secondary": RGBColor(0x25, 0x63, 0xEB),
        "accent": RGBColor(0x38, 0xBD, 0xF8),
        "text": RGBColor(0x1E, 0x29, 0x3B),
        "text_light": RGBColor(0x64, 0x74, 0x8B),
        "white": RGBColor(0xFF, 0xFF, 0xFF),
        "bg_light": RGBColor(0xFF, 0xFF, 0xFF),
        "bg_dark": RGBColor(0x0F, 0x17, 0x2A),
    },
    "dark": {
        "primary": RGBColor(0x38, 0xBD, 0xF8),
        "secondary": RGBColor(0x8B, 0x5C, 0xF6),
        "accent": RGBColor(0x22, 0xC5, 0x5E),
        "text": RGBColor(0xE2, 0xE8, 0xF0),
        "text_light": RGBColor(0x94, 0xA3, 0xB8),
        "white": RGBColor(0xFF, 0xFF, 0xFF),
        "bg_light": RGBColor(0x1E, 0x29, 0x3B),
        "bg_dark": RGBColor(0x0F, 0x17, 0x2A),
    },
}


def _hex_to_rgb(hex_str: str) -> RGBColor:
    h = hex_str.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _set_text(
    tf,
    text: str,
    font_size: int,
    color: RGBColor,
    bold: bool = False,
    alignment=PP_ALIGN.LEFT,
    font_name: str = "Microsoft YaHei",
):
    """设置文本框内容"""
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = alignment
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.name = font_name


def _set_rich_text(
    tf,
    items: List[str],
    font_size: int,
    color: RGBColor,
    font_name: str = "Microsoft YaHei",
):
    """设置带要点的富文本 (支持 **bold** 标记)"""
    tf.clear()
    for item in items:
        p = tf.add_paragraph()
        p.space_before = Pt(6)
        p.space_after = Pt(2)

        # 处理 **bold** 标记
        parts = re.split(r"\*\*(.+?)\*\*", item)
        for j, part in enumerate(parts):
            run = p.add_run()
            run.text = part
            run.font.size = Pt(font_size)
            run.font.color.rgb = color
            run.font.name = font_name
            if j % 2 == 1:  # 奇数索引是 bold 内容
                run.font.bold = True

    # 删除第一个空段落
    if tf.paragraphs and not tf.paragraphs[0].text:
        tf._txBody.remove(tf.paragraphs[0]._p)


import re


def _add_shape_bg(slide, color: RGBColor, left: int, top: int, width: int, height: int):
    """添加背景色块"""
    from pptx.enum.shapes import MSO_SHAPE

    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def _add_accent_bar(slide, color: RGBColor, left: int, top: int, height: int = 300):
    """添加强调色竖条"""
    from pptx.enum.shapes import MSO_SHAPE

    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, Inches(0.05), height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


# ════════════════════════════════════════════════════════════════════
# 版式渲染器
# ════════════════════════════════════════════════════════════════════

import httpx


def _download_image(url: str) -> Optional[bytes]:
    """下载图片"""
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def render_cover(prs: Presentation, slide_data: SlideContentV5, theme: dict):
    """封面版式"""
    layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(layout)

    # 全幅深色背景
    _add_shape_bg(
        slide, theme["bg_dark"], Inches(0), Inches(0), prs.slide_width, prs.slide_height
    )

    # 装饰圆
    from pptx.enum.shapes import MSO_SHAPE

    circle = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(12), Inches(-1.5), Inches(5), Inches(5)
    )
    circle.fill.solid()
    circle.fill.fore_color.rgb = theme["accent"]
    circle.fill.fore_color.brightness = 0.0
    circle.line.fill.background()

    # 主标题
    txBox = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(11), Inches(1.2))
    _set_text(txBox.text_frame, slide_data.content.title, 44, theme["white"], bold=True)

    # 装饰线
    _add_shape_bg(
        slide, theme["accent"], Inches(1), Inches(3.8), Inches(1), Inches(0.04)
    )

    # 副标题
    if slide_data.content.subtitle:
        txBox = slide.shapes.add_textbox(
            Inches(1), Inches(4.1), Inches(11), Inches(0.6)
        )
        _set_text(txBox.text_frame, slide_data.content.subtitle, 22, theme["accent"])


def render_bullet_points(prs: Presentation, slide_data: SlideContentV5, theme: dict):
    """要点列表版式"""
    layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(layout)

    # 标题栏
    _add_shape_bg(
        slide, theme["primary"], Inches(0), Inches(0), prs.slide_width, Inches(0.9)
    )

    # 标题
    txBox = slide.shapes.add_textbox(
        Inches(0.7), Inches(0.12), Inches(11), Inches(0.65)
    )
    _set_text(txBox.text_frame, slide_data.content.title, 28, theme["white"], bold=True)

    # 强调色竖条
    _add_accent_bar(
        slide,
        theme["accent"],
        Inches(0.7),
        Inches(1.2),
        Inches(min(len(slide_data.content.body_text) * 0.55, 5.5)),
    )

    # 要点列表
    if slide_data.content.body_text:
        txBox = slide.shapes.add_textbox(
            Inches(1), Inches(1.2), Inches(10.5), Inches(5.5)
        )
        tf = txBox.text_frame
        tf.word_wrap = True
        _set_rich_text(tf, slide_data.content.body_text, 18, theme["text"])

    # 高亮数据框 (右上)
    if slide_data.emphasis_words:
        highlight = slide_data.emphasis_words[0]
        _add_shape_bg(
            slide, theme["accent"], Inches(10), Inches(1.2), Inches(3), Inches(1.2)
        )
        txBox = slide.shapes.add_textbox(
            Inches(10.1), Inches(1.35), Inches(2.8), Inches(0.9)
        )
        _set_text(
            txBox.text_frame,
            highlight,
            24,
            theme["primary"],
            bold=True,
            alignment=PP_ALIGN.CENTER,
        )


def render_comparison(prs: Presentation, slide_data: SlideContentV5, theme: dict):
    """对比版式"""
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    comp = slide_data.content.comparison

    # 标题栏
    _add_shape_bg(
        slide, theme["primary"], Inches(0), Inches(0), prs.slide_width, Inches(0.9)
    )
    txBox = slide.shapes.add_textbox(
        Inches(0.7), Inches(0.12), Inches(11), Inches(0.65)
    )
    _set_text(txBox.text_frame, slide_data.content.title, 28, theme["white"], bold=True)

    if not comp:
        return

    # 左栏标题
    _add_shape_bg(
        slide, theme["secondary"], Inches(0.7), Inches(1.2), Inches(5.5), Inches(0.5)
    )
    txBox = slide.shapes.add_textbox(
        Inches(0.85), Inches(1.25), Inches(5.2), Inches(0.4)
    )
    _set_text(txBox.text_frame, comp.left_title, 18, theme["white"], bold=True)

    # 右栏标题
    _add_shape_bg(
        slide, theme["accent"], Inches(7.2), Inches(1.2), Inches(5.5), Inches(0.5)
    )
    txBox = slide.shapes.add_textbox(
        Inches(7.35), Inches(1.25), Inches(5.2), Inches(0.4)
    )
    _set_text(txBox.text_frame, comp.right_title, 18, theme["white"], bold=True)

    # 左栏要点
    if comp.left_items:
        items = [f"\u2713 {item}" for item in comp.left_items]
        txBox = slide.shapes.add_textbox(
            Inches(0.85), Inches(1.9), Inches(5.2), Inches(4.5)
        )
        tf = txBox.text_frame
        tf.word_wrap = True
        _set_rich_text(tf, items, 16, theme["text"])

    # 右栏要点
    if comp.right_items:
        items = [f"\u2713 {item}" for item in comp.right_items]
        txBox = slide.shapes.add_textbox(
            Inches(7.35), Inches(1.9), Inches(5.2), Inches(4.5)
        )
        tf = txBox.text_frame
        tf.word_wrap = True
        _set_rich_text(tf, items, 16, theme["text"])


def render_quote(prs: Presentation, slide_data: SlideContentV5, theme: dict):
    """名言/金句版式"""
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)

    # 深色背景
    _add_shape_bg(
        slide, theme["bg_dark"], Inches(0), Inches(0), prs.slide_width, prs.slide_height
    )

    # 引号装饰
    txBox = slide.shapes.add_textbox(Inches(1.5), Inches(1.5), Inches(1), Inches(1))
    _set_text(txBox.text_frame, "\u201c", 72, theme["accent"])

    # 金句正文
    text = (
        slide_data.content.body_text[0]
        if slide_data.content.body_text
        else slide_data.content.title
    )
    # 去掉 ** 标记但保留内容
    clean_text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    txBox = slide.shapes.add_textbox(Inches(2), Inches(2.5), Inches(9), Inches(2.5))
    tf = txBox.text_frame
    tf.word_wrap = True
    _set_text(tf, clean_text, 32, theme["white"])

    # 高亮词汇
    if slide_data.emphasis_words:
        highlighted = clean_text
        for w in slide_data.emphasis_words:
            highlighted = highlighted.replace(w, f"【{w}】")
        _set_text(tf, highlighted, 32, theme["white"])

    # 装饰线
    _add_shape_bg(
        slide, theme["accent"], Inches(2), Inches(5.2), Inches(1.5), Inches(0.04)
    )

    # 出处
    if slide_data.content.subtitle:
        txBox = slide.shapes.add_textbox(Inches(2), Inches(5.5), Inches(8), Inches(0.5))
        _set_text(
            txBox.text_frame,
            f"\u2014\u2014 {slide_data.content.subtitle}",
            16,
            theme["text_light"],
        )


def render_big_number(prs: Presentation, slide_data: SlideContentV5, theme: dict):
    """大数字版式"""
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)

    # 标题栏
    _add_shape_bg(
        slide, theme["primary"], Inches(0), Inches(0), prs.slide_width, Inches(0.9)
    )
    txBox = slide.shapes.add_textbox(
        Inches(0.7), Inches(0.12), Inches(11), Inches(0.65)
    )
    _set_text(txBox.text_frame, slide_data.content.title, 28, theme["white"], bold=True)

    bn = slide_data.content.big_number
    if bn:
        # 大数字
        txBox = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(11), Inches(2))
        _set_text(
            txBox.text_frame,
            bn.number,
            96,
            theme["secondary"],
            bold=True,
            alignment=PP_ALIGN.CENTER,
        )

        # 单位
        if bn.unit:
            txBox = slide.shapes.add_textbox(
                Inches(1), Inches(4.2), Inches(11), Inches(0.6)
            )
            _set_text(
                txBox.text_frame,
                bn.unit,
                24,
                theme["text_light"],
                alignment=PP_ALIGN.CENTER,
            )

        # 说明
        if bn.description:
            txBox = slide.shapes.add_textbox(Inches(2), Inches(5), Inches(9), Inches(1))
            _set_text(
                txBox.text_frame,
                bn.description,
                18,
                theme["text"],
                alignment=PP_ALIGN.CENTER,
            )


def render_split(
    prs: Presentation, slide_data: SlideContentV5, theme: dict, side: str = "left"
):
    """左右分栏版式 (图左文右 / 图右文左)"""
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)

    # 标题栏
    _add_shape_bg(
        slide, theme["primary"], Inches(0), Inches(0), prs.slide_width, Inches(0.9)
    )
    txBox = slide.shapes.add_textbox(
        Inches(0.7), Inches(0.12), Inches(11), Inches(0.65)
    )
    _set_text(txBox.text_frame, slide_data.content.title, 28, theme["white"], bold=True)

    if side == "left":
        # 左图
        if slide_data.content.image_url:
            img_data = _download_image(slide_data.content.image_url)
            if img_data:
                slide.shapes.add_picture(
                    io.BytesIO(img_data),
                    Inches(0.7),
                    Inches(1.2),
                    Inches(5.5),
                    Inches(4.5),
                )
        # 右文
        if slide_data.content.body_text:
            txBox = slide.shapes.add_textbox(
                Inches(6.5), Inches(1.2), Inches(6), Inches(5)
            )
            tf = txBox.text_frame
            tf.word_wrap = True
            _set_rich_text(tf, slide_data.content.body_text, 18, theme["text"])
    else:
        # 左文
        if slide_data.content.body_text:
            txBox = slide.shapes.add_textbox(
                Inches(0.7), Inches(1.2), Inches(6), Inches(5)
            )
            tf = txBox.text_frame
            tf.word_wrap = True
            _set_rich_text(tf, slide_data.content.body_text, 18, theme["text"])
        # 右图
        if slide_data.content.image_url:
            img_data = _download_image(slide_data.content.image_url)
            if img_data:
                slide.shapes.add_picture(
                    io.BytesIO(img_data),
                    Inches(6.5),
                    Inches(1.2),
                    Inches(5.5),
                    Inches(4.5),
                )


# ════════════════════════════════════════════════════════════════════
# 统一入口
# ════════════════════════════════════════════════════════════════════

RENDERERS = {
    "cover": render_cover,
    "bullet_points": render_bullet_points,
    "comparison": render_comparison,
    "quote": render_quote,
    "big_number": render_big_number,
    "split_left_img": lambda prs, s, t: render_split(prs, s, t, "left"),
    "split_right_img": lambda prs, s, t: render_split(prs, s, t, "right"),
}


def generate_pptx(
    slides: List[SlideContentV5],
    title: str,
    author: str,
    template_id: str = "professional",
) -> bytes:
    """
    使用母版模板生成 PPTX。

    Args:
        slides: 语义化幻灯片数据
        title: 演示文稿标题
        author: 作者
        template_id: 模板ID (professional / dark)

    Returns:
        PPTX 文件字节
    """
    theme = THEMES.get(template_id, THEMES["professional"])

    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = title
    prs.core_properties.author = author

    for slide_data in slides:
        renderer = RENDERERS.get(slide_data.layout_type, render_bullet_points)
        renderer(prs, slide_data, theme)

    # 输出为 bytes
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
