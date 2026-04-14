from src.ppt_service_v2 import _prepare_pipeline_contract_inputs
from src.schemas.ppt_pipeline import PPTPipelineRequest


def test_prepare_pipeline_contract_inputs_dedups_and_adds_anchor_constraints():
    req = PPTPipelineRequest(
        topic="ops review",
        required_facts=["Revenue +20%", "revenue +20%", "CAC down 8%", ""],
        anchors=["Q1", "q1", "Q2"],
        constraints=["must cite source", "", "must cite source"],
    )

    out = _prepare_pipeline_contract_inputs(req, execution_profile="prod_safe")

    assert out["required_facts"] == ["Revenue +20%", "CAC down 8%"]
    assert out["anchors"] == ["Q1", "Q2"]
    assert "must cite source" in out["constraints"]
    assert "anchor_constraint:Q1" in out["constraints"]
    assert "anchor_constraint:Q2" in out["constraints"]
    assert req.constraints == out["constraints"]


def test_prepare_pipeline_contract_inputs_handles_empty_lists():
    req = PPTPipelineRequest(topic="empty case")
    out = _prepare_pipeline_contract_inputs(req, execution_profile="prod_safe")

    assert out["required_facts"] == []
    assert out["anchors"] == []
    assert out["constraints"] == []
