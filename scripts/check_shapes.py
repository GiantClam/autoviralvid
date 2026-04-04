import zipfile
import xml.etree.ElementTree as ET

ref_path = "C:/Users/liula/Downloads/ppt2/ppt2/1.pptx"
z = zipfile.ZipFile(ref_path)

# Check slide 1 in detail
content = z.read("ppt/slides/slide1.xml")
root = ET.fromstring(content)

# Find all shapes
shapes = []
for elem in root.iter():
    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
    if "sp" in tag:
        shape_type = "unknown"
        has_text = False
        text = ""
        has_fill = False
        fill_color = None

        for child in elem:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if "prstGeom" in child_tag:
                shape_type = child.get("prst", "unknown")

            if "txBody" in child_tag:
                has_text = True
                text_parts = []
                for t in child.iter():
                    if "t" in t.tag and t.text:
                        text_parts.append(t.text)
                text = " ".join(text_parts)

            if "solidFill" in child_tag:
                has_fill = True
                for sf in child:
                    if "srgbClr" in sf.tag:
                        fill_color = sf.get("val")

        if has_text or shape_type != "unknown":
            shapes.append(
                {
                    "type": shape_type,
                    "text": text[:50] if text else "",
                    "has_fill": has_fill,
                    "fill_color": fill_color,
                }
            )

print("Slide 1 shapes/elements:")
for i, s in enumerate(shapes[:15]):
    print(
        f'{i + 1}. type={s["type"]:15s} fill={s["fill_color"] or "none":10s} text="{s["text"][:30]}"'
    )

# Check all slides for picture references
print("\nChecking all slides for images...")
for slide_num in range(1, 3):
    slide_file = f"ppt/slides/slide{slide_num}.xml"
    if slide_file in z.namelist():
        content = z.read(slide_file)
        root = ET.fromstring(content)

        # Count shapes and pictures
        shape_count = 0
        pic_count = 0
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if "sp" in tag:
                shape_count += 1
            if "pic" in tag:
                pic_count += 1

        print(f"Slide {slide_num}: shapes={shape_count}, pictures={pic_count}")
