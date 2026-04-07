from __future__ import annotations

from types import SimpleNamespace

from src import ppt_service


def test_relaxed_quality_issue_codes_keep_accuracy_hard_fails_strict():
    relaxed = ppt_service._relaxed_quality_issue_codes(
        route_mode="fast",
        quality_profile="lenient_draft",
        use_reference_reconstruct=True,
        requested_execution_profile="prod_safe",
        include_template_switch_relaxation=True,
    )
    assert "placeholder_kpi_data" not in relaxed
    assert "placeholder_chart_data" not in relaxed
    assert "placeholder_pollution" not in relaxed
    assert "layout_homogeneous" in relaxed


def test_relaxed_quality_issue_codes_disabled_in_dev_strict():
    relaxed = ppt_service._relaxed_quality_issue_codes(
        route_mode="fast",
        quality_profile="lenient_draft",
        use_reference_reconstruct=True,
        requested_execution_profile="dev_strict",
        include_template_switch_relaxation=True,
    )
    assert relaxed == set()


def test_relaxed_quality_issue_codes_export_mode_keeps_previous_scope():
    relaxed = ppt_service._relaxed_quality_issue_codes(
        route_mode="fast",
        quality_profile="lenient_draft",
        use_reference_reconstruct=False,
        requested_execution_profile="prod_safe",
        include_template_switch_relaxation=False,
    )
    assert "template_family_switch_frequent" not in relaxed
    assert "template_family_abab_repeat" not in relaxed
    assert "template_family_homogeneous" in relaxed


def test_requested_skills_for_slide_uses_deck_template_family_when_slide_missing():
    skills = ppt_service._requested_skills_for_slide(
        {"slide_type": "content", "layout_grid": "split_2", "render_path": "svg"},
        1,
        5,
        deck_template_family="dashboard_dark",
    )
    assert "ppt-editing-skill" in skills


def test_requested_skills_for_slide_forces_ppt_master_in_dev_strict():
    skills = ppt_service._requested_skills_for_slide(
        {"slide_type": "content", "layout_grid": "split_2", "render_path": "svg"},
        1,
        5,
        execution_profile="dev_strict",
    )
    assert "ppt-master" in skills


def test_apply_skill_planning_requests_template_editing_skill_from_deck_context(monkeypatch):
    calls = []

    def _fake_exec(payload: dict) -> dict:
        calls.append(payload)
        requested = payload.get("requested_skills") if isinstance(payload.get("requested_skills"), list) else []
        return {
            "version": 1,
            "results": [
                {"skill": str(skill), "status": "noop", "patch": {}, "note": "ok"}
                for skill in requested
            ],
            "patch": {},
            "context": {},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)

    render_payload = {
        "title": "Template Deck",
        "template_family": "dashboard_dark",
        "theme": {"style": "soft", "palette": "pure_tech_blue"},
        "slides": [
            {"slide_id": "s1", "slide_type": "content", "layout_grid": "split_2"},
        ],
    }

    out = ppt_service._apply_skill_planning_to_render_payload(render_payload)
    assert isinstance(out, dict)
    assert calls
    requested = calls[0].get("requested_skills") if isinstance(calls[0], dict) else []
    assert isinstance(requested, list)
    assert "ppt-editing-skill" in requested


def test_layer1_design_chain_requests_template_editing_skill_when_template_specified(monkeypatch):
    calls = []

    def _fake_exec(payload: dict) -> dict:
        calls.append(payload)
        requested = payload.get("requested_skills") if isinstance(payload.get("requested_skills"), list) else []
        return {
            "version": 1,
            "results": [
                {"skill": str(skill), "status": "noop", "patch": {}, "note": "ok"}
                for skill in requested
            ],
            "patch": {},
            "context": {},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)

    out = ppt_service._run_layer1_design_skill_chain(
        deck_title="Template Deck",
        slides=[{"slide_type": "cover", "title": "Title"}],
        requested_style_variant="auto",
        requested_palette_key="auto",
        requested_template_family="dashboard_dark",
        requested_skill_profile="auto",
    )

    runtime = out.get("runtime") if isinstance(out, dict) else {}
    assert isinstance(runtime, dict)
    assert "ppt-editing-skill" in (runtime.get("requested_skills") or [])
    assert calls
    requested = calls[0].get("requested_skills") if isinstance(calls[0], dict) else []
    assert "ppt-editing-skill" in requested


