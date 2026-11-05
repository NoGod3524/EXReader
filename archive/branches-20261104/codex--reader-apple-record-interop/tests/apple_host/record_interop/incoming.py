"""Actions-only collector for the sealed real Android sender, no synthetic peer."""
from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import types
import zipfile

from verify import ROOT, fetch, download_artifact_zip, require, load

SOURCE = 'b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7'
RUN = '40181402323'
PACKET = (12594712144, 16615, '08ce264db1a6e6083e15ddd20a60f6f088b7d82afe24e4d44aa8681e6551cac3')
SUMMARY = (12593694660, 1658, 'db82485a4f3a1055a33fbf94e9ffa48a19361b43e13bfc7de62f0847ec9c133a')
MANIFEST = '7628affd6e5ec37e748c9d09c57d5f50090c4060bbdd080b9800b45930829bbf'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def contract():
    # Reuse the sender's pure read-only validator byte-for-byte at its tested SHA.
    raw = subprocess.check_output(['git', 'show', SOURCE + ':tests/reader_android_record_interop/bundle.py'], cwd=ROOT)
    module = types.ModuleType('sealed_android_bundle_contract')
    exec(compile(raw, 'sealed_android_bundle_contract.py', 'exec'), module.__dict__)
    return module


def members(raw):
    archive = zipfile.ZipFile(io.BytesIO(raw))
    infos = archive.infolist()
    names = [item.filename for item in infos]
    require(len(names) == len(set(names)) <= 200 and sum(item.file_size for item in infos) <= 16 * 1024**2,
            'unbounded/duplicate peer ZIP')
    require(all(name and not PurePosixPath(name).is_absolute() and all(part not in ('', '.', '..') for part in name.split('/'))
                and '\\' not in name and ':' not in name and not item.is_dir()
                and (item.external_attr >> 16) & 0o170000 != 0o120000 for name, item in zip(names, infos)), 'unsafe peer ZIP')
    return {name: archive.read(name) for name in names}


def authenticate(packet_raw, summary_raw):
    for raw, pin in ((packet_raw, PACKET), (summary_raw, SUMMARY)):
        require(len(raw) == pin[1] and digest(raw) == pin[2], 'sealed sender ZIP differs')
    run = fetch('actions/runs/' + RUN)
    require(run['head_sha'] == SOURCE and run['run_attempt'] == 1 and run['status'] == 'completed' and
            run['conclusion'] == 'success' and run['path'] == '.github/workflows/reader-android-record-interop.yml', 'sender run identity differs')
    jobs = fetch('actions/runs/' + RUN + '/attempts/1/jobs?per_page=100')['jobs']
    require(all(any(job['id'] == job_id and job['conclusion'] == 'success' for job in jobs)
                for job_id in (121133053868, 121137003411)), 'actual sender and strict producer did not pass')
    metadata = fetch('actions/runs/' + RUN + '/artifacts?per_page=100')['artifacts']
    artifacts = []
    for pin in (PACKET, SUMMARY):
        matches = [item for item in metadata if item['id'] == pin[0]]
        require(len(matches) == 1, 'sealed sender artifact missing')
        item = matches[0]
        require(item['size_in_bytes'] == pin[1] and item['digest'] == 'sha256:' + pin[2] and not item['expired'] and
                item['workflow_run']['head_sha'] == SOURCE and item['workflow_run']['id'] == int(RUN) and
                datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'sender artifact provenance/expiry differs')
        artifacts.append({key: item[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
    summaries = members(summary_raw)
    require(set(summaries) == {'summary.json'}, 'unexpected strict sender summary members')
    summary = load(summaries['summary.json'])
    require(summary['source_sha'] == SOURCE and str(summary['run_id']) == RUN and str(summary['attempt']) == '1' and
            summary['sender_export_accepted'] is True and summary['inherited_130_accepted'] is True and summary['checks'] == 138 and
            summary['bidirectional_interoperability_accepted'] is False and summary['incoming_apple_status'] == 'pending' and
            summary['bundle']['id'] == PACKET[0] and summary['bundle']['digest'] == 'sha256:' + PACKET[2], 'sealed strict sender contract differs')
    files = members(packet_raw)
    verified = contract().verify(files.__getitem__)
    require(set(files) == set(verified['files']) and verified['manifest_sha256'] == MANIFEST == summary['manifest_sha256'] and
            verified['originals'] == 4 and verified['revisions'] == 19 and verified['reading_records'] == 11 and
            verified['manifest']['sender'] == summary['actual_sender'], 'real sender graph/manifest differs')
    return verified, dict(sender_source=SOURCE, sender_run=RUN, sender_attempt='1', sender_artifacts=artifacts,
                          manifest_sha256=MANIFEST, original_strict_checks=138,
                          actual_android_host_interop_accepted=False, bidirectional_interoperability_accepted=False)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    raws = []
    for name, pin in (('packet.zip', PACKET), ('upstream-summary.zip', SUMMARY)):
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(pin[0], stream)
            stream.seek(0)
            raw = stream.read(16 * 1024**2 + 1)
        (out / name).write_bytes(raw)
        raws.append(raw)
    verified, receipt = authenticate(*raws)
    files = members(raws[0])
    for name in verified['files']:
        target = out / 'bundle' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[name])
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
