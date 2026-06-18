import unittest
from unittest.mock import patch, MagicMock
import requests
from parser import get_domain, is_same_domain, download_page, extract_links, crawl, extract_title

class TestParserUtilities(unittest.TestCase):
    def test_get_domain(self):
        self.assertEqual(get_domain("https://example.com/path/to/page?query=1"), "example.com")
        self.assertEqual(get_domain("http://sub.domain.example.com/"), "sub.domain.example.com")
        self.assertEqual(get_domain("invalid-url"), "")

    def test_is_same_domain(self):
        # Exact match
        self.assertTrue(is_same_domain("https://example.com/about", "example.com"))
        # Subdomain match
        self.assertTrue(is_same_domain("http://sub.example.com/blog", "example.com"))
        self.assertTrue(is_same_domain("https://nested.sub.example.com/page", "example.com"))
        # Non-matching domain
        self.assertFalse(is_same_domain("https://another.com/about", "example.com"))
        # Partial match warning: e.g. "notexample.com" should not match "example.com"
        self.assertFalse(is_same_domain("https://notexample.com/about", "example.com"))

    def test_extract_links(self):
        html_content = """
        <html>
            <body>
                <a href="/about">About Us</a>
                <a href="contact.html">Contact</a>
                <a href="https://example.com/blog#section1">Blog Section</a>
                <a href="https://external.com/page">External Site</a>
                <a href="#top">Anchor</a>
                <a href="javascript:void(0)">JS Link</a>
                <a href="">Empty Link</a>
            </body>
        </html>
        """
        base_url = "https://example.com/home/"
        extracted = extract_links(html_content, base_url)
        
        expected = [
            "https://example.com/about",
            "https://example.com/home/contact.html",
            "https://example.com/blog", # Fragment removed
            "https://external.com/page"
        ]
        self.assertEqual(extracted, expected)

    def test_extract_title(self):
        self.assertEqual(extract_title("<html><title> Test Page </title></html>"), "Test Page")
        self.assertEqual(extract_title("<html><title></title></html>"), None)
        self.assertEqual(extract_title("<html><body>No Title</body></html>"), None)



class TestDownloader(unittest.TestCase):
    @patch("requests.get")
    def test_download_page_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "<html>Content</html>"
        mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_get.return_value = mock_response
        
        content = download_page("https://example.com")
        self.assertEqual(content, "<html>Content</html>")
        mock_get.assert_called_once_with("https://example.com", timeout=5.0)

    @patch("requests.get")
    def test_download_page_non_html(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "binary_data_here"
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_get.return_value = mock_response
        
        content = download_page("https://example.com/doc.pdf")
        self.assertIsNone(content)

    @patch("requests.get")
    def test_download_page_timeout(self, mock_get):
        mock_get.side_effect = requests.Timeout("Connection timed out")
        content = download_page("https://example.com")
        self.assertIsNone(content)

    @patch("requests.get")
    def test_download_page_http_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Client Error")
        mock_get.return_value = mock_response
        
        content = download_page("https://example.com/notfound")
        self.assertIsNone(content)


class TestCrawlEngine(unittest.TestCase):
    @patch("parser.download_page")
    def test_crawl_depth_limitations_and_domain_filter(self, mock_download):
        # We will mock the website graph:
        # http://example.com/ (depth 0)
        #   -> /page1 (internal, depth 1)
        #   -> https://external.com/ (external)
        #
        # http://example.com/page1 (depth 1)
        #   -> /page2 (internal, depth 2)
        #
        # http://example.com/page2 (depth 2)
        #   -> /page3 (internal, depth 3) -> should NOT be crawled since max_depth = 2

        pages = {
            "http://example.com/": """
                <html>
                    <a href="/page1">Page 1</a>
                    <a href="https://external.com/">External</a>
                </html>
            """,
            "http://example.com/page1": """
                <html>
                    <a href="/page2">Page 2</a>
                </html>
            """,
            "http://example.com/page2": """
                <html>
                    <a href="/page3">Page 3</a>
                </html>
            """,
            "http://example.com/page3": """
                <html>
                    <a href="/done">Finished</a>
                </html>
            """
        }
        
        def download_side_effect(url, timeout=5.0):
            return pages.get(url)
            
        mock_download.side_effect = download_side_effect
        
        # Run BFS crawl starting at seed URL with max_depth=2
        mock_db = MagicMock()
        results = crawl("http://example.com/", max_depth=2, db_manager=mock_db)
        
        # Verify database calls
        # We expect 3 crawled pages to be saved to the database:
        # http://example.com/, http://example.com/page1, and http://example.com/page2
        self.assertEqual(mock_db.save_page.call_count, 3)
        mock_db.save_page.assert_any_call("http://example.com/", None)
        mock_db.save_page.assert_any_call("http://example.com/page1", None)
        mock_db.save_page.assert_any_call("http://example.com/page2", None)

        # Verify the structure of crawled results
        self.assertIn("http://example.com/", results)
        self.assertIn("http://example.com/page1", results)
        self.assertIn("http://example.com/page2", results)
        self.assertNotIn("http://example.com/page3", results)
        
        # Check actual links mapped
        self.assertEqual(results["http://example.com/"], ["http://example.com/page1"])
        self.assertEqual(results["http://example.com/page1"], ["http://example.com/page2"])
        self.assertEqual(results["http://example.com/page2"], ["http://example.com/page3"])


if __name__ == "__main__":
    unittest.main()
