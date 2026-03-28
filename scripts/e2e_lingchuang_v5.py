"""灵创智能 v5 E2E 测试 — 语义化版式 + 母版渲染"""

import json, os, sys, subprocess
from pathlib import Path

BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUT = Path("test_outputs/lingchuang_v5")

OUTLINE = {
    "id": "lc-v5",
    "title": "灵创智能：引领数控加工新未来",
    "theme": "professional",
    "style": "professional",
    "slides": [
        {
            "id": "s1",
            "order": 1,
            "title": "灵创智能企业推介",
            "description": "封面",
            "key_points": ["精准智造，赋能工业新未来"],
            "suggested_layout": "cover",
            "estimated_duration": 15,
        },
        {
            "id": "s2",
            "order": 2,
            "title": "企业简介",
            "description": "公司定位和发展历程",
            "key_points": ["高端智能数控机床研发生产", "高新技术企业", "专精特新"],
            "suggested_layout": "bullet_points",
            "estimated_duration": 120,
        },
        {
            "id": "s3",
            "order": 3,
            "title": "核心研发实力",
            "description": "工厂规模和研发团队",
            "key_points": ["工厂50000平方米", "年产能2000台", "核心专利50+项"],
            "suggested_layout": "big_number",
            "estimated_duration": 120,
        },
        {
            "id": "s4",
            "order": 4,
            "title": "核心产品矩阵",
            "description": "三类核心产品",
            "key_points": [
                "高精度数控车床微米级",
                "五轴联动加工中心",
                "车铣复合机床效率提升40%",
            ],
            "suggested_layout": "bullet_points",
            "estimated_duration": 120,
        },
        {
            "id": "s5",
            "order": 5,
            "title": "核心技术优势",
            "description": "精智效三大优势",
            "key_points": ["精：微米级加工精度", "智：IoT智能监控", "效：自动化上下料"],
            "suggested_layout": "quote",
            "estimated_duration": 120,
        },
        {
            "id": "s6",
            "order": 6,
            "title": "行业应用",
            "description": "四大行业应用",
            "key_points": [
                "新能源汽车压铸件加工",
                "3C电子精密加工",
                "航空航天复杂曲面",
                "模具制造",
            ],
            "suggested_layout": "comparison",
            "estimated_duration": 120,
        },
        {
            "id": "s7",
            "order": 7,
            "title": "市场机遇",
            "description": "千亿级市场",
            "key_points": [
                "全球市场1000亿美元",
                "国产高端化率不足10%",
                "政策支持智能制造",
            ],
            "suggested_layout": "big_number",
            "estimated_duration": 120,
        },
        {
            "id": "s8",
            "order": 8,
            "title": "增长动能",
            "description": "三大驱动因素",
            "key_points": ["新能源汽车需求爆发", "5G通讯精密加工", "智能制造政策红利"],
            "suggested_layout": "bullet_points",
            "estimated_duration": 120,
        },
        {
            "id": "s9",
            "order": 9,
            "title": "合作模式",
            "description": "商业合作",
            "key_points": ["区域代理经销", "大客户直采集采", "设备融资租赁"],
            "suggested_layout": "bullet_points",
            "estimated_duration": 120,
        },
        {
            "id": "s10",
            "order": 10,
            "title": "生态合作",
            "description": "深度合作",
            "key_points": ["OEM/ODM定制研发", "产学研联合", "交钥匙工程"],
            "suggested_layout": "bullet_points",
            "estimated_duration": 120,
        },
        {
            "id": "s11",
            "order": 11,
            "title": "企业愿景",
            "description": "未来展望",
            "key_points": ["成为客户最信赖的数控机床伙伴", "持续为中国智造贡献力量"],
            "suggested_layout": "quote",
            "estimated_duration": 120,
        },
        {
            "id": "s12",
            "order": 12,
            "title": "联系方式",
            "description": "封底",
            "key_points": ["灵创智能", "400-XXX-XXXX"],
            "suggested_layout": "cover",
            "estimated_duration": 15,
        },
    ],
    "total_duration": 1230,
}


