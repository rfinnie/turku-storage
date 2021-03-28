#!/usr/bin/env python3

# SPDX-PackageSummary: Turku backups - storage module
# SPDX-FileCopyrightText: Copyright (C) 2015-2020 Canonical Ltd.
# SPDX-FileCopyrightText: Copyright (C) 2015-2021 Ryan Finnie <ryan@finnie.org>
# SPDX-License-Identifier: GPL-3.0-or-later

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
