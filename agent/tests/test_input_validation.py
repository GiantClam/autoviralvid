"""
测试用例: P0 — 输入校验加固 (Pydantic model validation)

覆盖范围:
- CreateProjectRequest 字段长度限制
- URL 格式校验（http/https only）
- duration 范围校验
- BatchCreateRequest 数组长度限制
- AIAssistantRequest message 限制
"""

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# CreateProjectRequest
# ---------------------------------------------------------------------------

class TestCreateProjectRequest:
    """测试 CreateProjectRequest 验证规则."""

    def _model(self):
        from src.api_routes import CreateProjectRequest
        return CreateProjectRequest

    def test_valid_minimal(self):
        """TC-VAL-01: 最小有效请求 — 只需 theme."""
        M = self._model()
        req = M(theme="测试主题")
        assert req.theme == "测试主题"
        assert req.duration == 30
        assert req.template_id == "product-ad"

    def test_theme_required(self):
        """TC-VAL-02: theme 字段必填."""
        M = self._model()
        with pytest.raises(ValidationError):
            M()

    def test_theme_empty_string_rejected(self):
        """TC-VAL-03: theme 空字符串应被拒绝 (min_length=1)."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="")

    def test_theme_too_long_rejected(self):
        """TC-VAL-04: theme 超过 500 字符应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="x" * 501)

    def test_template_id_max_length(self):
        """TC-VAL-05: template_id 超过 64 字符应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="ok", template_id="a" * 65)

    def test_duration_min(self):
        """TC-VAL-06: duration < 5 应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="ok", duration=3)

    def test_duration_max(self):
        """TC-VAL-07: duration > 3600 应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="ok", duration=7200)

    def test_duration_valid_range(self):
        """TC-VAL-08: duration 在 5-3600 范围内应通过."""
        M = self._model()
        assert M(theme="ok", duration=5).duration == 5
        assert M(theme="ok", duration=3600).duration == 3600

    def test_voice_mode_range(self):
        """TC-VAL-09: voice_mode 只接受 0 或 1."""
        M = self._model()
        assert M(theme="ok", voice_mode=0).voice_mode == 0
        assert M(theme="ok", voice_mode=1).voice_mode == 1
        with pytest.raises(ValidationError):
            M(theme="ok", voice_mode=2)
        with pytest.raises(ValidationError):
            M(theme="ok", voice_mode=-1)


# ---------------------------------------------------------------------------
# URL 校验
# ---------------------------------------------------------------------------

class TestURLValidation:
    """测试 URL 格式校验."""

    def _model(self):
        from src.api_routes import CreateProjectRequest
        return CreateProjectRequest

    def test_valid_https_url(self):
        """TC-VAL-10: https URL 应通过."""
        M = self._model()
        req = M(theme="ok", product_image_url="https://example.com/img.png")
        assert req.product_image_url == "https://example.com/img.png"

    def test_valid_http_url(self):
        """TC-VAL-11: http URL 应通过."""
        M = self._model()
        req = M(theme="ok", audio_url="http://cdn.example.com/audio.mp3")
        assert req.audio_url == "http://cdn.example.com/audio.mp3"

    def test_javascript_url_rejected(self):
        """TC-VAL-12: javascript: URL 应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="ok", product_image_url="javascript:alert(1)")

    def test_data_url_rejected(self):
        """TC-VAL-13: data: URL 应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="ok", product_image_url="data:image/png;base64,abc")

    def test_file_url_rejected(self):
        """TC-VAL-14: file:// URL 应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="ok", audio_url="file:///etc/passwd")

    def test_url_too_long_rejected(self):
        """TC-VAL-15: URL 超过 2048 字符应被拒绝."""
        M = self._model()
        long_url = "https://example.com/" + "a" * 2040
        with pytest.raises(ValidationError):
            M(theme="ok", product_image_url=long_url)

    def test_none_url_allowed(self):
        """TC-VAL-16: URL 为 None 应通过（可选字段）."""
        M = self._model()
        req = M(theme="ok", product_image_url=None, audio_url=None)
        assert req.product_image_url is None
        assert req.audio_url is None


# ---------------------------------------------------------------------------
# BatchCreateRequest
# ---------------------------------------------------------------------------

class TestBatchCreateRequest:
    """测试 BatchCreateRequest 验证规则."""

    def _model(self):
        from src.api_routes import BatchCreateRequest
        return BatchCreateRequest

    def test_valid_batch(self):
        """TC-VAL-17: 有效的批量请求."""
        M = self._model()
        req = M(
            theme="批量测试",
            product_images=["https://img1.com/a.png", "https://img2.com/b.png"],
        )
        assert len(req.product_images) == 2

    def test_empty_images_rejected(self):
        """TC-VAL-18: 空图片列表应被拒绝 (min_length=1)."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="ok", product_images=[])

    def test_too_many_images_rejected(self):
        """TC-VAL-19: 超过 20 张图片应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(theme="ok", product_images=[f"https://img{i}.com/x.png" for i in range(21)])


# ---------------------------------------------------------------------------
# AIAssistantRequest
# ---------------------------------------------------------------------------

class TestAIAssistantRequest:
    """测试 AIAssistantRequest 验证规则."""

    def _model(self):
        from src.api_routes import AIAssistantRequest
        return AIAssistantRequest

    def test_valid_message(self):
        """TC-VAL-20: 正常 message 应通过."""
        M = self._model()
        req = M(message="帮我写一段视频脚本")
        assert req.message == "帮我写一段视频脚本"

    def test_empty_message_rejected(self):
        """TC-VAL-21: 空 message 应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(message="")

    def test_message_too_long_rejected(self):
        """TC-VAL-22: message 超过 5000 字符应被拒绝."""
        M = self._model()
        with pytest.raises(ValidationError):
            M(message="x" * 5001)


# ---------------------------------------------------------------------------
# UpdateSceneRequest / RegenerateRequests
# ---------------------------------------------------------------------------

class TestSceneAndRegenerateRequests:
    """测试场景更新和重新生成请求的校验."""

    def test_scene_description_max_length(self):
        """TC-VAL-23: description 超过 2000 字符应被拒绝."""
        from src.api_routes import UpdateSceneRequest
        with pytest.raises(ValidationError):
            UpdateSceneRequest(description="x" * 2001)

    def test_scene_narration_max_length(self):
        """TC-VAL-24: narration 超过 5000 字符应被拒绝."""
        from src.api_routes import UpdateSceneRequest
        with pytest.raises(ValidationError):
            UpdateSceneRequest(narration="x" * 5001)

    def test_regen_image_prompt_max_length(self):
        """TC-VAL-25: 图片重新生成 prompt 超过 1000 字符应被拒绝."""
        from src.api_routes import RegenerateImageRequest
        with pytest.raises(ValidationError):
            RegenerateImageRequest(new_prompt="x" * 1001)

    def test_regen_video_prompt_max_length(self):
        """TC-VAL-26: 视频重新生成 prompt 超过 1000 字符应被拒绝."""
        from src.api_routes import RegenerateVideoRequest
        with pytest.raises(ValidationError):
            RegenerateVideoRequest(new_prompt="x" * 1001)
