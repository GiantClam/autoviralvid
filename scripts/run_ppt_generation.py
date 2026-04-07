"""完整 PPT 生成流程 — 使用真实 API Key"""

import json, sys, os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUTPUT_DIR = Path("test_outputs/ppt_generation")
SCREENSHOTS = OUTPUT_DIR / "screenshots"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(f"{BASE}/docs", wait_until="networkidle", timeout=15000)

        # ═══ Step 1: Generate Outline ═══
        print("[Step 1] Generating outline via LLM...")
        outline_result = page.evaluate(f"""
            async () => {{
                const res = await fetch('{BASE}/api/v1/ppt/outline', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        requirement: '制作一份Python编程入门的PPT，面向零基础学习者，包含变量、数据类型、函数、面向对象四个核心主题，每个主题有代码示例',
                        language: 'zh-CN',
                        num_slides: 6,
                        style: 'education',
                        purpose: '编程教学'
                    }})
                }});
                return await res.json();
            }}
        """)

        if not outline_result.get("success"):
            print(f"  FAILED: {outline_result.get('error')}")
            sys.exit(1)

        outline = outline_result["data"]
        td = outline.get("totalDuration") or outline.get("total_duration", 0)
        print(f'  OK: "{outline["title"]}" — {len(outline["slides"])} slides, {td}s')

        # Save outline
        with open(OUTPUT_DIR / "outline.json", "w", encoding="utf-8") as f:
            json.dump(outline, f, ensure_ascii=False, indent=2)

        # Screenshot: outline result
        outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
        page.evaluate(
            """(args) => {
            document.body.innerHTML = '<div style="font-family:Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;min-height:100vh;">'
                + '<h1 style="font-size:22px;color:#22c55e;margin-bottom:4px;">Step 1: Outline Generated</h1>'
                + '<p style="color:#94a3b8;font-size:13px;margin-bottom:16px;">POST /api/v1/ppt/outline — LLM generated in real-time</p>'
                + '<pre style="background:#1e293b;padding:16px;border-radius:8px;font-size:11px;overflow:auto;max-height:700px;border:1px solid #334155;white-space:pre-wrap;">' + args[0] + '</pre></div>';
        }""",
            arg=[outline_json],
        )
        page.screenshot(path=str(SCREENSHOTS / "01-outline-generated.png"))
        print(f"  -> {SCREENSHOTS / '01-outline-generated.png'}")

        # ═══ Step 2: Generate Content ═══
        print("\n[Step 2] Generating content via LLM (parallel)...")
        content_result = page.evaluate(f"""
            async () => {{
                const res = await fetch('{BASE}/api/v1/ppt/content', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        outline: {json.dumps(outline, ensure_ascii=False)},
                        language: 'zh-CN'
                    }})
                }});
                return await res.json();
            }}
        """)

        if not content_result.get("success"):
            print(f"  FAILED: {content_result.get('error')}")
            sys.exit(1)

        slides = content_result["data"]
        print(f"  OK: {len(slides)} slides generated")

        # Save content
        with open(OUTPUT_DIR / "slides.json", "w", encoding="utf-8") as f:
            json.dump(slides, f, ensure_ascii=False, indent=2)

        # Screenshot: PPT preview
        slides_json = json.dumps(slides, ensure_ascii=False)
        page.evaluate(
            """(slidesJson) => {
            var slides = JSON.parse(slidesJson);
            var cards = '';
            slides.forEach(function(s, i) {
                var elements = (s.elements || []).slice(0, 3);
                var elHtml = elements.map(function(e) {
                    if (e.type === 'text') {
                        var fs = (e.style && e.style.fontSize) ? Math.max(8, e.style.fontSize / 24) : 10;
                        return '<div style="font-size:' + fs + 'px;color:#475569;padding:2px 0;overflow:hidden;max-height:60px;">' + (e.content || '').substring(0, 100) + '</div>';
                    }
                    return '';
                }).join('');
                var nar = (s.narration || '').substring(0, 80);
                cards += '<div style="background:#1e293b;border-radius:10px;padding:14px;border:1px solid #334155;aspect-ratio:16/9;display:flex;flex-direction:column;position:relative;">'
                    + '<div style="position:absolute;top:6px;right:10px;font-size:9px;color:#64748b;background:#0f172a;padding:2px 6px;border-radius:4px;">' + (i+1) + '/' + slides.length + '</div>'
                    + '<div style="font-size:13px;font-weight:bold;color:#38bdf8;margin-bottom:6px;">' + s.title + '</div>'
                    + '<div style="flex:1;overflow:hidden;">' + elHtml + '</div>'
                    + '<div style="border-top:1px solid #334155;padding-top:4px;margin-top:auto;font-size:8px;color:#94a3b8;">' + nar + '...</div></div>';
            });
            document.body.innerHTML = '<div style="font-family:Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;min-height:100vh;">'
                + '<h1 style="font-size:20px;color:#22c55e;margin-bottom:4px;">Step 2: Content Generated</h1>'
                + '<p style="color:#94a3b8;font-size:13px;margin-bottom:16px;">POST /api/v1/ppt/content — ' + slides.length + ' slides with elements + narration</p>'
                + '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">' + cards + '</div></div>';
        }""",
            arg=slides_json,
        )
        page.screenshot(path=str(SCREENSHOTS / "02-content-generated.png"))
        print(f"  -> {SCREENSHOTS / '02-content-generated.png'}")

        # Show narration for each slide
        for i, s in enumerate(slides):
            nar = (s.get("narration") or "")[:60]
            print(
                f'  Slide {i + 1}: "{s["title"]}" — {len(s.get("elements", []))} elements, narration: "{nar}..."'
            )

        # ═══ Step 3: Export PPTX ═══
        print("\n[Step 3] Exporting PPTX...")
        export_result = page.evaluate(f"""
            async () => {{
                const res = await fetch('{BASE}/api/v1/ppt/export', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        slides: {json.dumps(slides, ensure_ascii=False)},
                        title: '{outline["title"]}',
                        author: 'AutoViralVid PPT Generator'
                    }})
                }});
                return await res.json();
            }}
        """)

        if export_result.get("success"):
            pptx_url = export_result["data"]["url"]
            print(f"  OK: PPTX uploaded to R2")
            print(f"  URL: {pptx_url}")
        else:
            print(f"  FAILED: {export_result.get('error')}")

        # Save export result
        with open(OUTPUT_DIR / "export_result.json", "w", encoding="utf-8") as f:
            json.dump(export_result, f, ensure_ascii=False, indent=2)

        # ═══ Step 4: Local Video Render ═══
        print("\n[Step 4] Rendering video locally...")
        render_result = page.evaluate(f"""
            async () => {{
                const res = await fetch('{BASE}/api/v1/ppt/render', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        slides: {json.dumps(slides, ensure_ascii=False)},
                        config: {{
                            width: 1920,
                            height: 1080,
                            fps: 30,
                            transition: 'fade',
                            include_narration: false
                        }},
                        idempotency_key: 'real-ppt-render-' + Date.now()
                    }})
                }});
                return await res.json();
            }}
        """)

        if render_result.get("success"):
            job = render_result["data"]
            print(
                f"  Render job: id={job['id']}, status={job['status']}, mode={job.get('mode', 'unknown')}"
            )
            if job.get("status") == "failed":
                print(f"  Error: {job.get('error', 'unknown')[:200]}")
        else:
            print(f"  FAILED: {render_result.get('error')}")

        # Save render result
        with open(OUTPUT_DIR / "render_result.json", "w", encoding="utf-8") as f:
            json.dump(render_result, f, ensure_ascii=False, indent=2)

        # ═══ Step 5: Final Summary Screenshot ═══
        print("\n[Step 5] Summary")
        summary = {
            "outline": {
                "title": outline["title"],
                "slides": len(outline["slides"]),
                "duration": outline["totalDuration"],
            },
            "content": {
                "slides": len(slides),
                "total_elements": sum(len(s.get("elements", [])) for s in slides),
            },
            "export": {"success": export_result.get("success", False)},
            "render": {
                "job_id": job.get("id") if render_result.get("success") else None,
                "status": job.get("status")
                if render_result.get("success")
                else "failed",
            },
        }

        page.evaluate(
            """(args) => {
            var s = JSON.parse(args[0]);
            document.body.innerHTML = '<div style="font-family:Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;min-height:100vh;">'
                + '<h1 style="font-size:24px;color:#38bdf8;margin-bottom:20px;">PPT Generation Pipeline — Complete</h1>'
                + '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px;">'
                + '<div style="background:#1e293b;padding:20px;border-radius:12px;border-left:4px solid #22c55e;"><div style="font-size:28px;font-weight:bold;color:#22c55e;">' + s.outline.slides + '</div><div style="font-size:12px;color:#94a3b8;">Outline Slides</div><div style="font-size:10px;color:#64748b;margin-top:4px;">' + (s.outline.duration/60).toFixed(1) + ' min</div></div>'
                + '<div style="background:#1e293b;padding:20px;border-radius:12px;border-left:4px solid #3b82f6;"><div style="font-size:28px;font-weight:bold;color:#3b82f6;">' + s.content.total_elements + '</div><div style="font-size:12px;color:#94a3b8;">Total Elements</div><div style="font-size:10px;color:#64748b;margin-top:4px;">' + s.content.slides + ' slides</div></div>'
                + '<div style="background:#1e293b;padding:20px;border-radius:12px;border-left:4px solid #8b5cf6;"><div style="font-size:28px;font-weight:bold;color:#8b5cf6;">' + (s.export.success ? 'OK' : 'FAIL') + '</div><div style="font-size:12px;color:#94a3b8;">PPTX Export</div><div style="font-size:10px;color:#64748b;margin-top:4px;">svg</div></div>'
                + '<div style="background:#1e293b;padding:20px;border-radius:12px;border-left:4px solid #f59e0b;"><div style="font-size:28px;font-weight:bold;color:#f59e0b;">' + (s.render.status || 'N/A') + '</div><div style="font-size:12px;color:#94a3b8;">Video Render</div><div style="font-size:10px;color:#64748b;margin-top:4px;">local mode</div></div>'
                + '</div>'
                + '<div style="background:#1e293b;padding:20px;border-radius:12px;border:1px solid #334155;">'
                + '<div style="font-size:14px;font-weight:bold;margin-bottom:12px;">' + s.outline.title + '</div>'
                + '<div style="font-size:12px;color:#94a3b8;">Pipeline: outline (LLM) \u2192 content (parallel LLM) \u2192 export (svg) \u2192 render (Remotion)</div>'
                + '</div></div>';
        }""",
            arg=[json.dumps(summary, ensure_ascii=False)],
        )
        page.screenshot(path=str(SCREENSHOTS / "05-final-summary.png"))
        print(f"  -> {SCREENSHOTS / '05-final-summary.png'}")

        page.close()
        browser.close()

    print(f"\nFiles saved to {OUTPUT_DIR}/")
    for f in sorted(OUTPUT_DIR.rglob("*")):
        if f.is_file():
            sz = f.stat().st_size
            unit = "KB" if sz < 1024 * 1024 else "MB"
            val = sz / 1024 if sz < 1024 * 1024 else sz / (1024 * 1024)
            print(f"  {f.relative_to(OUTPUT_DIR)} ({val:.1f}{unit})")


if __name__ == "__main__":
    main()
