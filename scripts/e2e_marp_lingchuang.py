"""灵创智能 Marp E2E — Markdown 驱动 PPT + 视频"""

import json, os, sys, subprocess
from pathlib import Path

BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUT = Path("test_outputs/lingchuang_marp")


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
    print("  灵创智能 Marp — Markdown 驱动")
    print("=" * 60)

    # Step 1: 生成 Marp 内容 (Markdown + Script)
    print("\n[Step 1] Generating Marp content...")
    r = call_api(
        "POST",
        "/api/v1/marp/generate",
        {
            "requirement": """灵创智能企业介绍PPT，包含以下详细内容：

第一部分：企业简介
- 公司定位：致力于高端智能数控机床的研发、生产与销售
- 发展历程：高新技术企业、专精特新，核心团队20年行业经验
- 荣誉资质：ISO9001认证、多项国家专利

第二部分：核心产品矩阵
- 高精度数控车床/铣床：加工精度达0.005mm，适用于基础零部件加工
- 五轴联动加工中心：复杂曲面加工能力，适用于航空航天、医疗器械
- 车铣复合机床：车削铣削一体化，效率提升40%

第三部分：核心技术优势
- 精：微米级加工精度，高刚性床身设计，直线度误差<0.003mm/m
- 智：自研IoT智能监控系统，实时设备状态监控与故障预警
- 效：高压冷却排屑系统，自动化上下料接口，24小时无人值守

第四部分：宏观市场机遇
- 全球数控机床市场规模突破1000亿美元，年增长率12%
- 国产高端数控化率不足10%，进口替代空间巨大
- 新能源汽车轻量化、5G通讯精密加工、智能制造政策红利

第五部分：多元合作模式
- 区域代理与经销：完善的渠道保护和利润空间
- 大客户直采集采：批量采购优惠及驻厂售后
- 设备融资租赁：降低客户初期资金门槛

第六部分：企业愿景
- 短期目标：成为细分市场领导者
- 长期愿景：做最懂客户的数控机床合作伙伴""",
            "num_slides": 10,
            "language": "zh-CN",
            "theme": "default",
        },
    )

    if not r.get("success"):
        print(f"  FAIL: {r.get('error', '')[:300]}")
        return

    data = r["data"]
    slides = data["slides"]
    print(f"  OK: {len(slides)} slides, theme: {data.get('theme', '?')}")

    # 展示每页 Markdown 和 Script
    for i, s in enumerate(slides):
        md_lines = s["markdown"].strip().split("\n")
        first_line = md_lines[0] if md_lines else "(empty)"
        script_lines = len(s.get("script", []))
        print(f"  {i + 1:2d}. [{first_line[:60]}] {script_lines} script lines")

    # Step 2: TTS
    print("\n[Step 2] TTS synthesis...")
    tts = call_api("POST", "/api/v1/marp/tts", {"slides": slides})

    if tts.get("success"):
        slides = tts["data"]["slides"]
        for i, s in enumerate(slides):
            dur = s.get("duration", 0)
            lines = s.get("script", [])
            audio = sum(1 for l in lines if l.get("audio_url"))
            print(f"  Slide {i + 1}: {dur:.0f}s, {audio}/{len(lines)} audio")
    else:
        print(f"  TTS FAIL: {tts.get('error', '')[:200]}")

    # Step 3: Export PPTX via marp-cli
    print("\n[Step 3] Export PPTX (marp-cli)...")
    export = call_api("POST", "/api/v1/marp/export", {"presentation": data})

    if export.get("success"):
        url = export["data"]["url"]
        print(f"  OK: {url[:80]}...")
    else:
        print(f"  FAIL: {export.get('error', '')[:300]}")

    # Save
    with open(OUT / "presentation.json", "w", encoding="utf-8") as f:
        json.dump(
            {"slides": slides, "theme": data.get("theme")},
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Save full markdown
    full_md = f"---\nmarp: true\ntheme: {data.get('theme', 'default')}\npaginate: true\nsize: 16:9\n---\n\n"
    full_md += "\n\n---\n\n".join(s["markdown"].strip() for s in slides)
    with open(OUT / "presentation.md", "w", encoding="utf-8") as f:
        f.write(full_md)

    # Summary
    total_dur = sum(s.get("duration", 0) for s in slides)
    total_lines = sum(len(s.get("script", [])) for s in slides)
    total_actions = sum(
        1 for s in slides for l in s.get("script", []) if l.get("action") != "none"
    )

    print(f"\n{'=' * 60}")
    print(f"  Summary")
    print(f"{'=' * 60}")
    print(f"  Slides: {len(slides)}")
    print(f"  Script lines: {total_lines}")
    print(f"  Actions: {total_actions}")
    print(f"  Duration: {total_dur:.0f}s ({total_dur / 60:.1f}min)")
    print(f"  Files:")
    print(f"    {OUT / 'presentation.md'} ({len(full_md)} chars)")
    print(f"    {OUT / 'presentation.json'}")


if __name__ == "__main__":
    main()
