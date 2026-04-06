from src.ppt_quality_gate import QualityIssue
from src.ppt_visual_critic import apply_visual_critic_patch, build_visual_critic_patch


def test_build_visual_critic_patch_collects_targets_and_actions():
    slides = [
        {"slide_id": "s1", "title": "Overview", "elements": [{"type": "text", "content": "hello"}]},
        {"slide_id": "s2", "title": "Growth", "elements": [{"type": "text", "content": "world"}]},
    ]
    visual_audit = {
        "slides": [
            {"slide": 1, "local_issues": ["excessive_whitespace"], "multimodal_issues": []},
            {"slide": 2, "local_issues": ["low_contrast"], "multimodal_issues": ["card_overlap"]},
        ]
    }
    gate_issues = [
        QualityIssue(
            slide_id="s1",
            code="visual_whitespace_ratio_high",
            message="too much blank area",
            retry_scope="slide",
            retry_target_ids=["s1"],
        ),
        QualityIssue(
            slide_id="s2",
            code="visual_low_contrast_ratio_high",
            message="contrast low",
            retry_scope="slide",
            retry_target_ids=["s2"],
        ),
    ]

    patch = build_visual_critic_patch(
        visual_audit=visual_audit,
        gate_issues=gate_issues,
        slides=slides,
        max_target_slides=4,
    )

    assert patch["enabled"] is True
    assert patch["summary"]["target_count"] == 2
    row1 = next(row for row in patch["targets"] if row["slide_id"] == "s1")
    row2 = next(row for row in patch["targets"] if row["slide_id"] == "s2")
    assert row1["actions"]["layout_grid"] == "split_2"
    assert row2["actions"]["visual_patch"]["force_high_contrast"] is True
    assert row2["actions"]["render_path"] == "pptxgenjs"


def test_apply_visual_critic_patch_mutates_slide_payload():
    slides = [
        {
            "slide_id": "s1",
            "title": "Overview",
            "layout_grid": "grid_4",
            "render_path": "pptxgenjs",
            "elements": [
                {"type": "text", "content": "x" * 260},
                {"type": "text", "content": "second"},
                {"type": "text", "content": "third"},
                {"type": "text", "content": "fourth"},
                {"type": "text", "content": "fifth"},
            ],
        }
    ]
    patch = {
        "enabled": True,
        "targets": [
            {
                "slide_id": "s1",
                "issue_codes": ["visual_whitespace_ratio_high", "visual_low_contrast_ratio_high"],
                "actions": {
                    "layout_grid": "split_2",
                    "render_path": "svg",
                    "visual_patch": {"force_high_contrast": True},
                    "semantic_constraints_patch": {"media_required": True},
                    "compact_text": True,
                    "limit_elements": 4,
                    "ensure_image_block": True,
                    "ensure_chart_block": False,
                },
            }
        ],
    }

    out = apply_visual_critic_patch(slides=slides, patch=patch)

    assert out["applied"] is True
    assert out["updated_slide_ids"] == ["s1"]
    assert slides[0]["layout_grid"] == "split_2"
    assert slides[0]["render_path"] == "svg"
    assert slides[0]["visual"]["force_high_contrast"] is True
    assert slides[0]["semantic_constraints"]["media_required"] is True
    assert len(slides[0]["elements"]) >= 4
    assert any(str(item.get("type")) == "image" for item in slides[0]["elements"])
    assert len(str(slides[0]["elements"][0].get("content") or "")) <= 180


def test_build_visual_critic_patch_routes_structural_exception_slide_to_svg():
    slides = [
        {
            "slide_id": "s-arch",
            "slide_type": "architecture",
            "layout_grid": "architecture",
            "structural_expression_failure": True,
            "elements": [{"type": "diagram", "content": "mesh"}],
        }
    ]
    visual_audit = {
        "slides": [
            {"slide": 1, "local_issues": [], "multimodal_issues": ["card_overlap"]},
        ]
    }
    gate_issues = [
        QualityIssue(
            slide_id="s-arch",
            code="visual_card_overlap_ratio_high",
            message="cards overlap",
            retry_scope="slide",
            retry_target_ids=["s-arch"],
        )
    ]

    patch = build_visual_critic_patch(
        visual_audit=visual_audit,
        gate_issues=gate_issues,
        slides=slides,
        max_target_slides=4,
    )

    row = next(row for row in patch["targets"] if row["slide_id"] == "s-arch")
    assert row["actions"]["render_path"] == "svg"


def test_build_visual_critic_patch_does_not_route_svg_from_storyline_intent_only():
    slides = [
        {
            "slide_id": "s-story",
            "slide_type": "content",
            "layout_grid": "split_2",
            "split_merge_exhausted": True,
            "intent": "workflow storyline architecture",
            "layout_intent": "storyline",
            "elements": [{"type": "text", "content": "Narrative-driven page"}],
        }
    ]
    visual_audit = {
        "slides": [
            {"slide": 1, "local_issues": [], "multimodal_issues": ["card_overlap"]},
        ]
    }
    gate_issues = [
        QualityIssue(
            slide_id="s-story",
            code="visual_card_overlap_ratio_high",
            message="cards overlap",
            retry_scope="slide",
            retry_target_ids=["s-story"],
        )
    ]

    patch = build_visual_critic_patch(
        visual_audit=visual_audit,
        gate_issues=gate_issues,
        slides=slides,
        max_target_slides=4,
    )

    row = next(row for row in patch["targets"] if row["slide_id"] == "s-story")
    assert row["actions"]["render_path"] != "svg"
