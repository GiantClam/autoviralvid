import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ref_path = Path("C:/Users/liula/Downloads/ppt2/ppt2/1.pptx")
with zipfile.ZipFile(ref_path, "r") as z:
    content = z.read("ppt/slides/slide1.xml")
    root = ET.fromstring(content)

    # Find a shape with fill
    for elem in root.iter():
        if "sp" in elem.tag:
            # Check for bg (background) fill
            for child in elem:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if "bg" in child_tag or "bgFill" in child_tag:
                    print(f"Found: {child_tag}")

                if "solidFill" in child_tag:
                    print(f"Found solidFill at top level: {child_tag}")
                    # Check children
                    for sf in child:
                        sf_tag = sf.tag.split("}")[-1] if "}" in sf.tag else sf.tag
                        print(f"  Child: {sf_tag}")
                        if "srgbClr" in sf_tag:
                            print(f"    srgbClr val={sf.get('val')}")
