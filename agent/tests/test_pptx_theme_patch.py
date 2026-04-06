import io
import zipfile

from src.pptx_theme_patch import patch_pptx_theme_colors


def _fake_theme_pptx() -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "ppt/theme/theme1.xml",
            """<?xml version='1.0' encoding='UTF-8'?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <a:themeElements>
    <a:clrScheme name="Test">
      <a:dk1><a:srgbClr val="111111"/></a:dk1>
      <a:lt1><a:srgbClr val="EEEEEE"/></a:lt1>
      <a:dk2><a:srgbClr val="222222"/></a:dk2>
      <a:lt2><a:srgbClr val="DDDDDD"/></a:lt2>
      <a:accent1><a:srgbClr val="333333"/></a:accent1>
      <a:accent2><a:srgbClr val="444444"/></a:accent2>
      <a:accent3><a:srgbClr val="555555"/></a:accent3>
      <a:accent4><a:srgbClr val="666666"/></a:accent4>
      <a:accent5><a:srgbClr val="777777"/></a:accent5>
      <a:accent6><a:srgbClr val="888888"/></a:accent6>
    </a:clrScheme>
  </a:themeElements>
</a:theme>
""",
        )
    return data.getvalue()


def test_patch_pptx_theme_colors_updates_office_classic_scheme():
    out = patch_pptx_theme_colors(_fake_theme_pptx(), "education_office_classic")
    with zipfile.ZipFile(io.BytesIO(out), "r") as z:
        xml = z.read("ppt/theme/theme1.xml").decode("utf-8")
    assert "1F497D" in xml
    assert "4F81BD" in xml
    assert "C0504D" in xml
    assert "9BBB59" in xml
    assert "8064A2" in xml
