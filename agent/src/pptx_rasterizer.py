"""Rasterize PPTX slides into PNG images for PPT-first video rendering."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import List

logger = logging.getLogger("pptx_rasterizer")


def _local_tmp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / "renders" / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_powershell_export(pptx_path: Path, out_dir: Path) -> bool:
    script = """
param(
  [string]$PptxPath,
  [string]$OutDir
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$app = $null
$presentation = $null
try {
  $app = New-Object -ComObject PowerPoint.Application
  $presentation = $app.Presentations.Open($PptxPath, $true, $false, $false)
  $index = 1
  foreach ($slide in $presentation.Slides) {
    $name = ('slide_{0:D3}.png' -f $index)
    $target = Join-Path $OutDir $name
    $slide.Export($target, 'PNG', 1920, 1080)
    $index++
  }
}
finally {
  if ($presentation -ne $null) { $presentation.Close() }
  if ($app -ne $null) { $app.Quit() }
}
"""

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".ps1",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write(script)
        script_path = Path(f.name)

    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                str(pptx_path),
                str(out_dir),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if proc.returncode != 0:
            logger.warning("[pptx_rasterizer] PowerPoint export failed: %s", proc.stderr[:800])
            return False
        return True
    except Exception as exc:
        logger.warning("[pptx_rasterizer] PowerPoint export exception: %s", exc)
        return False
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass


def _run_soffice_export(pptx_path: Path, out_dir: Path) -> bool:
    soffice = shutil.which("soffice")
    if not soffice:
        return False
    try:
        proc = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "png",
                "--outdir",
                str(out_dir),
                str(pptx_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if proc.returncode != 0:
            logger.warning("[pptx_rasterizer] soffice export failed: %s", proc.stderr[:800])
            return False
        return True
    except Exception as exc:
        logger.warning("[pptx_rasterizer] soffice export exception: %s", exc)
        return False


def rasterize_pptx_bytes_to_png_bytes(pptx_bytes: bytes) -> List[bytes]:
    """
    Convert PPTX bytes to per-slide PNG bytes.
    Returns [] when conversion is unavailable.
    """
    tmp_root = _local_tmp_root() / f"pptx_raster_{uuid.uuid4().hex[:12]}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        pptx_path = tmp_root / "presentation.pptx"
        out_dir = tmp_root / "slides"
        out_dir.mkdir(parents=True, exist_ok=True)
        pptx_path.write_bytes(pptx_bytes)

        exported = _run_powershell_export(pptx_path, out_dir)
        if not exported:
            exported = _run_soffice_export(pptx_path, out_dir)
        if not exported:
            return []

        png_paths = sorted(out_dir.glob("*.png"))
        # LibreOffice may emit "presentation.png"; PowerPoint emits slide_XXX.png.
        if not png_paths:
            png_paths = sorted(out_dir.glob("*.PNG"))
        if not png_paths:
            return []

        out: List[bytes] = []
        for path in png_paths:
            try:
                data = path.read_bytes()
                if data:
                    out.append(data)
            except Exception:
                continue
        return out
    finally:
        try:
            shutil.rmtree(tmp_root, ignore_errors=True)
        except Exception:
            pass