def test_layer1_design_chain_uses_first_slide_metadata_for_ppt_master_force(monkeypatch):
    calls = []

    def _fake_exec(payload: dict) -> dict:
        calls.append(payload)
        requested = payload.get("requested_skills") if isinstance(payload.get("requested_skills"), list) else []
        return {
            "version": 1,
            "results": [
                {"skill": str(skill), "status": "noop", "patch": {}, "note": "ok"}
                for skill in requested
            ],
            "patch": {},
            "context": {},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)

    out = ppt_service._run_layer1_design_skill_chain(
        deck_title="立法课程导论",
        slides=[
            {
                "slide_type": "cover",
                "title": "课程导入",
                "quality_profile": "training_deck",
            }
        ],
        requested_style_variant="auto",
        requested_palette_key="auto",
        requested_template_family="auto",
        requested_skill_profile="auto",
    )
    runtime = out.get("runtime") if isinstance(out, dict) else {}
    requested = runtime.get("requested_skills") if isinstance(runtime, dict) else []
    assert isinstance(requested, list)
    assert "ppt-master" in requested
    assert calls


def test_layer1_design_chain_raises_when_skill_runtime_reports_error(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "true")

    def _fake_exec(_payload: dict) -> dict:
        return {
            "version": 1,
            "results": [
                {"skill": "ppt-orchestra-skill", "status": "error", "note": "runtime_missing"},
            ],
            "patch": {},
            "context": {},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)

    try:
        ppt_service._run_layer1_design_skill_chain(
            deck_title="Strict Deck",
            slides=[{"slide_type": "cover", "title": "Title"}],
            requested_style_variant="auto",
            requested_palette_key="auto",
            requested_template_family="auto",
            requested_skill_profile="auto",
        )
    except RuntimeError as exc:
        assert "layer1_skill_runtime_unavailable" in str(exc) or "skill_runtime_failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when strict skill runtime reports error")


def test_layer1_design_chain_dev_strict_raises_when_runtime_optional(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")

    def _fake_exec(_payload: dict) -> dict:
        return {
            "version": 1,
            "results": [{"skill": "ppt-master", "status": "error", "note": "strict_miss"}],
            "patch": {},
            "context": {},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)

    try:
        ppt_service._run_layer1_design_skill_chain(
            deck_title="Strict Deck",
            slides=[{"slide_type": "cover", "title": "Title"}],
            requested_style_variant="auto",
            requested_palette_key="auto",
            requested_template_family="auto",
            requested_skill_profile="auto",
            execution_profile="dev_strict",
        )
    except RuntimeError as exc:
        assert "layer1_skill_runtime_unavailable" in str(exc) or "skill_runtime_failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError in dev_strict when skill runtime reports error")


def test_apply_skill_planning_dev_strict_raises_when_skill_error(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")

    def _fake_exec(_payload: dict) -> dict:
        return {
            "version": 1,
            "results": [{"skill": "ppt-master", "status": "error", "note": "strict_miss"}],
            "patch": {},
            "context": {},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)

    try:
        ppt_service._apply_skill_planning_to_render_payload(
            {
                "title": "Strict Deck",
                "slides": [{"slide_id": "s1", "slide_type": "content", "layout_grid": "split_2"}],
            },
            execution_profile="dev_strict",
            force_ppt_master=True,
        )
    except RuntimeError as exc:
        assert "skill_executor_exception" in str(exc) or "skill_runtime_failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError in dev_strict when skill planning reports error")


