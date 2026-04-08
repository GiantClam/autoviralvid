"""Test script to regenerate PPT with enhanced quality settings."""

import sys
import json
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, "agent")

# Configuration
API_BASE = "http://127.0.0.1:8124"
OUTPUT_DIR = Path("test_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Test case: Education PPT (should trigger ppt-master)
test_request = {
    "topic": "解码霍尔木兹海峡危机：国际关系影响",
    "audience": "high-school-students",
    "purpose": "课程讲义",
    "style_preference": "professional",
    "total_pages": 13,
    "language": "zh-CN",
    "with_export": True,
    "save_artifacts": True,
    "route_mode": "refine",
    "quality_profile": "high_density_consulting",
    "execution_profile": "auto",
}

print("=" * 70)
print("PPT Regeneration Test with Enhanced Quality Settings")
print("=" * 70)
print(f"\nTimestamp: {datetime.now().isoformat()}")
print(f"\nRequest Configuration:")
print(f"  Topic: {test_request['topic']}")
print(f"  Purpose: {test_request['purpose']}")
print(f"  Quality Profile: {test_request['quality_profile']}")
print(f"  Route Mode: {test_request['route_mode']}")
print(f"  Total Pages: {test_request['total_pages']}")

print("\n" + "-" * 70)
print("Expected Improvements:")
print("-" * 70)
print("[OK] Quality threshold: 80 (was 78)")
print("[OK] ppt-master forced: YES (education content detected)")
print("[OK] Storyline validation: ENABLED")
print("[OK] Design constraints: ENFORCED")

print("\n" + "-" * 70)
print("Sending request to API...")
print("-" * 70)

try:
    response = requests.post(
        f"{API_BASE}/api/v1/ppt/pipeline", json=test_request, timeout=900
    )

    if response.status_code != 200:
        print(f"[ERROR] API Error: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        sys.exit(1)

    result = response.json()

    if not result.get("success"):
        print(f"[ERROR] Pipeline Failed")
        print(f"Response: {json.dumps(result, indent=2, ensure_ascii=False)[:1000]}")
        sys.exit(1)

    data = result.get("data", {})

    print("\n[SUCCESS] PPT Generated Successfully!")
    print("\n" + "=" * 70)
    print("Generation Results")
    print("=" * 70)

    # Extract key metrics
    run_id = data.get("run_id", "unknown")
    export_data = data.get("export", {})

    # Quality metrics
    quality_score = export_data.get("quality_score", {})
    visual_score = export_data.get("visual_professional_score", {})

    print(f"\nRun ID: {run_id}")

    if quality_score:
        print(f"\nQuality Score:")
        print(f"  Score: {quality_score.get('score', 'N/A')}")
        print(f"  Passed: {quality_score.get('passed', False)}")
        print(f"  Threshold: {quality_score.get('threshold', 'N/A')}")

    if visual_score:
        print(f"\nVisual Professional Score:")
        print(f"  Average: {visual_score.get('visual_avg_score', 'N/A')}")
        print(
            f"  Color Consistency: {visual_score.get('color_consistency_score', 'N/A')}"
        )
        print(f"  Layout Order: {visual_score.get('layout_order_score', 'N/A')}")
        print(
            f"  Hierarchy Clarity: {visual_score.get('hierarchy_clarity_score', 'N/A')}"
        )
        print(f"  Accuracy Gate: {visual_score.get('accuracy_gate_passed', False)}")

    # Design decision
    design_decision = data.get("design_decision_v1", {})
    if design_decision:
        deck_decision = design_decision.get("deck", {})
        print(f"\nDesign Decision:")
        print(f"  Style Variant: {deck_decision.get('style_variant', 'N/A')}")
        print(f"  Palette Key: {deck_decision.get('palette_key', 'N/A')}")
        print(f"  Theme Recipe: {deck_decision.get('theme_recipe', 'N/A')}")
        print(f"  Template Family: {deck_decision.get('template_family', 'N/A')}")

    # Check if ppt-master was used
    skill_runtime = data.get("skill_planning_runtime", {})
    ppt_master_used = False
    if skill_runtime:
        slides_runtime = skill_runtime.get("slides", [])
        ppt_master_used = any(
            "ppt-master" in str(slide.get("requested_skills", []))
            for slide in slides_runtime
        )
        print(f"\nPPT-Master Used: {ppt_master_used}")

    # Save results
    output_file = OUTPUT_DIR / f"regeneration_result_{run_id}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Results saved to: {output_file}")

    # Check for PPTX file
    pptx_path = data.get("pptx_path")
    if pptx_path:
        print(f"[OK] PPTX file: {pptx_path}")

    print("\n" + "=" * 70)
    print("Comparison with Previous Version")
    print("=" * 70)
    print("\nPrevious (before fix):")
    print("  Quality Score: 55-56")
    print("  Visual Avg: ~5.5")
    print("  Pages: 10")
    print("  ppt-master: NO")

    current_visual = visual_score.get("visual_avg_score", 0) if visual_score else 0
    current_quality = quality_score.get("score", 0) if quality_score else 0

    print(f"\nCurrent (after fix):")
    print(f"  Quality Score: {current_quality}")
    print(f"  Visual Avg: {current_visual}")
    print(f"  Pages: {len(export_data.get('slides', []))}")
    print(f"  ppt-master: {ppt_master_used}")

    if current_visual > 5.5:
        improvement = current_visual - 5.5
        print(f"\n[IMPROVED] Visual Score: +{improvement:.2f}")

    if current_quality > 56:
        improvement = current_quality - 56
        print(f"[IMPROVED] Quality Score: +{improvement:.2f}")

    print("\n" + "=" * 70)
    print("Next Steps")
    print("=" * 70)
    print("1. Review generated PPTX file")
    print("2. Compare with reference PPT (D:\\private\\test\\2.pptx)")
    print("3. Generate visual comparison report")

except requests.exceptions.ConnectionError:
    print("\n[ERROR] Cannot connect to API server")
    print(f"Please ensure the server is running at {API_BASE}")
    print("\nTo start the server:")
    print("  cd D:\\github\\with-langgraph-fastapi")
    print("  python -m uvicorn agent.main:app --host 0.0.0.0 --port 8124")
    sys.exit(1)

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
