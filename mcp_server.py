#!/usr/bin/env python3
import html
import json
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

TOOL_NAME = "web_search"
USER_AGENT = "Mozilla/5.0 (compatible; search-mcp/1.0)"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def _extract_real_url(raw_url: str) -> str:
    if raw_url.startswith("//"):
        return f"https:{raw_url}"
    parsed = urlparse(raw_url)
    if parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return raw_url


def parse_duckduckgo_results(html_text: str, max_results: int) -> list[SearchResult]:
    anchors = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippets = re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    results: list[SearchResult] = []
    for idx, (href, title_html) in enumerate(anchors[:max_results]):
        snippet_raw = ""
        if idx < len(snippets):
            snippet_raw = snippets[idx][0] or snippets[idx][1]

        title_text = html.unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
        snippet_text = html.unescape(re.sub(r"<[^>]+>", "", snippet_raw)).strip()
        results.append(
            SearchResult(
                title=title_text,
                url=_extract_real_url(html.unescape(href.strip())),
                snippet=snippet_text,
            )
        )
    return results


def web_search(query: str, max_results: int = 5) -> list[SearchResult]:
    if not query or not query.strip():
        raise ValueError("query is required")
    if not isinstance(max_results, int):
        raise ValueError("max_results must be an integer")
    max_results = max(1, min(max_results, 10))

    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return parse_duckduckgo_results(body, max_results=max_results)


def _jsonrpc_result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _jsonrpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }


def handle_request(payload: dict[str, Any]) -> dict[str, Any]:
    msg_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    if method == "initialize":
        return _jsonrpc_result(
            msg_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "search-mcp", "version": "0.1.0"},
            },
        )

    if method == "tools/list":
        return _jsonrpc_result(
            msg_id,
            {
                "tools": [
                    {
                        "name": TOOL_NAME,
                        "description": "联网搜索并返回标题、链接和摘要。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "搜索关键词",
                                },
                                "max_results": {
                                    "type": "integer",
                                    "description": "最多返回结果数量（1-10）",
                                    "minimum": 1,
                                    "maximum": 10,
                                    "default": 5,
                                },
                            },
                            "required": ["query"],
                        },
                    }
                ]
            },
        )

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        if name != TOOL_NAME:
            return _jsonrpc_error(msg_id, -32602, f"unknown tool: {name}")

        try:
            try:
                max_results = int(args.get("max_results", 5))
            except (ValueError, TypeError) as exc:
                raise ValueError("max_results must be a valid integer") from exc
            results = web_search(
                query=str(args.get("query", "")),
                max_results=max_results,
            )
        except (ValueError, TypeError) as exc:
            return _jsonrpc_error(msg_id, -32602, f"invalid arguments: {exc}")
        except (URLError, HTTPError) as exc:
            return _jsonrpc_error(msg_id, -32000, f"search failed: {exc}")

        data = [r.__dict__ for r in results]
        return _jsonrpc_result(
            msg_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(data, ensure_ascii=False, indent=2),
                    }
                ],
                "isError": False,
            },
        )

    if msg_id is None:
        return {}
    return _jsonrpc_error(msg_id, -32601, f"method not found: {method}")


def _read_message() -> dict[str, Any] | None:
    content_length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        header = line.decode("utf-8", errors="replace").strip()
        if header.lower().startswith("content-length:"):
            raw_value = header.split(":", 1)[1].strip()
            try:
                content_length = int(raw_value)
            except ValueError as exc:
                raise ValueError(f"Invalid Content-Length header value: {raw_value}") from exc

    if content_length is None:
        return None
    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    if not payload:
        return
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def main() -> int:
    while True:
        try:
            msg = _read_message()
        except ValueError as exc:
            print(str(exc), file=sys.stderr, flush=True)
            continue
        if msg is None:
            return 0
        response = handle_request(msg)
        _write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