def test_apply_skill_planning_propagates_page_level_skill_context_and_history(monkeypatch):
    calls = []

    def _fake_exec(payload: dict) -> dict:
        calls.append(payload)
        idx = len(calls) - 1
        requested = payload.get("requested_skills") if isinstance(payload.get("requested_skills"), list) else []
        return {
            "version": 1,
            "results": [
                {
                    "skill": str(skill),
                    "status": "applied" if str(skill) == "ppt-orchestra-skill" else "noop",
                    "patch": {},
                    "note": "ok",
                }
                for skill in requested
            ],
            "patch": {
                "slide_type": "content",
                "layout_grid": "grid_3" if idx == 0 else "timeline",
                "render_path": "svg",
            },
            "context": {
                "agent_type": "content-page-generator",
                "recommended_load_skills": ["slide-making-skill", "ppt-orchestra-skill"],
                "page_skill_directives": ["Only one title area is allowed at the top of the slide."],
                "text_constraints": {"bullet_max_items": 4},
                "image_policy": {"prefer_real_stock_images": True},
                "page_design_intent": "Keep hierarchy stable and concise.",
            },
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)

    render_payload = {
        "title": "Skill Deck",
        "slides": [
            {"slide_id": "s1", "slide_type": "content", "title": "One"},
            {"slide_id": "s2", "slide_type": "content", "title": "Two"},
        ],
    }
    out = ppt_service._apply_skill_planning_to_render_payload(render_payload)
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    assert len(slides) == 2
    assert slides[0].get("layout_grid") == "grid_3"
    assert slides[1].get("layout_grid") == "timeline"
    assert isinstance(slides[0].get("skill_directives"), list)
    assert isinstance(slides[0].get("text_constraints"), dict)
    assert isinstance(slides[0].get("image_policy"), dict)
    assert slides[0].get("page_design_intent")
    assert len(calls) == 2
    second_deck = calls[1].get("deck") if isinstance(calls[1], dict) else {}
    used = second_deck.get("used_content_layouts") if isinstance(second_deck, dict) else []
    assert isinstance(used, list)
    assert "grid_3" in used


def test_apply_skill_planning_forwards_execution_profile_and_force(monkeypatch):
    calls = []

    def _fake_exec(payload: dict) -> dict:
        calls.append(payload)
        requested = payload.get("requested_skills") if isinstance(payload.get("requested_skills"), list) else []
        return {
            "version": 1,
            "results": [{"skill": str(skill), "status": "noop", "patch": {}, "note": "ok"} for skill in requested],
            "patch": {},
            "context": {},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)
    ppt_service._apply_skill_planning_to_render_payload(
        {
            "title": "Strict Deck",
            "slides": [{"slide_id": "s1", "slide_type": "content", "layout_grid": "split_2"}],
        },
        execution_profile="dev_strict",
        force_ppt_master=True,
    )
    assert calls
    payload = calls[0]
    assert payload.get("execution_profile") == "dev_strict"
    assert payload.get("force_ppt_master") is True
    requested = payload.get("requested_skills") if isinstance(payload.get("requested_skills"), list) else []
    assert "ppt-master" in requested


def test_apply_skill_planning_exposes_skill_write_policy_diagnostics(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")

    def _fake_exec(_payload: dict) -> dict:
        return {
            "version": 1,
            "results": [
                {
                    "skill": "design-style-skill",
                    "status": "applied",
                    "patch": {"style_variant": "soft"},
                    "note": "ok",
                }
            ],
            "patch": {"style_variant": "soft"},
            "context": {},
            "skill_write_violations": [
                {"skill": "design-style-skill", "field": "palette_key", "reason": "unauthorized_write"}
            ],
            "skill_write_conflicts": [
                {"field": "layout_grid", "first_skill": "slide-making-skill", "second_skill": "ppt-orchestra-skill"}
            ],
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)
    out = ppt_service._apply_skill_planning_to_render_payload(
        {"title": "Diag Deck", "slides": [{"slide_id": "s1", "slide_type": "content"}]}
    )
    runtime = out.get("skill_planning_runtime") if isinstance(out.get("skill_planning_runtime"), dict) else {}
    rows = runtime.get("slides") if isinstance(runtime.get("slides"), list) else []
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.get("skill_write_violations"), list)
    assert isinstance(row.get("skill_write_conflicts"), list)
    assert row["skill_write_violations"][0]["field"] == "palette_key"
    assert row["skill_write_conflicts"][0]["field"] == "layout_grid"


