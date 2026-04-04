import asyncio
import base64
import json
from pathlib import Path

from src.ppt_service import PPTService
from src.schemas.ppt_pipeline import PPTPipelineRequest


OUT_DIR = Path("../test_outputs/qa_round5_en").resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOPIC = "Please create a high school classroom presentation titled 'Decoding the legislative process: understanding its impact on international relations'."


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
        quality_profile="lenient_draft",
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
    )

    result = await asyncio.wait_for(svc.run_ppt_pipeline(req), timeout=900)
    payload = result.model_dump()
    (OUT_DIR / "pipeline_result_round5_en.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_payload = (((payload.get("artifacts") or {}).get("render_payload")) or {})
    (OUT_DIR / "render_payload_round5_en.json").write_text(
        json.dumps(render_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    export = payload.get("export") or {}
    pptx_b64 = str(export.get("pptx_base64") or "").strip()
    if pptx_b64:
        (OUT_DIR / "deck_round5_en.pptx").write_bytes(base64.b64decode(pptx_b64))

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
