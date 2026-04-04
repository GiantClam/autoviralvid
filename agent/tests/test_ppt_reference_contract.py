from src.ppt_reference_contract import audit_reference_contract


def _reference_desc() -> dict:
    return {
        "title": "季度经营复盘",
        "slides": [
            {
                "slide_id": "s1",
                "title": "经营总览",
                "blocks": [{"block_type": "body", "content": "营收同比提升 22%"}],
            },
            {
                "slide_id": "s2",
                "title": "增长引擎",
                "blocks": [{"block_type": "body", "content": "渠道转化率提升 8%"}],
            },
        ],
        "theme": {
            "primary": "22223b",
            "secondary": "4a4e69",
            "accent": "9a8c98",
            "bg": "f2e9e4",
        },
        "media_manifest": [
            {"path": "ppt/media/image1.png", "image_base64": "ZmFrZQ=="},
        ],
    }


def test_reference_contract_derives_anchors_and_required_facts():
    audit = audit_reference_contract(reference_desc=_reference_desc(), strict=True)
    assert not audit.errors
    assert len(audit.anchors) >= 2
    assert any("必须体现" in item for item in audit.required_facts)
    assert isinstance(audit.reference_desc.get("media_manifest"), list)


def test_reference_contract_strict_missing_media_manifest_fails_fast():
    bad = _reference_desc()
    bad.pop("media_manifest", None)
    audit = audit_reference_contract(reference_desc=bad, strict=True)
    assert any("media_manifest" in item for item in audit.errors)


def test_reference_contract_non_strict_theme_missing_key_reports_warning():
    bad = _reference_desc()
    bad["theme"] = {"primary": "111111"}
    audit = audit_reference_contract(reference_desc=bad, strict=False)
    assert not audit.errors
    assert any("theme missing keys" in item for item in audit.warnings)


def test_reference_contract_non_strict_missing_media_manifest_is_warning():
    bad = _reference_desc()
    bad.pop("media_manifest", None)
    audit = audit_reference_contract(reference_desc=bad, strict=False)
    assert not audit.errors
    assert any("media_manifest" in item for item in audit.warnings)
