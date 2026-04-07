import pytest
from pydantic import ValidationError

import src.ppt_service_v2 as ppt_service
from src.ppt_service_v2 import PPTService
from src.schemas.ppt_outline import OutlinePlan, OutlinePlanRequest, StickyNote
from src.schemas.ppt_pipeline import PPTPipelineRequest
from src.schemas.ppt_plan import ContentBlock, PresentationPlanRequest
from src.schemas.ppt_research import ResearchContext, ResearchQuestion, ResearchRequest


@pytest.mark.asyncio
async def test_research_outline_plan_flow_contract():
    svc = PPTService()

    research = await svc.generate_research_context(
        ResearchRequest(
            topic="AI marketing automation",
            audience="investors",
            purpose="fundraising pitch",
            style_preference="business",
            constraints=["10 slides", "15 minutes"],
            required_facts=["CAC", "LTV", "pipeline conversion"],
            geography="China",
            time_range="2023-2025",
        )
    )
    assert len(research.key_data_points) >= 5
    assert len(research.reference_materials) >= 3
    assert 0.0 <= research.completeness_score <= 1.0
    assert research.required_facts
    assert isinstance(research.gap_report, list)
    assert research.enrichment_strategy in {"none", "web", "web+fallback"}

    outline = await svc.generate_outline_plan(
        OutlinePlanRequest(research=research, total_pages=8)
    )
    assert outline.total_pages == len(outline.notes)
    assert outline.notes[0].layout_hint == "cover"
    assert outline.notes[-1].layout_hint == "summary"
    for idx in range(1, len(outline.notes)):
        assert outline.notes[idx].layout_hint != outline.notes[idx - 1].layout_hint
    middle_layouts = [str(item.layout_hint) for item in outline.notes[1:-1]]
    for start in range(0, max(0, len(middle_layouts) - 4)):
        window = middle_layouts[start:start + 5]
        assert any(layout in {"hero_1", "cover", "summary", "section", "divider"} for layout in window)

    plan = await svc.generate_presentation_plan(
        PresentationPlanRequest(outline=outline, research=research)
    )
    assert len(plan.slides) == outline.total_pages
    for slide in plan.slides:
        assert any(block.block_type == "title" for block in slide.blocks)
        assert any(block.block_type != "title" for block in slide.blocks)
        assert slide.content_strategy is not None
        title_block = next(block for block in slide.blocks if block.block_type == "title")
        assert title_block.content == slide.content_strategy.assertion
        assert slide.content_strategy.page_role in {"argument", "evidence", "transition", "summary"}
        assert slide.content_strategy.render_path == "svg"


def test_content_block_rejects_placeholder_content():
    with pytest.raises(ValidationError):
        ContentBlock(
            block_type="body",
            position="left",
            content="TODO: fill this later",
            emphasis=[],
        )


