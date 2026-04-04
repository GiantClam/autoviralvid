import re

from src.minimax_exporter import _template_family_supports_slide, build_payload


def _norm(text: str) -> str:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", lowered)


def _block_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        for key in ("title", "body", "text", "label", "caption", "description"):
            value = str(content.get(key) or "").strip()
            if value:
                return value
    data = block.get("data")
    if isinstance(data, dict):
        for key in ("title", "label", "description", "text"):
            value = str(data.get(key) or "").strip()
            if value:
                return value
    return ""


def test_exporter_default_mode_is_official():
    payload = build_payload(slides=[], title="t", author="a")
    assert payload.get("generator_mode") == "official"
    assert payload.get("render_channel") == "local"
    assert payload.get("route_mode") == "standard"
    assert payload.get("original_style") is False
    assert payload.get("disable_local_style_rewrite") is False
    assert payload.get("visual_priority") is True
    assert payload.get("visual_density") == "balanced"
    assert payload.get("constraint_hardness") == "minimal"
    assert payload.get("template_id")
    assert payload.get("skill_profile")
    assert payload.get("schema_profile")
    assert payload.get("quality_profile")
    assert isinstance(payload.get("design_decision_v1"), dict)


def test_exporter_payload_includes_design_spec_contract():
    payload = build_payload(
        slides=[{"title": "Intro"}],
        title="Deck",
        author="bot",
        style_variant="pill",
        palette_key="pure_tech_blue",
    )
    spec = payload.get("design_spec") or {}
    assert isinstance(spec, dict)
    assert isinstance(spec.get("colors"), dict)
    assert isinstance(spec.get("typography"), dict)
    assert isinstance(spec.get("spacing"), dict)
    assert isinstance(spec.get("visual"), dict)
    assert spec.get("visual", {}).get("style_recipe") == "pill"
    assert str(spec.get("colors", {}).get("primary") or "").strip()
    assert str(spec.get("typography", {}).get("title_font") or "").strip()
    assert float(spec.get("spacing", {}).get("page_margin") or 0) > 0


def test_original_style_forces_disable_local_rewrite():
    payload = build_payload(
        slides=[{"title": "灵创智能"}],
        title="灵创智能",
        author="a",
        original_style=True,
        disable_local_style_rewrite=False,
    )
    assert payload["original_style"] is True
    assert payload["disable_local_style_rewrite"] is True


def test_exporter_channel_auto_defaults_to_local():
    payload = build_payload(
        slides=[{"title": "灵创智能"}],
        title="灵创智能",
        author="a",
        render_channel="auto",
    )
    assert payload["render_channel"] == "local"


def test_exporter_route_mode_passthrough():
    payload = build_payload(
        slides=[{"title": "Deck"}],
        title="Deck",
        author="a",
        route_mode="refine",
    )
    assert payload["route_mode"] == "refine"


def test_exporter_rewrites_duplicate_non_title_text_without_dropping_visual_anchor():
    payload = build_payload(
        slides=[
            {
                "title": "Manufacturing Overview",
                "slide_type": "content",
                "layout_grid": "grid_4",
                "blocks": [
                    {"block_type": "title", "content": "Manufacturing Overview"},
                    {"block_type": "body", "content": "Phase transition"},
                    {
                        "block_type": "image",
                        "content": {"title": "Phase transition", "url": "https://example.com/anchor.png"},
                    },
                ],
            }
        ],
        title="Deck",
        author="a",
        quality_profile="high_density_consulting",
    )
    blocks = payload["slides"][0]["blocks"]
    non_title_keys = []
    for block in blocks:
        if str(block.get("block_type") or "").strip().lower() == "title":
            continue
        key = _norm(_block_text(block))
        if key:
            non_title_keys.append(key)
    assert len(non_title_keys) == len(set(non_title_keys))
    image_blocks = [
        block
        for block in blocks
        if str(block.get("block_type") or "").strip().lower() == "image"
    ]
    assert image_blocks
    image_content = image_blocks[0].get("content") or {}
    assert str(image_content.get("url") or "") == "https://example.com/anchor.png"


