import json


def color_distance(c1: str, c2: str) -> float:
    """Calculate Euclidean distance between two hex colors."""
    try:
        h1 = c1.upper().lstrip("#")
        h2 = c2.upper().lstrip("#")
        if len(h1) == 3:
            h1 = "".join(c * 2 for c in h1)
        if len(h2) == 3:
            h2 = "".join(c * 2 for c in h2)
        r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
        r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
        return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
    except Exception as e:
        print(f"Error: {e}")
        return 999


# Load files
ref_path = "output/regression/reference_extracted.json"
gen_path = "test_inputs/work-summary-minimax-format.json"

with open(ref_path, "r", encoding="utf-8") as f:
    ref_json = json.load(f)
with open(gen_path, "r", encoding="utf-8") as f:
    gen_json = json.load(f)

ref_theme = ref_json.get("theme", {})
gen_theme = gen_json.get("theme", {})

print("Reference theme:", ref_theme)
print("Target theme:", gen_theme)
print()

for key in ["primary", "secondary", "accent", "bg"]:
    ref_color = str(ref_theme.get(key, "")).upper().lstrip("#")
    gen_color = str(gen_theme.get(key, "")).upper().lstrip("#")
    print(f"{key}: ref={ref_color} gen={gen_color}")
    if ref_color and gen_color:
        dist = color_distance(ref_color, gen_color)
        print(f"  distance={dist:.1f}")
