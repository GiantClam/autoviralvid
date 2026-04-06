import pytest

from src.schemas.ppt import ExportRequest, SlideContent, SlideElement
from src.minimax_exporter import build_payload
from src.ppt_service import (
    _apply_visual_orchestration,
    _ensure_content_contract,
    _hydrate_image_assets,
    _presentation_plan_to_render_payload,
)
from src.ppt_quality_gate import validate_deck
from src.schemas.ppt_plan import ContentBlock, PresentationPlan, SlideContentStrategy, SlidePlan
from src.ppt_template_catalog import quality_profile as load_quality_profile


def test_export_request_has_retry_scope_fields():
    req = ExportRequest(slides=[], title="t", author="a")
    assert hasattr(req, "retry_scope")
    assert hasattr(req, "retry_hint")
    assert hasattr(req, "template_file_url")
    assert req.retry_scope == "deck"


def test_slide_and_block_ids_are_stable_defaults():
    slide = SlideContent(
        title="Hello",
        elements=[SlideElement(type="text", content="Body")],
        narration="x",
        duration=120,
    )
    assert slide.slide_id == slide.id
    assert slide.elements[0].block_id == slide.elements[0].id


def test_slide_content_preserves_extra_render_contract_fields():
    slide = SlideContent(
        title="Legislation process",
        narration="classroom",
        slide_type="content",
        layout_grid="split_2",
        template_family="split_media_dark",
        blocks=[{"block_type": "title", "content": "Legislation process"}],
    )
    dumped = slide.model_dump()
    assert dumped.get("slide_type") == "content"
    assert dumped.get("layout_grid") == "split_2"
    assert dumped.get("template_family") == "split_media_dark"
    assert isinstance(dumped.get("blocks"), list)


def test_export_request_template_file_url_validation():
    req = ExportRequest(slides=[], title="t", author="a", template_file_url="https://example.com/template.pptx")
    assert req.template_file_url == "https://example.com/template.pptx"


def test_minimax_payload_contains_theme_contract():
    payload = build_payload(
        slides=[{"title": "Intro"}],
        title="Deck",
        author="bot",
        style_variant="soft",
        palette_key="slate_minimal",
        theme_recipe="consulting_clean",
        tone="light",
    )
    assert payload["theme"]["style"] == "soft"
    assert payload["theme"]["palette"] == "slate_minimal"
    assert payload["theme"]["theme_recipe"] == "consulting_clean"
    assert payload["theme"]["tone"] == "light"
    assert payload["minimax_style_variant"] == "soft"
    assert payload["minimax_palette_key"] == "slate_minimal"
    assert payload["theme_recipe"] == "consulting_clean"
    assert payload["tone"] == "light"
    assert payload["template_id"]
    assert payload["skill_profile"]
    assert payload["schema_profile"]


def test_minimax_payload_normalizes_slide_contract_fields():
    payload = build_payload(
        slides=[{"title": "Intro"}, {"title": "Body"}, {"title": "End"}],
        title="Deck",
        author="bot",
    )
    slides = payload["slides"]
    assert slides[0]["slide_type"] == "cover"
    assert slides[-1]["slide_type"] == "summary"
    assert slides[0]["layout_grid"] == "hero_1"
    assert slides[1]["layout_grid"] == "split_2"
    assert slides[1]["page_number"] == 2
    assert isinstance(slides[1]["blocks"], list)
    assert slides[1]["template_id"]
    assert slides[1]["skill_profile"]
    assert slides[1]["hardness_profile"] in {"minimal", "balanced", "strict"}


