# search-mcp

一个从零实现的 MCP 搜索服务器，提供 `web_search` 工具用于联网检索公开网页信息。

## 运行

```bash
python mcp_server.py
```

## 工具

- `web_search`
  - `query` (string, 必填): 搜索关键词
  - `max_results` (integer, 可选): 返回数量，范围 1-10，默认 5

返回内容包括标题、链接和摘要。

## 测试

```bash
python -m unittest discover -s tests -p 'test_*.py'
```
