"""Test script to verify PPT quality fixes."""

import sys
import json
from pathlib import Path

sys.path.insert(0, "agent")

from src.ppt_master_skill_adapter import should_force_ppt_master_hit
from src.ppt_storyline_planning import ensure_education_storyline_completeness
from src.ppt_template_catalog import quality_profile


def test_quality_thresholds():
    """Test that quality thresholds have been raised."""
    print("=" * 60)
    print("Testing Quality Thresholds")
    print("=" * 60)

    default_profile = quality_profile("default")
    high_density_profile = quality_profile("high_density_consulting")

    default_threshold = default_profile.get("quality_score_threshold", 0)
    high_density_threshold = high_density_profile.get("quality_score_threshold", 0)

    print(f"✓ Default profile threshold: {default_threshold} (expected: 75)")
    print(f"✓ High density profile threshold: {high_density_threshold} (expected: 80)")

    assert default_threshold >= 75, f"Default threshold too low: {default_threshold}"
    assert high_density_threshold >= 80, (
        f"High density threshold too low: {high_density_threshold}"
    )

    print("✅ Quality thresholds verified\n")


def test_education_detection():
    """Test that education content is properly detected."""
    print("=" * 60)
    print("Testing Education Content Detection")
    print("=" * 60)

    # Test 1: Education keywords in purpose
    result1 = should_force_ppt_master_hit(
        quality_profile="default", purpose="课程讲义", topic="解码霍尔木兹海峡危机"
    )
    print(f"✓ Education purpose detection: {result1} (expected: True)")
    assert result1 == True, "Failed to detect education purpose"

    # Test 2: Education keywords in topic
    result2 = should_force_ppt_master_hit(
        quality_profile="default", purpose="", topic="高中课堂展示：国际关系"
    )
    print(f"✓ Education topic detection: {result2} (expected: True)")
    assert result2 == True, "Failed to detect education topic"

    # Test 3: High density consulting profile
    result3 = should_force_ppt_master_hit(
        quality_profile="high_density_consulting", purpose="", topic=""
    )
    print(f"✓ High density profile detection: {result3} (expected: True)")
    assert result3 == True, "Failed to detect high density profile"

    # Test 4: Non-education content
    result4 = should_force_ppt_master_hit(
        quality_profile="default", purpose="工作汇报", topic="季度总结"
    )
    print(f"✓ Non-education detection: {result4} (expected: False)")
    assert result4 == False, "False positive for non-education content"

    print("✅ Education detection verified\n")


def test_storyline_completeness():
    """Test storyline completeness validation."""
    print("=" * 60)
    print("Testing Storyline Completeness Validation")
    print("=" * 60)

    # Test incomplete education PPT
    incomplete_slides = [
        {"slide_type": "cover", "title": "解码霍尔木兹海峡危机"},
        {"slide_type": "content", "title": "海峡位置"},
        {"slide_type": "content", "title": "危机历史"},
    ]

    missing = ensure_education_storyline_completeness(
        incomplete_slides, purpose="课程讲义", topic="解码霍尔木兹海峡危机"
    )
    print(f"✓ Incomplete PPT missing sections: {missing}")
    assert len(missing) > 0, "Should detect missing sections"
    assert "learning_objectives" in missing, "Should detect missing learning objectives"
    assert "summary" in missing, "Should detect missing summary"

    # Test complete education PPT
    complete_slides = [
        {"slide_type": "cover", "title": "解码霍尔木兹海峡危机"},
        {"slide_type": "content", "title": "学习目标与课程结构"},
        {"slide_type": "content", "title": "核心概念：海峡战略价值"},
        {"slide_type": "content", "title": "案例分析"},
        {"slide_type": "summary", "title": "课程总结"},
    ]

    missing_complete = ensure_education_storyline_completeness(
        complete_slides, purpose="课程讲义", topic="解码霍尔木兹海峡危机"
    )
    print(f"✓ Complete PPT missing sections: {missing_complete}")
    assert len(missing_complete) == 0, (
        "Should not detect missing sections in complete PPT"
    )

    # Test non-education content
    non_edu_slides = [
        {"slide_type": "cover", "title": "季度工作汇报"},
        {"slide_type": "content", "title": "关键成果"},
    ]

    missing_non_edu = ensure_education_storyline_completeness(
        non_edu_slides, purpose="工作汇报", topic="季度总结"
    )
    print(f"✓ Non-education PPT missing sections: {missing_non_edu}")
    assert len(missing_non_edu) == 0, "Should not validate non-education content"

    print("✅ Storyline completeness verified\n")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PPT Quality Fix Verification")
    print("=" * 60 + "\n")

    try:
        test_quality_thresholds()
        test_education_detection()
        test_storyline_completeness()

        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSummary:")
        print("- Quality thresholds raised to 75/80")
        print("- Education content detection working")
        print("- Storyline completeness validation working")
        print("- ppt-master will be forced for education content")
        print("\nNext steps:")
        print("1. Regenerate test PPT with new settings")
        print("2. Run gap evaluation to measure improvement")
        print("3. Visual comparison with reference PPT")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
