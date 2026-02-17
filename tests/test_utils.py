# SPDX-PackageName: turku-storage
# SPDX-PackageSupplier: Ryan Finnie <ryan@finnie.org>
# SPDX-PackageDownloadLocation: https://github.com/rfinnie/turku-storage
# SPDX-FileCopyrightText: © 2015 Canonical Ltd.
# SPDX-FileCopyrightText: © 2015 Ryan Finnie <ryan@finnie.org>
# SPDX-License-Identifier: GPL-3.0-or-later

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
