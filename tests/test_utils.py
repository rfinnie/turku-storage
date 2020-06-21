import unittest
import unittest.mock

from turku_storage import utils


class TestUtils(unittest.TestCase):
    def test_api_call(self):
        with unittest.mock.patch.object(utils, "requests"), unittest.mock.patch.object(
            utils, "api_call_requests"
        ) as mock_api_call_requests:
            utils.api_call("https://example.com/", "cmd", {})
        mock_api_call_requests.assert_called()

    def test_api_call_requests(self):
        with unittest.mock.patch.object(utils, "requests") as mock_requests:
            mock_requests.post.return_value.json.return_value = {
                "machine": {"sources": {}}
            }
            j = utils.api_call_requests("https://example.com/", "cmd", {})
        self.assertIn("machine", j)
