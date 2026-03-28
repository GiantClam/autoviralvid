"""截图展示当前 PPT 功能界面"""

import os, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

RENDERER_BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUTPUT_DIR = Path("test_outputs/screenshots")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})

        # ── 1. API Docs 全览 ──
        print("[1] API Docs overview")
        page = ctx.new_page()
        page.goto(f"{RENDERER_BASE}/docs", wait_until="networkidle", timeout=15000)
        page.locator("text=PPT").first.click()
        page.wait_for_timeout(800)
        page.screenshot(
            path=str(OUTPUT_DIR / "01-api-docs-overview.png"), full_page=False
        )
        page.close()
        print("  -> 01-api-docs-overview.png")

        # ── 2. API Response Preview ──
        print("[2] API response preview")
        page = ctx.new_page()
        page.goto(f"{RENDERER_BASE}/docs", wait_until="networkidle", timeout=15000)

        request_payload = {
            "title": "Python 编程入门",
            "slides": [
                {
                    "title": "变量与数据类型",
                    "key_points": ["int/float/str/bool", "变量赋值", "类型转换"],
                },
                {"title": "函数定义", "key_points": ["def语句", "参数传递", "返回值"]},
                {"title": "面向对象", "key_points": ["class定义", "继承", "多态"]},
            ],
        }

        result = page.evaluate(f"""
            async () => {{
                const res = await fetch('{RENDERER_BASE}/api/v1/ppt/outline', {{
                    method: 'PUT',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({
            json.dumps(
                {
                    "title": "Python 编程入门",
                    "theme": "default",
                    "style": "education",
                    "slides": [
                        {
                            "id": "s1",
                            "order": 1,
                            "title": "变量与数据类型",
                            "description": "Python基础变量",
                            "key_points": [
                                "int/float/str/bool",
                                "变量赋值",
                                "类型转换",
                            ],
                            "suggested_elements": ["text", "chart"],
                            "estimated_duration": 120,
                        },
                        {
                            "id": "s2",
                            "order": 2,
                            "title": "函数定义",
                            "description": "def关键字",
                            "key_points": ["def语句", "参数传递", "返回值"],
                            "suggested_elements": ["text", "table"],
                            "estimated_duration": 180,
                        },
                        {
                            "id": "s3",
                            "order": 3,
                            "title": "面向对象",
                            "description": "类与对象",
                            "key_points": ["class定义", "继承", "多态"],
                            "suggested_elements": ["text", "image"],
                            "estimated_duration": 150,
                        },
                    ],
                    "total_duration": 0,
                },
                ensure_ascii=False,
            )
        })
                }});
                return await res.json();
            }}
        """)

        req_json = json.dumps(request_payload, indent=2, ensure_ascii=False)
        res_json = json.dumps(result, indent=2, ensure_ascii=False)
        page.evaluate(
            """(args) => {
            document.body.innerHTML = '<div style="font-family: Segoe UI, sans-serif; background: #0f172a; color: #e2e8f0; padding: 32px; min-height: 100vh;">'
                + '<h1 style="font-size: 24px; color: #38bdf8; margin-bottom: 8px;">PPT API Response</h1>'
                + '<p style="color: #94a3b8; margin-bottom: 24px;">PUT /api/v1/ppt/outline</p>'
                + '<div style="display: flex; gap: 24px;">'
                + '<div style="flex: 1;"><h2 style="font-size: 16px; color: #f1f5f9; margin-bottom: 12px;">Request</h2>'
                + '<pre style="background: #1e293b; padding: 16px; border-radius: 8px; font-size: 12px; overflow: auto; max-height: 400px; border: 1px solid #334155; white-space: pre-wrap;">' + args[0] + '</pre></div>'
                + '<div style="flex: 1;"><h2 style="font-size: 16px; color: #f1f5f9; margin-bottom: 12px;">Response (200 OK)</h2>'
                + '<pre style="background: #1e293b; padding: 16px; border-radius: 8px; font-size: 12px; overflow: auto; max-height: 400px; border: 1px solid #334155; white-space: pre-wrap;">' + args[1] + '</pre></div>'
                + '</div></div>';
        }""",
            arg=[req_json, res_json],
        )
        page.screenshot(path=str(OUTPUT_DIR / "02-api-response.png"), full_page=False)
        page.close()
        print("  -> 02-api-response.png")

        # ── 3. PPT Preview ──
        print("[3] PPT preview simulation")
        page = ctx.new_page()
        page.goto(f"{RENDERER_BASE}/docs", wait_until="networkidle", timeout=15000)

        slides_json = json.dumps(
            [
                {
                    "t": "Python 编程入门",
                    "sub": "变量 · 函数 · 类",
                    "bg": "#1e3a5f",
                    "ac": "#38bdf8",
                    "pts": [],
                    "nar": "大家好，今天我们来学习Python编程的基础知识。",
                },
                {
                    "t": "变量与数据类型",
                    "sub": "",
                    "bg": "#ffffff",
                    "ac": "#2563eb",
                    "pts": [
                        "整数 (int): 42",
                        "浮点数 (float): 3.14",
                        "字符串 (str): 'hello'",
                        "布尔 (bool): True / False",
                    ],
                    "nar": "Python有四种基本数据类型，整数、浮点数、字符串和布尔值。",
                },
                {
                    "t": "函数定义",
                    "sub": "",
                    "bg": "#f8fafc",
                    "ac": "#7c3aed",
                    "pts": [
                        "def greet(name):",
                        "    return f'Hello, {name}!'",
                        "",
                        "函数是可复用的代码块",
                    ],
                    "nar": "使用def关键字定义函数，可以接收参数并返回结果。",
                },
                {
                    "t": "面向对象编程",
                    "sub": "",
                    "bg": "#fef3c7",
                    "ac": "#d97706",
                    "pts": [
                        "class Animal:",
                        "    def __init__(self, name):",
                        "        self.name = name",
                    ],
                    "nar": "类是创建对象的蓝图，通过class关键字定义。",
                },
            ],
            ensure_ascii=False,
        )

        page.evaluate(
            """(slidesJson) => {
            const slides = JSON.parse(slidesJson);
            let cards = '';
            slides.forEach(function(s, i) {
                var pts = s.pts.map(function(p) { return '<div style="font-size:11px;color:#475569;padding:1px 0;font-family:monospace;">' + p + '</div>'; }).join('');
                var sub = s.sub ? '<p style="font-size:13px;color:#64748b;margin:0 0 8px 0;">' + s.sub + '</p>' : '<div style="height:8px"></div>';
                cards += '<div style="background:' + s.bg + ';border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.3);aspect-ratio:16/9;padding:20px;display:flex;flex-direction:column;position:relative;border:1px solid #334155;">'
                    + '<div style="position:absolute;top:6px;right:10px;font-size:10px;color:#94a3b8;background:rgba(0,0,0,0.3);padding:2px 8px;border-radius:4px;">' + (i+1) + '/4</div>'
                    + '<h2 style="font-size:18px;font-weight:bold;color:' + s.ac + ';margin:0 0 2px 0;">' + s.t + '</h2>' + sub
                    + '<div style="flex:1">' + pts + '</div>'
                    + '<div style="border-top:1px solid rgba(0,0,0,0.1);padding-top:6px;margin-top:auto;">'
                    + '<div style="font-size:9px;color:#94a3b8;margin-bottom:2px;">' + String.fromCodePoint(0x1F3A4) + ' 讲解文本</div>'
                    + '<div style="font-size:10px;color:#475569;line-height:1.4;">' + s.nar + '</div></div></div>';
            });
            document.body.innerHTML = '<div style="font-family:Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;min-height:100vh;">'
                + '<h1 style="font-size:20px;color:#38bdf8;margin-bottom:4px;">PPT Preview \u2014 Python 编程入门</h1>'
                + '<p style="color:#94a3b8;font-size:13px;margin-bottom:20px;">4 slides \u00b7 ~7.5 minutes \u00b7 Education style</p>'
                + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">' + cards + '</div></div>';
        }""",
            arg=slides_json,
        )
        page.screenshot(path=str(OUTPUT_DIR / "03-ppt-preview.png"), full_page=False)
        page.close()
        print("  -> 03-ppt-preview.png")

        # ── 4. Endpoint Map ──
        print("[4] Endpoint map")
        page = ctx.new_page()
        page.goto(f"{RENDERER_BASE}/docs", wait_until="networkidle", timeout=15000)
        page.evaluate("""() => {
            var eps = [
                ['POST','/api/v1/ppt/outline','Generate outline','A','#22c55e'],
                ['PUT','/api/v1/ppt/outline','Edit outline','A','#22c55e'],
                ['POST','/api/v1/ppt/content','Fill content (parallel)','A','#22c55e'],
                ['POST','/api/v1/ppt/export','Export PPTX','A','#22c55e'],
                ['POST','/api/v1/ppt/tts','TTS synthesis','A','#22c55e'],
                ['POST','/api/v1/ppt/parse','Parse PPT/PDF','B','#8b5cf6'],
                ['POST','/api/v1/ppt/enhance','LLM enhance + TTS','B','#8b5cf6'],
                ['POST','/api/v1/ppt/render','Start render','B','#8b5cf6'],
                ['GET','/api/v1/ppt/render/:id','Check status','B','#8b5cf6'],
                ['GET','/api/v1/ppt/download/:id','Get download','B','#8b5cf6'],
            ];
            var colA='', colB='';
            eps.forEach(function(e) {
                var html = '<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;margin-bottom:6px;background:#1e293b;border-radius:8px;border-left:3px solid '+e[4]+';">'
                    + '<span style="background:'+e[4]+';color:#000;font-size:10px;font-weight:bold;padding:2px 6px;border-radius:4px;min-width:42px;text-align:center;">'+e[0]+'</span>'
                    + '<code style="font-size:11px;color:#e2e8f0;">'+e[1]+'</code>'
                    + '<span style="margin-left:auto;font-size:11px;color:#94a3b8;">'+e[2]+'</span></div>';
                if(e[3]==='A') colA+=html; else colB+=html;
            });
            document.body.innerHTML = '<div style="font-family:Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;min-height:100vh;">'
                + '<h1 style="font-size:22px;margin-bottom:4px;">PPT API Endpoint Map</h1>'
                + '<p style="color:#94a3b8;font-size:13px;margin-bottom:20px;">10 endpoints \u00b7 Feature A: PPT Generation \u00b7 Feature B: PPT/PDF Video</p>'
                + '<div style="display:flex;gap:32px;">'
                + '<div style="flex:1"><div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;"><div style="width:12px;height:12px;border-radius:50%;background:#22c55e;"></div><span style="font-size:14px;font-weight:bold;">Feature A: PPT Generation</span></div>'+colA+'</div>'
                + '<div style="flex:1"><div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;"><div style="width:12px;height:12px;border-radius:50%;background:#8b5cf6;"></div><span style="font-size:14px;font-weight:bold;">Feature B: PPT/PDF Video</span></div>'+colB+'</div>'
                + '</div></div>';
        }""")
        page.screenshot(path=str(OUTPUT_DIR / "04-endpoint-map.png"), full_page=False)
        page.close()
        print("  -> 04-endpoint-map.png")

        # ── 5. Architecture ──
        print("[5] Architecture diagram")
        page = ctx.new_page()
        page.goto(f"{RENDERER_BASE}/docs", wait_until="networkidle", timeout=15000)
        page.evaluate("""() => {
            document.body.innerHTML = '<div style="font-family:Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;min-height:100vh;">'
                + '<h1 style="font-size:22px;color:#38bdf8;margin-bottom:4px;">PPT/Video System Architecture</h1>'
                + '<p style="color:#94a3b8;font-size:13px;margin-bottom:24px;">Two independent features sharing common infrastructure</p>'
                + '<div style="display:flex;gap:16px;margin-bottom:24px;">'
                + '<div style="flex:1;background:#1e293b;border-radius:12px;padding:20px;border:2px solid #22c55e;">'
                    + '<div style="font-size:14px;font-weight:bold;color:#22c55e;margin-bottom:12px;">Feature A: PPT Generation</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;margin-bottom:8px;text-align:center;font-size:12px;">User Input</div>'
                    + '<div style="text-align:center;color:#475569;font-size:16px;">\u2193</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;margin-bottom:8px;text-align:center;font-size:12px;">LLM Outline Generation</div>'
                    + '<div style="text-align:center;color:#475569;font-size:16px;">\u2193</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;margin-bottom:8px;text-align:center;font-size:12px;">User Confirm / Edit</div>'
                    + '<div style="text-align:center;color:#475569;font-size:16px;">\u2193</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;margin-bottom:8px;text-align:center;font-size:12px;">Parallel Content Generation</div>'
                    + '<div style="text-align:center;color:#475569;font-size:16px;">\u2193</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;text-align:center;font-size:12px;">Export PPTX</div>'
                + '</div>'
                + '<div style="flex:1;background:#1e293b;border-radius:12px;padding:20px;border:2px solid #8b5cf6;">'
                    + '<div style="font-size:14px;font-weight:bold;color:#8b5cf6;margin-bottom:12px;">Feature B: PPT/PDF Video</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;margin-bottom:8px;text-align:center;font-size:12px;">Import PPT/PDF</div>'
                    + '<div style="text-align:center;color:#475569;font-size:16px;">\u2193</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;margin-bottom:8px;text-align:center;font-size:12px;">Parse Document</div>'
                    + '<div style="text-align:center;color:#475569;font-size:16px;">\u2193</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;margin-bottom:8px;text-align:center;font-size:12px;">LLM Enhance + TTS</div>'
                    + '<div style="text-align:center;color:#475569;font-size:16px;">\u2193</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;margin-bottom:8px;text-align:center;font-size:12px;">Remotion Render</div>'
                    + '<div style="text-align:center;color:#475569;font-size:16px;">\u2193</div>'
                    + '<div style="background:#0f172a;padding:10px;border-radius:8px;text-align:center;font-size:12px;">MP4 Video</div>'
                + '</div></div>'
                + '<div style="background:#1e293b;border-radius:12px;padding:16px;border:1px solid #334155;">'
                    + '<div style="font-size:12px;font-weight:bold;color:#f1f5f9;margin-bottom:12px;">Shared Infrastructure</div>'
                    + '<div style="display:flex;gap:12px;">'
                        + '<div style="background:#0f172a;padding:8px 16px;border-radius:8px;font-size:11px;text-align:center;flex:1;"><div style="color:#38bdf8;font-weight:bold;">LLM</div><div style="color:#94a3b8;">OpenRouter</div></div>'
                        + '<div style="background:#0f172a;padding:8px 16px;border-radius:8px;font-size:11px;text-align:center;flex:1;"><div style="color:#38bdf8;font-weight:bold;">TTS</div><div style="color:#94a3b8;">Minimax</div></div>'
                        + '<div style="background:#0f172a;padding:8px 16px;border-radius:8px;font-size:11px;text-align:center;flex:1;"><div style="color:#38bdf8;font-weight:bold;">Storage</div><div style="color:#94a3b8;">Cloudflare R2</div></div>'
                        + '<div style="background:#0f172a;padding:8px 16px;border-radius:8px;font-size:11px;text-align:center;flex:1;"><div style="color:#38bdf8;font-weight:bold;">Render</div><div style="color:#94a3b8;">Local / Lambda</div></div>'
                        + '<div style="background:#0f172a;padding:8px 16px;border-radius:8px;font-size:11px;text-align:center;flex:1;"><div style="color:#38bdf8;font-weight:bold;">DB</div><div style="color:#94a3b8;">Supabase</div></div>'
                    + '</div></div></div>';
        }""")
        page.screenshot(path=str(OUTPUT_DIR / "05-architecture.png"), full_page=False)
        page.close()
        print("  -> 05-architecture.png")

        # ── 6. Rendered Video ──
        print("[6] Rendered video info")
        page = ctx.new_page()
        page.goto(f"{RENDERER_BASE}/docs", wait_until="networkidle", timeout=15000)
        page.evaluate("""() => {
            document.body.innerHTML = '<div style="font-family:Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;min-height:100vh;">'
                + '<h1 style="font-size:22px;color:#38bdf8;margin-bottom:16px;">Local Render Result</h1>'
                + '<div style="background:#1e293b;border-radius:12px;padding:24px;border:1px solid #334155;max-width:600px;">'
                + '<div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">'
                + '<div style="width:120px;height:68px;background:#334155;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:24px;">' + String.fromCodePoint(0x1F3AC) + '</div>'
                + '<div><div style="font-size:16px;font-weight:bold;color:#f1f5f9;">test_render.mp4</div>'
                + '<div style="font-size:12px;color:#94a3b8;">Made with Remotion 4.0.438</div></div></div>'
                + '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">'
                + '<div style="background:#0f172a;padding:12px;border-radius:8px;text-align:center;"><div style="font-size:20px;font-weight:bold;color:#22c55e;">5.0s</div><div style="font-size:10px;color:#94a3b8;">Duration</div></div>'
                + '<div style="background:#0f172a;padding:12px;border-radius:8px;text-align:center;"><div style="font-size:20px;font-weight:bold;color:#3b82f6;">235KB</div><div style="font-size:10px;color:#94a3b8;">File Size</div></div>'
                + '<div style="background:#0f172a;padding:12px;border-radius:8px;text-align:center;"><div style="font-size:20px;font-weight:bold;color:#8b5cf6;">H.264</div><div style="font-size:10px;color:#94a3b8;">Codec</div></div>'
                + '</div>'
                + '<div style="margin-top:16px;padding-top:16px;border-top:1px solid #334155;">'
                + '<div style="font-size:12px;color:#94a3b8;margin-bottom:8px;">Render Pipeline</div>'
                + '<div style="display:flex;gap:8px;align-items:center;">'
                + '<div style="background:#22c55e;color:#000;padding:4px 12px;border-radius:6px;font-size:11px;font-weight:bold;">Bundle</div>'
                + '<div style="color:#475569;">\u2192</div>'
                + '<div style="background:#3b82f6;color:#000;padding:4px 12px;border-radius:6px;font-size:11px;font-weight:bold;">Chrome</div>'
                + '<div style="color:#475569;">\u2192</div>'
                + '<div style="background:#8b5cf6;color:#fff;padding:4px 12px;border-radius:6px;font-size:11px;font-weight:bold;">FFmpeg</div>'
                + '<div style="color:#475569;">\u2192</div>'
                + '<div style="background:#f59e0b;color:#000;padding:4px 12px;border-radius:6px;font-size:11px;font-weight:bold;">MP4</div>'
                + '</div></div></div></div>';
        }""")
        page.screenshot(path=str(OUTPUT_DIR / "06-rendered-video.png"), full_page=False)
        page.close()
        print("  -> 06-rendered-video.png")

        browser.close()

    print(f"\nAll screenshots in {OUTPUT_DIR}/")
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        sz = f.stat().st_size / 1024
        print(f"  {f.name} ({sz:.0f}KB)")


if __name__ == "__main__":
    main()
