#!/usr/bin/env python

from distutils.core import setup

setup(
    name='turku_storage',
    description='Turku backups - storage units',
    author='Ryan Finnie',
    author_email='ryan.finnie@canonical.com',
    url='https://launchpad.net/turku',
    packages=['turku_storage'],
    scripts=['turku-storage-ping', 'turku-storage-update-config'],
)
