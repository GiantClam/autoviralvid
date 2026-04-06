from src.svg_to_pptx.pptx_notes import markdown_to_plain_text


def test_markdown_to_plain_text_preserves_list_items_with_ascii_prefix():
    text = markdown_to_plain_text("# Title\n- first item\n- second item")
    assert "Title" in text
    assert "- first item" in text
    assert "- second item" in text
