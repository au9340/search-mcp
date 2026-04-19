import unittest

from mcp_server import _extract_real_url, handle_request, parse_duckduckgo_results


class ParseSearchResultsTest(unittest.TestCase):
    def test_parse_duckduckgo_results(self):
        html = '''
        <a class="result__a" href="https://example.com/a">A title</a>
        <div class="result__snippet">A snippet</div>
        <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fb">B title</a>
        <a class="result__snippet">B snippet</a>
        '''
        results = parse_duckduckgo_results(html, max_results=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "A title")
        self.assertEqual(results[0].url, "https://example.com/a")
        self.assertEqual(results[1].url, "https://example.com/b")

    def test_extract_real_url_handles_protocol_relative(self):
        self.assertEqual(_extract_real_url("//example.com"), "https://example.com")


class HandleRequestTest(unittest.TestCase):
    def test_tools_list_contains_web_search(self):
        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = response["result"]["tools"]
        self.assertEqual(tools[0]["name"], "web_search")


if __name__ == "__main__":
    unittest.main()