def test_render_payload_preserves_semantic_slide_type_and_layout_grid():
    plan = PresentationPlan(
        title="Deck",
        theme="slate",
        style="soft",
        slides=[
            SlidePlan(
                page_number=1,
                slide_type="cover",
                layout_grid="cover",
                blocks=[
                    ContentBlock(block_type="title", position="top", content="Deck"),
                    ContentBlock(block_type="subtitle", position="center", content="Intro"),
                ],
            ),
            SlidePlan(
                page_number=2,
                slide_type="content",
                layout_grid="split_2",
                blocks=[
                    ContentBlock(block_type="title", position="top", content="Growth"),
                    ContentBlock(
                        block_type="chart",
                        position="right",
                        content="Trend",
                        data={
                            "labels": ["2024", "2025E"],
                            "datasets": [{"label": "Revenue", "data": [100, 128]}],
                        },
                    ),
                    ContentBlock(block_type="body", position="left", content="Key points"),
                ],
            ),
            SlidePlan(
                page_number=3,
                slide_type="summary",
                layout_grid="summary",
                blocks=[
                    ContentBlock(block_type="title", position="top", content="Summary"),
                    ContentBlock(block_type="list", position="center", content="Done"),
                ],
            ),
        ],
    )

    payload = _presentation_plan_to_render_payload(plan)
    middle = payload["slides"][1]
    assert middle["slide_type"] == "content"
    assert middle["layout_grid"] == "split_2"
    assert middle["page_type"] == "data_visualization"
    assert middle["subtype"] == "data_visualization"
    assert [block["card_id"] for block in middle["blocks"]] == ["title", "right", "left"]


def test_render_payload_preserves_slide_content_strategy_contract():
    plan = PresentationPlan(
        title="Deck",
        theme="slate",
        style="soft",
        slides=[
            SlidePlan(
                page_number=1,
                slide_type="cover",
                layout_grid="cover",
                blocks=[
                    ContentBlock(block_type="title", position="top", content="Deck"),
                    ContentBlock(block_type="subtitle", position="center", content="Intro"),
                ],
                content_strategy=SlideContentStrategy(
                    assertion="Deck",
                    evidence=["Context", "Problem"],
                    data_anchor="Market baseline",
                    page_role="transition",
                    density_hint="breathing",
                    render_path="pptxgenjs",
                ),
            ),
            SlidePlan(
                page_number=2,
                slide_type="content",
                layout_grid="timeline",
                blocks=[
                    ContentBlock(block_type="title", position="top", content="Execution path defined: Q1-Q3 milestones"),
                    ContentBlock(block_type="list", position="left", content="Q1 validate;Q2 launch;Q3 scale"),
                ],
                content_strategy=SlideContentStrategy(
                    assertion="Execution path defined: Q1-Q3 milestones",
                    evidence=["Q1 validate", "Q2 launch", "Q3 scale"],
                    data_anchor="Q1-Q3 milestones",
                    page_role="transition",
                    density_hint="medium",
                    render_path="svg",
                ),
            ),
            SlidePlan(
                page_number=3,
                slide_type="summary",
                layout_grid="summary",
                blocks=[
                    ContentBlock(block_type="title", position="top", content="Summary"),
                    ContentBlock(block_type="list", position="center", content="Done"),
                ],
                content_strategy=SlideContentStrategy(
                    assertion="Summary",
                    evidence=["Outcome"],
                    data_anchor="Outcome",
                    page_role="summary",
                    density_hint="breathing",
                    render_path="pptxgenjs",
                ),
            ),
        ],
    )

    payload = _presentation_plan_to_render_payload(plan)
    middle = payload["slides"][1]
    strategy = middle.get("content_strategy") or {}
    assert strategy.get("assertion") == "Execution path defined: Q1-Q3 milestones"
    assert strategy.get("page_role") == "transition"
    assert strategy.get("render_path") == "svg"


def test_content_contract_trims_blocks_by_layout_capacity_without_placeholder_image():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "title": "增长总览",
        "narration": "营收提升 32%，转化率提升 18%",
        "blocks": [
            {"block_type": "title", "content": "增长总览"},
            {"block_type": "body", "content": "营收提升 32%"},
            {"block_type": "list", "content": "转化率提升 18%;留存提升 9%"},
            {"block_type": "image", "content": {"title": "Visual only"}},
        ],
    }

    fixed = _ensure_content_contract(slide)
    blocks = fixed["blocks"]
    text_non_title = [
        b
        for b in blocks
        if str(b.get("block_type") or "").strip().lower()
        in {"body", "list", "text", "subtitle", "quote", "icon_text", "comparison"}
    ]
    assert len(text_non_title) >= 2
    assert all(
        "brand visual placeholder" not in str(b.get("content"))
        for b in blocks
    )


