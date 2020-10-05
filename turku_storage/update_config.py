# Turku backups - storage module
# Copyright 2015 Canonical Ltd.
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
import random
import time

try:
    import pwd
except ImportError as e:
    pwd = e

from .utils import load_config, acquire_lock, api_call, SafeWrite


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--config-dir", "-c", type=str, default="/etc/turku-storage")
    parser.add_argument("--wait", "-w", type=float)
    return parser.parse_args()


def main():
    args = parse_args()

    # Sleep a random amount of time if requested
    if args.wait:
        time.sleep(random.uniform(0, args.wait))

    config = load_config(args.config_dir)

    lock = acquire_lock(
        os.path.join(config["lock_dir"], "turku-storage-update-config.lock")
    )

    space_total = 0
    space_available = 0
    seen_devs = []
    for volume_name in config["volumes"]:
        v = config["volumes"][volume_name]
        st_dev = os.stat(v["path"]).st_dev
        if st_dev in seen_devs:
            continue
        seen_devs.append(st_dev)
        try:
            sv = os.statvfs(v["path"])
        except OSError:
            continue
        s_t = sv.f_bsize * sv.f_blocks / 1048576
        s_a = sv.f_bsize * sv.f_bavail / 1048576
        pct_used = (1.0 - float(s_a) / float(s_t)) * 100.0
        if (not v["accept_new"]) or (pct_used > v["accept_new_high_water_pct"]):
            s_a = 0
        space_total += s_t
        space_available += s_a

    api_out = {
        "storage": {
            "name": config["name"],
            "secret": config["secret"],
            "ssh_ping_host": config["ssh_ping_host"],
            "ssh_ping_port": config["ssh_ping_port"],
            "ssh_ping_user": config["ssh_ping_user"],
            "ssh_ping_host_keys": config["ssh_ping_host_keys"],
            "space_total": space_total,
            "space_available": space_available,
        }
    }
    if ("api_auth_name" in config) and ("api_auth_secret" in config):
        api_out["auth"] = {
            "name": config["api_auth_name"],
            "secret": config["api_auth_secret"],
        }
    else:
        # XXX legacy
        api_out["auth"] = config["api_auth"]
    if "published" in config:
        api_out["storage"]["published"] = config["published"]

    api_reply = api_call(config["api_url"], "storage_update_config", api_out)

    authorized_keys_out = "# Automatically generated, please do not edit\n"
    authorized_keys_out += (
        "# Local additions may be placed in %s.static\n"
        % config["authorized_keys_file"]
    )
    if os.path.isfile(config["authorized_keys_file"] + ".static"):
        with open(config["authorized_keys_file"] + ".static") as f:
            authorized_keys_out += f.read()
    for machine_uuid in api_reply["machines"]:
        machine = api_reply["machines"][machine_uuid]
        authorized_keys_out += '%s,command="%s %s" %s (%s)\n' % (
            "no-pty,no-agent-forwarding,no-X11-forwarding,no-user-rc",
            config["authorized_keys_command"],
            machine_uuid,
            machine["ssh_public_key"],
            machine["unit_name"],
        )

    if isinstance(pwd, ImportError):
        f_uid = None
        f_gid = None
    else:
        f_uid = pwd.getpwnam(config["authorized_keys_user"]).pw_uid
        f_gid = pwd.getpwnam(config["authorized_keys_user"]).pw_gid
    keys_dirname = os.path.dirname(config["authorized_keys_file"])
    if not os.path.isdir(keys_dirname):
        os.makedirs(keys_dirname)
        if f_uid is not None:
            os.chown(keys_dirname, f_uid, f_gid)
    with SafeWrite(config["authorized_keys_file"]) as f:
        if f_uid is not None:
            os.fchown(f.fileno(), f_uid, f_gid)
        f.write(authorized_keys_out)

    lock.close()
