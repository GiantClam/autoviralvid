"""灵创智能 Premium PPT — HTML 截图方案"""

import json, os, sys, subprocess
from pathlib import Path

BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUT = Path("test_outputs/lingchuang_premium_v2")

REQUIREMENT = """灵创智能企业介绍PPT，12页，详细内容如下：

【封面】灵创智能企业推介 — 精准智造，赋能工业新未来

【第一部分：走进灵创智能】
幻灯片1 企业简介：
- 高端智能数控机床的研发、生产与销售
- 2015年成立，高新技术企业，专精特新
- ISO9001认证，68项国家专利

幻灯片2 核心研发与生产实力：
- 50,000平方米现代化智能工厂
- 年产能2,000台高端数控机床
- 150名工程师团队，自研LC-OS数控系统

【第二部分：匠心智造】
幻灯片3 核心产品矩阵：
- 高精度数控车床/铣床：精度0.005mm
- 五轴联动加工中心：航空航天应用
- 车铣复合机床：效率提升40%

幻灯片4 产品核心技术优势：
- 精：微米级精度0.005mm
- 智：IoT智能监控故障预警
- 效：高压冷却自动上下料

幻灯片5 行业应用案例：
- 新能源汽车压铸件加工精度0.01mm
- 3C电子手机中框Ra0.4
- 航空航天钛合金AS9100认证
- 模具制造寿命提升30%

【第三部分：蓝海启航】
幻灯片6 市场机遇：
- 全球市场1000亿美元，年增长12%
- 中国市场300亿美元占全球30%
- 国产高端化率不足10%

幻灯片7 增长动能：
- 新能源汽车需求年增25%
- 5G通讯精密加工爆发
- 智能制造2025政策支持

【第四部分：携手共赢】
幻灯片8 合作模式：
- 区域代理：渠道保护，利润30-50%
- 大客户直采：优惠15%，驻厂售后
- 融资租赁：首付低至20%

幻灯片9 生态合作：
- OEM/ODM非标机床定制
- 产学研联合：清华/上交大共建实验室
- 交钥匙工程全套服务

【第五部分：未来展望】
幻灯片10 企业愿景：
- 短期目标：年营收突破10亿
- 长期愿景：全球领先智能数控方案商
- 做最懂客户的数控机床伙伴

幻灯片11 联系方式：
- 灵创智能科技有限公司
- 深圳市南山区科技园
- 400-888-XXXX / www.lingchuang-cnc.com"""


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
    print("  灵创智能 Premium PPT v2 — HTML 截图方案")
    print("=" * 60)

    # Step 1: 生成内容
    print("\n[Step 1] Generating content...")
    r = call_api(
        "POST",
        "/api/v1/premium/generate",
        {
            "requirement": REQUIREMENT,
            "num_slides": 11,
            "language": "zh-CN",
        },
    )
    if not r.get("success"):
        print(f"  FAIL: {r.get('error', '')[:300]}")
        return

    slides = r["data"]
    print(f"  OK: {len(slides)} slides")

    # Step 2: TTS
    print("\n[Step 2] TTS...")
    tts = call_api("POST", "/api/v1/premium/tts", {"slides": slides})
    if tts.get("success"):
        slides = tts["data"]["slides"]
        total_dur = sum(s.get("duration", 0) for s in slides)
        audio = sum(
            1 for s in slides for l in s.get("script", []) if l.get("audio_url")
        )
        lines = sum(len(s.get("script", [])) for s in slides)
        print(f"  OK: {audio}/{lines} audio, {total_dur:.0f}s")

    # Step 3: 截图 + PPTX
    print("\n[Step 3] Rendering HTML screenshots...")
    import sys

    sys.path.insert(0, "agent")
    from src.screenshot_engine import render_slides_to_images, images_to_pptx

    img_dir = str(OUT / "slides")
    image_paths = render_slides_to_images(slides, img_dir)
    print(f"  OK: {len(image_paths)} screenshots")

    if image_paths:
        pptx_path = str(OUT / "lingchuang_premium.pptx")
        images_to_pptx(image_paths, pptx_path, "灵创智能：引领数控加工新未来")
        size = os.path.getsize(pptx_path)
        print(f"  PPTX: {pptx_path} ({size / 1024:.0f}KB)")

    # Save data
    with open(OUT / "slides.json", "w", encoding="utf-8") as f:
        json.dump(slides, f, ensure_ascii=False, indent=2)

    # Summary
    layouts = {}
    for s in slides:
        lt = s.get("layout_type", "?")
        layouts[lt] = layouts.get(lt, 0) + 1
    total_dur = sum(s.get("duration", 0) for s in slides)

    print(f"\n{'=' * 60}")
    print(f"  Slides: {len(slides)}, Layouts: {layouts}, Duration: {total_dur:.0f}s")
    print(f"  Images: {len(image_paths)}")
    if image_paths:
        print(f"  PPTX: {OUT / 'lingchuang_premium.pptx'}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