def test_visual_orchestration_reapplies_contract_after_pagination():
    bullets = [f"要点{i}" for i in range(1, 9)]
    payload = {
        "title": "测试分页续页",
        "quality_profile": "default",
        "slides": [
            {
                "slide_id": "s-1",
                "title": "核心能力",
                "slide_type": "content",
                "layout_grid": "split_2",
                "blocks": [
                    {"block_type": "title", "content": "核心能力"},
                    {"block_type": "list", "content": ";".join(bullets)},
                ],
            }
        ],
    }

    out = _apply_visual_orchestration(payload)
    slides = out["slides"]
    assert len(slides) >= 2

    for slide in slides:
        if str(slide.get("slide_type") or "").strip().lower() != "content":
            continue
        text_non_title = [
            b
            for b in (slide.get("blocks") or [])
            if str(b.get("block_type") or "").strip().lower() in {"body", "list", "text", "subtitle", "quote", "icon_text", "comparison"}
        ]
        assert len(text_non_title) >= 2


def test_visual_orchestration_assigns_render_path_per_slide():
    payload = {
        "title": "Render path routing",
        "quality_profile": "default",
        "slides": [
            {
                "slide_id": "s-cover",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "title": "Cover",
                "blocks": [{"block_type": "title", "content": "Cover"}],
            },
            {
                "slide_id": "s-flow",
                "slide_type": "content",
                "layout_grid": "timeline",
                "title": "Flow",
                "blocks": [
                    {"block_type": "title", "content": "Flow"},
                    {"block_type": "workflow", "content": "step1;step2;step3"},
                ],
            },
            {
                "slide_id": "s-summary",
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "title": "Summary",
                "blocks": [{"block_type": "title", "content": "Summary"}],
            },
        ],
    }
    out = _apply_visual_orchestration(payload)
    slides = out.get("slides") or []
    assert slides[0].get("render_path") == "pptxgenjs"
    assert slides[1].get("render_path") in {"svg", "pptxgenjs"}
    assert slides[-1].get("render_path") == "pptxgenjs"


def test_content_contract_keeps_two_text_blocks_for_content_even_hero_layout():
    slide = {
        "slide_type": "content",
        "layout_grid": "hero_1",
        "title": "市场机会",
        "blocks": [
            {"block_type": "title", "content": "市场机会"},
            {"block_type": "list", "content": "需求增长;国产替代"},
        ],
    }

    fixed = _ensure_content_contract(slide)
    text_non_title = [
        b
        for b in (fixed.get("blocks") or [])
        if str(b.get("block_type") or "").strip().lower() in {"body", "list", "text", "subtitle", "quote", "icon_text", "comparison"}
    ]
    assert len(text_non_title) >= 2


def test_content_contract_avoids_title_echo_in_non_title_blocks():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "title": "增长总览",
        "blocks": [
            {"block_type": "title", "content": "增长总览"},
            {"block_type": "body", "content": "增长总览"},
        ],
    }
    fixed = _ensure_content_contract(slide)
    title = str(fixed.get("title") or "").strip()
    non_title_texts = [
        str(block.get("content") or "").strip()
        for block in (fixed.get("blocks") or [])
        if str(block.get("block_type") or "").strip().lower() != "title"
    ]
    assert all(text and text != title for text in non_title_texts)


def test_content_contract_kpi_anchor_never_uses_zero_placeholder():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "title": "工业升级",
        "narration": "关键指标待更新，当前基线为 0",
        "blocks": [{"block_type": "title", "content": "工业升级"}],
    }
    fixed = _ensure_content_contract(slide)
    for block in fixed.get("blocks") or []:
        if str(block.get("block_type") or "").strip().lower() != "kpi":
            continue
        data = block.get("data") or {}
        assert float(data.get("number") or 0) != 0.0


def test_content_contract_injects_image_anchor_when_required():
    slide = {
        "slide_type": "content",
        "layout_grid": "grid_4",
        "title": "视觉锚点",
        "blocks": [
            {"block_type": "title", "content": "视觉锚点"},
            {"block_type": "body", "content": "核心要点A"},
            {"block_type": "list", "content": "要点B;要点C"},
        ],
    }
    fixed = _ensure_content_contract(slide, min_content_blocks=3, require_image_anchor=True)
    image_blocks = [
        block
        for block in (fixed.get("blocks") or [])
        if str(block.get("block_type") or "").strip().lower() == "image"
    ]
    assert image_blocks
    image_content = image_blocks[0].get("content") or {}
    assert str(image_content.get("url") or "").startswith("data:image/svg+xml")


