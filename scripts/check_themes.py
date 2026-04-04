import zipfile
import re

ref_path = "C:/Users/liula/Downloads/ppt2/ppt2/1.pptx"
z = zipfile.ZipFile(ref_path)

# List all theme files
theme_files = [n for n in z.namelist() if "theme" in n.lower() and n.endswith(".xml")]
print("Theme files found:", theme_files)
print()

for tf in theme_files:
    content = z.read(tf).decode("utf-8", errors="replace")
    print(f"=== {tf} ===")

    # Extract clrScheme colors
    matches = re.findall(
        r"<a:clrScheme[^>]*name=\"([^\"]+)\">(.*?)</a:clrScheme>", content, re.DOTALL
    )
    for name, scheme in matches:
        print(f"  Color Scheme: {name}")

        # Extract individual colors
        color_map = {
            "dk1": "Dark 1",
            "lt1": "Light 1 (Background)",
            "dk2": "Dark 2",
            "lt2": "Light 2",
            "accent1": "Accent 1 (Primary)",
            "accent2": "Accent 2 (Secondary)",
            "accent3": "Accent 3",
            "accent4": "Accent 4",
            "accent5": "Accent 5",
            "accent6": "Accent 6",
        }

        for tag, label in color_map.items():
            # Find srgbClr values
            pattern = f'<a:{tag}><a:srgbClr val="([A-F0-9]+)"'
            vals = re.findall(pattern, scheme)
            if vals:
                print(f"    {label}: #{vals[0]}")

            # Find sysClr values
            pattern2 = f'<a:{tag}><a:sysClr val="[^"]+" lastClr="([A-F0-9]+)"'
            vals2 = re.findall(pattern2, scheme)
            if vals2:
                print(f"    {label}: #{vals2[0]} (system)")
    print()