@pytest.mark.asyncio
async def test_research_uses_serper_when_key_is_configured(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    async def _fake_serper_search(*, query: str, api_key: str, num: int = 5, gl: str = "us", hl: str = "zh-cn"):
        assert api_key == "test-key"
        return [
            {
                "title": f"{query} market report",
                "url": "https://example.com/market-report",
                "snippet": "Market grew 30% year-over-year with strong automation demand.",
            },
            {
                "title": f"{query} benchmark",
                "url": "https://example.com/benchmark",
                "snippet": "Benchmark indicates conversion lift after workflow adoption.",
            },
            {
                "title": f"{query} industry data",
                "url": "https://example.com/industry-data",
                "snippet": "Industry baseline shows higher ROI in data-driven campaigns.",
            },
        ]

    monkeypatch.setattr(ppt_service, "_search_serper_web", _fake_serper_search)

    svc = PPTService()
    research = await svc.generate_research_context(
        ResearchRequest(topic="AI marketing automation")
    )

    assert len(research.reference_materials) >= 3
    assert any("example.com/market-report" in row["url"] for row in research.reference_materials)
    assert any("30%" in point or "ROI" in point for point in research.key_data_points)
    assert research.enrichment_applied is True
    assert any(item.provenance == "web" for item in research.evidence)


@pytest.mark.asyncio
async def test_outline_uses_generic_storyline_defaults():
    svc = PPTService()
    research = await svc.generate_research_context(
        ResearchRequest(
            topic="AI governance strategy for enterprise rollout",
            audience="strategy leaders",
            purpose="decision briefing",
            style_preference="professional",
            web_enrichment=False,
        )
    )
    outline = await svc.generate_outline_plan(
        OutlinePlanRequest(research=research, total_pages=10)
    )
    titles = [str(note.core_message) for note in outline.notes]
    assert titles[1] in {"内容导航", "Table of Contents"}
    assert titles[-1] in {"总结与启示", "Summary & Insights", "Summary & Takeaways"}
    assert outline.theme_suggestion == "business_authority"
    assert outline.style_suggestion == "soft"


@pytest.mark.asyncio
async def test_presentation_plan_preserves_storyline_titles():
    svc = PPTService()
    research = await svc.generate_research_context(
        ResearchRequest(
            topic="AI governance strategy for enterprise rollout",
            audience="strategy leaders",
            purpose="decision briefing",
            style_preference="professional",
            web_enrichment=False,
        )
    )
    outline = await svc.generate_outline_plan(
        OutlinePlanRequest(research=research, total_pages=10)
    )
    plan = await svc.generate_presentation_plan(
        PresentationPlanRequest(outline=outline, research=research)
    )
    slide_titles = []
    for slide in plan.slides:
        title_block = next(block for block in slide.blocks if block.block_type == "title")
        slide_titles.append(str(title_block.content))
    assert slide_titles[1] == str(outline.title)
    for slide_title, note in zip(slide_titles[2:9], outline.notes[2:9]):
        normalized_slide_title = str(slide_title or "").replace("…", "").strip()
        normalized_note_title = str(note.core_message or "").strip()
        assert normalized_slide_title
        assert normalized_note_title.startswith(normalized_slide_title)
    assert slide_titles[-1] == str(outline.title)
    assert plan.slides[1].slide_type == "toc"
    assert plan.slides[-1].slide_type == "summary"


def test_profile_field_ownership_overrides_slide_level_profile_drift():
    payload = {
        "quality_profile": "training_deck",
        "slides": [
            {"slide_id": "s1", "quality_profile": "high_density_consulting", "hardness_profile": "strict"},
            {"slide_id": "s2", "quality_profile": "high_density_consulting", "hardness_profile": "strict"},
        ],
    }
    out = ppt_service._enforce_profile_field_ownership(
        payload,
        quality_profile="training_deck",
        hardness_profile="balanced",
    )
    assert out.get("quality_profile") == "training_deck"
    assert out.get("hardness_profile") == "balanced"
    for slide in out.get("slides") or []:
        assert slide.get("quality_profile") == "training_deck"
        assert slide.get("hardness_profile") == "balanced"


@pytest.mark.asyncio
async def test_pipeline_strips_instructional_boilerplate_from_content_blocks(monkeypatch):
    monkeypatch.setenv("PPT_DEV_FAST_FAIL", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    from src.ppt_quality_gate import QualityResult, QualityScoreResult

    monkeypatch.setattr("src.ppt_quality_gate.validate_layout_diversity", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr("src.ppt_quality_gate.validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(
        "src.ppt_quality_gate.score_deck_quality",
        lambda *_args, **_kwargs: QualityScoreResult(
            score=90.0,
            passed=True,
            threshold=75.0,
            warn_threshold=82.0,
            dimensions={},
            issue_counts={},
            diagnostics={},
        ),
    )
    svc = PPTService()
    result = await svc.run_ppt_pipeline(
        PPTPipelineRequest(
            topic="AI governance strategy for enterprise rollout",
            audience="strategy leaders",
            purpose="decision briefing",
            style_preference="professional",
            total_pages=8,
            route_mode="fast",
            quality_profile="lenient_draft",
            web_enrichment=False,
            with_export=False,
            save_artifacts=False,
            execution_profile="prod_safe",
        )
    )
    content_slides = [
        slide for slide in (result.artifacts.render_payload.get("slides") or [])
        if isinstance(slide, dict) and str(slide.get("slide_type") or "") == "content"
    ]
    assert content_slides
    flattened = "\n".join(
        str((block or {}).get("content") or "")
        for slide in content_slides
        for block in (slide.get("blocks") or [])
        if isinstance(block, dict)
    )
    for prefix in (
        "Core takeaway:",
        "Core question:",
        "Class prompt:",
        "Case context:",
        "Debate focus:",
    ):
        assert prefix not in flattened


@pytest.mark.asyncio
async def test_pipeline_reclassifies_non_terminal_hero_layout_as_section(monkeypatch):
    monkeypatch.setenv("PPT_DEV_FAST_FAIL", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    from src.ppt_quality_gate import QualityResult, QualityScoreResult

    monkeypatch.setattr("src.ppt_quality_gate.validate_layout_diversity", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr("src.ppt_quality_gate.validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(
        "src.ppt_quality_gate.score_deck_quality",
        lambda *_args, **_kwargs: QualityScoreResult(
            score=90.0,
            passed=True,
            threshold=75.0,
            warn_threshold=82.0,
            dimensions={},
            issue_counts={},
            diagnostics={},
        ),
    )
    svc = PPTService()
    result = await svc.run_ppt_pipeline(
        PPTPipelineRequest(
            topic="AI governance strategy for enterprise rollout",
            audience="strategy leaders",
            purpose="decision briefing",
            style_preference="professional",
            total_pages=8,
            route_mode="fast",
            quality_profile="lenient_draft",
            web_enrichment=False,
            with_export=False,
            save_artifacts=False,
            execution_profile="prod_safe",
        )
    )
    for slide in result.artifacts.render_payload.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("slide_type") or "")
        layout_grid = str(slide.get("layout_grid") or "")
        if layout_grid == "hero_1":
            assert slide_type in {"cover", "summary", "toc", "divider", "hero_1", "section"}


@pytest.mark.asyncio
async def test_pipeline_stage13_fallback_path_keeps_stage_order(monkeypatch):
    monkeypatch.setenv("PPT_DEV_FAST_FAIL", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    monkeypatch.setenv("PPT_STAGE13_GRAPH_ENABLED", "false")
    from src.ppt_quality_gate import QualityResult, QualityScoreResult

    monkeypatch.setattr(
        "src.ppt_quality_gate.validate_layout_diversity",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )
    monkeypatch.setattr(
        "src.ppt_quality_gate.validate_deck",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )
    monkeypatch.setattr(
        "src.ppt_quality_gate.score_deck_quality",
        lambda *_args, **_kwargs: QualityScoreResult(
            score=90.0,
            passed=True,
            threshold=75.0,
            warn_threshold=82.0,
            dimensions={},
            issue_counts={},
            diagnostics={},
        ),
    )

    svc = PPTService()
    result = await svc.run_ppt_pipeline(
        PPTPipelineRequest(
            topic="AI governance strategy for enterprise rollout",
            audience="strategy leaders",
            purpose="decision briefing",
            style_preference="professional",
            total_pages=8,
            route_mode="fast",
            quality_profile="lenient_draft",
            web_enrichment=False,
            with_export=False,
            save_artifacts=False,
            execution_profile="prod_safe",
        )
    )
    stage_names = [str(stage.stage) for stage in (result.stages or [])]
    assert stage_names[:3] == ["research", "outline_plan", "presentation_plan"]


@pytest.mark.asyncio
async def test_research_gap_driven_queries_include_required_facts(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    captured_queries = []

    async def _fake_serper_search(*, query: str, api_key: str, num: int = 5, gl: str = "us", hl: str = "zh-cn"):
        captured_queries.append(query)
        return []

    monkeypatch.setattr(ppt_service, "_search_serper_web", _fake_serper_search)

    svc = PPTService()
    research = await svc.generate_research_context(
        ResearchRequest(
            topic="AI marketing automation",
            required_facts=["CAC payback period", "pipeline conversion rate"],
            geography="US",
            time_range="2022-2025",
            web_enrichment=True,
            max_web_queries=3,
        )
    )

    assert captured_queries, "gap-driven enrichment should trigger web queries"
    joined = " | ".join(captured_queries).lower()
    assert "cac payback period" in joined or "pipeline conversion rate" in joined
    assert research.reference_materials
    assert research.completeness_score >= 0.3


@pytest.mark.asyncio
async def test_generate_presentation_plan_emits_structured_comparison_slide_hints():
    svc = PPTService()
    research = ResearchContext(
        topic="Agent solution comparison",
        audience="product and engineering leads",
        purpose="proposal review",
        style_preference="professional",
        key_data_points=[
            "Automation uplift +80%",
            "Launch cycle reduced by 60%",
            "Manual handoff overhead reduced",
        ],
        reference_materials=[{"title": "benchmark", "url": "https://example.com/benchmark"}],
        completeness_score=0.7,
        enrichment_strategy="web+fallback",
        questions=[
            ResearchQuestion(
                question="Who is the audience?",
                category="audience",
                why="Tune narrative depth",
            ),
            ResearchQuestion(
                question="What decision is needed?",
                category="purpose",
                why="Prioritize recommendation framing",
            ),
            ResearchQuestion(
                question="Which metrics are required?",
                category="data",
                why="Ground claims with evidence",
            ),
        ],
    )
    outline = OutlinePlan(
        title="Agent solution comparison",
        total_pages=3,
        theme_suggestion="slate_minimal",
        style_suggestion="soft",
        logic_flow="cover-comparison-summary",
        notes=[
            StickyNote(
                page_number=1,
                core_message="Agent solution comparison",
                layout_hint="cover",
                key_points=["Context", "Goal", "Scope"],
            ),
            StickyNote(
                page_number=2,
                core_message="Traditional vs agentic",
                layout_hint="split_2",
                data_elements=["comparison"],
                visual_anchor="text",
                key_points=[
                    "Manual handoff overhead",
                    "Long response chain",
                    "Automation uplift +80%",
                    "Launch cycle reduced by 60%",
                ],
            ),
            StickyNote(
                page_number=3,
                core_message="Summary and action plan",
                layout_hint="summary",
                key_points=["Unified routing", "Improve content first", "Then optimize SVG lane"],
            ),
        ],
    )

    plan = await svc.generate_presentation_plan(
        PresentationPlanRequest(outline=outline, research=research)
    )

    middle = plan.slides[1]
    assert str(getattr(middle, "archetype", "") or "").strip().lower() == "comparison_2col"
    assert "comparison_cards_light" in list(getattr(middle, "template_candidates", []) or [])
    assert any(block.block_type == "comparison" for block in middle.blocks)