def test_content_contract_image_anchor_keeps_min_text_blocks_for_visual_anchor_profile():
    slide = {
        "slide_type": "content",
        "layout_grid": "grid_3",
        "title": "企业简介",
        "template_family": "bento_mosaic_dark",
        "blocks": [
            {"block_type": "title", "content": "企业简介"},
            {"block_type": "body", "content": "公司定位与核心能力"},
            {
                "block_type": "chart",
                "content": {
                    "labels": ["研发", "交付", "服务"],
                    "datasets": [{"label": "占比", "data": [35, 40, 25]}],
                },
            },
        ],
    }

    fixed = _ensure_content_contract(slide, min_content_blocks=3, require_image_anchor=True)
    blocks = fixed.get("blocks") or []
    visual_types = {"image", "chart", "kpi", "workflow", "diagram"}
    text_non_visual = [
        block
        for block in blocks
        if str(block.get("block_type") or "").strip().lower()
        in {"body", "list", "text", "subtitle", "quote", "icon_text", "comparison"}
        and str(block.get("block_type") or "").strip().lower() not in visual_types
    ]
    block_types = [str(block.get("block_type") or "").strip().lower() for block in blocks]
    assert len(text_non_visual) >= 2
    assert any(bt in {"image", "chart", "kpi", "workflow", "diagram", "table"} for bt in block_types)


def test_content_contract_prefers_chart_kpi_hard_contract_over_soft_image_anchor():
    slide = {
        "slide_type": "content",
        "layout_grid": "grid_3",
        "title": "宏观市场机遇",
        "template_family": "dashboard_dark",
        "blocks": [
            {"block_type": "title", "content": "宏观市场机遇"},
            {"block_type": "body", "content": "市场空间持续扩张"},
            {
                "block_type": "chart",
                "content": {
                    "labels": ["2024", "2025E", "2026E"],
                    "datasets": [{"label": "规模", "data": [120, 160, 210]}],
                },
            },
        ],
    }

    fixed = _ensure_content_contract(slide, min_content_blocks=3, require_image_anchor=True)
    blocks = fixed.get("blocks") or []
    block_types = [str(block.get("block_type") or "").strip().lower() for block in blocks]
    text_non_visual_count = len(
        [
            bt
            for bt in block_types
            if bt in {"body", "list", "text", "subtitle", "quote", "icon_text", "comparison"}
        ]
    )
    assert text_non_visual_count >= 2
    assert any(bt in {"chart", "kpi"} for bt in block_types)


def test_content_contract_fulfills_chart_or_kpi_template_requirements():
    slide = {
        "slide_type": "content",
        "layout_grid": "grid_3",
        "title": "市场进展",
        "template_family": "dashboard_dark",
        "narration": "重点行业订单增长稳定。",
        "blocks": [
            {"block_type": "title", "content": "市场进展"},
            {"block_type": "body", "content": "订单结构持续优化"},
        ],
    }
    fixed = _ensure_content_contract(slide)
    blocks = fixed.get("blocks") or []
    non_title_text = [
        b
        for b in blocks
        if str(b.get("block_type") or "").strip().lower() in {"body", "list", "text", "subtitle", "quote", "icon_text", "comparison"}
    ]
    assert len(non_title_text) >= 2
    assert any(str(b.get("block_type") or "").strip().lower() in {"chart", "kpi"} for b in blocks)


def test_visual_orchestration_high_density_injects_image_anchor():
    payload = {
        "title": "高标准视觉锚点",
        "quality_profile": "high_density_consulting",
        "slides": [
            {
                "slide_id": "s-cover",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "title": "封面",
                "blocks": [{"block_type": "title", "content": "封面"}],
            },
            {
                "slide_id": "s-content",
                "slide_type": "content",
                "layout_grid": "grid_4",
                "title": "方案能力",
                "blocks": [
                    {"block_type": "title", "content": "方案能力"},
                    {"block_type": "body", "content": "能力一"},
                    {"block_type": "list", "content": "能力二;能力三;能力四"},
                ],
            },
            {
                "slide_id": "s-summary",
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "title": "总结",
                "blocks": [{"block_type": "title", "content": "总结"}],
            },
        ],
    }
    out = _apply_visual_orchestration(payload)
    content = (out.get("slides") or [])[1]
    blocks = content.get("blocks") or []
    block_types = [str(block.get("block_type") or "").strip().lower() for block in blocks]
    text_non_visual_count = len(
        [
            bt
            for bt in block_types
            if bt in {"body", "list", "text", "subtitle", "quote", "icon_text", "comparison"}
        ]
    )
    assert text_non_visual_count >= 2
    assert any(bt in {"image", "chart", "kpi", "workflow", "diagram"} for bt in block_types)


