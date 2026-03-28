"""
Marp 服务 — marp-cli 转换 Markdown → PPTX
"""

from __future__ import annotations
import asyncio, logging, os, tempfile
from typing import Optional

from src.schemas.ppt_marp import PresentationMarp
from src.r2 import upload_bytes_to_r2

logger = logging.getLogger("marp_service")


async def generate_pptx(
    presentation: PresentationMarp, output_name: str = "presentation"
) -> str:
    """
    将 Marp Markdown 转换为 PPTX，上传 R2，返回下载 URL。
    """
    full_md = presentation.to_full_markdown()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(full_md)
        md_path = f.name

    pptx_path = md_path.replace(".md", ".pptx")

    try:
        import shutil

        npx_path = shutil.which("npx") or "npx"
        theme_css = os.path.join(
            os.path.dirname(__file__), "..", "themes", "modern-tailwind.css"
        )
        cmd = [
            npx_path,
            "@marp-team/marp-cli",
            md_path,
            "--pptx",
            "-o",
            pptx_path,
            "--allow-local-files",
            "--theme",
            theme_css,
        ]

        logger.info(f"[marp_service] Converting to PPTX...")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode != 0:
            err = stderr.decode()[:500]
            raise RuntimeError(f"marp-cli failed: {err}")

        with open(pptx_path, "rb") as f:
            pptx_bytes = f.read()

        import uuid

        key = f"projects/{uuid.uuid4().hex[:12]}/pptx/{output_name}.pptx"
        url = await upload_bytes_to_r2(
            pptx_bytes,
            key,
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        logger.info(f"[marp_service] PPTX uploaded: {url}")
        return url

    finally:
        for p in [md_path, pptx_path]:
            try:
                os.unlink(p)
            except Exception:
                pass
