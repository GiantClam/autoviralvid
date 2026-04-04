import zipfile
import xml.etree.ElementTree as ET

ref_path = "C:/Users/liula/Downloads/ppt2/ppt2/1.pptx"
z = zipfile.ZipFile(ref_path)

# Check which theme is used by each slide
print("=== Checking which theme each slide uses ===\n")

for slide_num in [1, 2, 3]:
    slide_file = f"ppt/slides/slide{slide_num}.xml"
    content = z.read(slide_file)

    # Find theme reference
    theme_id = None
    root = ET.fromstring(content)
    for elem in root.iter():
        if "theme" in elem.tag.lower():
            # Get relationship
            for attr in elem.attrib:
                if "id" in attr.lower():
                    theme_id = elem.attrib[attr]
                    break

    # Also check relationships
    rel_file = f"ppt/slides/_rels/slide{slide_num}.xml.rels"
    if rel_file in z.namelist():
        rel_content = z.read(rel_file).decode("utf-8", errors="replace")
        import re

        # Find theme relationship
        theme_rels = re.findall(
            r"Type=\"[^\"]*theme[^\"]*\"[^>]*Id=\"([^\"]+)\"", rel_content
        )
        print(f"Slide {slide_num}: uses theme relationship ID = {theme_rels}")

print("\n=== Checking slide background colors ===")
# Check slide 1 background
slide1 = z.read("ppt/slides/slide1.xml")
root = ET.fromstring(slide1)

# Check bgFill
for elem in root.iter():
    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
    if "bgFill" in tag or (tag == "bg" and "fill" in tag.lower()):
        print(f"Background fill: {elem.tag}")

print("\n=== Common colors used in slides (sampling) ===")
# Sample a few slides for common colors
all_colors = set()
for slide_num in [1, 2, 10]:
    content = z.read(f"ppt/slides/slide{slide_num}.xml")
    import re

    colors = re.findall(
        r'val="([A-Fa-f0-9]{6})"', content.decode("utf-8", errors="replace")
    )
    all_colors.update([c.upper() for c in colors])

print("Colors found:", sorted(all_colors)[:15])