def test_exporter_strips_supporting_point_prefix_from_non_title_blocks():
    payload = build_payload(
        slides=[
            {
                "title": "交付计划",
                "slide_type": "content",
                "layout_grid": "grid_3",
                "blocks": [
                    {"block_type": "title", "content": "交付计划"},
                    {"block_type": "body", "content": "补充要点：阶段一完成需求澄清"},
                    {"block_type": "body", "content": "补充要点：阶段一完成需求澄清"},
                ],
            }
        ],
        title="Deck",
        author="a",
    )
    texts = [
        _block_text(block)
        for block in payload["slides"][0]["blocks"]
        if str(block.get("block_type") or "").strip().lower() != "title"
    ]
    assert all(not str(text).startswith("补充要点") for text in texts)
    assert len({_norm(text) for text in texts if _norm(text)}) == len([text for text in texts if _norm(text)])


def test_exporter_payload_prefers_design_decision_when_requested_values_are_auto():
    payload = build_payload(
        slides=[
            {"slide_id": "s1", "title": "Intro", "slide_type": "content"},
        ],
        title="Deck",
        author="a",
        style_variant="auto",
        palette_key="auto",
        template_family="auto",
        design_decision={
            "version": "v1",
            "deck": {
                "style_variant": "rounded",
                "palette_key": "pure_tech_blue",
                "template_family": "ops_lifecycle_light",
                "skill_profile": "architecture",
            },
            "slides": [
                {"slide_id": "s1", "layout_grid": "timeline", "render_path": "svg"},
            ],
        },
    )
    assert payload.get("minimax_style_variant") == "rounded"
    assert payload.get("minimax_palette_key") == "pure_tech_blue"
    assert payload.get("template_family") == "ops_lifecycle_light"
    assert payload.get("skill_profile") == "architecture"
    assert payload["slides"][0].get("layout_grid") == "timeline"
    assert payload["slides"][0].get("render_path") == "svg"


def test_exporter_payload_derives_style_and_tone_from_theme_recipe_when_auto():
    payload = build_payload(
        slides=[
            {"slide_id": "s1", "title": "Classroom Intro", "slide_type": "content"},
        ],
        title="Deck",
        author="a",
        style_variant="auto",
        palette_key="auto",
        theme_recipe="classroom_soft",
        tone="auto",
        template_family="auto",
    )
    assert payload.get("theme_recipe") == "classroom_soft"
    assert payload.get("tone") == "light"
    assert payload.get("minimax_style_variant") == "rounded"
    design_spec = payload.get("design_spec") if isinstance(payload.get("design_spec"), dict) else {}
    visual = design_spec.get("visual") if isinstance(design_spec.get("visual"), dict) else {}
    assert visual.get("style_recipe") == "rounded"
    assert visual.get("theme_recipe") == "classroom_soft"
    assert visual.get("tone") == "light"


def test_exporter_rejects_incompatible_locked_cover_template_for_content_slide():
    payload = build_payload(
        slides=[
            {
                "slide_id": "s1",
                "title": "Classroom analysis",
                "slide_type": "content",
                "layout_grid": "split_2",
                "template_family": "hero_tech_cover",
                "template_lock": True,
                "blocks": [
                    {"block_type": "title", "content": "Classroom analysis"},
                    {"block_type": "body", "content": "explain legislative process impact"},
                ],
            }
        ],
        title="Deck",
        author="a",
    )
    slide = payload["slides"][0]
    assert slide.get("template_family") != "hero_tech_cover"
    assert slide.get("contract_profile") != "cover_meta_required"


def test_exporter_prefers_requested_deck_template_when_compatible():
    payload = build_payload(
        slides=[
            {
                "slide_id": "s1",
                "title": "Legislation process",
                "slide_type": "content",
                "layout_grid": "split_2",
                "blocks": [
                    {"block_type": "title", "content": "Legislation process"},
                    {"block_type": "body", "content": "stakeholders and policy flow"},
                ],
            }
        ],
        title="Deck",
        author="a",
        template_family="split_media_dark",
    )
    slide = payload["slides"][0]
    assert slide.get("template_family") == "split_media_dark"


def test_exporter_treats_toc_and_divider_as_cover_compatible_for_hero_template():
    assert _template_family_supports_slide(
        "hero_tech_cover",
        slide_type="toc",
        layout_grid="hero_1",
    )
    assert _template_family_supports_slide(
        "hero_tech_cover",
        slide_type="divider",
        layout_grid="hero_1",
    )