def test_apply_skill_planning_attaches_design_decision_v1(monkeypatch):
    def _fake_exec(_payload: dict) -> dict:
        return {
            "version": 1,
            "results": [
                {"skill": "design-style-skill", "status": "applied", "patch": {"style_variant": "sharp"}, "note": "ok"},
                {"skill": "color-font-skill", "status": "applied", "patch": {"palette_key": "business_authority"}, "note": "ok"},
                {"skill": "slide-making-skill", "status": "applied", "patch": {"layout_grid": "grid_3"}, "note": "ok"},
                {"skill": "ppt-orchestra-skill", "status": "applied", "patch": {"layout_grid": "grid_3"}, "note": "ok"},
                {"skill": "ppt-master", "status": "noop", "patch": {}, "note": "ok"},
            ],
            "patch": {
                "style_variant": "sharp",
                "palette_key": "business_authority",
                "template_family": "dashboard_dark",
                "layout_grid": "grid_3",
            },
            "context": {"skill_profile": "general-content"},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)
    out = ppt_service._apply_skill_planning_to_render_payload(
        {
            "title": "Decision Deck",
            "slides": [{"slide_id": "s1", "slide_type": "content", "title": "Overview"}],
        }
    )
    decision = out.get("design_decision_v1")
    assert isinstance(decision, dict)
    assert decision.get("version") == "v1"
    assert isinstance(decision.get("deck"), dict)
    assert decision["deck"].get("style_variant") == "sharp"
    assert decision["deck"].get("palette_key") == "business_authority"
    rows = decision.get("slides")
    assert isinstance(rows, list) and rows
    assert rows[0].get("slide_id") == "s1"
    assert rows[0].get("layout_grid") == "grid_3"


def test_apply_skill_planning_attaches_theme_recipe_and_tone(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")

    def _fake_exec(payload: dict) -> dict:
        requested = payload.get("requested_skills") if isinstance(payload.get("requested_skills"), list) else []
        return {
            "version": 1,
            "results": [
                {
                    "skill": str(skill),
                    "status": "applied" if skill == "design-style-skill" else "noop",
                    "patch": (
                        {
                            "style_variant": "rounded",
                            "theme_recipe": "classroom_soft",
                            "tone": "light",
                        }
                        if skill == "design-style-skill"
                        else {}
                    ),
                    "note": "ok",
                }
                for skill in requested
            ],
            "patch": {
                "style_variant": "rounded",
                "theme_recipe": "classroom_soft",
                "tone": "light",
                "template_family": "consulting_warm_light",
            },
            "context": {"skill_profile": "general-content"},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)
    out = ppt_service._apply_skill_planning_to_render_payload(
        {
            "title": "Classroom Deck",
            "slides": [{"slide_id": "s1", "slide_type": "content", "title": "Overview"}],
        }
    )
    assert out.get("theme_recipe") == "classroom_soft"
    assert out.get("tone") == "light"
    theme = out.get("theme") if isinstance(out.get("theme"), dict) else {}
    assert theme.get("theme_recipe") == "classroom_soft"
    assert theme.get("tone") == "light"
    decision = out.get("design_decision_v1")
    assert isinstance(decision, dict)
    assert decision["deck"].get("theme_recipe") == "classroom_soft"
    assert decision["deck"].get("tone") == "light"


def test_layer1_design_chain_derives_style_from_theme_recipe_not_template_family(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")

    def _fake_exec(payload: dict) -> dict:
        requested = payload.get("requested_skills") if isinstance(payload.get("requested_skills"), list) else []
        return {
            "version": 1,
            "results": [
                {"skill": str(skill), "status": "noop", "patch": {}, "note": "ok"}
                for skill in requested
            ],
            "patch": {},
            "context": {},
        }

    monkeypatch.setattr("src.installed_skill_executor.execute_installed_skill_request", _fake_exec)
    out = ppt_service._run_layer1_design_skill_chain(
        deck_title="Classroom Deck",
        slides=[{"slide_type": "content", "title": "Overview"}],
        requested_style_variant="auto",
        requested_palette_key="auto",
        requested_template_family="architecture_dark_panel",
        requested_skill_profile="auto",
        requested_theme_recipe="classroom_soft",
        requested_tone="auto",
    )
    assert out.get("theme_recipe") == "classroom_soft"
    assert out.get("tone") == "light"
    assert out.get("style_variant") == "rounded"


def test_visual_orchestration_repairs_incompatible_cover_template_on_content_slide():
    payload = {
        "title": "Legislation class",
        "quality_profile": "default",
        "template_family": "auto",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "template_family": "hero_tech_cover",
                "template_lock": True,
                "title": "封面",
                "blocks": [{"block_type": "title", "content": "封面"}],
            },
            {
                "slide_id": "s2",
                "slide_type": "content",
                "layout_grid": "split_2",
                "template_family": "hero_tech_cover",
                "template_lock": True,
                "title": "立法流程",
                "blocks": [
                    {"block_type": "title", "content": "立法流程"},
                    {"block_type": "body", "content": "解释流程影响"},
                ],
            },
        ],
    }
    out = ppt_service._apply_visual_orchestration(payload)
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    assert len(slides) >= 2
    content = slides[1]
    assert str(content.get("template_family") or "").lower() != "hero_tech_cover"
    assert str(content.get("contract_profile") or "").lower() != "cover_meta_required"


