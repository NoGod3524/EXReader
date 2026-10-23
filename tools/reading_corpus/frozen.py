#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Recover only registered raw inputs from a digest-pinned accepted Actions archive."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import download_artifact_zip, fetch, pages, require

REGISTRY = Path(__file__).with_name('frozen-inputs.json')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_origin(registry, run, artifacts):
    require(run['id'] == registry['run_id'] and run['head_sha'] == registry['source_sha'] and
            run['run_attempt'] == registry['run_attempt'] and run['path'] == registry['workflow'] and
            run['status'] == 'completed' and run['conclusion'] == 'success', 'Frozen input run identity/status refused')
    selected = [item for item in artifacts if item['id'] == registry['artifact_id'] or item['name'] == registry['artifact_name']]
    require(len(selected) == 1, 'Frozen input artifact missing/duplicate')
    item = selected[0]
    require(item['id'] == registry['artifact_id'] and item['name'] == registry['artifact_name'] and
            item['size_in_bytes'] == registry['artifact_bytes'] > 0 and item['digest'] == registry['artifact_digest'] and
            item['expired'] is False and item['workflow_run']['id'] == registry['run_id'] and
            item['workflow_run']['head_sha'] == registry['source_sha'], 'Frozen input artifact identity refused')


def restore_archive(raw, manifest_bytes, registry):
    require(len(raw) == registry['artifact_bytes'] and 'sha256:' + sha(raw) == registry['artifact_digest'],
            'Frozen input ZIP size/digest refused')
    require(sha(manifest_bytes) == registry['manifest_sha256'], 'Frozen input manifest digest refused')
    manifest = json.loads(manifest_bytes)
    entries = manifest['files']
    require(len(entries) == 8 and len({entry['id'] for entry in entries}) == 8 and
            len({entry['path'] for entry in entries}) == 8, 'Frozen input coverage refused')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate frozen ZIP member')
        require(all(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and
                    '\\' not in name and ':' not in name for name in names), 'Unsafe frozen ZIP member')
        expected = {'inputs/assets/' + entry['path'] for entry in entries}
        require({name for name in names if name.startswith('inputs/assets/') and not name.endswith('/')} == expected,
                'Frozen input member coverage refused')
        def member(name, limit):
            require(names.count(name) == 1, 'Missing/duplicate frozen member: ' + name)
            info = archive.getinfo(name)
            require(not info.is_dir() and info.external_attr >> 16 & 0o170000 in (0, 0o100000) and
                    0 < info.file_size <= limit, 'Frozen member type/size refused: ' + name)
            return archive.read(name)
        archived = json.loads(member('inputs/manifest.json', 1024 * 1024))
        require(archived['complete'] is True and archived['engine_executed'] is False and
                archived['original_manifest_sha256'] == registry['manifest_sha256'], 'Frozen collection identity refused')
        records = {row['id']: row for row in archived['files']}
        require(len(archived['files']) == len(records) == 8 and set(records) == {entry['id'] for entry in entries},
                'Frozen collection coverage refused')
        inputs, origins = {}, {}
        for entry in entries:
            path = entry['path']
            require(not PurePosixPath(path).is_absolute() and '..' not in PurePosixPath(path).parts and
                    '\\' not in path and ':' not in path, 'Unsafe frozen manifest path')
            prior = records[entry['id']]
            require(all(prior[key] == entry[key] for key in ('path', 'source_url', 'sha256', 'size')),
                    'Frozen source record refused: ' + entry['id'])
            data = member('inputs/assets/' + path, entry['limits']['download_bytes'])
            require(len(data) == entry['size'] and sha(data) == entry['sha256'], 'Frozen document identity refused: ' + entry['id'])
            rights = member('inputs/licenses/' + entry['id'] + '.txt', 4 * 1024 * 1024)
            require(sha(rights) == prior['observed_license_sha256'], 'Archived license evidence refused')
            inputs[path] = data
            origins[path] = {'publisher_retrieved_url': prior['retrieved_url'],
                             'archived_license_sha256': sha(rights)}
    return inputs, origins


def recover(manifest_bytes):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Frozen input recovery runs only in Actions')
    registry = json.loads(REGISTRY.read_bytes())
    require(registry['schema'] == 1 and os.environ.get('GITHUB_REPOSITORY') == registry['repository'],
            'Frozen input repository refused')
    run = fetch('actions/runs/' + str(registry['run_id']))
    artifacts = pages('actions/runs/' + str(registry['run_id']) + '/artifacts', 'artifacts')
    verify_origin(registry, run, artifacts)
    inputs, origins = restore_archive(download_artifact_zip(registry['artifact_id']), manifest_bytes, registry)
    return inputs, origins, registry
