#!/usr/bin/env python3

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

import os
from setuptools import setup


def read(filename):
    with open(os.path.join(os.path.dirname(__file__), filename), encoding="utf-8") as f:
        return f.read()


setup(
    name="turku_storage",
    description="Turku backups - storage units",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    author="Ryan Finnie",
    url="https://github.com/rfinnie/turku-storage",
    python_requires="~=3.4",
    packages=["turku_storage"],
    install_requires=["requests"],
    entry_points={
        "console_scripts": [
            "turku-storage-ping = turku_storage.ping:main",
            "turku-storage-update-config = turku_storage.update_config:main",
        ]
    },
)
