"""
删除无效的技能记录

删除 'tokenengine' 和 'zhenzhen' 两个无效的技能
"""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def delete_invalid_skills():
    """删除使用无效 provider 的技能"""
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 要删除的无效 provider
    invalid_providers = ['tokenengine', 'zhenzhen']
    
    print("\n查询所有技能...")
    all_skills = client.table("autoviralvid_skills").select("*").execute()
    
    if not all_skills.data:
        print("  ℹ️  数据库中没有技能记录")
        return
    
    print(f"  找到 {len(all_skills.data)} 个技能")
    
    for provider in invalid_providers:
        print(f"\n正在删除 provider='{provider}' 的技能:")
        
        # 查找使用此 provider 的技能
        skills_to_delete = [s for s in all_skills.data if s.get('provider') == provider]
        
        if not skills_to_delete:
            print(f"  ℹ️  未找到使用 provider '{provider}' 的技能")
            continue
        
        for skill in skills_to_delete:
            print(f"  找到: {skill['name']}")
            print(f"    ID: {skill['id']}")
            print(f"    Provider: {skill.get('provider')}")
            print(f"    Category: {skill.get('category')}")
            
            try:
                # 删除技能
                client.table("autoviralvid_skills").delete().eq("id", skill['id']).execute()
                print(f"    ✅ 已删除")
            except Exception as e:
                print(f"    ❌ 删除失败: {e}")
    
    print("\n" + "="*50)
    print("删除操作完成")
    
    # 显示剩余的技能
    print("\n剩余的技能:")
    try:
        remaining_skills = client.table("autoviralvid_skills").select("name, provider, category").execute()
        if remaining_skills.data:
            for skill in remaining_skills.data:
                print(f"  - {skill['name']} ({skill.get('provider')}, {skill.get('category')})")
        else:
            print("  (无)")
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")


if __name__ == "__main__":
    delete_invalid_skills()
