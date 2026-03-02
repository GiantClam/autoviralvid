"""
Test script for Skills system.

This script verifies that:
1. Skills can be loaded from the database
2. The RunningHub Sora2 skill is registered
3. The skill selector can find appropriate skills for the i2v category

Usage:
    python -m src.test_skills
"""
import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.skills import get_skills_registry, get_skill_selector, SkillCategory


async def test_skills_loading():
    """Test that skills can be loaded from database."""
    print("=" * 60)
    print("TEST 1: Loading Skills from Database")
    print("=" * 60)
    
    try:
        registry = await get_skills_registry()
        print(f"✓ Skills registry initialized successfully")
        
        all_skills = registry.get_all_skills()
        print(f"✓ Loaded {len(all_skills)} skills from database")
        
        if not all_skills:
            print("⚠ WARNING: No skills found in database. Did you run the migration?")
            return False
            
        print("\nRegistered skills:")
        for skill in all_skills:
            print(f"  - {skill.name} ({skill.display_name})")
            print(f"    Category: {skill.category}, Provider: {skill.provider}")
            print(f"    Priority: {skill.priority}, Enabled: {skill.is_enabled}")
        
        return True
    except Exception as e:
        print(f"✗ ERROR: Failed to load skills: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_runninghub_sora2_skill():
    """Test that RunningHub Sora2 skill is registered."""
    print("\n" + "=" * 60)
    print("TEST 2: RunningHub Sora2 Skill Registration")
    print("=" * 60)
    
    try:
        registry = await get_skills_registry()
        
        # Try to get the skill by name
        skill = registry.get_skill("runninghub_sora2_i2v")
        
        if not skill:
            print("✗ ERROR: RunningHub Sora2 skill not found")
            return False
        
        print(f"✓ Found skill: {skill.display_name}")
        print(f"  ID: {skill.id}")
        print(f"  Name: {skill.name}")
        print(f"  Category: {skill.category}")
        print(f"  Provider: {skill.provider}")
        print(f"  Workflow ID: {skill.workflow_id}")
        print(f"  Priority: {skill.priority}")
        print(f"  Enabled: {skill.is_enabled}")
        print(f"  Capabilities: {skill.capabilities}")
        print(f"  Node Mappings: {skill.node_mappings}")
        
        return True
    except Exception as e:
        print(f"✗ ERROR: Failed to get RunningHub Sora2 skill: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_skill_selection():
    """Test that skill selector can find appropriate skills."""
    print("\n" + "=" * 60)
    print("TEST 3: Skill Selection for i2v Category")
    print("=" * 60)
    
    try:
        selector = await get_skill_selector()
        
        # Test requirements
        requirements = {
            "duration": 10,
            "orientation": "landscape",
            "requires_image": True,
        }
        
        print(f"Requirements: {requirements}")
        
        # Select skills with fallback
        skills = await selector.select_with_fallback(
            category=SkillCategory.I2V,
            requirements=requirements,
            max_fallbacks=3
        )
        
        if not skills:
            print("✗ ERROR: No skills selected")
            return False
        
        print(f"✓ Selected {len(skills)} skill(s):")
        for i, skill in enumerate(skills, 1):
            print(f"  {i}. {skill.name} ({skill.display_name})")
            print(f"     Priority: {skill.priority}, Score: {skill.quality_score}")
        
        # Verify RunningHub Sora2 is in the selection
        sora2_selected = any(s.name == "runninghub_sora2_i2v" for s in skills)
        if sora2_selected:
            print("✓ RunningHub Sora2 is in the selection")
        else:
            print("⚠ WARNING: RunningHub Sora2 not in selection")
        
        return True
    except Exception as e:
        print(f"✗ ERROR: Failed to select skills: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SKILLS SYSTEM TEST SUITE")
    print("=" * 60)
    
    # Check environment variables
    print("\nEnvironment Check:")
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "RUNNINGHUB_SORA2_WORKFLOW_ID",
        "RUNNINGHUB_API_KEY"
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if "KEY" in var or "SECRET" in var:
                display_value = value[:10] + "..." if len(value) > 10 else "***"
            else:
                display_value = value
            print(f"  ✓ {var}: {display_value}")
        else:
            print(f"  ✗ {var}: NOT SET")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n⚠ WARNING: Missing environment variables: {', '.join(missing_vars)}")
        print("Some tests may fail.\n")
    
    # Run tests
    results = []
    
    test1 = await test_skills_loading()
    results.append(("Skills Loading", test1))
    
    test2 = await test_runninghub_sora2_skill()
    results.append(("RunningHub Sora2 Registration", test2))
    
    test3 = await test_skill_selection()
    results.append(("Skill Selection", test3))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
