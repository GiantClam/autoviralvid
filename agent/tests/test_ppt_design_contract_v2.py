from __future__ import annotations

from src import ppt_service


def _base_payload() -> dict:
    return {
        "title": "Contract V2 Deck",
        "template_family": "auto",
        "theme": {"palette": "pure_tech_blue", "style": "soft"},
        "slides": [
            {
                "slide_id": "s-cover",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "blocks": [{"block_type": "title", "card_id": "title", "content": "封面"}],
            },
            {
                "slide_id": "s-content",
                "slide_type": "content",
                "layout_grid": "grid_4",
                "blocks": [
                    {"block_type": "title", "card_id": "title", "content": "业务进展"},
                    {"block_type": "kpi", "card_id": "k1", "content": {"label": "增长", "value": "42%"}},
                    {"block_type": "chart", "card_id": "c1", "content": {"title": "趋势"}},
                ],
            },
            {
                "slide_id": "s-summary",
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "blocks": [{"block_type": "body", "card_id": "b1", "content": "结论与行动"}],
            },
        ],
    }


def test_apply_visual_orchestration_emits_presentation_contract_v2():
    out = ppt_service._apply_visual_orchestration(_base_payload())

    contract = out.get("presentation_contract_v2")
    assert isinstance(contract, dict)
    assert contract.get("version") == "v2"
    assert isinstance(contract.get("deck_spec"), dict)

    slides = out.get("slides")
    assert isinstance(slides, list)
    assert len(slides) == 3
    assert isinstance(contract.get("slides"), list)
    assert len(contract["slides"]) == len(slides)

    for idx, slide in enumerate(slides):
        assert isinstance(slide.get("slide_id"), str) and slide["slide_id"]
        assert slide.get("page_role") in {"cover", "toc", "divider", "content", "summary"}
        assert slide.get("archetype") in ppt_service._ARCHETYPE_ALLOWED

        row = contract["slides"][idx]
        assert row.get("slide_id") == slide.get("slide_id")
        assert row.get("page_role") == slide.get("page_role")
        assert row.get("archetype") == slide.get("archetype")
        assert isinstance(row.get("archetype_plan"), dict)
        assert str((row.get("archetype_plan") or {}).get("selected") or "").strip().lower() == str(
            row.get("archetype") or ""
        ).strip().lower()
        assert isinstance(row.get("archetype_candidates"), list)
        assert len(row.get("archetype_candidates") or []) >= 1
        assert 0.0 <= float(row.get("archetype_confidence") or 0.0) <= 1.0
        assert isinstance(row.get("content_channel"), dict)
        assert isinstance(row.get("visual_channel"), dict)
        assert row["visual_channel"].get("layout") == row.get("layout_grid")
        assert row["visual_channel"].get("render_path") == row.get("render_path")
        semantic = row.get("semantic_constraints")
        assert isinstance(semantic, dict)
        assert isinstance(semantic.get("media_required"), bool)
        assert isinstance(semantic.get("chart_required"), bool)
        assert isinstance(semantic.get("diagram_type"), str)
        assert isinstance(row.get("layout_solution"), dict)
        assert row["layout_solution"].get("status") in {"ok", "overflow", "underflow"}


def test_apply_visual_orchestration_preserves_explicit_archetype_when_allowed():
    payload = _base_payload()
    payload["slides"][1]["archetype"] = "risk_mitigation"
    payload["slides"][1]["layout_grid"] = "split_2"

    out = ppt_service._apply_visual_orchestration(payload)
    slides = out.get("slides")
    assert isinstance(slides, list)
    content = next(s for s in slides if s.get("slide_id") == "s-content")
    assert content.get("archetype") == "risk_mitigation"
    assert isinstance(content.get("archetype_plan"), dict)
    assert str(content["archetype_plan"].get("selected") or "").strip().lower() == "risk_mitigation"

    contract_rows = out.get("presentation_contract_v2", {}).get("slides", [])
    row = next(r for r in contract_rows if r.get("slide_id") == "s-content")
    assert row.get("archetype") == "risk_mitigation"
    assert str((row.get("archetype_plan") or {}).get("selected") or "").strip().lower() == "risk_mitigation"


def test_presentation_contract_v2_has_minimum_archetype_coverage_for_20_slides():
    slide_specs = [
        ("cover", "hero_1", ""),
        ("content", "split_2", "comparison"),
        ("content", "grid_3", ""),
        ("content", "grid_4", ""),
        ("content", "timeline", "workflow"),
        ("content", "bento_5", "showcase"),
        ("content", "bento_6", ""),
        ("content", "split_2", "risk"),
        ("content", "split_2", "data_visualization"),
        ("content", "asymmetric_2", ""),
    ]
    slides = []
    for idx in range(20):
        slide_type, layout_grid, semantic_type = slide_specs[idx % len(slide_specs)]
        slides.append(
            {
                "slide_id": f"s-{idx + 1}",
                "slide_type": slide_type,
                "layout_grid": layout_grid,
                "semantic_type": semantic_type,
                "blocks": [{"block_type": "body", "card_id": "b1", "content": f"内容 {idx + 1}"}],
            }
        )

    out = ppt_service._apply_visual_orchestration(
        {
            "title": "Coverage Deck",
            "theme": {"palette": "pure_tech_blue", "style": "soft"},
            "slides": slides,
        }
    )
    rows = out.get("presentation_contract_v2", {}).get("slides", [])
    assert isinstance(rows, list)
    assert len(rows) == 20
    unique_archetypes = {str(row.get("archetype") or "") for row in rows if str(row.get("archetype") or "")}
    assert len(unique_archetypes) >= 6
