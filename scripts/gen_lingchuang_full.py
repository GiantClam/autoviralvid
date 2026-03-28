"""灵创智能完整 PPT 生成 — 12页 (含封面封底)"""

import json, os, sys, subprocess, shutil
from pathlib import Path

BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUT = Path("test_outputs/lingchuang_full")
NPX = shutil.which("npx") or "npx"

REQUIREMENT = """灵创智能企业介绍PPT，12页，详细内容如下：

【封面】灵创智能企业推介 — 精准智造，赋能工业新未来

【第一部分：走进灵创智能】
幻灯片1 企业简介：
- 公司定位：致力于高端智能数控机床的研发、生产与销售
- 发展历程：2015年成立，2018年获评高新技术企业，2020年获评专精特新企业
- 荣誉资质：ISO9001认证，累计获得68项国家专利

幻灯片2 核心研发与生产实力：
- 工厂规模：50,000平方米现代化智能工厂
- 年产能：高端数控机床2,000台
- 研发团队：150名工程师，其中博士12人，硕士45人
- 核心技术：自研灵创数控系统(LC-OS)，高精度主轴技术，直线度误差<0.003mm/m

【第二部分：匠心智造】
幻灯片3 核心产品矩阵：
- 高精度数控车床/铣床：加工精度达0.005mm，适用于基础零部件加工
- 高端五轴联动加工中心：复杂曲面加工能力，适用于航空航天、医疗器械
- 数控专用机床与复合机床：车铣复合等高效加工设备，效率提升40%

幻灯片4 产品核心技术优势：
- "精"：微米级加工精度0.005mm，高刚性铸铁床身，热变形补偿系统
- "智"：搭载自研LC-OS数控系统，支持IoT接入，实时设备状态监控与故障预警
- "效"：高压冷却排屑系统，自动上下料接口，支持24小时无人值守

幻灯片5 行业应用案例：
- 新能源汽车：压铸件加工，精度控制在0.01mm以内，年交付200台
- 3C电子：手机中框精密加工，表面粗糙度Ra0.4
- 航空航天：钛合金复杂曲面零件加工，通过AS9100认证
- 模具制造：高精度模具加工，寿命提升30%

【第三部分：蓝海启航】
幻灯片6 宏观市场机遇：
- 全球数控机床市场规模突破1,000亿美元，年增长率12%
- 中国市场占全球30%，规模约300亿美元
- 国产高端数控化率不足10%，进口替代空间巨大

幻灯片7 驱动增长的核心动能：
- 下游产业升级：新能源汽车轻量化需求年增长25%，5G通讯精密加工需求爆发
- 政策红利：国家智能制造2025、设备更新换代补贴政策
- 灵创市场占位：高端数控车床细分市场占有率5%，目标3年内提升至15%

【第四部分：携手共赢】
幻灯片8 灵活的商业合作模式：
- 区域代理：完善渠道保护，利润空间30-50%，提供市场支持
- 大客户直采：批量采购优惠15%，驻厂售后团队
- 设备融资租赁：首付低至20%，月供灵活，降低资金门槛

幻灯片9 深度技术与生态合作：
- OEM/ODM定制研发：根据客户工艺需求，提供非标机床定制
- 产学研联合：与清华大学、上海交通大学共建实验室
- 交钥匙工程：设备选型→工艺规划→夹具设计→打样生产全套服务

【第五部分：未来展望】
幻灯片10 企业愿景：
- 短期目标(2026-2028)：年营收突破10亿元，进入行业前十
- 长期愿景：成为全球领先的智能数控机床解决方案提供商
- 承诺：做最懂客户的数控机床合作伙伴

幻灯片11 联系方式：
- 公司：灵创智能科技有限公司
- 地址：中国广东省深圳市南山区科技园
- 电话：400-888-XXXX
- 官网：www.lingchuang-cnc.com
- 结语：感谢聆听，期待合作！"""


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
    print("  灵创智能完整 PPT 生成")
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
    for i, s in enumerate(slides):
        lt = s.get("layout_type", "?")
        title = s.get("content", {}).get("title", "")[:30]
        items = s.get("content", {}).get("body_items", [])
        comp = s.get("content", {}).get("comparison")
        emphasis = s.get("content", {}).get("emphasis_words", [])
        print(f"  {i + 1:2d}. [{lt:16s}] {title}")
        if comp:
            lt_l = comp["left_title"].replace("\u274c", "[X]").replace("\u2705", "[V]")
            lt_r = comp["right_title"].replace("\u274c", "[X]").replace("\u2705", "[V]")
            print(f"      LEFT: {lt_l} ({len(comp['left_items'])} items)")
            print(f"      RIGHT: {lt_r} ({len(comp['right_items'])} items)")
        else:
            for item in items[:3]:
                safe_item = (
                    item.replace("\u274c", "[X]")
                    .replace("\u2705", "[V]")
                    .replace("\u2713", "[v]")
                )
                print(f"      - {safe_item[:50]}")
        if emphasis:
            print(f"      emphasis: {emphasis}")

    # Step 2: TTS
    print("\n[Step 2] TTS synthesis...")
    tts = call_api("POST", "/api/v1/premium/tts", {"slides": slides})
    if tts.get("success"):
        slides = tts["data"]["slides"]
        total_dur = sum(s.get("duration", 0) for s in slides)
        audio_count = sum(
            1 for s in slides for l in s.get("script", []) if l.get("audio_url")
        )
        total_lines = sum(len(s.get("script", [])) for s in slides)
        print(f"  OK: {audio_count}/{total_lines} audio tracks, {total_dur:.0f}s total")

    # Step 3: PPTX
    print("\n[Step 3] Exporting PPTX...")
    export = call_api(
        "POST",
        "/api/v1/ppt-v3/export",
        {
            "slides": slides,
            "title": "灵创智能：引领数控加工新未来",
            "author": "灵创智能科技有限公司",
        },
    )
    pptx_url = ""
    if export.get("success"):
        pptx_url = export["data"]["url"]
        print(f"  OK: {pptx_url}")
    else:
        print(f"  FAIL: {export.get('error', '')[:200]}")

    # Save
    with open(OUT / "slides.json", "w", encoding="utf-8") as f:
        json.dump(slides, f, ensure_ascii=False, indent=2)

    # Download PPTX
    if pptx_url:
        print("\n[Step 4] Downloading PPTX...")
        subprocess.run(
            f'curl -sL "{pptx_url}" -o "{OUT / "lingchuang_ppt.pptx"}"',
            shell=True,
            timeout=30,
        )
        size = (
            (OUT / "lingchuang_ppt.pptx").stat().st_size
            if (OUT / "lingchuang_ppt.pptx").exists()
            else 0
        )
        print(f"  OK: lingchuang_ppt.pptx ({size / 1024:.0f}KB)")

    # Summary
    total_dur = sum(s.get("duration", 0) for s in slides)
    total_actions = sum(
        1 for s in slides for l in s.get("script", []) if l.get("action") != "none"
    )
    layouts = {}
    for s in slides:
        lt = s.get("layout_type", "?")
        layouts[lt] = layouts.get(lt, 0) + 1

    print(f"\n{'=' * 60}")
    print(f"  Summary")
    print(f"{'=' * 60}")
    print(f"  Slides: {len(slides)}")
    print(f"  Layouts: {layouts}")
    print(f"  Duration: {total_dur:.0f}s ({total_dur / 60:.1f}min)")
    print(f"  Actions: {total_actions}")
    if pptx_url:
        print(f"  PPTX: {pptx_url}")
    print(f"  Files: {OUT}/")


if __name__ == "__main__":
    main()
