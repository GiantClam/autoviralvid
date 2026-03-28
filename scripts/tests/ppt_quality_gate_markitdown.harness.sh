#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR/agent"

python - <<'PY'
from src.ppt_quality_gate import validate_deck, validate_layout_diversity

bad_deck = [
    {
        "slide_id": "s1",
        "title": "灵创智能",
        "elements": [{"type": "text", "content": "xxxx TODO placeholder"}],
    }
]
good_deck = [
    {
        "slide_id": "s2",
        "title": "灵创智能 AI营销",
        "elements": [{"type": "text", "content": "聚焦数字人营销闭环"}],
    }
]

bad = validate_deck(bad_deck)
good = validate_deck(good_deck)
assert bad.ok is False, "bad deck should fail quality gate"
assert good.ok is True, "good deck should pass quality gate"

bad_layout = validate_layout_diversity(
    {
        "slides": [
            {"slide_id": f"s{i}", "slide_type": "grid_3"}
            for i in range(10)
        ]
    }
)
assert bad_layout.ok is False, "homogeneous layout should fail diversity gate"
print("quality gate harness passed")
PY
