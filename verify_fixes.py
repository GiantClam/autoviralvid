"""Verify PPT quality fixes - simplified version."""

import sys

sys.path.insert(0, "agent")

from src.ppt_master_skill_adapter import should_force_ppt_master_hit
from src.ppt_storyline_planning import ensure_education_storyline_completeness
from src.ppt_template_catalog import quality_profile

print("=" * 60)
print("PPT Quality Fix Verification")
print("=" * 60)

# Test 1: Quality thresholds
print("\n[1] Testing Quality Thresholds...")
default_profile = quality_profile("default")
high_density_profile = quality_profile("high_density_consulting")

default_threshold = default_profile.get("quality_score_threshold", 0)
high_density_threshold = high_density_profile.get("quality_score_threshold", 0)

print(f"  Default profile threshold: {default_threshold} (expected: 75)")
print(f"  High density profile threshold: {high_density_threshold} (expected: 80)")

if default_threshold >= 75 and high_density_threshold >= 80:
    print("  [PASS] Quality thresholds verified")
else:
    print("  [FAIL] Quality thresholds not raised")
    sys.exit(1)

# Test 2: Education detection
print("\n[2] Testing Education Content Detection...")
test_cases = [
    (True, "default", "课程讲义", "解码霍尔木兹海峡危机"),
    (True, "default", "", "高中课堂展示"),
    (True, "high_density_consulting", "", ""),
    (False, "default", "工作汇报", "季度总结"),
]

all_passed = True
for expected, profile, purpose, topic in test_cases:
    result = should_force_ppt_master_hit(
        quality_profile=profile, purpose=purpose, topic=topic
    )
    status = "PASS" if result == expected else "FAIL"
    print(
        f"  [{status}] profile={profile}, purpose={purpose[:10]}, topic={topic[:10]} => {result}"
    )
    if result != expected:
        all_passed = False

if all_passed:
    print("  [PASS] Education detection verified")
else:
    print("  [FAIL] Education detection failed")
    sys.exit(1)

# Test 3: Storyline completeness
print("\n[3] Testing Storyline Completeness...")
incomplete_slides = [
    {"slide_type": "cover", "title": "解码霍尔木兹海峡危机"},
    {"slide_type": "content", "title": "海峡位置"},
]

missing = ensure_education_storyline_completeness(
    incomplete_slides, purpose="课程讲义", topic="解码霍尔木兹海峡危机"
)
print(f"  Incomplete PPT missing: {missing}")

complete_slides = [
    {"slide_type": "cover", "title": "解码霍尔木兹海峡危机"},
    {"slide_type": "content", "title": "学习目标与课程结构"},
    {"slide_type": "content", "title": "核心概念：海峡战略价值"},
    {"slide_type": "summary", "title": "课程总结"},
]

missing_complete = ensure_education_storyline_completeness(
    complete_slides, purpose="课程讲义", topic="解码霍尔木兹海峡危机"
)
print(f"  Complete PPT missing: {missing_complete}")

if len(missing) > 0 and len(missing_complete) == 0:
    print("  [PASS] Storyline completeness verified")
else:
    print("  [FAIL] Storyline completeness failed")
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
print("\nSummary:")
print("- Quality thresholds: default=75, high_density=80")
print("- Education detection: Working correctly")
print("- Storyline validation: Working correctly")
print("- ppt-master forced for education content")
print("\nNext steps:")
print("1. Regenerate test PPT with new settings")
print("2. Run gap evaluation to measure improvement")
print("3. Compare with reference PPT (D:\\private\\test\\2.pptx)")
