import pytest

from src.ppt_service import _prepare_pipeline_contract_inputs
from src.schemas.ppt_pipeline import PPTPipelineRequest


def _reference_desc() -> dict:
    return {
        "title": "重建样例",
        "slides": [
            {
                "slide_id": "s1",
                "title": "经营总览",
                "blocks": [{"block_type": "body", "content": "营收提升 22%"}],
            },
            {
                "slide_id": "s2",
                "title": "执行路径",
                "blocks": [{"block_type": "list", "content": "Q1 验证;Q2 放量"}],
            },
        ],
        "theme": {
            "primary": "22223b",
            "secondary": "4a4e69",
            "accent": "9a8c98",
            "bg": "f2e9e4",
        },
        "media_manifest": [{"path": "ppt/media/image1.png", "image_base64": "ZmFrZQ=="}],
    }


def test_prepare_pipeline_contract_inputs_fails_fast_when_reference_contract_missing_fields():
    req = PPTPipelineRequest(
        topic="经营复盘",
        reconstruct_from_reference=True,
        reference_desc={
            "slides": [],
            "theme": {
                "primary": "22223b",
                "secondary": "4a4e69",
                "accent": "9a8c98",
                "bg": "f2e9e4",
            },
        },
    )
    with pytest.raises(ValueError, match="media_manifest"):
        _prepare_pipeline_contract_inputs(req, execution_profile="dev_strict")


def test_prepare_pipeline_contract_inputs_derives_and_persists_contract_fields():
    req = PPTPipelineRequest(
        topic="经营复盘",
        reconstruct_from_reference=True,
        reference_desc=_reference_desc(),
    )
    out = _prepare_pipeline_contract_inputs(req, execution_profile="dev_strict")
    assert out["anchors"]
    assert out["required_facts"]
    assert any(str(item).startswith("锚点约束:") for item in out["constraints"])
    assert req.anchors == out["anchors"]
    assert req.required_facts == out["required_facts"]
    assert isinstance(req.reference_desc, dict)
    assert req.reference_desc.get("anchors") == out["anchors"]
