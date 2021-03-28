# turku-storage

## About Turku
Turku is an agent-based backup system where the server doing the backups has no direct access to the machine being backed up.  Instead, the machine's agent coordinates with an API server and opens a reverse tunnel to the storage server when it is time to do a backup.

Turku is comprised of the following components:

* [turku-api](https://github.com/rfinnie/turku-api), a Django web application which acts as an API server and coordinator.
* [turku-storage](https://github.com/rfinnie/turku-storage), an agent installed on the servers which do the actual backups.
* [turku-agent](https://github.com/rfinnie/turku-agent), an agent installed on the machines to be backed up.

## Installation

turku-storage is a standard Python 3 package.  It requires the following non-stdlib Python packages:

* requests, for HTTPS communication with turku-api.

A dedicated non-root user is required for agents to SSH into; the username `turku-ping` is assumed.

Create the necessary sudoers configuration to allow `turku-ping` to run `turku-storage-ping`, for example in `/etc/sudoers.d/turku-storage`:

```
turku-ping  ALL=(ALL) NOPASSWD: /usr/local/bin/turku-storage-ping

```

Several periodic programs will also need to be run; .cron or systemd .service/.timer examples are available in the source distribution (pick either cron or systemd).

## Configuration

Standard configuration is done with `.json` files and is supported in all installations.  Additionally, equivalent `.yaml` files are supported if the PyYAML package installed. In the following sections, `.json` examples will be provided.

Once turku-storage is installed, create `/etc/turku-storage/config.d/config.json` with the following information:

```json
{
    "api_auth": "STORAGE AUTH STRING",
    "api_url": "https://turku.example.com/v1",
    "authorized_keys_command": "sudo /usr/local/bin/turku-storage-ping",
    "name": "primary",
    "secret": "RANDOM SECRET",
    "snapshot_mode": "link-dest",
    "ssh_ping_host": "primary.turku.example.com",
    "ssh_ping_port": 22,
    "ssh_ping_user": "turku-ping",
    "volumes": {
        "default": {
            "path": "/media/backup/turku"
        }
    }
}
```

* **api_auth** - Registration string for a Storage Auth as defined in turku-api.
* **api_url** - URL of the turku-api service.
* **authorized_keys_command** - Command to invoke `turku-storage-ping` when building `authorized_keys`.
* **name** - Short name of this Storage unit.
* **secret** - Random string to be used as an authentication identifier for this Storage unit.
* **ssh_ping_host**, **ssh_ping_port**, **ssh_ping_user** - Hostname, port and username which turku-api will give to turku-agent to SSH to this Storage unit. The hostname may be an IP address instead of an FQDN.
* **volumes** - Dictionary of storage volumes to be defined on this Storage unit.

Once configured, run the following to register the Storage unit:

```
sudo turku-storage-update-config
```

## Running

Once registered, the Storage unit will require little upkeep.  It will periodically run `turku-storage-update-config` to pull in information about agents assigned to it, and the agents will connect to it via SSH when turku-api tells the agent it is time to do so.  Actual backups are stored in the volume paths, while symlinks to them are available in `/var/lib/turku-storage/machines`.

One situation which will require direct Storage unit access is restores.  When `turku-agent-ping --restore` is run, it sets up a writable rsync module on the machine to restore to, sets up an idle reverse SSH tunnel to the Storage unit, then gives basic information of what to do on the storage unit. For example:

```
$ sudo turku-agent-ping --restore
Entering restore mode.

This machine's sources are on the following storage units:
    primary
        baremetal

Machine UUID: 9bef0a75-5a9b-43f7-a66a-7e8c6d7ad91d
Machine unit: examplemachine
Storage unit: primary
Local destination path: /var/backups/turku-agent/restore
Sample restore usage from storage unit:
    cd /var/lib/turku-storage/machines/9bef0a75-5a9b-43f7-a66a-7e8c6d7ad91d/
    RSYNC_PASSWORD=RNxHVnnl2zt33ktbkccT rsync -avzP --numeric-ids ${P?}/ \
        rsync://e908212b-e35f-453e-9503-0de047ee9e22@127.0.0.1:64951/turku-restore/

[2020-10-01 06:40:59,439 primary] INFO: Restore mode active on port 64951.  Good luck.
```

## License

Turku backups - storage module

Copyright (C) 2015-2021 Canonical Ltd., Ryan Finnie and other contributors

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program.  If not, see <https://www.gnu.org/licenses/>.
