from src.ppt_export_contract_service import PPTExportContractService


def test_build_final_slide_contract_normalizes_fields():
    svc = PPTExportContractService()
    out = svc.build_final_slide_contract(
        [
            {
                "slide_id": "s1",
                "slide_type": "Content",
                "layout_grid": "Grid_3",
                "template_family": "Consulting",
            },
            {
                "id": "s2",
                "type": "Summary",
                "layout": "Hero_1",
                "template_id": "Auto",
            },
        ]
    )
    assert len(out) == 2
    assert out[0]["slide_id"] == "s1"
    assert out[0]["slide_type"] == "content"
    assert out[0]["layout_grid"] == "grid_3"
    assert out[0]["template_family"] == "consulting"
    assert out[1]["slide_id"] == "s2"
    assert out[1]["slide_type"] == "summary"
    assert out[1]["layout_grid"] == "hero_1"
    assert out[1]["template_family"] == "auto"

