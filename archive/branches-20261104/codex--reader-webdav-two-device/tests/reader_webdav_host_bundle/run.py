"""Actions-only replay of an authenticated real Android export through real WebDAV.

This exercises installed public modules, not either host's sync UI or receiver.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path[:0] = ['tests/reader_webdav_interop', 'tests/reader_android_record_interop']
from run_interop import Apache, Device, Harness, Independent, Nextcloud, require, run
from bundle import verify

RUN = '40181402323'
SOURCE = 'b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7'
ARTIFACT = 12594712144
DIGEST = '08ce264db1a6e6083e15ddd20a60f6f088b7d82afe24e4d44aa8681e6551cac3'
MANIFEST = '7628affd6e5ec37e748c9d09c57d5f50090c4060bbdd080b9800b45930829bbf'


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--service', choices=['apache', 'nextcloud'], required=True)
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    h = Harness(args)
    report = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'service': args.service,
              'sender_source': SOURCE, 'sender_run': RUN, 'sender_artifact': ARTIFACT,
              'actual_host_sync': False, 'bidirectional_host_interop': False, 'accepted': False}
    copies = []
    try:
        producer = api('actions/runs/' + RUN)
        artifact = api('actions/artifacts/' + str(ARTIFACT))
        require(producer['head_sha'] == SOURCE and producer['conclusion'] == 'success', 'sender run identity')
        require(artifact['workflow_run']['id'] == int(RUN) and artifact['workflow_run']['head_sha'] == SOURCE
                and not artifact['expired'] and artifact['digest'] == 'sha256:' + DIGEST, 'sender artifact identity')
        data = subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] +
                                        '/actions/artifacts/' + str(ARTIFACT) + '/zip'])
        require(len(data) == artifact['size_in_bytes'] and hashlib.sha256(data).hexdigest() == DIGEST, 'sender ZIP digest')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)), 'duplicate archive members')
            def read(name):
                candidates = [n for n in names if n == name or n.endswith('/' + name)]
                require(len(candidates) == 1 and archive.getinfo(candidates[0]).file_size <= 32 * 1024 * 1024, 'bundle member')
                return archive.read(candidates[0])
            checked = verify(read)
            require(checked['manifest_sha256'] == MANIFEST, 'manifest digest')
            manifest = checked['manifest']
            require(manifest['sender']['source_sha'] == SOURCE and manifest['sender']['run_id'] == RUN
                    and manifest['sender']['attempt'] == '1', 'manifest sender identity')
            files = {name: read(name) for name in checked['files']}
        ca = h.certificates()
        cls = Apache if args.service == 'apache' else Nextcloud
        h.service = cls(args.service, h.work, h.evidence, ca, h.secret)
        h.service.admin = h.admin
        h.client = Independent(h.service.host, h.service.port, ca, h.auth)
        h.service.pull()
        h.service.start(h.client)
        root = h.root('host-export')
        a, b = Device(h, 'sender-replay'), Device(h, 'receiver-replay')
        for row in manifest['originals']:
            (a.originals / (row['sha256'] + '.' + row['format'])).write_bytes(files[row['file']])
        pending = {row['id']: row for row in manifest['revisions']}
        ordered = []
        while pending:
            ready = [row for row in pending.values() if all(parent not in pending for parent in row['parents'])]
            require(ready, 'revision graph has missing parents or cycle')
            for row in ready:
                wire = h.evidence / 'wires' / (row['id'] + '.json')
                wire.parent.mkdir(exist_ok=True)
                wire.write_bytes(files[row['file']])
                value = h.consumer('local', a.db, wire)
                require(value['status'] == 0 and value['created'] == 1 and value['sha256'] == row['sha256'], 'local retained revision')
                ordered.append(row)
                del pending[row['id']]
        shards = sorted({int(row['id'][:2], 16) for row in ordered})
        url = h.url(root)
        for shard in shards:
            a.sync(url, shard)
        require(a.counts() == (len(ordered), 0), 'sender outbox not drained')
        for _ in range(2):
            for shard in shards:
                b.sync(url, shard)
        require(b.counts() == (len(ordered), 0), 'receiver history differs')
        for row in ordered:
            original = files[row['file']]
            require(a.exported(row['id']) == original and b.exported(row['id']) == original, 'retained wire differs')
            target = root + 'exreader-sync-v1/revisions/' + row['id'][:2] + '/' + row['id'] + '-' + row['sha256'] + '.json'
            status, data = h.client.get(target)
            require(status == 200 and data == original, 'server revision differs')
        for row in manifest['originals']:
            require((b.cache / (row['sha256'] + '.' + row['format'])).read_bytes() == files[row['file']], 'received original differs')
            target = root + 'exreader-sync-v1/objects/' + row['sha256'][:2] + '/' + row['sha256'] + '.' + row['format']
            status, data = h.client.get(target)
            require(status == 200 and data == files[row['file']], 'server original differs')
        report.update(accepted=True, manifest_sha256=MANIFEST, originals=len(manifest['originals']),
                      revisions=len(ordered), shards=shards, sender_counts=a.counts(), receiver_counts=b.counts())
    except Exception as error:
        report['failure'] = str(error)
        report['trace'] = traceback.format_exc()
    finally:
        if hasattr(h, 'service'):
            try:
                copies = h.service.collect()
            except Exception as error:
                report['collect_failure'] = str(error)
                report['accepted'] = False
            h.service.remove()
        (h.evidence / 'invocations.json').write_text(json.dumps(h.invocations, indent=2), encoding='utf-8')
        found, scanned = h.scrub(copies)
        if found or not scanned:
            report['accepted'] = False
            report['credential_scan_matches'] = found
        run(['sudo', 'rm', '-f', getattr(h, 'trust', '/nonexistent')], check=False)
        run(['sudo', 'update-ca-certificates', '--fresh'], check=False)
        run(['sudo', 'rm', '-rf', str(h.work)], check=False)
        (h.evidence / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report), flush=True)
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