def test_visual_orchestration_remaps_split_layout_for_high_density_profile():
    payload = {
        "title": "高密度测试",
        "quality_profile": "high_density_consulting",
        "slides": [
            {
                "slide_id": "s-cover",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "title": "封面",
                "blocks": [{"block_type": "title", "content": "封面"}],
            },
            {
                "slide_id": "s-1",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "核心结论",
                "blocks": [
                    {"block_type": "title", "content": "核心结论"},
                    {"block_type": "list", "content": "结论一;结论二;结论三"},
                ],
            },
            {
                "slide_id": "s-end",
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "title": "总结",
                "blocks": [{"block_type": "title", "content": "总结"}],
            },
        ],
    }
    out = _apply_visual_orchestration(payload)
    middle = out["slides"][1]
    assert str(middle.get("layout_grid") or "").strip().lower() in {"grid_3", "grid_4", "bento_5", "timeline", "bento_6"}


def test_visual_orchestration_locks_template_family_per_slide():
    payload = {
        "title": "Template lock",
        "quality_profile": "high_density_consulting",
        "slides": [
            {
                "slide_id": "s-cover",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "title": "Cover",
                "blocks": [{"block_type": "title", "content": "Cover"}],
            },
            {
                "slide_id": "s-1",
                "slide_type": "content",
                "layout_grid": "grid_3",
                "title": "Body",
                "blocks": [
                    {"block_type": "title", "content": "Body"},
                    {"block_type": "list", "content": "a;b;c;d;e;f"},
                ],
            },
            {
                "slide_id": "s-end",
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "title": "Summary",
                "blocks": [{"block_type": "title", "content": "Summary"}],
            },
        ],
    }
    out = _apply_visual_orchestration(payload)
    assert all(bool(slide.get("template_lock")) for slide in out.get("slides") or [])


def test_visual_orchestration_high_density_converges_template_family_set():
    payload = {
        "title": "Family convergence",
        "quality_profile": "high_density_consulting",
        "template_family": "auto",
        "slides": [
            {
                "slide_id": "s-cover",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "title": "Cover",
                "blocks": [{"block_type": "title", "content": "Cover"}],
            },
            {
                "slide_id": "s-1",
                "slide_type": "content",
                "layout_grid": "grid_3",
                "template_family": "ecosystem_orange_dark",
                "title": "A",
                "blocks": [{"block_type": "title", "content": "A"}, {"block_type": "list", "content": "a;b;c;d;e"}],
            },
            {
                "slide_id": "s-2",
                "slide_type": "content",
                "layout_grid": "grid_4",
                "template_family": "neural_blueprint_light",
                "title": "B",
                "blocks": [{"block_type": "title", "content": "B"}, {"block_type": "list", "content": "a;b;c;d;e"}],
            },
            {
                "slide_id": "s-3",
                "slide_type": "content",
                "layout_grid": "bento_5",
                "template_family": "consulting_warm_light",
                "title": "C",
                "blocks": [{"block_type": "title", "content": "C"}, {"block_type": "list", "content": "a;b;c;d;e"}],
            },
            {
                "slide_id": "s-4",
                "slide_type": "content",
                "layout_grid": "timeline",
                "template_family": "architecture_dark_panel",
                "title": "D",
                "blocks": [{"block_type": "title", "content": "D"}, {"block_type": "list", "content": "a;b;c;d;e"}],
            },
            {
                "slide_id": "s-end",
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "title": "Summary",
                "blocks": [{"block_type": "title", "content": "Summary"}],
            },
        ],
    }
    out = _apply_visual_orchestration(payload)
    content_families = {
        str(slide.get("template_family") or "").strip().lower()
        for slide in (out.get("slides") or [])
        if str(slide.get("slide_type") or "").strip().lower() == "content"
    }
    assert content_families.issubset(
        {"dashboard_dark", "bento_2x2_dark", "bento_mosaic_dark", "ops_lifecycle_light", "process_flow_dark"}
    )


