from src.schemas.ppt import ExportRequest, SlideContent, SlideElement
from src.minimax_exporter import build_payload
from src.ppt_service import _ensure_content_contract, _presentation_plan_to_render_payload
from src.schemas.ppt_plan import ContentBlock, PresentationPlan, SlidePlan


def test_export_request_has_retry_scope_fields():
    req = ExportRequest(slides=[], title="t", author="a")
    assert hasattr(req, "retry_scope")
    assert hasattr(req, "retry_hint")
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


def test_minimax_payload_contains_theme_contract():
    payload = build_payload(
        slides=[{"title": "Intro"}],
        title="Deck",
        author="bot",
        style_variant="soft",
        palette_key="slate_minimal",
    )
    assert payload["theme"]["style"] == "soft"
    assert payload["theme"]["palette"] == "slate_minimal"
    assert payload["minimax_style_variant"] == "soft"
    assert payload["minimax_palette_key"] == "slate_minimal"
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
    assert middle["page_type"] == "data"
    assert middle["subtype"] == "data"
    assert [block["card_id"] for block in middle["blocks"]] == ["title", "right", "left"]


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
    non_title = [b for b in blocks if b.get("block_type") != "title"]
    assert len(non_title) <= 2
    assert all(
        "brand visual placeholder" not in str(b.get("content"))
        for b in blocks
    )
