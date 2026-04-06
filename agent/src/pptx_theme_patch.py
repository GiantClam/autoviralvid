from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET


def _normalize_hex(value: str, fallback: str = "000000") -> str:
    text = str(value or "").replace("#", "").strip()
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return fallback
    try:
        int(text, 16)
    except ValueError:
        return fallback
    return text.upper()


def _palette_theme_scheme(palette_key: str) -> dict[str, str]:
    key = str(palette_key or "").strip().lower()
    if key == "education_office_classic":
        return {
            "dk1": "000000",
            "lt1": "FFFFFF",
            "dk2": "1F497D",
            "lt2": "EEECE1",
            "accent1": "4F81BD",
            "accent2": "C0504D",
            "accent3": "9BBB59",
            "accent4": "8064A2",
            "accent5": "4BACC6",
            "accent6": "F79646",
            "hlink": "0000FF",
            "folHlink": "800080",
        }
    return {}


def patch_pptx_theme_colors(pptx_bytes: bytes, palette_key: str) -> bytes:
    scheme = _palette_theme_scheme(palette_key)
    if not scheme or not isinstance(pptx_bytes, (bytes, bytearray)):
        return bytes(pptx_bytes)

    src = io.BytesIO(bytes(pptx_bytes))
    dst = io.BytesIO()

    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("ppt/theme/") and info.filename.endswith(".xml"):
                try:
                    root = ET.fromstring(data)
                    for elem in root.iter():
                        tag = elem.tag.split("}")[-1]
                        if tag not in scheme:
                            continue
                        color = _normalize_hex(scheme[tag])
                        elem.clear()
                        child = ET.SubElement(elem, "{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr")
                        child.set("val", color)
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                except Exception:
                    pass
            zout.writestr(info, data)

    return dst.getvalue()
