import json

with open("output/regression/reference_extracted.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("=== Slide 1 视觉信息 ===")
slide1 = data["slides"][0]
print(f"文本元素数: {len(slide1.get('elements', []))}")
print(f"形状元素数: {len(slide1.get('shapes', []))}")

print("\n形状元素 (前10个):")
for i, sh in enumerate(slide1.get("shapes", [])[:10]):
    print(
        f"  {i + 1}. type={sh.get('subtype', 'unknown'):15s} fill={sh.get('fill_color', 'none'):10s} size=({sh.get('width', 0):.2f}x{sh.get('height', 0):.2f})"
    )

print("\n=== 幻灯片统计 ===")
total_shapes = 0
total_elements = 0
for slide in data["slides"]:
    total_shapes += len(slide.get("shapes", []))
    total_elements += len(slide.get("elements", []))

print(f"总幻灯片数: {len(data['slides'])}")
print(f"总形状数: {total_shapes}")
print(f"总文本元素数: {total_elements}")
print(f"平均每页形状: {total_shapes / len(data['slides']):.1f}")