def test_visual_orchestration_high_density_limits_template_family_switch_ratio():
    slides = [
        {
            "slide_id": "s-cover",
            "slide_type": "cover",
            "layout_grid": "hero_1",
            "title": "Cover",
            "blocks": [{"block_type": "title", "content": "Cover"}],
        }
    ]
    layout_cycle = ["grid_3", "grid_4", "bento_5", "timeline", "bento_6"]
    for idx in range(1, 11):
        layout = layout_cycle[(idx - 1) % len(layout_cycle)]
        slides.append(
            {
                "slide_id": f"s-{idx}",
                "slide_type": "content",
                "layout_grid": layout,
                "title": f"Topic {idx}",
                "blocks": [
                    {"block_type": "title", "content": f"Topic {idx}"},
                    {"block_type": "list", "content": "a;b;c;d;e"},
                ],
            }
        )
    slides.append(
        {
            "slide_id": "s-summary",
            "slide_type": "summary",
            "layout_grid": "hero_1",
            "title": "Summary",
            "blocks": [{"block_type": "title", "content": "Summary"}],
        }
    )
    payload = {
        "title": "Switch ratio control",
        "quality_profile": "high_density_consulting",
        "template_family": "auto",
        "slides": slides,
    }
    out = _apply_visual_orchestration(payload)
    families = [
        str(slide.get("template_family") or "").strip().lower()
        for slide in (out.get("slides") or [])
        if str(slide.get("slide_type") or "").strip().lower() == "content"
    ]
    switches = sum(1 for i in range(1, len(families)) if families[i] != families[i - 1])
    switch_ratio = switches / max(1, len(families) - 1)
    threshold = float(load_quality_profile("high_density_consulting").get("template_family_max_switch_ratio") or 0.8)
    assert switch_ratio <= threshold


def test_visual_orchestration_enforces_density_rhythm_every_five_middle_pages():
    slides = [
        {
            "slide_id": "s-cover",
            "slide_type": "cover",
            "layout_grid": "hero_1",
            "title": "Cover",
            "blocks": [{"block_type": "title", "content": "Cover"}],
        }
    ]
    for idx, layout in enumerate(["grid_4", "bento_5", "bento_6", "grid_3", "split_2", "timeline", "grid_4"], start=1):
        slides.append(
            {
                "slide_id": f"s-{idx}",
                "slide_type": "content",
                "layout_grid": layout,
                "title": f"Topic {idx}",
                "blocks": [
                    {"block_type": "title", "content": f"Topic {idx}"},
                    {"block_type": "list", "content": "a;b;c;d;e"},
                ],
            }
        )
    slides.append(
        {
            "slide_id": "s-summary",
            "slide_type": "summary",
            "layout_grid": "hero_1",
            "title": "Summary",
            "blocks": [{"block_type": "title", "content": "Summary"}],
        }
    )
    out = _apply_visual_orchestration(
        {
            "title": "Density rhythm",
            "quality_profile": "high_density_consulting",
            "template_family": "auto",
            "slides": slides,
        }
    )
    middle_layouts = [
        str(slide.get("layout_grid") or "").strip().lower()
        for slide in (out.get("slides") or [])[1:-1]
        if isinstance(slide, dict)
    ]
    for start in range(0, len(middle_layouts) - 4):
        window = middle_layouts[start:start + 5]
        assert any(item in {"hero_1", "section", "divider"} for item in window)


@pytest.mark.asyncio
async def test_hydrate_image_assets_uses_placeholder_when_serper_unavailable(monkeypatch):
    monkeypatch.setenv("PPT_IMAGE_ASSET_ENABLED", "false")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    payload = {
        "title": "Image fallback",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "Visual",
                "blocks": [
                    {"block_type": "image", "card_id": "img1", "content": {"title": "Factory"}},
                ],
            }
        ],
    }
    out = await _hydrate_image_assets(payload)
    image_block = out["slides"][0]["blocks"][0]
    content = image_block.get("content") or {}
    url = str(content.get("url") or "")
    assert url.startswith("data:image/svg+xml")


