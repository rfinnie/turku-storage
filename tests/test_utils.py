# SPDX-PackageSummary: Turku backups - storage module
# SPDX-FileCopyrightText: Copyright (C) 2015-2020 Canonical Ltd.
# SPDX-FileCopyrightText: Copyright (C) 2015-2021 Ryan Finnie <ryan@finnie.org>
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
