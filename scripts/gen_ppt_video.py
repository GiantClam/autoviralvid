"""灵创智能 PPT + 视频 — 完整管线 (7种模板+转场+音频)"""

import subprocess, json, os, glob, sys, tempfile

sys.path.insert(0, "agent")
from src.screenshot_engine import render_slides_to_images

BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUT = "test_outputs/lingchuang_v5"


def call_api(path, body):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(body, f, ensure_ascii=False)
        rf = f.name
    r = subprocess.run(
        f'curl -s -X POST {BASE}{path} -H "Content-Type: application/json" -d @{rf}',
        shell=True,
        capture_output=True,
        timeout=600,
    )
    os.unlink(rf)
    raw = r.stdout.decode("utf-8", errors="replace").replace("\ufffd", "")
    try:
        return json.loads(raw)
    except:
        import re

        raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
        return json.loads(raw)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(f"{OUT}/audio", exist_ok=True)
    os.makedirs(f"{OUT}/slides", exist_ok=True)

    # Step 1: Content
    print("[Step 1] Generating content...")
    d = call_api(
        "/api/v1/premium/generate",
        {
            "requirement": "灵创智能企业介绍PPT：封面、企业简介(2015年50000平方米200人68专利)、核心产品(车床0.005mm五轴加工中心车铣复合效率提升40%)、技术优势(精智效三大优势)、行业应用(新能源汽车压铸件3C电子航空航天)、市场机遇(全球1000亿美元国产高端化率不足10%)、增长动能(新能源年增25% 5G通讯智能制造)、合作模式(区域代理利润30%直采优惠15%融资租赁首付20%)、客户案例(某汽车厂精度提升10倍月省8000元)、企业愿景(年营收突破10亿)、联系方式(深圳南山科技园400-888-XXXX www.lingchuang-cnc.com)",
            "num_slides": 11,
            "language": "zh-CN",
        },
    )
    if not d.get("success"):
        print(f"FAIL: {d.get('error', '')[:300]}")
        return

    slides = d["data"]
    layouts = {}
    for s in slides:
        lt = s.get("layout_type", "?")
        layouts[lt] = layouts.get(lt, 0) + 1

    print(f"  {len(slides)} slides, layouts: {layouts}")
    for i, s in enumerate(slides):
        lt = s.get("layout_type", "?")
        title = s.get("content", {}).get("title", "")[:30]
        items = s.get("content", {}).get("body_items", [])
        comp = s.get("content", {}).get("comparison")
        script = s.get("script", [])
        script_text = (
            script[0].get("text", "")[:50]
            if script and isinstance(script[0], dict)
            else ""
        )
        print(
            f"  {i + 1:2d}. [{lt:16s}] {title} | {len(items)} items | script: {script_text}"
        )

    # Step 2: TTS
    print("\n[Step 2] TTS...")
    d = call_api("/api/v1/premium/tts", {"slides": slides})
    slides = d["data"]["slides"]
    total_dur = sum(s.get("duration", 0) for s in slides)
    print(f"  {total_dur:.0f}s total")

    with open(f"{OUT}/slides.json", "w", encoding="utf-8") as f:
        json.dump(slides, f, ensure_ascii=False, indent=2)

    # Step 3: Screenshots
    print("[Step 3] Screenshots...")
    images = render_slides_to_images(slides, f"{OUT}/slides")
    print(f"  {len(images)} screenshots")

    # Step 4: Audio download
    print("[Step 4] Audio...")
    for i, s in enumerate(slides):
        script = s.get("script", [])
        urls = [
            l.get("audio_url", "")
            for l in script
            if isinstance(l, dict) and l.get("audio_url")
        ]
        if urls:
            path = f"{OUT}/audio/audio_{i:02d}.mp3"
            subprocess.run(
                f'curl -sL "{urls[0]}" -o "{path}"',
                shell=True,
                capture_output=True,
                timeout=30,
            )

    # Step 5: Video with xfade transitions
    print("[Step 5] Video with transitions...")
    audio_files = sorted(glob.glob(f"{OUT}/audio/audio_*.mp3"))
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
        dur = float(r.stdout.strip()) + 0.5 if r.returncode == 0 else 10
        durations.append(dur)

    # Method: concat with xfade transitions
    # First create individual video clips for each slide
    clip_dir = f"{OUT}/clips"
    os.makedirs(clip_dir, exist_ok=True)
    clips = []

    for i, (img, dur) in enumerate(zip(images, durations)):
        clip_path = f"{clip_dir}/clip_{i:02d}.mp4"
        audio_path = audio_files[i] if i < len(audio_files) else None

        if audio_path and os.path.exists(audio_path):
            cmd = [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                img,
                "-i",
                audio_path,
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-pix_fmt",
                "yuv420p",
                "-shortest",
                "-t",
                str(dur),
                clip_path,
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                img,
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-pix_fmt",
                "yuv420p",
                "-t",
                str(dur),
                clip_path,
            ]

        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if os.path.exists(clip_path):
            clips.append(clip_path)

    if not clips:
        print("  FAIL: no clips")
        return

    # Merge clips with xfade transitions
    output = f"{OUT}/lingchuang_video.mp4"
    if len(clips) == 1:
        cmd = ["ffmpeg", "-y", "-i", clips[0], "-c", "copy", output]
    else:
        # Build xfade filter chain
        transition_dur = 0.5  # 0.5s transition
        inputs = []
        filter_parts = []
        for c in clips:
            inputs.extend(["-i", c])

        # Chain xfade filters
        current = "[0:v]"
        current_a = "[0:a]"
        for i in range(1, len(clips)):
            offset = sum(durations[:i]) - transition_dur * i
            v_out = f"[v{i}]"
            a_out = f"[a{i}]"
            filter_parts.append(
                f"[{i}:v][{i}:a][{current}][{current_a}]xfade=transition=fade:duration={transition_dur}:offset={offset:.2f}{v_out}{a_out}"
            )
            current = v_out
            current_a = a_out

        filter_complex = ";".join(filter_parts)
        last_v = f"[v{len(clips) - 1}]"
        last_a = f"[a{len(clips) - 1}]"

        cmd = (
            ["ffmpeg", "-y"]
            + inputs
            + [
                "-filter_complex",
                filter_complex,
                "-map",
                last_v,
                "-map",
                last_a,
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
                "-pix_fmt",
                "yuv420p",
                output,
            ]
        )

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if r.returncode == 0 and os.path.exists(output):
        size = os.path.getsize(output)
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                output,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        dur = float(probe.stdout.strip()) if probe.returncode == 0 else 0
        print(f"\nDone: {output} ({size / 1024 / 1024:.1f}MB, {dur:.0f}s)")
        print(f"  Layouts: {layouts}")
        print(f"  Transitions: {len(clips) - 1} xfade (0.5s)")
        print(f"  Audio: {len(audio_files)} tracks")
    else:
        print(f"FAIL: {r.stderr[:500]}")


if __name__ == "__main__":
    main()