@pytest.mark.asyncio
async def test_hydrate_image_assets_prefers_user_url_as_level_1(monkeypatch):
    import src.ppt_service as ppt_service

    monkeypatch.setenv("PPT_IMAGE_ASSET_ENABLED", "true")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    async def _fake_fetch_image_data_uri(url: str, max_bytes: int = 3_000_000):
        assert "example.com/image.png" in url
        return "data:image/png;base64,ZmFrZQ=="

    monkeypatch.setattr(ppt_service, "_fetch_image_data_uri", _fake_fetch_image_data_uri)

    payload = {
        "title": "User image",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "Visual",
                "blocks": [
                    {"block_type": "image", "card_id": "img1", "content": {"title": "Factory", "url": "https://example.com/image.png"}},
                ],
            }
        ],
    }
    out = await _hydrate_image_assets(payload)
    image_block = out["slides"][0]["blocks"][0]
    content = image_block.get("content") or {}
    data = image_block.get("data") or {}
    assert str(content.get("url") or "").startswith("data:image/png;base64,")
    assert data.get("source_type") == "user_url"
    assert data.get("source_level") == 1


@pytest.mark.asyncio
async def test_hydrate_image_assets_uses_ai_svg_for_abstract_intent(monkeypatch):
    monkeypatch.setenv("PPT_IMAGE_ASSET_ENABLED", "true")
    monkeypatch.setenv("PPT_IMAGE_AI_SVG_ENABLED", "true")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    payload = {
        "title": "AI strategy",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "AI workflow strategy",
                "blocks": [
                    {"block_type": "image", "card_id": "img1", "content": {"title": "Architecture strategy"}},
                ],
            }
        ],
    }
    out = await _hydrate_image_assets(payload)
    image_block = out["slides"][0]["blocks"][0]
    content = image_block.get("content") or {}
    data = image_block.get("data") or {}
    assert str(content.get("url") or "").startswith("data:image/svg+xml")
    assert data.get("source_type") == "ai_svg"
    assert data.get("source_level") == 2


@pytest.mark.asyncio
async def test_hydrate_image_assets_falls_back_to_icon_bg_before_brand_placeholder(monkeypatch):
    import src.ppt_service as ppt_service

    monkeypatch.setenv("PPT_IMAGE_ASSET_ENABLED", "true")
    monkeypatch.setenv("PPT_IMAGE_ICON_BG_ENABLED", "true")
    monkeypatch.setenv("SERPER_API_KEY", "fake-serper-key")

    async def _fake_search_serper_images(*, query: str, api_key: str, num: int = 5, hl: str = "zh-cn"):
        assert api_key == "fake-serper-key"
        return []

    monkeypatch.setattr(ppt_service, "_search_serper_images", _fake_search_serper_images)

    payload = {
        "title": "Quarterly report",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "Sales comparison",
                "blocks": [
                    {"block_type": "image", "card_id": "img1", "content": {"title": "Sales outlook"}},
                ],
            }
        ],
    }
    out = await _hydrate_image_assets(payload)
    image_block = out["slides"][0]["blocks"][0]
    content = image_block.get("content") or {}
    data = image_block.get("data") or {}
    assert str(content.get("url") or "").startswith("data:image/svg+xml")
    assert data.get("source_type") == "icon_bg"
    assert data.get("source_level") == 4


@pytest.mark.asyncio
async def test_hydrate_image_assets_uses_serper_stock_as_level_3(monkeypatch):
    import src.ppt_service as ppt_service

    monkeypatch.setenv("PPT_IMAGE_ASSET_ENABLED", "true")
    monkeypatch.setenv("PPT_IMAGE_AI_SVG_ENABLED", "false")
    monkeypatch.setenv("PPT_IMAGE_ICON_BG_ENABLED", "true")
    monkeypatch.setenv("SERPER_API_KEY", "fake-serper-key")

    async def _fake_search_serper_images(*, query: str, api_key: str, num: int = 5, hl: str = "zh-cn"):
        assert api_key == "fake-serper-key"
        return [
            {
                "url": "https://images.unsplash.com/photo-123",
                "title": "Factory assembly line",
                "source": "unsplash.com",
            }
        ]

    async def _fake_fetch_image_data_uri(url: str, max_bytes: int = 3_000_000):
        assert "unsplash.com" in url
        return "data:image/jpeg;base64,ZmFrZQ=="

    monkeypatch.setattr(ppt_service, "_search_serper_images", _fake_search_serper_images)
    monkeypatch.setattr(ppt_service, "_fetch_image_data_uri", _fake_fetch_image_data_uri)

    payload = {
        "title": "Manufacturing report",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "Factory production line",
                "blocks": [
                    {"block_type": "image", "card_id": "img1", "content": {"title": "On-site production photo"}},
                ],
            }
        ],
    }
    out = await _hydrate_image_assets(payload)
    image_block = out["slides"][0]["blocks"][0]
    content = image_block.get("content") or {}
    data = image_block.get("data") or {}
    assert str(content.get("url") or "").startswith("data:image/jpeg;base64,")
    assert data.get("source_type") == "stock"
    assert data.get("source_level") == 3


