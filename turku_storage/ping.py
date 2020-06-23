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

import datetime
import json
import logging
import os
import subprocess
import sys
import tempfile
import time

from .utils import (
    load_config,
    acquire_lock,
    api_call,
    random_weighted,
    get_latest_snapshot,
    get_snapshots_to_delete,
)


class StoragePing:
    def __init__(self, uuid, config_dir="/etc/turku-storage"):
        self.arg_uuid = uuid

        self.config = load_config(config_dir)
        for k in ("name", "secret"):
            if k not in self.config:
                raise Exception("Incomplete config")

        self.logger = logging.getLogger(self.config["name"])
        self.logger.setLevel(logging.DEBUG)

        self.lh_console = logging.StreamHandler()
        self.lh_console_formatter = logging.Formatter(
            "[%(asctime)s %(name)s] %(levelname)s: %(message)s"
        )
        self.lh_console.setFormatter(self.lh_console_formatter)
        self.lh_console.setLevel(logging.ERROR)
        self.logger.addHandler(self.lh_console)

        self.lh_master = logging.FileHandler(self.config["log_file"])
        self.lh_master_formatter = logging.Formatter(
            "[%(asctime)s " + self.arg_uuid + " %(process)s] %(levelname)s: %(message)s"
        )
        self.lh_master.setFormatter(self.lh_master_formatter)
        self.lh_master.setLevel(logging.DEBUG)
        self.logger.addHandler(self.lh_master)

    def run_logging(self, args, loglevel=logging.DEBUG, cwd=None, env=None):
        self.logger.log(loglevel, "Running: %s" % repr(args))
        with subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            encoding="UTF-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as proc:
            with proc.stdout as stdout:
                for line in iter(stdout.readline, ""):
                    self.logger.log(loglevel, line.rstrip("\n"))
        self.logger.log(loglevel, "Return code: %d" % proc.returncode)
        return proc.returncode

    def process_ping(self):
        jsonin = ""
        while True:
            line = sys.stdin.readline()
            if (line == ".\n") or (not line):
                break
            jsonin = jsonin + line
        try:
            j = json.loads(jsonin)
        except ValueError:
            raise Exception("Invalid input JSON")

        lock = acquire_lock(
            os.path.join(
                self.config["lock_dir"], "turku-storage-ping-%s.lock" % self.arg_uuid
            )
        )

        if "port" not in j:
            raise Exception("Port required")
        forwarded_port = int(j["port"])

        verbose = False
        if "verbose" in j and j["verbose"]:
            verbose = True
        if verbose:
            self.lh_console.setLevel(logging.INFO)

        if "action" in j and j["action"] == "restore":
            self.logger.info(
                "Restore mode active on port %d.  Good luck." % forwarded_port
            )
            subprocess.call(["/bin/cat"])
            return

        api_out = {
            "storage": {"name": self.config["name"], "secret": self.config["secret"]},
            "machine": {"uuid": self.arg_uuid},
        }
        api_reply = api_call(self.config["api_url"], "storage_ping_checkin", api_out)

        machine = api_reply["machine"]
        scheduled_sources = machine["scheduled_sources"]
        if len(scheduled_sources) > 0:
            self.logger.info(
                "Sources to back up: %s" % ", ".join([s for s in scheduled_sources])
            )
        else:
            self.logger.info("No sources to back up now")
        for source_name in scheduled_sources:
            time_begin = time.time()
            s = scheduled_sources[source_name]
            source_username = None
            source_password = None
            if ("sources" in j) and (source_name in j["sources"]):
                if ("username" in j["sources"][source_name]) and j["sources"][
                    source_name
                ]["username"]:
                    source_username = j["sources"][source_name]["username"]
                if ("password" in j["sources"][source_name]) and j["sources"][
                    source_name
                ]["password"]:
                    source_password = j["sources"][source_name]["password"]
            else:
                if ("username" in s) and s["username"]:
                    source_username = s["username"]
                if ("password" in s) and s["password"]:
                    source_password = s["password"]
            if not (source_username and source_password):
                self.logger.error(
                    'Cannot find authentication for source "%s"' % source_name
                )
                continue
            snapshot_mode = self.config["snapshot_mode"]
            if snapshot_mode == "link-dest":
                if "large_rotating_files" in s and s["large_rotating_files"]:
                    snapshot_mode = "none"
                if "large_modifying_files" in s and s["large_modifying_files"]:
                    snapshot_mode = "none"
            if "snapshot_mode" in s and s["snapshot_mode"]:
                snapshot_mode = s["snapshot_mode"]

            var_machines = os.path.join(self.config["var_dir"], "machines")
            if not os.path.exists(var_machines):
                os.makedirs(var_machines)

            if os.path.islink(os.path.join(var_machines, machine["uuid"])):
                machine_dir = os.readlink(os.path.join(var_machines, machine["uuid"]))
            else:
                weights = {}
                for volume_name in self.config["volumes"]:
                    v = self.config["volumes"][volume_name]
                    try:
                        sv = os.statvfs(v["path"])
                    except OSError:
                        continue
                    s_t = sv.f_bsize * sv.f_blocks / 1048576
                    s_a = sv.f_bsize * sv.f_bavail / 1048576
                    pct_used = (1.0 - float(s_a) / float(s_t)) * 100.0
                    if (not v["accept_new"]) or (
                        pct_used > v["accept_new_high_water_pct"]
                    ):
                        continue
                    weights[volume_name] = s_a
                if len(weights) == 0:
                    raise Exception("Cannot find a suitable storage directory")
                chosen_volume = random_weighted(weights)
                if not chosen_volume:
                    raise Exception("Cannot find a suitable storage directory")
                machine_dir = os.path.join(
                    self.config["volumes"][chosen_volume]["path"], machine["uuid"]
                )
                os.symlink(machine_dir, os.path.join(var_machines, machine["uuid"]))
            if not os.path.exists(machine_dir):
                os.makedirs(machine_dir)

            machine_symlink = machine["unit_name"]
            if "service_name" in machine and machine["service_name"]:
                machine_symlink = machine["service_name"] + "-" + machine_symlink
            if "environment_name" in machine and machine["environment_name"]:
                machine_symlink = machine["environment_name"] + "-" + machine_symlink
            machine_symlink = machine_symlink.replace("/", "_")
            if os.path.islink(os.path.join(var_machines, machine_symlink)):
                os.unlink(os.path.join(var_machines, machine_symlink))
            if not os.path.exists(os.path.join(var_machines, machine_symlink)):
                os.symlink(machine["uuid"], os.path.join(var_machines, machine_symlink))

            self.logger.info("Begin: %s %s" % (machine["unit_name"], source_name))

            rsync_args = [
                "rsync",
                "--archive",
                "--compress",
                "--numeric-ids",
                "--delete",
                "--delete-excluded",
            ]
            rsync_args.append("--verbose")

            dest_dir = os.path.join(machine_dir, source_name)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            if snapshot_mode == "link-dest":
                snapshot_dir = os.path.join(machine_dir, "%s.snapshots" % source_name)
                if not os.path.exists(snapshot_dir):
                    os.makedirs(snapshot_dir)
                dirs = [
                    d
                    for d in os.listdir(snapshot_dir)
                    if os.path.isdir(os.path.join(snapshot_dir, d))
                ]
                base_snapshot = get_latest_snapshot(dirs)
                if base_snapshot:
                    rsync_args.append(
                        "--link-dest=%s" % os.path.join(snapshot_dir, base_snapshot)
                    )
            else:
                rsync_args.append("--inplace")
            if self.config["preserve_hard_links"]:
                rsync_args.append("--hard-links")

            filter_file = None
            filter_data = ""
            if "filter" in s:
                for filter in s["filter"]:
                    if filter.startswith("merge") or filter.startswith(":"):
                        # Do not allow local merges
                        continue
                    filter_data += "%s\n" % filter
            if "exclude" in s:
                for exclude in s["exclude"]:
                    filter_data += "- %s\n" % exclude
            if filter_data:
                filter_file = tempfile.NamedTemporaryFile(mode="w+", encoding="UTF-8")
                filter_file.write(filter_data)
                filter_file.flush()
                rsync_args.append("--filter=merge %s" % filter_file.name)

            if "bwlimit" in s and s["bwlimit"]:
                rsync_args.append("--bwlimit=%s" % s["bwlimit"])

            rsync_args.append(
                "rsync://%s@127.0.0.1:%d/%s/"
                % (source_username, forwarded_port, source_name)
            )

            rsync_args.append("%s/" % dest_dir)

            rsync_env = {"RSYNC_PASSWORD": source_password}
            returncode = self.run_logging(rsync_args, env=rsync_env)
            if returncode in (0, 24):
                success = True
            else:
                success = False
            if filter_file:
                filter_file.close()

            snapshot_name = None
            summary_output = None
            if success:
                if snapshot_mode == "link-dest":
                    summary_output = ""
                    if base_snapshot:
                        summary_output = (
                            summary_output + "Base snapshot: %s\n" % base_snapshot
                        )
                    snapshot_name = datetime.datetime.now().isoformat()
                    os.rename(dest_dir, os.path.join(snapshot_dir, snapshot_name))
                    if os.path.islink(os.path.join(snapshot_dir, "latest")):
                        os.unlink(os.path.join(snapshot_dir, "latest"))
                    if not os.path.exists(os.path.join(snapshot_dir, "latest")):
                        os.symlink(snapshot_name, os.path.join(snapshot_dir, "latest"))
                    if "retention" in s:
                        dirs = [
                            d
                            for d in os.listdir(snapshot_dir)
                            if os.path.isdir(os.path.join(snapshot_dir, d))
                        ]
                        to_delete = get_snapshots_to_delete(s["retention"], dirs)
                        for snapshot in to_delete:
                            temp_delete_tree = os.path.join(
                                snapshot_dir, "_delete-%s" % snapshot
                            )
                            os.rename(
                                os.path.join(snapshot_dir, snapshot), temp_delete_tree
                            )
                            # Should better handle this
                            subprocess.call(["rm", "-rf", temp_delete_tree])
                            summary_output = (
                                summary_output + "Removed old snapshot: %s\n" % snapshot
                            )
            else:
                summary_output = "rsync exited with return code %d" % returncode

            time_end = time.time()
            api_out = {
                "storage": {
                    "name": self.config["name"],
                    "secret": self.config["secret"],
                },
                "machine": {
                    "uuid": self.arg_uuid,
                    "sources": {
                        source_name: {
                            "success": success,
                            "snapshot": snapshot_name,
                            "summary": summary_output,
                            "time_begin": time_begin,
                            "time_end": time_end,
                        }
                    },
                },
            }
            api_reply = api_call(
                self.config["api_url"], "storage_ping_source_update", api_out
            )

            self.logger.info("End: %s %s" % (machine["unit_name"], source_name))

        self.logger.info("Done")
        lock.close()

    def main(self):
        try:
            return self.process_ping()
        except Exception as e:
            self.logger.exception(e)
            return 1


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--config-dir", "-c", type=str, default="/etc/turku-storage")
    parser.add_argument("uuid")
    return parser.parse_args()


def main():
    args = parse_args()
    sys.exit(StoragePing(args.uuid, config_dir=args.config_dir).main())
