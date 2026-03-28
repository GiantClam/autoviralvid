"""灵创智能 v3 E2E — 多角色剧本 + 动作引擎 + 母版渲染"""

import json, os, sys, subprocess
from pathlib import Path

BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUT = Path("test_outputs/lingchuang_v3")

OUTLINE = {
    "id": "lc-v3",
    "title": "灵创智能：引领数控加工新未来",
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
            "key_points": [
                "高端智能数控机床研发生产销售",
                "高新技术企业专精特新",
                "核心团队20年行业经验",
            ],
            "suggested_layout": "bullet_points",
            "estimated_duration": 120,
        },
        {
            "id": "s3",
            "order": 3,
            "title": "核心研发与生产实力",
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
                "高精度数控车床微米级精度",
                "五轴联动加工中心复杂曲面",
                "车铣复合机床效率提升40%",
            ],
            "suggested_layout": "bullet_points",
            "estimated_duration": 120,
        },
        {
            "id": "s5",
            "order": 5,
            "title": "产品核心技术优势",
            "description": "精智效三大优势",
            "key_points": [
                "精：微米级加工精度高刚性",
                "智：IoT智能监控故障预警",
                "效：高效排屑冷却自动化",
            ],
            "suggested_layout": "quote",
            "estimated_duration": 120,
        },
        {
            "id": "s6",
            "order": 6,
            "title": "行业应用案例",
            "description": "四大行业应用",
            "key_points": [
                "新能源汽车压铸件加工",
                "3C电子精密加工",
                "航空航天复杂曲面",
                "模具制造高精度",
            ],
            "suggested_layout": "comparison",
            "estimated_duration": 120,
        },
        {
            "id": "s7",
            "order": 7,
            "title": "宏观市场机遇",
            "description": "千亿级市场",
            "key_points": [
                "全球机床市场1000亿美元",
                "国产高端化率不足10%",
                "政策支持智能制造升级",
            ],
            "suggested_layout": "big_number",
            "estimated_duration": 120,
        },
        {
            "id": "s8",
            "order": 8,
            "title": "驱动增长的核心动能",
            "description": "三大驱动因素",
            "key_points": [
                "新能源汽车需求爆发式增长",
                "5G通讯精密加工需求",
                "智能制造政策红利释放",
            ],
            "suggested_layout": "bullet_points",
            "estimated_duration": 120,
        },
        {
            "id": "s9",
            "order": 9,
            "title": "灵活的商业合作模式",
            "description": "三种合作方式",
            "key_points": [
                "区域代理与经销渠道",
                "大客户直采集采模式",
                "设备融资租赁方案",
            ],
            "suggested_layout": "bullet_points",
            "estimated_duration": 120,
        },
        {
            "id": "s10",
            "order": 10,
            "title": "深度技术与生态合作",
            "description": "生态合作",
            "key_points": ["OEM/ODM定制研发", "产学研联合创新", "交钥匙工程全套方案"],
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
            "key_points": ["灵创智能", "400-XXX-XXXX", "www.lingchuang.com"],
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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("  灵创智能 v3 — 多角色剧本 + 动作引擎 + 母版渲染")
    print("=" * 60)

    # Step 1: 生成内容 (多角色剧本)
    print(f"\n[Step 1] Generating v3 content (multi-role script)...")
    r = call_api(
        "POST", "/api/v1/ppt-v3/content", {"outline": OUTLINE, "language": "zh-CN"}
    )
    if not r.get("success"):
        print(f"  FAIL: {r.get('error', '')[:300]}")
        return

    slides = r["data"]
    print(f"  OK: {len(slides)} slides")

    # 统计
    for i, s in enumerate(slides):
        layout = s.get("layout_type", "?")
        script = s.get("script", [])
        roles = set(l.get("role", "?") for l in script)
        actions = [l.get("action") for l in script if l.get("action") != "none"]
        print(
            f"  {i + 1}. [{layout:16s}] roles={roles} actions={actions} lines={len(script)}"
        )

    # Step 2: TTS (多角色)
    print(f"\n[Step 2] Multi-role TTS...")
    tts_r = call_api(
        "POST",
        "/api/v1/ppt-v3/tts",
        {
            "slides": slides,
            "host_voice": "zh-CN-male",
            "student_voice": "zh-CN-female",
        },
    )
    if tts_r.get("success"):
        slides = tts_r["data"]["slides"]
        for i, s in enumerate(slides):
            dur = s.get("duration", 0)
            lines = s.get("script", [])
            audio_count = sum(1 for l in lines if l.get("audio_url"))
            print(
                f"  Slide {i + 1}: {dur:.0f}s, {audio_count}/{len(lines)} lines with audio"
            )
    else:
        print(f"  TTS FAIL: {tts_r.get('error', '')[:200]}")

    # Step 3: PPTX 母版渲染
    print(f"\n[Step 3] PPTX template rendering...")
    export = call_api(
        "POST",
        "/api/v1/ppt-v3/export",
        {
            "slides": slides,
            "title": OUTLINE["title"],
            "author": "灵创智能",
        },
    )
    if export.get("success"):
        print(f"  OK: {export['data']['url'][:80]}...")
    else:
        print(f"  FAIL: {export.get('error', '')[:200]}")

    # Save
    with open(OUT / "slides_v3.json", "w", encoding="utf-8") as f:
        json.dump(slides, f, ensure_ascii=False, indent=2)

    # Summary
    total_dur = sum(s.get("duration", 0) for s in slides)
    total_lines = sum(len(s.get("script", [])) for s in slides)
    total_actions = sum(
        1 for s in slides for l in s.get("script", []) if l.get("action") != "none"
    )
    total_audio = sum(
        1 for s in slides for l in s.get("script", []) if l.get("audio_url")
    )

    print(f"\n{'=' * 60}")
    print(f"  Summary")
    print(f"{'=' * 60}")
    print(f"  Slides: {len(slides)}")
    print(f"  Total dialogue lines: {total_lines}")
    print(f"  Visual actions: {total_actions}")
    print(f"  Audio tracks: {total_audio}")
    print(f"  Total duration: {total_dur:.0f}s ({total_dur / 60:.1f}min)")


if __name__ == "__main__":
    main()