def test_visual_orchestration_prefers_explicit_deck_template_when_compatible():
    payload = {
        "title": "Policy deck",
        "quality_profile": "default",
        "template_family": "split_media_dark",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "议题",
                "blocks": [
                    {"block_type": "title", "content": "议题"},
                    {"block_type": "body", "content": "背景与影?"},
                ],
            }
        ],
    }
    out = ppt_service._apply_visual_orchestration(payload)
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    assert slides
    assert str(slides[0].get("template_family") or "").lower() == "split_media_dark"


def test_visual_orchestration_repairs_incompatible_family_after_second_cohesion(monkeypatch):
    calls = {"count": 0}

    def _fake_cohesion(family_sequence, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return list(family_sequence)
        return ["hero_tech_cover" for _ in family_sequence]

    monkeypatch.setattr(ppt_service, "enforce_template_family_cohesion", _fake_cohesion)

    payload = {
        "title": "Policy deck",
        "quality_profile": "default",
        "template_family": "auto",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "template_family": "hero_tech_cover",
                "template_lock": True,
                "title": "封面",
                "blocks": [{"block_type": "title", "content": "封面"}],
            },
            {
                "slide_id": "s2",
                "slide_type": "content",
                "layout_grid": "split_2",
                "template_family": "dashboard_dark",
                "title": "立法流程",
                "blocks": [
                    {"block_type": "title", "content": "立法流程"},
                    {"block_type": "body", "content": "理解流程与影?"},
                ],
            },
        ],
    }

    out = ppt_service._apply_visual_orchestration(payload)
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    assert len(slides) >= 2
    content = slides[1]
    content_family = str(content.get("template_family") or "").lower()
    assert content_family != "hero_tech_cover"
    assert ppt_service._template_family_supports_slide(
        content_family,
        slide_type=str(content.get("slide_type") or "content"),
        layout_grid=str(content.get("layout_grid") or "split_2"),
    )
    assert calls["count"] >= 2


def test_visual_orchestration_adds_visual_anchor_for_text_only_split_content():
    payload = {
        "title": "Legislation deck",
        "quality_profile": "default",
        "template_family": "auto",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "title": "Cover",
                "blocks": [{"block_type": "title", "content": "Cover"}],
            },
            {
                "slide_id": "s2",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "Legislative process",
                "blocks": [
                    {"block_type": "title", "content": "Legislative process"},
                    {"block_type": "body", "content": "Background and process"},
                    {"block_type": "list", "content": "Step 1; Step 2; Step 3"},
                ],
            },
            {
                "slide_id": "s3",
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "title": "Summary",
                "blocks": [{"block_type": "title", "content": "Summary"}],
            },
        ],
    }
    out = ppt_service._apply_visual_orchestration(payload)
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    content = next((row for row in slides if str((row or {}).get("slide_id") or "") == "s2"), {})
    blocks = content.get("blocks") if isinstance(content.get("blocks"), list) else []
    visual_types = {"image", "chart", "kpi", "table", "workflow", "diagram"}
    assert any(str((block or {}).get("block_type") or "").lower() in visual_types for block in blocks)


