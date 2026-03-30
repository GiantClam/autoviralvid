from __future__ import annotations

from src import ppt_service


def test_requested_skills_for_slide_uses_deck_template_family_when_slide_missing():
    skills = ppt_service._requested_skills_for_slide(
        {"slide_type": "content", "layout_grid": "split_2", "render_path": "pptxgenjs"},
        1,
        5,
        deck_template_family="dashboard_dark",
    )
    assert "ppt-editing-skill" in skills


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
                "render_path": "pptxgenjs",
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
