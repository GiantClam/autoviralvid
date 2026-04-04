import json

with open("output/regression/reference_extracted.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("Slide 1 elements (sorted by font size):")
elements = data["slides"][0]["elements"]
for e in sorted(elements, key=lambda x: x.get("font_size", 0), reverse=True)[:10]:
    content = e["content"][:30] if len(e["content"]) > 30 else e["content"]
    print(f'  font={e.get("font_size", 0):3d}pt  top={e["top"]:.2f}  "{content}"')

print()
print("Blocks:")
for b in data["slides"][0]["blocks"]:
    content = b["content"][:30] if len(b["content"]) > 30 else b["content"]
    print(f'  {b["block_type"]:10s}: "{content}"')
