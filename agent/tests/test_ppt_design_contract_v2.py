from __future__ import annotations

from pathlib import Path

from src import ppt_master_native_runtime as runtime


def test_parse_executor_output_reads_svg_and_notes_fences() -> None:
    raw = """
    ```svg
    <svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">
      <rect width="1280" height="720" fill="#ffffff"/>
    </svg>
    ```
    ```notes
    This page introduces the key strategic chokepoint logic.
    ```
    """
    svg, notes = runtime._parse_executor_output(raw)  # noqa: SLF001
    assert "<svg" in svg.lower()
    assert "strategic chokepoint" in notes.lower()


def test_extract_svg_title_prefers_title_tag() -> None:
    svg = '<svg><title>Hormuz Crisis Overview</title><text>Fallback</text></svg>'
    assert runtime._extract_svg_title(svg, "slide_1") == "Hormuz Crisis Overview"  # noqa: SLF001


def test_select_style_reference_consulting(tmp_path: Path) -> None:
    refs = tmp_path / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "executor-consultant-top.md").write_text("top", encoding="utf-8")
    (refs / "executor-consultant.md").write_text("consultant", encoding="utf-8")
    (refs / "executor-general.md").write_text("general", encoding="utf-8")
    selected = runtime._select_style_reference(  # noqa: SLF001
        references_dir=refs,
        style="consulting",
        template_name="mckinsey",
    )
    assert selected.name == "executor-consultant-top.md"


def test_looks_mojibake_detects_garbled_text() -> None:
    assert runtime._looks_mojibake("锛锛锛锛锛锛锛")  # noqa: SLF001
    assert not runtime._looks_mojibake("霍尔木兹海峡危机")


def test_validate_executor_page_rejects_numeric_only_title() -> None:
    svg = '<svg viewBox="0 0 1280 720"><text>2</text><text>内容</text></svg>'
    issues = runtime._validate_executor_page(  # noqa: SLF001
        svg_markup=svg,
        speaker_notes="围绕霍尔木兹海峡危机展开分析",
        page_no=2,
        total_pages=12,
        language="zh-CN",
        topic_keywords={"霍尔木兹", "危机"},
    )
    assert "title_is_numeric_only" in issues
