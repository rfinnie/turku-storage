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
import httplib
import urlparse
import subprocess
import datetime
import re
import fcntl
import logging
import tempfile
import copy
import time


CONFIG_D = '/etc/turku-storage/config.d'
LOCK_DIR = '/var/lock'


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


def get_snapshots_to_delete(retention, snapshots):
    snapshot_dict = {}
    for ss in snapshots:
        if 'save' in ss:
            continue
        # If a snapshot name matches one of these formats
        #     1424392089.43
        #     2015-02-20T03:20:36
        #     2015-02-20T03:21:18.152575
        # use it as a timestamp, otherwise ignore it
        try:
            snapshot_dict[datetime.datetime.strptime(ss, '%Y-%m-%dT%H:%M:%S.%f')] = ss
            continue
        except ValueError:
            pass
        try:
            snapshot_dict[datetime.datetime.strptime(ss, '%Y-%m-%dT%H:%M:%S')] = ss
            continue
        except ValueError:
            pass
        try:
            snapshot_dict[datetime.datetime.utcfromtimestamp(float(ss))] = ss
            continue
        except ValueError:
            pass

    now = datetime.datetime.now()
    to_keep = []
    for ritem in retention.split(','):
        ritem = ritem.strip()
        r = re.findall('^earliest of (\d+) (day|week|month)', ritem)
        if len(r) > 0:
            earliest_num = int(r[0][0])
            earliest_word = r[0][1]
            if earliest_word == 'fortnight':
                earliest_word = 'week'
                earliest_num = earliest_num * 2
            if earliest_word == 'day':
                cutoff_time = (now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=(earliest_num - 1)))
            elif earliest_word == 'week':
                cutoff_time = now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=((now.weekday() + 1) % 7))
                for i in range(earliest_num - 1):
                    cutoff_time = (cutoff_time - datetime.timedelta(weeks=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            elif earliest_word == 'month':
                cutoff_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                for i in range(earliest_num - 1):
                    cutoff_time = (cutoff_time - datetime.timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                cutoff_time = (now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=(earliest_num - 1)))
            candidate_s = None
            for s in snapshot_dict.keys():
                if s < cutoff_time:
                    continue
                if not candidate_s:
                    candidate_s = s
                    continue
                if s >= candidate_s:
                    continue
                candidate_s = s
            if candidate_s and candidate_s not in to_keep:
                to_keep.append(candidate_s)
        r = re.findall('^last (\d+) day', ritem)
        if len(r) > 0:
            last_days = int(r[0])
            cutoff_time = (now - datetime.timedelta(days=last_days))
            for s in snapshot_dict.keys():
                if s < cutoff_time:
                    continue
                if s not in to_keep:
                    to_keep.append(s)
        r = re.findall('^last (\d+) snapshot', ritem)
        if len(r) > 0:
            last_snapshots = int(r[0])
            i = 0
            for s in sorted(snapshot_dict.keys(), reverse=True):
                i = i + 1
                if s not in to_keep:
                    to_keep.append(s)
                if i == last_snapshots:
                    break

    # If something went wrong and nothing was found to keep,
    # don't delete everything.
    if len(to_keep) == 0:
        return []

    to_delete = []
    for s in snapshot_dict.keys():
        if not s in to_keep:
            to_delete.append(snapshot_dict[s])
    return to_delete


class StoragePing():
    def __init__(self, arg_uuid):
        self.arg_uuid = arg_uuid

        config = {}
        # Merge in config.d/*.json
        config_files = [os.path.join(CONFIG_D, fn) for fn in os.listdir(CONFIG_D) if fn.endswith('.json') and os.path.isfile(os.path.join(CONFIG_D, fn)) and os.access(os.path.join(CONFIG_D, fn), os.R_OK)]
        config_files.sort()
        for file in config_files:
            with open(file) as f:
                j = json.load(f)
            config = dict_merge(config, j)

        for k in ('api_url', 'api_auth', 'name', 'secret', 'storage_dir'):
            if k not in config:
                return

        if not 'log_file' in config:
            config['log_file'] = '/var/log/turku-storage.log'

        if not 'snapshot_mode' in config:
            config['snapshot_mode'] = 'none'

        self.config = config

        self.logger = logging.getLogger(self.config['name'])
        self.logger.setLevel(logging.DEBUG)

        self.lh_console = logging.StreamHandler()
        self.lh_console_formatter = logging.Formatter('[%(asctime)s %(name)s] %(levelname)s: %(message)s')
        self.lh_console.setFormatter(self.lh_console_formatter)
        self.lh_console.setLevel(logging.ERROR)
        self.logger.addHandler(self.lh_console)

        self.lh_master = logging.FileHandler(self.config['log_file'])
        self.lh_master_formatter = logging.Formatter('[%(asctime)s ' + self.arg_uuid + ' %(process)s] %(levelname)s: %(message)s')
        self.lh_master.setFormatter(self.lh_master_formatter)
        self.lh_master.setLevel(logging.DEBUG)
        self.logger.addHandler(self.lh_master)

    def api_call(self, api_url, cmd, post_data, timeout=5):
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

    def run_logging(self, args, loglevel=logging.DEBUG, cwd=None, env=None, return_output=False):
        self.logger.log(loglevel, 'Running: %s' % repr(args))
        t = tempfile.NamedTemporaryFile()
        self.logger.log(loglevel, '(Command output is in %s until written here at the end)' % t.name)
        returncode = subprocess.call(args, cwd=cwd, env=env, stdout=t, stderr=t)
        t.flush()
        t.seek(0)
        out = ''
        for line in t:
            if return_output:
                out = out + line
            self.logger.log(loglevel, line.rstrip('\n'))
        t.close()
        self.logger.log(loglevel, 'Return code: %d' % returncode)
        if return_output:
            return (returncode, out)
        else:
            return returncode

    def process_ping(self):
        jsonin = ''
        while True:
            l = sys.stdin.readline()
            if (l == '.\n') or (not l):
                break
            jsonin = jsonin + l
        try:
            j = json.loads(jsonin)
        except ValueError:
            raise Exception('Invalid input JSON')

        lock = open(os.path.join(LOCK_DIR, 'turku-ping-%s.lock' % self.arg_uuid), 'w')
        try:
            fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError, e:
            import errno
            if e.errno in (errno.EACCES, errno.EAGAIN):
                raise Exception('Previous run still in progress')

        if not 'port' in j:
            raise Exception('Port required')
        forwarded_port = int(j['port'])

        verbose = False
        if 'verbose' in j and j['verbose']:
            verbose = True
        if verbose:
            self.lh_console.setLevel(logging.INFO)

        if 'action' in j and j['action'] == 'restore':
            self.logger.info('Restore mode active on port %d.  Good luck.' % forwarded_port)
            subprocess.call(['/bin/cat'])
            return

        api_out = {
            'name': self.config['name'],
            'secret': self.config['secret'],
            'machine_uuid': self.arg_uuid,
        }
        api_reply = self.api_call(self.config['api_url'], 'storage_ping_checkin', api_out)

        machine = api_reply['machine']
        scheduled_sources = api_reply['scheduled_sources']
        if len(scheduled_sources) > 0:
            self.logger.info('Sources to back up: %s' % ', '.join([s['name'] for s in scheduled_sources]))
        else:
            self.logger.info('No sources to back up now')
        for s in scheduled_sources:
            time_begin = time.time()
            machine_dir = os.path.join(self.config['storage_dir'], machine['uuid'])
            if not os.path.exists(machine_dir):
                os.makedirs(machine_dir)

            self.logger.info('Begin: %s %s' % (machine['unit_name'], s['name']))

            rsync_args = ['rsync', '--archive', '--compress', '--numeric-ids', '--delete', '--delete-excluded']
            rsync_args.append('--verbose')

            if self.config['snapshot_mode'] == 'attic':
                rsync_args.append('--inplace')
            elif self.config['snapshot_mode'] == 'none':
                rsync_args.append('--inplace')

            filter_file = tempfile.NamedTemporaryFile()
            if 'filter' in s:
                for filter in s['filter']:
                    if filter.startswith('merge') or filter.startswith(':'):
                        # Do not allow local merges
                        continue
                    filter_file.write('%s\n' % filter)
            if 'exclude' in s:
                for exclude in s['exclude']:
                    filter_file.write('- %s\n' % exclude)
            filter_file.flush()
            rsync_args.append('--filter=merge %s' % filter_file.name)

            rsync_args.append('rsync://%s@127.0.0.1:%d/%s/' % (s['username'], forwarded_port, s['name']))

            storage_dir = os.path.join(machine_dir, s['name'])
            if not os.path.exists(storage_dir):
                os.makedirs(storage_dir)
            rsync_args.append('%s/' % storage_dir)

            machine_symlink = machine['unit_name']
            if 'service_name' in machine and machine['service_name']:
                machine_symlink = machine['service_name'] + '-'
            if 'environment_name' in machine and machine['environment_name']:
                machine_symlink = machine['environment_name'] + '-'
            machine_symlink = machine_symlink.replace('/', '_')
            if os.path.exists(os.path.join(self.config['storage_dir'], machine_symlink)):
                if os.path.islink(os.path.join(self.config['storage_dir'], machine_symlink)):
                    if not os.readlink(os.path.join(self.config['storage_dir'], machine_symlink)) == machine['uuid']:
                        os.symlink(machine['uuid'], os.path.join(self.config['storage_dir'], machine_symlink))
            else:
                os.symlink(machine['uuid'], os.path.join(self.config['storage_dir'], machine_symlink))

            rsync_env = {
                'RSYNC_PASSWORD': s['password']
            }
            returncode = self.run_logging(rsync_args, env=rsync_env)
            if returncode in (0, 24):
                success = True
            else:
                success = False
            filter_file.close()

            summary_output = ''
            if self.config['snapshot_mode'] == 'attic':
                attic_dir = '%s.attic' % storage_dir
                if not os.path.exists(attic_dir):
                    attic_args = ['attic', 'init', attic_dir]
                    self.run_logging(attic_args)
                now = datetime.datetime.now()
                attic_args = ['attic', 'create', '--numeric-owner', '%s::%s' % (attic_dir, now.isoformat()), '.']
                self.run_logging(attic_args, cwd=storage_dir)
                if 'retention' in s:
                    attic_snapshots = re.findall('^([\w\.\-\:]+)', subprocess.check_output(['attic', 'list', attic_dir]), re.M)
                    to_delete = get_snapshots_to_delete(s['retention'], attic_snapshots)
                    for snapshot in to_delete:
                        attic_args = ['attic', 'delete', '%s::%s' % (attic_dir, snapshot)]
                        self.run_logging(attic_args)
                attic_args = ['attic', 'info', '%s::%s' % (attic_dir, now.isoformat())]
                (ret, summary_output) = self.run_logging(attic_args, return_output=True)
            elif self.config['snapshot_mode'] == 'link-dest':
                # XXX todo
                pass

            time_end = time.time()
            api_out = {
                'name': self.config['name'],
                'secret': self.config['secret'],
                'machine_uuid': self.arg_uuid,
                'source_name': s['name'],
                'success': success,
                'backup_data': {
                    'summary': summary_output,
                    'time_begin': time_begin,
                    'time_end': time_end,
                },
            }
            api_reply = self.api_call(self.config['api_url'], 'storage_ping_source_update', api_out)

            self.logger.info('End: %s %s' % (machine['unit_name'], s['name']))

        self.logger.info('Done')

    def main(self):
        try:
            return self.process_ping()
        except Exception as e:
            self.logger.exception(e.message)
            return 1

def main(argv):
    if len(argv) < 2:
        return 1
    sys.exit(StoragePing(argv[1]).main())
