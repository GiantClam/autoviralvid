from src.ppt_template_catalog import list_template_ids, template_capabilities, template_profiles


def test_ppt_master_templates_are_registered():
    ids = set(list_template_ids())
    expected = {
        "pm_mckinsey_light",
        "pm_ai_ops_light",
        "pm_exhibit_dark",
        "pm_google_style_light",
    }
    assert expected.issubset(ids)


def test_ppt_master_template_profiles_have_catalog_contract():
    profile = template_profiles("pm_mckinsey_light")
    assert profile["template_id"] == "pm_mckinsey_light"
    assert profile["schema_profile"] == "ppt-template/v2-ppt-master-mckinsey"
    assert profile["contract_profile"] in {"default", "hierarchy_blocks_required"}

    cap = template_capabilities("pm_mckinsey_light")
    assert "split_2" in cap["supported_layouts"]
    assert "title" in cap["supported_block_types"]
