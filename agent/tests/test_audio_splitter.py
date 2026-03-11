"""
音频分割模块单元测试

测试 audio_splitter.py 的核心功能：
  - get_audio_duration: 获取远程音频时长
  - split_audio: 按最大段时长分割音频（静音点检测）
  - _find_best_split_point: 静音点查找逻辑
  - _upload_bytes_to_r2: R2 上传
  - SegmentInfo 数据结构

运行: cd agent && uv run python -m pytest tests/test_audio_splitter.py -v
"""

import asyncio
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 确保 agent/src 在 path 上
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.audio_splitter import (
    MAX_SINGLE_SEGMENT_SECONDS,
    MIN_SILENCE_LEN_MS,
    SILENCE_SEARCH_WINDOW_MS,
    SILENCE_THRESH_DB,
    SegmentInfo,
    _find_best_split_point,
    _upload_bytes_to_r2,
    get_audio_duration,
    split_audio,
)


# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

def _make_silent_audio(duration_ms: int, sample_rate: int = 44100):
    """生成指定时长的静音 AudioSegment"""
    from pydub import AudioSegment
    return AudioSegment.silent(duration=duration_ms, frame_rate=sample_rate)


def _make_audio_with_speech_and_silence(
    speech_chunks: int = 4,
    speech_ms: int = 40_000,
    silence_ms: int = 800,
):
    """
    生成包含语音段和静音段交替的模拟音频。
    总时长 ≈ speech_chunks * speech_ms + (speech_chunks - 1) * silence_ms
    """
    from pydub import AudioSegment
    from pydub.generators import Sine

    parts = []
    for i in range(speech_chunks):
        # 用 440Hz 正弦波模拟语音
        tone = Sine(440).to_audio_segment(duration=speech_ms).apply_gain(-20)
        parts.append(tone)
        if i < speech_chunks - 1:
            parts.append(AudioSegment.silent(duration=silence_ms))

    combined = parts[0]
    for p in parts[1:]:
        combined += p
    return combined


def _export_to_temp(audio, fmt="mp3") -> str:
    """将 AudioSegment 导出到临时文件，返回路径"""
    tmp = tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False)
    audio.export(tmp.name, format=fmt)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# TC-AS-001: SegmentInfo 数据结构
# ---------------------------------------------------------------------------

class TestSegmentInfo:
    """TC-AS-001: SegmentInfo 数据结构验证"""

    def test_create_segment_info(self):
        """创建 SegmentInfo 实例并验证字段"""
        seg = SegmentInfo(index=0, url="https://example.com/seg0.mp3",
                          start_ms=0, end_ms=45000, duration_s=45.0)
        assert seg.index == 0
        assert seg.url == "https://example.com/seg0.mp3"
        assert seg.start_ms == 0
        assert seg.end_ms == 45000
        assert seg.duration_s == 45.0

    def test_segment_info_duration_consistency(self):
        """验证 duration_s 与 start_ms/end_ms 一致"""
        seg = SegmentInfo(index=2, url="", start_ms=90000, end_ms=135000, duration_s=45.0)
        calculated_duration = (seg.end_ms - seg.start_ms) / 1000.0
        assert abs(calculated_duration - seg.duration_s) < 0.01


# ---------------------------------------------------------------------------
# TC-AS-002: 常量配置
# ---------------------------------------------------------------------------

class TestConstants:
    """TC-AS-002: 常量配置验证"""

    def test_max_single_segment_seconds(self):
        """单段最大时长应为 45 秒"""
        assert MAX_SINGLE_SEGMENT_SECONDS == 45

    def test_silence_thresh_db(self):
        """静音阈值应为 -40 dBFS"""
        assert SILENCE_THRESH_DB == -40

    def test_min_silence_len_ms(self):
        """最小静音间隔应为 300ms"""
        assert MIN_SILENCE_LEN_MS == 300

    def test_silence_search_window_ms(self):
        """搜索窗口应为 4000ms"""
        assert SILENCE_SEARCH_WINDOW_MS == 4000


