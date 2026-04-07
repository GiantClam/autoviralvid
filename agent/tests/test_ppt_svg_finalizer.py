from pathlib import Path

from src.ppt_svg_finalizer import PPTSvgFinalizer


def _write_svg(path: Path) -> None:
    path.write_text(
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">'
            '<rect x="10" y="10" width="200" height="120" rx="16" ry="16" fill="#3366FF"/>'
            '<text x="40" y="80">hello</text>'
            "</svg>"
        ),
        encoding="utf-8",
    )


def test_finalize_svg_files_disabled_returns_skipped(tmp_path: Path):
    svg = tmp_path / "slide_001.svg"
    _write_svg(svg)
    finalizer = PPTSvgFinalizer(enabled=False)
    result = finalizer.finalize_svg_files([svg])
    assert result.success is True
    assert result.processed_files == 1
    assert len(result.skipped_steps) >= 1


def test_finalize_project_missing_helpers_is_non_fatal_by_default(tmp_path: Path):
    project = tmp_path / "demo"
    output_dir = project / "svg_output"
    output_dir.mkdir(parents=True)
    _write_svg(output_dir / "slide_001.svg")

    finalizer = PPTSvgFinalizer(
        enabled=True,
        strict=False,
        helper_root=tmp_path / "missing_helpers",
    )
    result = finalizer.finalize_project(project)

    assert result.success is True
    assert result.processed_files == 1
    assert "finalizer_helpers_unavailable" in result.errors
    assert (project / "svg_final" / "slide_001.svg").exists()


def test_finalize_project_missing_helpers_can_fail_in_strict_mode(tmp_path: Path):
    project = tmp_path / "demo"
    output_dir = project / "svg_output"
    output_dir.mkdir(parents=True)
    _write_svg(output_dir / "slide_001.svg")

    finalizer = PPTSvgFinalizer(
        enabled=True,
        strict=True,
        helper_root=tmp_path / "missing_helpers",
    )
    result = finalizer.finalize_project(project)
    assert result.success is False
    assert "finalizer_helpers_unavailable" in result.errors