def test_ensure_content_contract_clips_overlong_visible_text():
    long_title = "高中课堂展示课件主题" * 20
    slide = {
        "slide_type": "cover",
        "layout_grid": "hero_1",
        "title": long_title,
        "blocks": [
            {"block_type": "title", "content": long_title},
            {"block_type": "subtitle", "content": long_title},
        ],
    }
    out = ppt_service._ensure_content_contract(slide)
    assert len(str(out.get("title") or "")) < len(long_title)
    blocks = out.get("blocks") if isinstance(out.get("blocks"), list) else []
    title_blocks = [b for b in blocks if str((b or {}).get("block_type") or "").lower() == "title"]
    assert title_blocks
    assert len(str(title_blocks[0].get("content") or "")) < len(long_title)


def test_template_support_treats_toc_and_divider_as_cover_compatible():
    assert ppt_service._template_family_supports_slide(
        "hero_tech_cover",
        slide_type="toc",
        layout_grid="hero_1",
    )
    assert ppt_service._template_family_supports_slide(
        "hero_tech_cover",
        slide_type="divider",
        layout_grid="hero_1",
    )


def test_topic_relevance_score_penalizes_irrelevant_search_hits():
    score = ppt_service._topic_relevance_score(
        topic="解码立法过程：理解其对国际关系的影响",
        title="北京大学本科专业核心课程手册—文科卷",
        snippet="课程名称：临床药物治疗学，教学对象：大三药学专业学生?",
        domain_terms=["立法", "国际关系"],
        required_facts=["立法流程", "政策影响"],
    )
    assert score < 0.18


def test_mojibake_detector_flags_corrupted_utf8_text():
    assert ppt_service._looks_mojibake("\ufffd")
    assert not ppt_service._looks_mojibake("解码立法过程：理解其对国际关系的影响")



def test_research_noise_filter_blocks_prompt_and_repo_pollution_for_non_software_topic():
    assert ppt_service._is_research_noise_hit(
        topic="解码立法过程：理解其对国际关系的影响",
        title="GitHub - icip-cas/PPTAgent",
        snippet="Prompt: 请制作一份高中课堂展示课件，主题为解码立法过程?",
    )
    assert not ppt_service._is_research_noise_hit(
        topic="如何用Python构建多智能体系统",
        title="GitHub - multi-agent framework",
        snippet="Prompt engineering and agent orchestration patterns.",
    )


def test_normalize_research_topic_extracts_subject_from_instruction_prompt():
    topic = "请制作一份高中课堂展示课件，主题为解码立法过程：理解其对国际关系的影响?"
    normalized = ppt_service._normalize_research_topic(topic, is_zh=True)
    assert normalized.startswith("解码立法过程")
    assert "请制" not in normalized


def test_build_research_queries_does_not_duplicate_topic_when_gap_hint_contains_topic():
    req = SimpleNamespace(
        topic="请制作一份高中课堂展示课件，主题为解码立法过程：理解其对国际关系的影响?",
        required_facts=[],
        time_range="",
        geography="",
        domain_terms=[],
        max_web_queries=4,
    )
    gaps = [
        ppt_service.ResearchGap(
            code="required_facts",
            severity="high",
            message="missing required facts",
            query_hint="解码立法过程：理解其对国际关系的影响 核心指标 数据",
        )
    ]
    queries = ppt_service._build_research_queries(req, is_zh=True, gaps=gaps)
    assert queries
    assert queries[0].count("解码立法过程") == 1
    assert "请制" not in queries[0]


def test_build_fallback_topic_points_is_semantic_not_instruction_echo():
    points = ppt_service._build_fallback_topic_points(
        "解码立法过程：理解其对国际关系的影响",
        is_zh=True,
    )
    assert len(points) >= 3
    assert all("请制" not in item for item in points)


def test_build_fallback_topic_points_avoids_duplicated_impact_phrase():
    points = ppt_service._build_fallback_topic_points(
        "解码立法过程：理解其对国际关系的影响",
        is_zh=True,
    )
    assert len(points) >= 3
    assert points[2].count("对国际关系的影响") <= 1