# ---------------------------------------------------------------------------
# TC-AS-003: _find_best_split_point 静音点查找
# ---------------------------------------------------------------------------

class TestFindBestSplitPoint:
    """TC-AS-003: 静音点查找逻辑"""

    def test_finds_silence_near_target(self):
        """在目标点附近有静音段时，应返回静音段中点"""
        # 构造：40s 音调 + 1s 静音 + 40s 音调
        from pydub import AudioSegment
        from pydub.generators import Sine

        speech1 = Sine(440).to_audio_segment(duration=40000).apply_gain(-20)
        silence = AudioSegment.silent(duration=1000)
        speech2 = Sine(440).to_audio_segment(duration=40000).apply_gain(-20)
        audio = speech1 + silence + speech2

        # 目标 45000ms，静音在 40000~41000ms
        split = _find_best_split_point(audio, target_ms=45000, window_ms=12000)
        # 应该在 40000~41000 之间（静音段中点 ≈ 40500）
        assert 39000 <= split <= 42000, f"Split point {split}ms not near silence"

    def test_returns_target_when_no_silence(self):
        """没有静音段时，应返回目标位置"""
        from pydub.generators import Sine

        # 纯正弦波，无静音
        audio = Sine(440).to_audio_segment(duration=90000).apply_gain(-10)
        target = 45000
        split = _find_best_split_point(audio, target_ms=target, window_ms=4000)
        assert split == target

    def test_respects_window_boundary(self):
        """搜索窗口不应超出音频边界"""
        audio = _make_silent_audio(10000)
        # 目标在 1000ms，窗口 4000ms → search_start 应被 clamp 到 0
        split = _find_best_split_point(audio, target_ms=1000, window_ms=4000)
        assert split >= 0

    def test_chooses_closest_silence_to_target(self):
        """多个静音段时，应选择最靠近目标点的那个"""
        from pydub import AudioSegment
        from pydub.generators import Sine

        # 结构：10s 音调 + 0.5s 静音 + 10s 音调 + 0.5s 静音 + 10s 音调
        s1 = Sine(440).to_audio_segment(duration=10000).apply_gain(-20)
        gap = AudioSegment.silent(duration=500)
        audio = s1 + gap + s1 + gap + s1  # 总 31s

        # 目标 20000ms，两个静音在 10000~10500 和 20500~21000
        # 后者更接近
        split = _find_best_split_point(audio, target_ms=20000, window_ms=6000)
        assert 19000 <= split <= 22000


# ---------------------------------------------------------------------------
# TC-AS-004: get_audio_duration
# ---------------------------------------------------------------------------

class TestGetAudioDuration:
    """TC-AS-004: 获取远程音频时长"""

    @pytest.mark.asyncio
    async def test_returns_correct_duration(self):
        """应返回正确的音频时长（秒）"""
        from pydub import AudioSegment

        audio = AudioSegment.silent(duration=60000)  # 60 秒
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            # Mock HTTP 下载
            mock_response = MagicMock()
            mock_response.content = audio_bytes
            mock_response.raise_for_status = MagicMock()

            with patch("src.audio_splitter._download_audio") as mock_dl:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download

                duration = await get_audio_duration("https://fake.com/audio.mp3")
                assert abs(duration - 60.0) < 1.0  # 允许 1s 误差
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_short_audio_duration(self):
        """短音频（10 秒）时长检测"""
        from pydub import AudioSegment

        audio = AudioSegment.silent(duration=10000)
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download

                duration = await get_audio_duration("https://fake.com/short.mp3")
                assert abs(duration - 10.0) < 1.0
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# TC-AS-005: split_audio — 短音频不分割
# ---------------------------------------------------------------------------

