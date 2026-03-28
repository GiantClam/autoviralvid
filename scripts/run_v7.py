"""灵创智能 V7 — Skill架构+并发工作流+Marp双路输出+Ken Burns动效"""

import subprocess, json, os, glob, sys, tempfile, re

sys.path.insert(0, "agent")
from src.screenshot_engine import render_slides_to_images

BASE = "http://127.0.0.1:8124"
OUT = "test_outputs/lingchuang_v7"
os.makedirs(OUT, exist_ok=True)


def call_api(path, body):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(body, f, ensure_ascii=False)
        rf = f.name
    r = subprocess.run(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            f"{BASE}{path}",
            "-H",
            "Content-Type: application/json",
            "-d",
            f"@{rf}",
        ],
        capture_output=True,
        timeout=600,
    )
    os.unlink(rf)
    raw = r.stdout.decode("utf-8", errors="replace").replace("\ufffd", "")
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    return json.loads(raw)


# Step 1: Content (V7 concurrent workflow)
print("[1] Content (V7 concurrent workflow)...")
d = call_api(
    "/api/v1/v7/generate",
    {
        "requirement": "灵创智能企业介绍：封面、企业简介(2015年成立50000平方米工厂200人团队68项专利高新技术企业)、核心产品(高精度车床0.005mm五轴加工中心航空航天车铣复合效率提升40%)、技术优势(精微米级精度智IoT监控效自动上下料24小时无人值守)、行业应用(新能源汽车压铸件精度0.01mm3C电子Ra0.4航空航天AS9100钛合金)、市场机遇(全球1000亿美元国产高端化率不足10%新能源需求年增25%)、合作模式(区域代理利润30%大客户直采优惠15%设备融资租赁首付20%)、客户案例(某汽车厂改造精度提升10倍月省电费8000元3个月回本)、企业愿景(年营收突破10亿成为客户最信赖的伙伴)、联系方式(深圳南山科技园400-888-XXXX)",
        "num_slides": 11,
        "language": "zh-CN",
    },
)
slides = d["data"]["slides"]
title = d["data"].get("title", "灵创智能")

layouts = {}
for s in slides:
    lt = s.get("slide_type", s.get("layout_type", "?"))
    layouts[lt] = layouts.get(lt, 0) + 1

print(f"  Title: {title}")
print(f"  {len(slides)} slides: {layouts}")
for i, s in enumerate(slides):
    st = s.get("slide_type", s.get("layout_type", "?"))
    content = s.get("content", {})
    title_s = content.get("title", "")[:30]
    items = content.get("body_items", [])
    comp = content.get("comparison")
    script = s.get("script", [])
    script_text = (
        script[0].get("text", "")[:50] if script and isinstance(script[0], dict) else ""
    )
    print(f"  {i + 1:2d}. [{st:16s}] {title_s} ({len(items)} items)")

# Save markdown if available
md_content = d["data"].get("markdown", "")
if md_content:
    with open(f"{OUT}/presentation.md", "w", encoding="utf-8") as f:
        f.write(md_content)

# Step 2: TTS
print("\n[2] TTS...")
d = call_api("/api/v1/v7/tts", {"slides": slides})
slides = d["data"]["slides"]
total_dur = sum(s.get("duration", 0) for s in slides)
print(f"  {total_dur:.0f}s")

with open(f"{OUT}/slides.json", "w", encoding="utf-8") as f:
    json.dump(slides, f, ensure_ascii=False, indent=2)

# Step 3: Screenshots
print("[3] Screenshots...")
images = render_slides_to_images(slides, f"{OUT}/slides")
print(f"  {len(images)}")

# Step 4: Audio
print("[4] Audio...")
os.makedirs(f"{OUT}/audio", exist_ok=True)
for i, s in enumerate(slides):
    url = s.get("narration_audio_url", "")
    if url:
        subprocess.run(
            ["curl", "-sL", url, "-o", f"{OUT}/audio/a_{i:02d}.mp3"],
            capture_output=True,
            timeout=30,
        )

# Step 5: Video
print("[5] Video...")
audio_files = sorted(glob.glob(f"{OUT}/audio/a_*.mp3"))
durations = []
for af in audio_files:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            af,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    durations.append(float(r.stdout.strip()) + 1 if r.returncode == 0 else 10)

images = sorted(glob.glob(f"{OUT}/slides/slide_*.png"))

with open(f"{OUT}/concat.txt", "w") as f:
    for i, dur in enumerate(durations):
        if i < len(images):
            f.write(f"file '{os.path.abspath(images[i])}'\n")
            f.write(f"duration {dur:.2f}\n")
    if images:
        f.write(f"file '{os.path.abspath(images[-1])}'\n")

with open(f"{OUT}/audio_concat.txt", "w") as f:
    for af in audio_files:
        f.write(f"file '{os.path.abspath(af)}'\n")
subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        f"{OUT}/audio_concat.txt",
        "-c",
        "copy",
        f"{OUT}/audio.mp3",
    ],
    capture_output=True,
    timeout=120,
)

output = f"{OUT}/video.mp4"
cmd = [
    "ffmpeg",
    "-y",
    "-f",
    "concat",
    "-safe",
    "0",
    "-i",
    f"{OUT}/concat.txt",
    "-i",
    f"{OUT}/audio.mp3",
    "-vf",
    "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "23",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    "-shortest",
    "-pix_fmt",
    "yuv420p",
    output,
]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
if r.returncode == 0 and os.path.exists(output):
    size = os.path.getsize(output)
    print(f"\nOK: {output} ({size / 1024 / 1024:.1f}MB)")
    print(f"  Layouts: {layouts}")
else:
    print(f"FAIL: {r.stderr[:300]}")
