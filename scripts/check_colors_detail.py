import zipfile
import xml.etree.ElementTree as ET

ref_path = "C:/Users/liula/Downloads/ppt2/ppt2/1.pptx"
z = zipfile.ZipFile(ref_path)

# Check slide 1 in detail for colors
slide1 = z.read("ppt/slides/slide1.xml")
root = ET.fromstring(slide1)

print("=== Slide 1 all colors ===")

# Find all color references
colors_found = {}
for elem in root.iter():
    # Check for srgbClr
    for child in elem:
        if "srgbClr" in child.tag:
            val = child.get("val", "")
            if val:
                parent_tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if parent_tag not in colors_found:
                    colors_found[parent_tag] = []
                colors_found[parent_tag].append(f"#{val.upper()}")

        # Check for schemeClr
        if "schemeClr" in child.tag:
            val = child.get("val", "")
            if val:
                parent_tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if parent_tag not in colors_found:
                    colors_found[parent_tag] = []
                colors_found[parent_tag].append(f"scheme:{val}")

# Print unique colors
all_colors = set()
for tag, vals in colors_found.items():
    for v in vals:
        all_colors.add(v)

print("All colors found:", sorted(all_colors)[:20])

# Now let's check what visual look the slide has by analyzing shape fills
print("\n=== Shape fills in Slide 1 ===")
shape_fills = []
for elem in root.iter():
    if "sp" in elem.tag:
        has_fill = False
        fill_type = None
        fill_val = None

        for child in elem:
            if "solidFill" in child.tag:
                has_fill = True
                for sf in child:
                    if "srgbClr" in sf.tag:
                        fill_type = "srgb"
                        fill_val = sf.get("val", "")
                    elif "schemeClr" in sf.tag:
                        fill_type = "scheme"
                        fill_val = sf.get("val", "")
                    elif "sysClr" in sf.tag:
                        fill_type = "sys"
                        fill_val = sf.get("lastClr", "")

        if has_fill and fill_val:
            shape_fills.append(f"{fill_type}:{fill_val}")

from collections import Counter

fill_counts = Counter(shape_fills)
print("Fill colors:", fill_counts.most_common(10))