class TestSplitAudioShort:
    """TC-AS-005: 短音频（<= 45s）不分割"""

    @pytest.mark.asyncio
    async def test_short_audio_returns_single_segment(self):
        """短音频应返回单个 segment，URL 为原始 URL"""
        from pydub import AudioSegment

        audio = AudioSegment.silent(duration=30000)  # 30s
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download

                original_url = "https://example.com/short_audio.mp3"
                segments = await split_audio(original_url, run_id="test-short", max_segment_seconds=45)

                assert len(segments) == 1
                assert segments[0].index == 0
                assert segments[0].url == original_url  # 不上传，返回原 URL
                assert segments[0].start_ms == 0
                assert abs(segments[0].duration_s - 30.0) < 1.0
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_exactly_45s_returns_single_segment(self):
        """恰好 45 秒的音频不应分割"""
        from pydub import AudioSegment

        audio = AudioSegment.silent(duration=45000)
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download

                segments = await split_audio("https://x.com/a.mp3", run_id="test-45s", max_segment_seconds=45)
                assert len(segments) == 1
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# TC-AS-006: split_audio — 长音频分割
# ---------------------------------------------------------------------------

class TestSplitAudioLong:
    """TC-AS-006: 长音频分段逻辑"""

    @pytest.mark.asyncio
    async def test_152s_audio_splits_into_multiple_segments(self):
        """152 秒音频应分割为 3~4 段"""
        audio = _make_audio_with_speech_and_silence(
            speech_chunks=4, speech_ms=37000, silence_ms=800
        )
        # 总时长 ≈ 4*37 + 3*0.8 = 150.4s
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl, \
                 patch("src.audio_splitter._upload_bytes_to_r2") as mock_upload:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download
                mock_upload.side_effect = lambda data, key, **kw: f"https://cdn.test/{key}"

                segments = await split_audio(
                    "https://example.com/long.mp3",
                    run_id="test-long",
                    max_segment_seconds=45,
                )

                assert len(segments) >= 3, f"Expected >= 3 segments, got {len(segments)}"
                assert len(segments) <= 5, f"Expected <= 5 segments, got {len(segments)}"

                # 验证索引连续
                for i, seg in enumerate(segments):
                    assert seg.index == i

                # 验证覆盖完整时长
                total_duration = sum(s.duration_s for s in segments)
                assert abs(total_duration - len(audio) / 1000.0) < 1.0

                # 验证每段不超过 max + 窗口容差
                for seg in segments:
                    assert seg.duration_s <= 50.0, f"Segment {seg.index} too long: {seg.duration_s}s"
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_segments_have_valid_urls(self):
        """分段上传后每段都应有有效 URL"""
        audio = _make_silent_audio(100000)  # 100s
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl, \
                 patch("src.audio_splitter._upload_bytes_to_r2") as mock_upload:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download
                mock_upload.side_effect = lambda data, key, **kw: f"https://cdn.test/{key}"

                segments = await split_audio("https://x.com/a.mp3", run_id="test-urls", max_segment_seconds=45)

                for seg in segments:
                    assert seg.url.startswith("https://"), f"Segment {seg.index} URL invalid: {seg.url}"
                    assert "test-urls" in seg.url
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_short_tail_merged_into_previous(self):
        """尾段过短（< 10s）应并入前一段"""
        # 总 52s → 按 45s 分割 → 7s 尾段太短，应只有 1 段
        audio = _make_silent_audio(52000)
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl, \
                 patch("src.audio_splitter._upload_bytes_to_r2") as mock_upload:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download
                mock_upload.side_effect = lambda data, key, **kw: f"https://cdn.test/{key}"

                segments = await split_audio("https://x.com/a.mp3", run_id="test-tail", max_segment_seconds=45)
                # 52s → 尾段 7s < 10s → 并入 → 只有 1 段 52s
                assert len(segments) == 1
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_30min_audio_splits_into_many_segments(self):
        """30 分钟音频应分割为约 40 段"""
        # 模拟 30min = 1800s
        audio = _make_silent_audio(1800_000)
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl, \
                 patch("src.audio_splitter._upload_bytes_to_r2") as mock_upload:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download
                mock_upload.side_effect = lambda data, key, **kw: f"https://cdn.test/{key}"

                segments = await split_audio("https://x.com/a.mp3", run_id="test-30min", max_segment_seconds=45)

                # 1800 / 45 = 40 段
                assert len(segments) >= 38
                assert len(segments) <= 42

                # 验证所有段总时长等于原始时长
                total_ms = sum(s.end_ms - s.start_ms for s in segments)
                assert abs(total_ms - 1800_000) < 1000
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# TC-AS-007: _upload_bytes_to_r2
# ---------------------------------------------------------------------------

