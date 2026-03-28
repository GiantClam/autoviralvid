"""灵创智能 PPT + 视频 v6 — 7种模板+充实内容+多样化script"""

import subprocess, json, os, glob, sys, tempfile, re

sys.path.insert(0, "agent")
from src.screenshot_engine import render_slides_to_images

BASE = "http://127.0.0.1:8124"
OUT = "test_outputs/lingchuang_v6"
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


# Step 1
print("[1] Content...")
d = call_api(
    "/api/v1/premium/generate",
    {
        "requirement": "灵创智能企业介绍：封面、企业简介(2015年成立50000平方米工厂200人团队68项专利高新技术企业)、核心产品(高精度车床0.005mm五轴加工中心航空航天车铣复合效率提升40%)、技术优势(精微米级智IoT监控效自动上下料)、行业应用(新能源汽车压铸件3C电子航空航天钛合金)、市场机遇(全球1000亿美元国产高端化率不足10%)、合作模式(区域代理利润30%大客户直采优惠15%设备融资租赁首付20%)、客户案例(某汽车厂改造精度提升10倍月省电费8000元3个月回本)、企业愿景(年营收突破10亿)、联系方式(深圳南山科技园400-888-XXXX)",
        "num_slides": 11,
        "language": "zh-CN",
    },
)
slides = d["data"]
layouts = {}
for s in slides:
    lt = s.get("layout_type", "?")
    layouts[lt] = layouts.get(lt, 0) + 1
print(f"  {len(slides)} slides: {layouts}")
for i, s in enumerate(slides):
    lt = s.get("layout_type", "?")
    title = s.get("content", {}).get("title", "")[:25]
    items = s.get("content", {}).get("body_items", [])
    script = s.get("script", [])
    st = (
        script[0].get("text", "")[:40] if script and isinstance(script[0], dict) else ""
    )
    print(f"  {i + 1:2d}. [{lt:16s}] {title} ({len(items)} items)")

# Step 2
print("[2] TTS...")
d = call_api("/api/v1/premium/tts", {"slides": slides})
slides = d["data"]["slides"]
total_dur = sum(s.get("duration", 0) for s in slides)
print(f"  {total_dur:.0f}s")

with open(f"{OUT}/slides.json", "w", encoding="utf-8") as f:
    json.dump(slides, f, ensure_ascii=False, indent=2)

# Step 3
print("[3] Screenshots...")
images = render_slides_to_images(slides, f"{OUT}/slides")
print(f"  {len(images)}")

# Step 4
print("[4] Audio...")
os.makedirs(f"{OUT}/audio", exist_ok=True)
for i, s in enumerate(slides):
    script = s.get("script", [])
    urls = [
        l.get("audio_url", "")
        for l in script
        if isinstance(l, dict) and l.get("audio_url")
    ]
    if urls:
        subprocess.run(
            ["curl", "-sL", urls[0], "-o", f"{OUT}/audio/a_{i:02d}.mp3"],
            capture_output=True,
            timeout=30,
        )

# Step 5
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

# concat
with open(f"{OUT}/concat.txt", "w") as f:
    for i, dur in enumerate(durations):
        if i < len(images):
            f.write(f"file '{os.path.abspath(images[i])}'\n")
            f.write(f"duration {dur:.2f}\n")
    if images:
        f.write(f"file '{os.path.abspath(images[-1])}'\n")

# audio merge
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

# render
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
