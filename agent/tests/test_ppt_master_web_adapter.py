from __future__ import annotations

from src import ppt_master_web_adapter as adapter


def test_extract_plain_text_strips_tags() -> None:
    raw = "<html><head><title>A</title><style>.x{}</style></head><body><h1>Hello</h1><script>bad()</script><p>World</p></body></html>"
    text = adapter._extract_plain_text(raw)
    assert "Hello" in text
    assert "World" in text
    assert "bad()" not in text


def test_extract_title() -> None:
    raw = "<html><head><title> Test Title </title></head><body></body></html>"
    assert adapter._extract_title(raw) == "Test Title"