def test_pick_input_derived_point_prefers_unused_source_phrase():
    value = ppt_service._pick_input_derived_point(
        point_pool=["Legislative process", "Stakeholder coordination", "Policy timeline"],
        title_text="Legislative process",
        prefer_zh=False,
        index=0,
        title_key=ppt_service._normalize_text_key("Legislative process"),
        existing_keys={ppt_service._normalize_text_key("Legislative process")},
        slide_type="content",
    )
    assert value == "Stakeholder coordination"


def test_pick_input_derived_point_uses_semantic_variant_when_exhausted():
    value = ppt_service._pick_input_derived_point(
        point_pool=["Legislative process"],
        title_text="Legislative process",
        prefer_zh=False,
        index=1,
        title_key=ppt_service._normalize_text_key("Legislative process"),
        existing_keys={
            ppt_service._normalize_text_key("Legislative process"),
            ppt_service._normalize_text_key("Legislative process #2"),
        },
        slide_type="content",
    )
    assert value
    assert "legislative process" in value.lower()
    assert "#" not in value
    assert "international relations" not in value.lower()


def test_sanitize_placeholder_text_keeps_valid_unicode_without_transcoding():
    source = "推进路径明确：解码立法过程：理解其对国际关系的影响"
    cleaned = ppt_service._sanitize_placeholder_text(source, prefer_zh=True)
    assert cleaned == source
    assert "?" not in cleaned


def test_sanitize_placeholder_text_rejects_writing_instruction_phrases():
    source = "先说?GDPR 的背景与定义"
    cleaned = ppt_service._sanitize_placeholder_text(source, prefer_zh=True)
    assert cleaned == ""


def test_infer_visual_semantic_mode_prefers_process_over_weak_numeric_signal():
    mode = ppt_service._infer_visual_semantic_mode(
        semantic_text="立法流程与阶段推进（2024-2026?",
        keypoints=["立法流程", "阶段推进", "阶段一", "阶段二"],
        numeric_values=[2024.0, 2025.0, 2026.0],
    )
    assert mode == "process"


def test_visual_orchestration_repairs_kpi_block_for_process_template():
    payload = {
        "title": "立法流程课件",
        "quality_profile": "default",
        "template_family": "auto",
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "title": "封面",
                "blocks": [{"block_type": "title", "content": "封面"}],
            },
            {
                "slide_id": "s2",
                "slide_type": "content",
                "layout_grid": "timeline",
                "template_family": "process_flow_dark",
                "template_lock": True,
                "title": "立法流程",
                "blocks": [
                    {"block_type": "title", "content": "立法流程"},
                    {"block_type": "body", "content": "阶段推进和参与方"},
                    {"block_type": "kpi", "content": "覆盖?86%"},
                ],
            },
            {
                "slide_id": "s3",
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "title": "总结",
                "blocks": [{"block_type": "title", "content": "总结"}],
            },
        ],
    }
    out = ppt_service._apply_visual_orchestration(payload)
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    content = next((row for row in slides if str((row or {}).get("slide_id") or "") == "s2"), {})
    blocks = content.get("blocks") if isinstance(content.get("blocks"), list) else []
    assert blocks
    assert all(str((block or {}).get("block_type") or "").lower() != "kpi" for block in blocks)


def test_visual_orchestration_harmonizes_content_family_when_switching_excessive():
    payload = {
        "title": "Family cohesion deck",
        "quality_profile": "default",
        "template_family": "auto",
        "slides": [
            {"slide_id": "c1", "slide_type": "cover", "layout_grid": "hero_1", "title": "Cover", "blocks": [{"block_type": "title", "content": "Cover"}]},
            {"slide_id": "s1", "slide_type": "content", "layout_grid": "split_2", "template_family": "split_media_dark", "title": "A", "blocks": [{"block_type": "title", "content": "A"}, {"block_type": "body", "content": "a"}]},
            {"slide_id": "s2", "slide_type": "content", "layout_grid": "grid_3", "template_family": "dashboard_dark", "title": "B", "blocks": [{"block_type": "title", "content": "B"}, {"block_type": "body", "content": "b"}]},
            {"slide_id": "s3", "slide_type": "content", "layout_grid": "timeline", "template_family": "process_flow_dark", "title": "C", "blocks": [{"block_type": "title", "content": "C"}, {"block_type": "body", "content": "c"}]},
            {"slide_id": "s4", "slide_type": "content", "layout_grid": "grid_4", "template_family": "bento_2x2_dark", "title": "D", "blocks": [{"block_type": "title", "content": "D"}, {"block_type": "body", "content": "d"}]},
            {"slide_id": "z1", "slide_type": "summary", "layout_grid": "hero_1", "title": "Summary", "blocks": [{"block_type": "title", "content": "Summary"}]},
        ],
    }
    out = ppt_service._apply_visual_orchestration(payload)
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    content_families = [
        str((row or {}).get("template_family") or "").strip().lower()
        for row in slides
        if isinstance(row, dict) and str(row.get("slide_type") or "").strip().lower() == "content"
    ]
    unique = {name for name in content_families if name}
    # Timeline/grid compatibility can require a dedicated family, but
    # orchestration should still reduce pathological switching.
    assert len(unique) <= 3
    switches = sum(1 for idx in range(1, len(content_families)) if content_families[idx] != content_families[idx - 1])
    switch_ratio = switches / max(1, len(content_families) - 1)
    assert switch_ratio <= 0.75


