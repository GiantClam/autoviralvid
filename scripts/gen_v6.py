"""灵创智能 PPT + 视频 v6 — 7种模板+充实内容+多样化script+转场"""
import subprocess, json, os, glob, sys, tempfile, re

sys.path.insert(0, 'agent')
from src.screenshot_engine import render_slides_to_images

BASE = 'http://127.0.0.1:8124'
OUT = 'test_outputs/lingchuang_v6'

def call_api(path, body):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(body, f, ensure_ascii=False)
        rf = f.name
    r = subprocess.run(f'curl -s -X POST {BASE}{path} -H "Content-Type: application/json" -d @{rf}', shell=True, capture_output=True, timeout=600)
    os.unlink(rf)
    raw = r.stdout.decode('utf-8', errors='replace').replace('\ufffd', '')
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
    return json.loads(raw)

def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(f'{OUT}/audio', exist_ok=True)
    os.makedirs(f'{OUT}/clips', exist_ok=True)

    # Step 1: Content
    print('[Step 1] Content...')
    d = call_api('/api/v1/premium/generate', {
        'requirement': '灵创智能企业介绍PPT：封面、企业简介(2015年50000平方米200人68专利)、核心产品(车床0.005mm五轴加工中心车铣复合效率提升40%)、技术优势(精智效)、行业应用(新能源3C航空航天)、市场机遇(1000亿国产10%)、增长动能(新能源25%增长5G智能制造)、合作模式(代理利润30%直采优惠15%融资租赁首付20%)、客户案例(精度提升10倍月省8000)、企业愿景(10亿营收)、联系方式',
        'num_slides': 11, 'language': 'zh-CN',
    })
    slides = d['data']
    layouts = {}
    for s in slides:
        lt = s.get('layout_type','?')
        layouts[lt] = layouts.get(lt, 0) + 1
    print(f'  {len(slides)} slides: {layouts}')
    for i, s in enumerate(slides):
        lt = s.get('layout_type','?')
        title = s.get('content',{}).get('title','')[:25]
        items = s.get('content',{}).get('body_items',[])
        script_text = s.get('script',[{}])[0].get('text','')[:50] if s.get('script') else ''
        print(f'  {i+1:2d}. [{lt:16s}] {title} items={len(items)}')

    # Step 2: TTS
    print('[Step 2] TTS...')
    d = call_api('/api/v1/premium/tts', {'slides': slides})
    slides = d['data']['slides']
    total_dur = sum(s.get('duration', 0) for s in slides)
    print(f'  {total_dur:.0f}s')

    with open(f'{OUT}/slides.json', 'w', encoding='utf-8') as f:
        json.dump(slides, f, ensure_ascii=False, indent=2)

    # Step 3: Screenshots
    print('[Step 3] Screenshots...')
    images = render_slides_to_images(slides, f'{OUT}/slides')
    print(f'  {len(images)} screenshots')

    # Step 4: Audio
    print('[Step 4] Audio...')
    audio_files = []
    for i, s in enumerate(slides):
        script = s.get('script', [])
        urls = [l.get('audio_url','') for l in script if isinstance(l, dict) and l.get('audio_url')]
        path = f'test_outputs/lingchuang_premium_v2/audio/audio_{i:02d}.mp3'
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if urls:
            subprocess.run(f'curl -sL "{urls[0]}" -o "{path}"', shell=True, capture_output=True, timeout=30)
        audio_files.append(path if os.path.exists(path) and os.path.getsize(path) > 100 else '')

    # Get durations
    durations = []
    for af in audio_files:
        if af:
            r = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', af],
                               capture_output=True, text=True, timeout=10)
            dur = float(r.stdout.strip()) + 1 if r.returncode == 0 else 10
        else:
            dur = 10
        durations.append(dur)

    # Build concat files
    images = sorted(glob.glob(f'test_outputs/lingchuang_premium_v2/slides/slide_*.png'))
    concat_file = f'test_outputs/lingchuang_premium_v2/concat.txt'
    with open(concat_file, 'w') as f:
        for i, dur in enumerate(durations):
            if i < len(images):
                f.write(f"file '{os.path.abspath(images[i])}'\n")
                f.write(f"duration {dur:.2f}\n")
        if images:
            f.write(f"file '{os.path.abspath(images[-1])}'\n")

    # Merge audio
    audio_concat = f'test_outputs/lingchuang_premium_v2/audio_concat.txt'
    with open(audio_concat, 'w') as f:
        for af in audio_files:
            if af:
                f.write(f"file '{os.path.abspath(af)}'\n")
    audio_merged = f'test_outputs/lingchuang_premium_v2/audio_merged.mp3'
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', audio_concat, '-c', 'copy', audio_merged],
                   capture_output=True, text=True, timeout=120)

    # Render video
    output = f'test_outputs/lingchuang_premium_v2/lingchuang_video.mp4'
    cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file,
           '-i', audio_merged, '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '23', '-c:a', 'aac', '-b:a', '128k',
           '-shortest', '-pix_fmt', 'yuv420p', output]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode == 0 and os.path.exists(output):
        size = os.path.getsize(output)
        print(f'OK: {output} ({size/1024/1024:.1f}MB)')
    else:
        print(f'FAIL: {r.stderr[:300]}')

if __name__ == '__main__':
    main()
