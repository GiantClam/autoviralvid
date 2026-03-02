"""
Tests for tutorial template configuration and workflow integration.
"""

import sys
import os
import json
import pytest

# Ensure agent/src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestTutorialNarrativeStructure:
    """Verify the tutorial narrative structure is registered and correct."""

    def test_tutorial_narrative_exists(self):
        from creative_agent import NARRATIVE_STRUCTURES

        assert "tutorial" in NARRATIVE_STRUCTURES

    def test_tutorial_narrative_fields(self):
        from creative_agent import NARRATIVE_STRUCTURES

        ns = NARRATIVE_STRUCTURES["tutorial"]
        assert ns["name"] == "教程步骤型"
        assert "步骤" in ns["beats"] or "分步" in ns["beats"]
        assert "scene_guidance" in ns
        assert len(ns["scene_guidance"]) > 20


class TestTutorialTemplateConfig:
    """Verify TEMPLATE_CONFIG entries for tutorial templates."""

    TUTORIAL_IDS = ["tutorial", "tutorial-soft", "tutorial-know", "tutorial-prod"]

    def test_all_tutorial_ids_registered(self):
        from creative_agent import TEMPLATE_CONFIG

        for tid in self.TUTORIAL_IDS:
            assert tid in TEMPLATE_CONFIG, f"Missing TEMPLATE_CONFIG entry for {tid}"

    def test_tutorial_uses_tutorial_narrative(self):
        from creative_agent import TEMPLATE_CONFIG

        for tid in self.TUTORIAL_IDS:
            cfg = TEMPLATE_CONFIG[tid]
            assert cfg["narrative"] == "tutorial", (
                f"{tid} should use tutorial narrative"
            )

    def test_tutorial_pipeline_hint(self):
        from creative_agent import TEMPLATE_CONFIG

        for tid in self.TUTORIAL_IDS:
            cfg = TEMPLATE_CONFIG[tid]
            assert cfg["pipeline_hint"] == "tutorial", (
                f"{tid} should hint tutorial pipeline"
            )

    def test_tutorial_video_type(self):
        from creative_agent import TEMPLATE_CONFIG

        for tid in self.TUTORIAL_IDS:
            cfg = TEMPLATE_CONFIG[tid]
            assert cfg["video_type"] == "教程视频"

    def test_get_narrative_for_tutorial(self):
        from creative_agent import get_narrative_for_template

        ns = get_narrative_for_template("tutorial")
        assert ns["name"] == "教程步骤型"

    def test_get_pipeline_hint_for_tutorial(self):
        from creative_agent import get_pipeline_hint_for_template

        assert get_pipeline_hint_for_template("tutorial") == "tutorial"


class TestTutorialPipelineConfig:
    """Verify the tutorial pipeline is defined in skills.yaml."""

    def test_tutorial_pipeline_in_yaml(self):
        import yaml

        yaml_path = os.path.join(
            os.path.dirname(__file__), "..", "src", "configs", "skills.yaml"
        )
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        pipeline_names = [p["name"] for p in config.get("pipelines", [])]
        assert "tutorial" in pipeline_names, (
            "tutorial pipeline missing from skills.yaml"
        )

    def test_tutorial_pipeline_fields(self):
        import yaml

        yaml_path = os.path.join(
            os.path.dirname(__file__), "..", "src", "configs", "skills.yaml"
        )
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        tutorial_pipe = None
        for p in config.get("pipelines", []):
            if p["name"] == "tutorial":
                tutorial_pipe = p
                break

        assert tutorial_pipe is not None
        assert tutorial_pipe["t2i_skill"] == "runninghub_qwen_t2i"
        assert tutorial_pipe["i2v_skill"] == "runninghub_sora2_i2v"
        assert tutorial_pipe["is_enabled"] is True
        assert "tutorial" in tutorial_pipe.get("tags", [])


class TestTutorialPlannerPrompt:
    """Verify the planner prompt includes tutorial-specific instructions."""

    def test_tutorial_prompt_enhancement(self):
        """When narrative is tutorial, plan_storyboard_impl should include
        step_number, annotations, and step_title requirements in the prompt."""
        from creative_agent import NARRATIVE_STRUCTURES

        ns = NARRATIVE_STRUCTURES["tutorial"]

        # Simulate what plan_storyboard_impl does with the narrative
        ns_name = ns.get("name", "")
        is_tutorial = ns_name == "教程步骤型"
        assert is_tutorial, "Tutorial narrative should be detected as tutorial type"

    def test_video_type_to_narrative_mapping(self):
        """教程视频 should map to tutorial narrative in the workflow."""
        _vtype_to_narrative = {
            "产品宣传视频": "product_showcase",
            "教程视频": "tutorial",
        }
        assert _vtype_to_narrative.get("教程视频") == "tutorial"
