"""灵创智能 Premium E2E — 商业级视频组件"""

import json, os, sys, subprocess
from pathlib import Path

BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUT = Path("test_outputs/lingchuang_premium")


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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("  灵创智能 Premium — 商业级视频组件")
    print("=" * 60)

    # Step 1: 生成 premium 数据
    print("\n[Step 1] Generating premium content...")
    r = call_api(
        "POST",
        "/api/v1/premium/generate",
        {
            "requirement": """灵创智能企业介绍PPT，详细内容：

企业简介：高端智能数控机床研发生产销售，高新技术企业，核心团队20年行业经验
核心产品：高精度数控车床精度0.005mm、五轴联动加工中心航空航天应用、车铣复合机床效率提升40%
技术优势：精(微米级精度)、智(IoT智能监控)、效(自动化上下料)
市场机遇：全球机床市场1000亿美元，国产高端化率不足10%
合作模式：区域代理经销、大客户直采、设备融资租赁
企业愿景：成为客户最信赖的数控机床伙伴""",
            "num_slides": 8,
            "language": "zh-CN",
        },
    )

    if not r.get("success"):
        print(f"  FAIL: {r.get('error', '')[:300]}")
        return

    slides = r["data"]
    print(f"  OK: {len(slides)} slides")

    layouts = {}
    for i, s in enumerate(slides):
        lt = s.get("layout_type", s.get("layout", "?"))
        title = s.get("content", {}).get("title", s.get("title", ""))
        layouts[lt] = layouts.get(lt, 0) + 1
        print(f"  {i + 1}. [{lt:16s}] {title[:30]}")

    # Step 2: TTS
    print("\n[Step 2] TTS synthesis...")
    tts = call_api("POST", "/api/v1/premium/tts", {"slides": slides})

    if tts.get("success"):
        slides = tts["data"]["slides"]
        for i, s in enumerate(slides):
            dur = s.get("duration", 0)
            print(f"  Slide {i + 1}: {dur:.0f}s")

    # Save
    with open(OUT / "slides.json", "w", encoding="utf-8") as f:
        json.dump(slides, f, ensure_ascii=False, indent=2)

    total_dur = sum(s.get("duration", 0) for s in slides)
    print(f"\n{'=' * 60}")
    print(f"  Layouts: {layouts}")
    print(f"  Duration: {total_dur:.0f}s ({total_dur / 60:.1f}min)")
    print(f"  Output: {OUT / 'slides.json'}")


if __name__ == "__main__":
    main()
