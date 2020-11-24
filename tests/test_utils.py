# Turku backups - storage module
# Copyright (C) 2015-2020 Canonical Ltd., Ryan Finnie and other contributors
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <http://www.gnu.org/licenses/>.

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
