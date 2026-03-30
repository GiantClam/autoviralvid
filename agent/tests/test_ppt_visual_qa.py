import base64

import pytest

from src.ppt_visual_qa import (
    audit_rendered_slides,
    audit_textual_slides,
    run_markitdown_text_qa,
    summarize_markitdown_text,
)


_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO6Wf1EAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_visual_qa_empty_input():
    result = await audit_rendered_slides([], route_mode="standard")
    assert result["slide_count"] == 0
    assert result["local_score"] == 100.0


@pytest.mark.asyncio
async def test_visual_qa_returns_expected_keys():
    result = await audit_rendered_slides([_TINY_PNG], route_mode="standard", enable_multimodal=False)
    assert result["slide_count"] == 1
    assert "blank_slide_ratio" in result
    assert "low_contrast_ratio" in result
    assert "blank_area_ratio" in result
    assert "style_drift_ratio" in result
    assert "issue_counts" in result
    assert "issue_ratios" in result
    assert "slides" in result
    assert "combined_score" in result


@pytest.mark.asyncio
async def test_visual_qa_local_issue_ratios_present():
    result = await audit_rendered_slides([_TINY_PNG, _TINY_PNG], route_mode="standard", enable_multimodal=False)
    assert result["slide_count"] == 2
    assert result["multimodal_enabled"] is False
    assert float(result.get("blank_area_ratio") or 0.0) >= 0.0
    ratios = result.get("issue_ratios") if isinstance(result.get("issue_ratios"), dict) else {}
    assert "low_contrast" in ratios or "excessive_whitespace" in ratios


@pytest.mark.asyncio
async def test_visual_qa_fuses_local_and_multimodal_without_double_count(monkeypatch):
    async def _fake_mm(*_args, **_kwargs):
        return {
            "enabled": True,
            "score": 70.0,
            "issue_counts": {"excessive_whitespace": 2},
            "issue_ratios": {"excessive_whitespace": 1.0},
            "slides": [
                {"slide": 1, "score": 68.0, "issues": ["excessive_whitespace"], "summary": "s1", "error": False},
                {"slide": 2, "score": 72.0, "issues": ["excessive_whitespace"], "summary": "s2", "error": False},
            ],
        }

    monkeypatch.setattr("src.ppt_visual_qa._multimodal_audit", _fake_mm)
    result = await audit_rendered_slides(
        [_TINY_PNG, _TINY_PNG],
        route_mode="refine",
        enable_multimodal=True,
    )
    ratios = result.get("issue_ratios") if isinstance(result.get("issue_ratios"), dict) else {}
    counts = result.get("issue_counts") if isinstance(result.get("issue_counts"), dict) else {}
    assert float(ratios.get("excessive_whitespace") or 0.0) <= 1.0
    assert int(counts.get("excessive_whitespace") or 0) <= int(result.get("slide_count") or 0)


def test_textual_qa_detects_placeholder_and_page_number_gap():
    slides = [
        {
            "slide_id": "s1",
            "title": "增长策略结论",
            "content_strategy": {
                "assertion": "增长策略结论",
                "evidence": ["同比增长 38%"],
            },
            "elements": [{"type": "text", "content": "核心证据：同比增长 38%"}],
        },
        {
            "slide_id": "s2",
            "title": "",
            "content_strategy": {
                "assertion": "关键结论：转化率提升",
                "evidence": ["转化率提升 22%", "渠道 ROI 增长"],
            },
            "elements": [{"type": "text", "content": "TODO placeholder xxxx"}],
        },
    ]
    render_spec = {"slides": [{"slide_id": "s1", "page_number": 1}, {"slide_id": "s2", "page_number": 3}]}
    result = audit_textual_slides(slides, render_spec=render_spec)
    assert result["slide_count"] == 2
    assert result["page_number_discontinuous"] is True
    assert float(result.get("placeholder_ratio") or 0.0) > 0.0
    assert float(result.get("assertion_coverage_ratio") or 0.0) < 1.0
    assert float(result.get("evidence_coverage_ratio") or 0.0) < 1.0
    issue_codes = set(result.get("issue_codes") or [])
    assert "missing_assertion_title" in issue_codes
    assert "placeholder_text" in issue_codes
    assert "assertion_not_covered" in issue_codes
    assert "evidence_not_fully_covered" in issue_codes
    assert "page_number_discontinuous" in issue_codes


def test_summarize_markitdown_text_detects_placeholder():
    summary = summarize_markitdown_text(
        "# Slide 1\nThis is a real line\nTODO placeholder xxxx\n",
    )
    assert summary["line_count"] == 3
    assert summary["placeholder_hits"] > 0
    assert float(summary["placeholder_ratio"]) > 0.0
    assert "markitdown_placeholder_text" in set(summary["issue_codes"])


def test_run_markitdown_text_qa_propagates_extraction_failure(monkeypatch):
    import src.ppt_visual_qa as ppt_visual_qa

    monkeypatch.setattr(
        ppt_visual_qa,
        "extract_text_with_markitdown",
        lambda *_args, **_kwargs: {
            "enabled": True,
            "ok": False,
            "error": "markitdown_not_found",
            "text": "",
            "text_length": 0,
        },
    )
    result = run_markitdown_text_qa(b"pptx-bytes")
    assert result["enabled"] is True
    assert result["ok"] is False
    assert "markitdown_extraction_failed" in set(result.get("issue_codes") or [])
