"""
Test script for AI prompt-based PPT generation
"""

import asyncio
import sys
import json
from pathlib import Path

# Add agent to path
sys.path.insert(0, str(Path(__file__).parent / "agent"))

from src.ppt_master_service import PPTMasterService


async def test_generate_from_prompt():
    """Test PPT generation from AI prompt"""

    print("=" * 80)
    print("Testing AI Prompt-based PPT Generation")
    print("=" * 80)

    # Initialize service
    service = PPTMasterService()

    # Test prompt
    prompt = """创建一份关于人工智能发展历程的演示文稿，包括：
1. AI的起源和早期发展
2. 重要的里程碑事件
3. 当前的主要应用领域
4. 未来发展趋势和挑战
"""

    print(f"\nPrompt: {prompt}")
    print(f"Total pages: 10")
    print(f"Style: professional")
    print("\nGenerating PPT...")

    try:
        result = await service.generate_from_prompt(
            prompt=prompt,
            total_pages=10,
            style="professional",
            color_scheme="blue",
            language="zh-CN",
            include_images=False,
        )

        print("\n" + "=" * 80)
        if result.get("success"):
            print("[OK] Generation successful!")
            print(f"Project: {result['project_name']}")
            print(f"Path: {result['project_path']}")
            print(f"Total slides: {result['total_slides']}")
            print(f"Generation time: {result['generation_time_seconds']:.1f}s")

            if result.get("output_pptx"):
                print(f"Output PPTX: {result['output_pptx']}")

            # Save result
            result_file = Path(result["project_path"]) / "test_result.json"
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Result saved: {result_file}")

        else:
            print("[FAIL] Generation failed!")
            print(f"Error: {result.get('error', 'Unknown error')}")

        print("=" * 80)

        return result

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


async def test_list_templates():
    """Test listing available templates"""

    print("\n" + "=" * 80)
    print("Testing Template Listing")
    print("=" * 80)

    service = PPTMasterService()
    templates = service.list_available_templates()

    print(f"\nFound {len(templates)} templates:")
    for i, template in enumerate(templates[:10], 1):
        print(f"{i}. {template['name']}")
        if template.get("description"):
            print(f"   {template['description'][:80]}")

    if len(templates) > 10:
        print(f"... and {len(templates) - 10} more")

    return templates


async def main():
    """Main test function"""

    # Test 1: List templates
    templates = await test_list_templates()

    # Test 2: Generate from prompt
    result = await test_generate_from_prompt()

    # Summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    print(f"Templates available: {len(templates)}")
    print(f"Generation test: {'PASS' if result.get('success') else 'FAIL'}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
