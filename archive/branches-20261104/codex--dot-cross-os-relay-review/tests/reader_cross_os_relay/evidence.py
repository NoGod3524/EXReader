# SPDX-License-Identifier: MIT
"""Strict relay evidence validators. Invoked and tested only inside Actions."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath
import re
import stat

from relaylib import INVENTORY_FORMAT, need, parse_no_duplicates


def strict_json(data):
    return json.loads(data, object_pairs_hook=parse_no_duplicates)


def verify_job(identity, job, name, os_name=None):
    need(job.get('name') == name and job.get('status') == 'completed' and job.get('conclusion') == 'success', 'job incomplete/failed: ' + name)
    for actual, expected in (('head_sha', 'source_sha'), ('run_id', 'run_id'), ('run_attempt', 'attempt')):
        need(str(job.get(actual)) == str(identity[expected]), 'job identity differs: ' + name + ' ' + actual)
    need(type(job.get('id')) is int and job['id'] > 0, 'job id missing: ' + name)
    if os_name:
        label = {'Linux': 'ubuntu-22.04', 'Windows': 'windows-2022', 'macOS': 'macos-15'}[os_name]
        need(label in job.get('labels', []), 'job runner platform differs: ' + name)


def verify_artifact(identity, artifact, name):
    need(artifact.get('name') == name and type(artifact.get('id')) is int and artifact['id'] > 0, 'artifact name/id differs: ' + name)
    need(artifact.get('expired') is False and artifact.get('size_in_bytes', 0) > 0, 'artifact empty/expired: ' + name)
    run = artifact.get('workflow_run', {})
    need(run.get('head_sha') == identity['source_sha'] and str(run.get('id')) == str(identity['run_id']), 'artifact run/source differs: ' + name)
    need(re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest', '')) is not None, 'artifact digest missing: ' + name)
    expiry = datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00'))
    need(expiry > datetime.now(timezone.utc), 'artifact expiry elapsed: ' + name)


def verify_zip_bytes(data, artifact):
    need(len(data) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'ZIP bytes/digest differ: ' + artifact['name'])


def verify_binary(archive, path, digest):
    need(re.fullmatch('[0-9a-f]{64}', digest or '') is not None and hashlib.sha256(archive.read(path)).hexdigest() == digest, 'binary hash differs: ' + path)


def archive_files(archive):
    names, files = set(), set()
    for member in archive.infolist():
        name = member.filename
        path = name.rstrip('/')
        need(path and not name.startswith('/') and '\\' not in name and ':' not in name and
             all(p not in ('', '.', '..') for p in path.split('/')) and
             all(ord(c) >= 32 and ord(c) != 127 for c in name), 'unsafe ZIP member: ' + name)
        need(path not in names, 'duplicate ZIP member: ' + name)
        names.add(path)
        kind = stat.S_IFMT(member.external_attr >> 16)
        need(kind in (0, stat.S_IFDIR if member.is_dir() else stat.S_IFREG), 'special ZIP member: ' + name)
        if not member.is_dir():
            files.add(name)
    need('result.json' in files and all(n == 'result.json' for n in files if PurePosixPath(n).name == 'result.json'), 'missing/duplicate result report')
    need(not any(n.endswith(('.key', '.sqlite')) for n in files), 'package carries a key or database')
    return files


def verify_inventory(archive, files, identity):
    raw = archive.read('inventory.json')
    need(hashlib.sha256(raw).hexdigest() == identity['inventory_sha256'], 'inventory bytes differ from identity')
    value = strict_json(raw)
    need(value['format'] == INVENTORY_FORMAT, 'inventory format differs')
    directories = value['dirs']
    rows = value['files']
    paths = [row['path'] for row in rows]
    need(len(set(directories)) == len(directories) and directories == sorted(directories, key=lambda s: s.encode('utf-8')), 'duplicate/unsorted inventory directory')
    need(len(set(paths)) == len(paths) and paths == sorted(paths, key=lambda s: s.encode('utf-8')), 'duplicate/unsorted inventory file')
    need(not set(paths).intersection(directories), 'inventory file/directory collision')
    need({'tree/' + p for p in paths} == {f for f in files if f.startswith('tree/')}, 'ZIP tree members differ from inventory')
    need(value['file_count'] == len(rows) and value['dir_count'] == len(directories), 'inventory counts differ')
    digest, total = hashlib.sha256(), 0
    for directory in directories:
        digest.update(('D\t%s\n' % directory).encode('utf-8'))
    for row in rows:
        data = archive.read('tree/' + row['path'])
        need(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'raw tree bytes differ: ' + row['path'])
        total += len(data)
        digest.update(('F\t%d\t%s\t%s\n' % (len(data), row['sha256'], row['path'])).encode('utf-8'))
    need(total == value['total_bytes'] and digest.hexdigest() == value['digest'] == identity['inventory_digest'], 'inventory total/digest differs')
    return {row['path']: (row['bytes'], row['sha256']) for row in rows}


def verify_probe(report, stage, expected):
    checks = report.get('checks', [])
    need(report.get('failures') == 0 and checks and all(c.get('pass') is True for c in checks), 'raw SDK probe failed')
    if stage == 'send':
        need(report.get('originals_exported') == 4 and report.get('network_pushed') == 31 and
             report.get('cancelled_attempts', 0) >= 1 and report.get('reopens', 0) >= 1, 'sender SDK counters differ')
    else:
        cases = report.get('cases', [])
        need([(c.get('id'), c.get('state')) for c in cases] == [(c['id'], c['state']) for c in expected['cases']], 'SDK capture ids/outcomes differ')
        need(report.get('receiver_found') == 17 and report.get('receiver_ambiguous') == 1 and report.get('receiver_mislocated') == 0, 'SDK capture counters differ')
        if stage == 'receive':
            need(report.get('network_pulled', 0) >= 31 and report.get('metadata_projected') == 4 and
                 report.get('cancelled_attempts', 0) >= 1 and report.get('reopens', 0) >= 3, 'receiver SDK counters differ')