def test_resolve_execution_profile_for_runtime_defaults_to_dev_strict(monkeypatch):
    monkeypatch.delenv("PPT_DEFAULT_EXECUTION_PROFILE", raising=False)
    assert ppt_service._resolve_execution_profile_for_runtime("auto") == "dev_strict"
    monkeypatch.setenv("PPT_DEFAULT_EXECUTION_PROFILE", "prod_safe")
    assert ppt_service._resolve_execution_profile_for_runtime("auto") == "prod_safe"


def test_visual_contract_block_uses_table_for_education_without_numeric_values():
    block = ppt_service._make_visual_contract_block(
        preferred_types=["chart", "image", "table"],
        keypoints=["国际关系的交汇点", "制度接口的主要类型", "课堂案例与证据"],
        numeric_values=[],
        prefer_zh=True,
        semantic_text="高中课堂 教学 课程 国际关系 制度 案例",
        card_id="visual_anchor",
        position="right",
    )
    assert block.get("block_type") == "table"
    rows = (block.get("data") or {}).get("table_rows")
    assert isinstance(rows, list) and len(rows) >= 2


def test_layout_solver_underflow_adds_table_not_image_when_no_visual_anchor():
    slides = [
        {
            "slide_id": "s1",
            "slide_type": "content",
            "layout_grid": "split_2",
            "title": "课堂重点",
            "blocks": [
                {"block_type": "title", "content": "课堂重点"},
                {"block_type": "body", "content": "关键概念与案?"},
            ],
        }
    ]
    contract_rows = [
        {
            "slide_id": "s1",
            "layout_solution": {
                "status": "underflow",
                "underflow_actions": ["add_visual_anchor"],
                "overflow_actions": [],
            },
        }
    ]
    summary = ppt_service._apply_layout_solution_actions(slides, contract_rows)
    assert summary.get("updated_slides") == 1
    block_types = [str((block or {}).get("block_type") or "") for block in slides[0].get("blocks") or []]
    assert "table" in block_types
    assert "image" not in block_types


def test_collect_image_asset_issues_detects_placeholder_and_missing():
    payload = {
        "slides": [
            {
                "slide_id": "s1",
                "blocks": [
                    {"block_type": "image", "content": {"url": ppt_service._brand_placeholder_svg_data_uri("Brand")}},
                    {"block_type": "image", "content": {"title": "no url"}},
                ],
            }
        ]
    }
    issues = ppt_service._collect_image_asset_issues(payload)
    assert any("placeholder_url" in item for item in issues)
    assert any("missing_url" in item for item in issues)


def test_ensure_content_contract_strict_raises_instead_of_autofill():
    slide = {
        "slide_id": "s2",
        "slide_type": "content",
        "layout_grid": "split_2",
        "title": "Legislative process",
        "blocks": [{"block_type": "title", "content": "Legislative process"}],
    }
    try:
        ppt_service._ensure_content_contract(
            slide,
            min_content_blocks=2,
            blank_area_max_ratio=0.45,
            require_image_anchor=True,
            strict_contract=True,
        )
        assert False, "expected strict contract to fail"
    except ValueError as exc:
        assert "strict_content_contract_unmet" in str(exc)