def call_api(method, path, body=None):
    import tempfile

    if body:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(body, f, ensure_ascii=False)
            rf = f.name
        cmd = f'curl -s -X {method} {BASE}{path} -H "Content-Type: application/json" -d @{rf}'
    else:
        cmd = f"curl -s -X {method} {BASE}{path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, timeout=600)
    if body:
        os.unlink(rf)
    raw = result.stdout.decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"success": False, "error": raw[:500]}


def get_audio_duration(url):
    import tempfile, urllib.request

    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        urllib.request.urlretrieve(url, tmp.name)
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                tmp.name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        os.unlink(tmp.name)
        if r.returncode == 0:
            return float(r.stdout.strip())
    except Exception:
        pass
    return 15.0


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  灵创智能 v5 — 语义化版式 + 母版渲染")
    print("=" * 60)

    # Step 1: 大纲
    print(f"\n[Step 1] Outline: {len(OUTLINE['slides'])} slides")

    # Step 2: 内容生成 (v5 语义化)
    print(f"\n[Step 2] Generating v5 content...")
    result = call_api(
        "POST",
        "/api/v1/ppt-v5/content",
        {
            "outline": OUTLINE,
            "language": "zh-CN",
        },
    )

    if not result.get("success"):
        print(f"  FAIL: {result.get('error', '')[:300]}")
        return

    slides = result["data"]
    print(f"  OK: {len(slides)} slides")

    for i, s in enumerate(slides):
        layout = s.get("layout_type", "?")
        emphasis = s.get("emphasis_words", [])
        nar_len = len(s.get("narration", ""))
        print(
            f"  {i + 1:2d}. [{layout:16s}] emphasis={emphasis} narration={nar_len}chars"
        )

    # Step 3: TTS
    print(f"\n[Step 3] TTS synthesis...")
    texts = [s.get("narration", "") for s in slides]
    tts = call_api(
        "POST", "/api/v1/ppt/tts", {"texts": texts, "voice_style": "zh-CN-female"}
    )

    if tts.get("success"):
        urls = tts["data"].get("audio_urls", [])
        durations = tts["data"].get("audio_durations", [])
        for i, s in enumerate(slides):
            if i < len(urls) and urls[i]:
                s["narrationAudioUrl"] = urls[i]
                dur = durations[i] if i < len(durations) else 15.0
                s["duration"] = max(3, int(dur + 1))
                print(f"  Slide {i + 1}: {dur:.1f}s -> {s['duration']}s")

    # Step 4: PPTX 导出 (母版渲染)
    print(f"\n[Step 4] Export PPTX (template rendering)...")
    export = call_api(
        "POST",
        "/api/v1/ppt-v5/export",
        {
            "slides": slides,
            "title": OUTLINE["title"],
            "author": "灵创智能",
            "template_id": "professional",
        },
    )
    if export.get("success"):
        print(f"  OK: {export['data']['url'][:80]}...")
    else:
        print(f"  FAIL: {export.get('error', '')[:200]}")

    # Save
    with open(OUT / "slides_v5.json", "w", encoding="utf-8") as f:
        json.dump(slides, f, ensure_ascii=False, indent=2)

    # Summary
    layouts = {}
    for s in slides:
        lt = s.get("layout_type", "unknown")
        layouts[lt] = layouts.get(lt, 0) + 1

    total_dur = sum(s.get("duration", 0) for s in slides)
    print(f"\n{'=' * 60}")
    print(f"  Summary")
    print(f"{'=' * 60}")
    print(f"  Slides: {len(slides)}")
    print(f"  Layouts: {layouts}")
    print(f"  Total duration: {total_dur}s")
    print(
        f"  Audio: {sum(1 for s in slides if s.get('narrationAudioUrl'))}/{len(slides)}"
    )


if __name__ == "__main__":
    main()