@pytest.mark.asyncio
async def test_hydrate_image_assets_falls_back_to_brand_placeholder_as_level_5(monkeypatch):
    import src.ppt_service as ppt_service

    monkeypatch.setenv("PPT_IMAGE_ASSET_ENABLED", "true")
    monkeypatch.setenv("PPT_IMAGE_AI_SVG_ENABLED", "false")
    monkeypatch.setenv("PPT_IMAGE_ICON_BG_ENABLED", "false")
    monkeypatch.setenv("SERPER_API_KEY", "fake-serper-key")

    async def _fake_search_serper_images(*, query: str, api_key: str, num: int = 5, hl: str = "zh-cn"):
        assert api_key == "fake-serper-key"
        return []

    monkeypatch.setattr(ppt_service, "_search_serper_images", _fake_search_serper_images)

    payload = {
        "title": "Quarterly operations",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "Factory operations photo",
                "blocks": [
                    {"block_type": "image", "card_id": "img1", "content": {"title": "Factory floor scene"}},
                ],
            }
        ],
    }
    out = await _hydrate_image_assets(payload)
    image_block = out["slides"][0]["blocks"][0]
    content = image_block.get("content") or {}
    data = image_block.get("data") or {}
    assert str(content.get("url") or "").startswith("data:image/svg+xml")
    assert data.get("source_type") == "placeholder"
    assert data.get("source_level") == 5


def test_visual_orchestration_does_not_paginate_cover_without_explicit_slide_type():
    payload = {
        "title": "Cover pagination guard",
        "quality_profile": "high_density_consulting",
        "slides": [
            {
                "slide_id": "s-cover",
                "title": "Cover",
                "blocks": [
                    {"block_type": "title", "content": "Cover"},
                    {
                        "block_type": "list",
                        "content": ";".join([f"cover point {i} with enough text" for i in range(1, 12)]),
                    },
                ],
            },
            {
                "slide_id": "s-body",
                "title": "Body",
                "blocks": [
                    {"block_type": "title", "content": "Body"},
                    {"block_type": "list", "content": "a;b;c;d;e;f;g;h"},
                ],
            },
            {
                "slide_id": "s-summary",
                "title": "Summary",
                "blocks": [
                    {"block_type": "title", "content": "Summary"},
                    {"block_type": "list", "content": "x;y;z"},
                ],
            },
        ],
    }
    out = _apply_visual_orchestration(payload)
    slides = out.get("slides") or []
    assert slides[0].get("slide_type") == "cover"
    assert slides[-1].get("slide_type") == "summary"
    assert all(str(item.get("continuation_of") or "") != "s-cover" for item in slides[1:])


def test_visual_orchestration_sanitizes_placeholder_text_in_summary_elements():
    payload = {
        "title": "Placeholder sanitize",
        "quality_profile": "high_density_consulting",
        "slides": [
            {
                "slide_id": "s-cover",
                "title": "Cover",
                "blocks": [{"block_type": "title", "content": "Cover"}],
            },
            {
                "slide_id": "s-summary",
                "title": "联系方式",
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "elements": [
                    {"type": "text", "content": "电话: 400-XXX-XXXX"},
                    {"type": "text", "content": "TODO"},
                ],
                "blocks": [],
            },
        ],
    }
    out = _apply_visual_orchestration(payload)
    issues = validate_deck(out.get("slides") or [], profile="high_density_consulting").issues
    assert not any(issue.code == "placeholder_pollution" for issue in issues)
    summary = (out.get("slides") or [])[-1]
    texts = [
        str(item.get("content") or "")
        for item in (summary.get("elements") or [])
        if str(item.get("type") or "").strip().lower() == "text"
    ]
    joined = " ".join(texts).lower()
    assert "xxx" not in joined
    assert "todo" not in joined
