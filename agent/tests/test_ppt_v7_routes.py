from src.schemas.ppt_v7 import SlideAction
from src.v7_routes import _align_action_start_frames


def test_align_highlight_action_to_keyword():
    actions = [SlideAction(type="highlight", keyword="340%", startFrame=0)]
    narration = "今年营收增长了340%，并且交付效率提升。"
    aligned = _align_action_start_frames(actions, narration, duration_secs=8, fps=30)
    assert aligned[0].startFrame > 0
    assert aligned[0].keyword == "340%"


def test_align_non_highlight_defaults():
    actions = [
        SlideAction(type="appear_items", items=["要点1", "要点2"], startFrame=0),
        SlideAction(type="zoom_in", region="right", startFrame=0),
    ]
    aligned = _align_action_start_frames(actions, "说明文本", duration_secs=6, fps=30)
    assert aligned[0].startFrame > 0
    assert aligned[1].startFrame > aligned[0].startFrame

