# Turku backups - storage module
# Copyright (C) 2015-2020 Canonical Ltd., Ryan Finnie and other contributors
#
# SPDX-License-Identifer: GPL-3.0-or-later

import unittest
import unittest.mock

from turku_storage import utils


class TestUtils(unittest.TestCase):
    def test_api_call(self):
        with unittest.mock.patch.object(utils, "requests") as mock_requests:
            mock_requests.post.return_value.json.return_value = {
                "machine": {"sources": {}}
            }
            j = utils.api_call("https://example.com/", "cmd", {})
        self.assertIn("machine", j)
