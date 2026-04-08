"""Web search/fetch adapter for ppt-master research stage."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from typing import Any, Dict, List
from urllib import error as urllib_error
from urllib import request as urllib_request


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _search_serper_sync(
    *,
    query: str,
    api_key: str,
    num: int = 5,
    gl: str = "us",
    hl: str = "zh-cn",
    api_url: str = "https://google.serper.dev/search",
) -> List[Dict[str, str]]:
    payload = json.dumps(
        {
            "q": query,
            "num": max(1, min(10, int(num))),
            "gl": gl,
            "hl": hl,
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        api_url,
        data=payload,
        method="POST",
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=16) as resp:  # nosec B310
            raw = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
    except (
        urllib_error.URLError,
        urllib_error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        return []

    organic = parsed.get("organic") if isinstance(parsed, dict) else []
    if not isinstance(organic, list):
        return []

    items: List[Dict[str, str]] = []
    for row in organic:
        if not isinstance(row, dict):
            continue
        title = _normalize_text(row.get("title"), "")
        url = _normalize_text(row.get("link"), "")
        snippet = _normalize_text(row.get("snippet"), "")
        if not title or not url:
            continue
        items.append({"title": title, "url": url, "snippet": snippet})
        if len(items) >= max(1, min(10, int(num))):
            break
    return items


def _extract_title(html_text: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html_text)
    if not match:
        return ""
    return _normalize_text(html.unescape(match.group(1)), "")


def _extract_plain_text(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html_text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fetch_url_text(
    *,
    url: str,
    max_chars: int = 6000,
    timeout_sec: int = 18,
) -> Dict[str, str]:
    req = urllib_request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ppt-master-web-adapter/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib_request.urlopen(req, timeout=max(3, timeout_sec)) as resp:  # nosec B310
        content_type = _normalize_text(resp.headers.get("Content-Type"), "").lower()
        if "text/html" not in content_type and "xml" not in content_type and "text/plain" not in content_type:
            raise RuntimeError(f"unsupported_content_type:{content_type or 'unknown'}")
        raw = resp.read(max(3_000_000, max_chars * 3))
    html_text = raw.decode("utf-8", errors="replace")
    title = _extract_title(html_text)
    text = _extract_plain_text(html_text)
    return {
        "title": title,
        "content": text[: max(500, min(50000, int(max_chars)))],
    }


def _print_json(payload: Dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(raw.encode("utf-8"))
    else:
        sys.stdout.write(raw)
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="ppt-master web search/fetch adapter")
    subparsers = parser.add_subparsers(dest="command")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--num", type=int, default=5)
    search_parser.add_argument("--language", default="zh-CN")
    search_parser.add_argument("--gl", default="")
    search_parser.add_argument("--hl", default="")

    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.add_argument("--url", required=True)
    fetch_parser.add_argument("--max-chars", type=int, default=6000)
    fetch_parser.add_argument("--timeout-sec", type=int, default=18)

    args = parser.parse_args()
    if args.command == "search":
        api_key = _normalize_text(os.getenv("SERPER_API_KEY", ""), "")
        if not api_key:
            _print_json({"ok": False, "error": "missing_SERPER_API_KEY", "items": []})
            return 1
        language = _normalize_text(args.language, "zh-CN")
        gl = _normalize_text(args.gl, "cn" if language == "zh-CN" else "us")
        hl = _normalize_text(args.hl, "zh-cn" if language == "zh-CN" else "en")
        items = _search_serper_sync(
            query=_normalize_text(args.query, ""),
            api_key=api_key,
            num=max(1, min(10, int(args.num))),
            gl=gl,
            hl=hl,
            api_url=_normalize_text(
                os.getenv("SERPER_API_URL", "https://google.serper.dev/search"),
                "https://google.serper.dev/search",
            ),
        )
        _print_json(
            {
                "ok": True,
                "query": _normalize_text(args.query, ""),
                "count": len(items),
                "items": items,
            }
        )
        return 0

    if args.command == "fetch":
        try:
            data = _fetch_url_text(
                url=_normalize_text(args.url, ""),
                max_chars=max(500, min(50000, int(args.max_chars))),
                timeout_sec=max(3, min(60, int(args.timeout_sec))),
            )
        except Exception as exc:
            _print_json(
                {
                    "ok": False,
                    "url": _normalize_text(args.url, ""),
                    "error": str(exc),
                }
            )
            return 1
        _print_json(
            {
                "ok": True,
                "url": _normalize_text(args.url, ""),
                "title": data.get("title", ""),
                "content": data.get("content", ""),
                "content_length": len(_normalize_text(data.get("content"), "")),
            }
        )
        return 0

    _print_json({"ok": False, "error": "missing_command"})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
