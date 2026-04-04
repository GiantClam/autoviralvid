# -*- coding: utf-8 -*-
import asyncio
import base64
import json
from pathlib import Path

from src.ppt_service import PPTService
from src.schemas.ppt_pipeline import PPTPipelineRequest


OUT_DIR = Path("../test_outputs/qa_round5").resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOPIC = "请制作一份高中课堂展示课件，主题为“解码立法过程：理解其对国际关系的影响”"


async def main() -> None:
    svc = PPTService()
    req = PPTPipelineRequest(
        topic=TOPIC,
        audience="high school students",
        purpose="classroom presentation",
        style_preference="clear educational",
        total_pages=10,
        language="zh-CN",
        execution_profile="prod_safe",
        quality_profile="default",
        with_export=True,
        save_artifacts=True,
        export_channel="local",
        route_mode="fast",
        visual_preset="auto",
        template_family="auto",
        skill_profile="auto",
        web_enrichment=True,
        image_asset_enrichment=False,
        max_web_queries=1,
        max_search_results=3,
        desired_citations=2,
        min_reference_materials=1,
        min_key_data_points=3,
        required_facts=[
            "立法一般包含提出、审议、表决、公布等阶段",
            "国内立法会通过贸易、制裁、条约批准影响国际关系",
            "适合高中课堂，需有案例和课堂讨论问题",
        ],
        domain_terms=["立法过程", "国际关系", "条约", "制裁", "贸易政策"],
    )

    result = await asyncio.wait_for(svc.run_ppt_pipeline(req), timeout=900)
    payload = result.model_dump()
    (OUT_DIR / "pipeline_result_round5.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_payload = (((payload.get("artifacts") or {}).get("render_payload")) or {})
    (OUT_DIR / "render_payload_round5.json").write_text(
        json.dumps(render_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    export = payload.get("export") or {}
    pptx_b64 = str(export.get("pptx_base64") or "").strip()
    if pptx_b64:
        (OUT_DIR / "deck_round5.pptx").write_bytes(base64.b64decode(pptx_b64))

    print(
        json.dumps(
            {
                "ok": True,
                "run_id": payload.get("run_id"),
                "slides": len((render_payload.get("slides") or [])),
                "has_export": bool(export),
                "has_pptx_base64": bool(pptx_b64),
                "out_dir": str(OUT_DIR),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
