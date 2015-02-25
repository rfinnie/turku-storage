#!/usr/bin/env python

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

from __future__ import print_function
import json
import os
import sys
import time
import httplib
import urlparse
import glob
import random
import platform
import socket
import pwd
import copy
import string

CONFIG_FILE = '/etc/turku-storage/config.json'
CONFIG_D = '/etc/turku-storage/config.d'


def json_dump_p(obj, f):
    """Calls json.dump with standard (pretty) formatting"""
    return json.dump(obj, f, sort_keys=True, indent=4, separators=(',', ': '))


def json_dumps_p(obj):
    """Calls json.dumps with standard (pretty) formatting"""
    return json.dumps(obj, sort_keys=True, indent=4, separators=(',', ': '))


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--wait', '-w', type=float)
    return parser.parse_args()


def api_call(api_url, cmd, post_data, timeout=5):
    url = urlparse.urlparse(api_url)
    if url.scheme == 'https':
        h = httplib.HTTPSConnection(url.netloc, timeout=timeout)
    else:
        h = httplib.HTTPConnection(url.netloc, timeout=timeout)
    out = json.dumps(post_data)
    h.putrequest('POST', '%s/%s' % (url.path, cmd))
    h.putheader('Content-Type', 'application/json')
    h.putheader('Content-Length', len(out))
    h.putheader('Accept', 'application/json')
    h.endheaders()
    h.send(out)

    res = h.getresponse()
    if not res.status == httplib.OK:
        raise Exception('Received error %d (%s) from API server' % (res.status, res.reason))
    if not res.getheader('content-type') == 'application/json':
        raise Exception('Received invalid reply from API server')
    try:
        return json.load(res)
    except ValueError:
        raise Exception('Received invalid reply from API server')


def dict_merge(s, m):
    """Recursively merge one dict into another."""
    if not isinstance(m, dict):
        return m
    out = copy.deepcopy(s)
    for k, v in m.items():
        if k in out and isinstance(out[k], dict):
            out[k] = dict_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def check_directories():
    for d in (CONFIG_D,):
        if not os.path.isdir(d):
            os.makedirs(d)
            os.chmod(d, 0o700)


def main(argv):
    args = parse_args()

    check_directories()

    # Sleep a random amount of time if requested
    if args.wait:
        time.sleep(random.uniform(0, args.wait))

    config = {}
    # Merge in config.d/*.json
    config_files = [os.path.join(CONFIG_D, fn) for fn in os.listdir(CONFIG_D) if fn.endswith('.json') and os.path.isfile(os.path.join(CONFIG_D, fn)) and os.access(os.path.join(CONFIG_D, fn), os.R_OK)]
    config_files.sort()
    for file in config_files:
        with open(file) as f:
            j = json.load(f)
        config = dict_merge(config, j)

    for k in ('api_url', 'api_auth'):
        if k not in config:
            return

    write_name_data = False
    if not 'name' in config:
        config['name'] = platform.node()
        write_name_data = True
    if not 'secret' in config:
        config['secret'] = ''.join(random.choice(string.ascii_letters + string.digits) for i in range(30))
        write_name_data = True
    if write_name_data:
        with open(os.path.join(CONFIG_D, '10-name.json'), 'w') as f:
            os.chmod(os.path.join(CONFIG_D, '10-name.json'), 0o600)
            json_dump_p({'name': config['name'], 'secret': config['secret']}, f)

    if not 'ssh_ping_host' in config:
        config['ssh_ping_host'] = socket.getfqdn()
    if not 'ssh_ping_port' in config:
        config['ssh_ping_port'] = 22
    if not 'ssh_ping_user' in config:
        config['ssh_ping_user'] = 'root'
    if not 'ssh_ping_host_keys' in config:
        config['ssh_ping_host_keys'] = []
        keys_glob = '/etc/ssh/ssh_host_*_key.pub'
        if 'ssh_ping_host_keys_glob' in config:
            keys_glob = config['ssh_ping_host_keys_glob']
        for pubkey in glob.glob(keys_glob):
            with open(pubkey) as f:
                config['ssh_ping_host_keys'].append(f.read().rstrip())
    if not 'authorized_keys_file' in config:
        config['authorized_keys_file'] = '%s/.ssh/authorized_keys' % pwd.getpwnam(config['ssh_ping_user']).pw_dir
    if not 'authorized_keys_user' in config:
        config['authorized_keys_user'] = config['ssh_ping_user']
    if not 'authorized_keys_command' in config:
        config['authorized_keys_command'] = 'turku-storage-ping'

    api_out = {
        'auth': config['api_auth'],
        'storage': {
            'name': config['name'],
            'secret': config['secret'],
            'ssh_ping_host': config['ssh_ping_host'],
            'ssh_ping_port': config['ssh_ping_port'],
            'ssh_ping_user': config['ssh_ping_user'],
            'ssh_ping_host_keys': config['ssh_ping_host_keys'],
        },
    }

    api_reply = api_call(config['api_url'], 'storage_update_config', api_out)

    authorized_keys_out = ''
    for machine_uuid in api_reply['machines']:
        machine = api_reply['machines'][machine_uuid]
        authorized_keys_out += 'no-pty,no-agent-forwarding,no-X11-forwarding,no-user-rc,command="%s %s" %s (%s)\n' % (config['authorized_keys_command'], machine_uuid, machine['ssh_public_key'], machine['unit_name'])

    f_uid = pwd.getpwnam(config['authorized_keys_user']).pw_uid
    f_gid = pwd.getpwnam(config['authorized_keys_user']).pw_gid
    keys_dirname = os.path.dirname(config['authorized_keys_file'])
    if not os.path.isdir(keys_dirname):
        os.makedirs(keys_dirname)
        os.chown(keys_dirname, f_uid, f_gid)
    with open(config['authorized_keys_file'], 'w') as f:
        os.fchown(f.fileno(), f_uid, f_gid)
        f.write(authorized_keys_out)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
