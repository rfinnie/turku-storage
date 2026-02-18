# SPDX-PackageName: turku-storage
# SPDX-PackageSupplier: Ryan Finnie <ryan@finnie.org>
# SPDX-PackageDownloadLocation: https://github.com/rfinnie/turku-storage
# SPDX-FileCopyrightText: © 2015 Canonical Ltd.
# SPDX-FileCopyrightText: © 2015 Ryan Finnie <ryan@finnie.org>
# SPDX-License-Identifier: GPL-3.0-or-later

SYSTEMD_SYSTEM := /etc/systemd/system

install-systemd:
	install -m 0644 turku-storage-update-config.service $(SYSTEMD_SYSTEM)/turku-storage-update-config.service
	install -m 0644 turku-storage-update-config.timer $(SYSTEMD_SYSTEM)/turku-storage-update-config.timer
	systemctl enable turku-storage-update-config.timer
	systemctl start turku-storage-update-config.timer