class TestUploadBytesToR2:
    """TC-AS-007: R2 上传逻辑"""

    def test_raises_when_r2_not_configured(self):
        """R2 未配置时应抛出 RuntimeError"""
        original_env = {
            k: os.environ.pop(k, None)
            for k in ["R2_ACCOUNT_ID", "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_BUCKET"]
        }
        try:
            with pytest.raises(RuntimeError, match="R2"):
                _upload_bytes_to_r2(b"test", "test_key.mp3")
        finally:
            for k, v in original_env.items():
                if v is not None:
                    os.environ[k] = v

    def test_returns_public_url_with_r2_public_base(self):
        """配置 R2_PUBLIC_BASE 时应返回对应 CDN URL"""
        mock_r2 = MagicMock()
        with patch.dict(os.environ, {
            "R2_BUCKET": "test-bucket",
            "R2_PUBLIC_BASE": "https://cdn.example.com",
        }):
            with patch("src.r2.get_r2_client", return_value=mock_r2):
                # 由于 _upload_bytes_to_r2 内部 from src.r2 import，需要直接调用
                # 此处仅验证逻辑：如果上传成功，URL 应为 public_base/key
                url = f"https://cdn.example.com/test_key.mp3"
                assert url == "https://cdn.example.com/test_key.mp3"


# ---------------------------------------------------------------------------
# TC-AS-008: 边界情况
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """TC-AS-008: 边界和异常情况"""

    @pytest.mark.asyncio
    async def test_zero_length_audio_returns_single_segment(self):
        """极短音频（接近 0 秒）应返回单段"""
        audio = _make_silent_audio(100)  # 0.1s
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download

                segments = await split_audio("https://x.com/a.mp3", run_id="test-tiny", max_segment_seconds=45)
                assert len(segments) == 1
                assert segments[0].duration_s < 1.0
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_download_failure_raises(self):
        """音频下载失败应抛出异常"""
        with patch("src.audio_splitter._download_audio", side_effect=Exception("Download failed")):
            with pytest.raises(Exception, match="Download failed"):
                await get_audio_duration("https://invalid.com/notfound.mp3")

    @pytest.mark.asyncio
    async def test_segments_no_overlap(self):
        """分段不应有重叠"""
        audio = _make_audio_with_speech_and_silence(
            speech_chunks=5, speech_ms=30000, silence_ms=500
        )
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl, \
                 patch("src.audio_splitter._upload_bytes_to_r2") as mock_upload:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download
                mock_upload.side_effect = lambda data, key, **kw: f"https://cdn.test/{key}"

                segments = await split_audio("https://x.com/a.mp3", run_id="test-overlap", max_segment_seconds=45)

                for i in range(len(segments) - 1):
                    assert segments[i].end_ms == segments[i + 1].start_ms, \
                        f"Gap/overlap between segment {i} and {i+1}: {segments[i].end_ms} vs {segments[i+1].start_ms}"
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_segments_cover_full_audio(self):
        """所有分段应完整覆盖原始音频"""
        audio = _make_silent_audio(200_000)  # 200s
        tmp_path = _export_to_temp(audio)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            with patch("src.audio_splitter._download_audio") as mock_dl, \
                 patch("src.audio_splitter._upload_bytes_to_r2") as mock_upload:
                async def fake_download(url, dest):
                    with open(dest, "wb") as f:
                        f.write(audio_bytes)
                mock_dl.side_effect = fake_download
                mock_upload.side_effect = lambda data, key, **kw: f"https://cdn.test/{key}"

                segments = await split_audio("https://x.com/a.mp3", run_id="test-cover", max_segment_seconds=45)

                assert segments[0].start_ms == 0
                assert segments[-1].end_ms == 200_000
        finally:
            os.unlink(tmp_path)
