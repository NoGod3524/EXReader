"""Actions-only raw native sender/loopback authentication; no Android grant."""
import base64
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip, require


def pairs(values):
    result = {}
    for key, value in values:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def load(raw):
    return json.loads(raw, object_pairs_hook=pairs)


def identity(value, source, run, attempt):
    require(value.get('source_sha') == source and str(value.get('run_id')) == run and str(value.get('attempt')) == attempt,
            'sender/consumer identity differs')


def validate(result, read, source, run, attempt):
    identity(result, source, run, attempt)
    require(result.get('accepted') is True and result.get('actual_android_host_interop_accepted') is False and
            result.get('actual_android_peer') == 'pending' and result.get('host_ui_accepted') is False and
            result.get('physical_device_accepted') is False, 'false scope')
    program = read('record-interop')
    executable = hashlib.sha256(program).hexdigest()
    require(program[:4] in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe'), 'not native Mach-O')
    require(executable == result['program_sha256'] and read('sender-bundle/proofs/program') == program, 'actual executable differs')
    product = load(read('record-interop.product.json'))
    require(product['binary_sha256'] == executable and product['static_sdk_linked'] is False and
            product['installed_reading_commands_linked'] is True, 'actual installed owner providers differ')
    raw_manifest = read('sender-bundle/manifest.json')
    require(hashlib.sha256(raw_manifest).hexdigest() == result['manifest_sha256'], 'transport manifest differs')
    manifest = load(raw_manifest)
    require(set(manifest) == {'schema', 'sender', 'originals', 'revisions', 'reading_records'} and manifest['schema'] == 1,
            'manifest contract differs')
    sender = manifest['sender']; identity(sender, source, run, attempt)
    require(sender['platform'] == 'macos' and sender['exr_version'] == sender['parser_version'] == '3.41.0' and
            sender['program_sha256'] == executable and sender['sdk_dso_sha256'] == hashlib.sha256(read('sender-bundle/proofs/sdk.dylib')).hexdigest(),
            'actual sender runtime/program/loaded SDK differs')
    basename=sender['sdk_dso_basename']
    require(isinstance(basename,str) and basename.startswith('libexreader') and basename.endswith('.dylib') and
            '/' not in basename and '\\' not in basename and ':' not in basename and
            read('original-compatibility/libraries-new/'+basename)==read('sender-bundle/proofs/sdk.dylib'),
            'actual loaded SDK differs from original same-producer installed library')
    originals, revisions, records = manifest['originals'], manifest['revisions'], manifest['reading_records']
    roles = {'txt', 'epub', 'pdf', 'cbz'}
    require(len(originals) == 4 and {row['role'] for row in originals} == roles, 'four genuine originals required')
    for original in originals:
        raw = read('sender-bundle/' + original['file'])
        require(0 < len(raw) == original['bytes'] <= 32 * 1024**2 and hashlib.sha256(raw).hexdigest() == original['sha256'] and
                original['format'] == original['role'] and original['book_key'] == original['format'] + ':' + original['sha256'], 'actual original bytes/key differ')
    ids = {row['id'] for row in revisions}
    require(11 < len(revisions) == len(ids) <= 100 and any(row['entity_kind'] == 'book' for row in revisions), 'complete actual graph absent')
    by_id = {}
    for revision in revisions:
        raw = read('sender-bundle/' + revision['file']); wire = load(raw)
        require(0 < len(raw) == revision['bytes'] <= 1024**2 and hashlib.sha256(raw).hexdigest() == revision['sha256'], 'actual raw wire bytes differ')
        require(wire['id'] == revision['id'] and wire['parents'] == revision['parents'] and
                wire['entity_kind'] == revision['entity_kind'] and wire['entity_key'] == revision['entity_key'] and
                all(parent in ids for parent in revision['parents']), 'real graph identity/ancestor differs')
        by_id[revision['id']] = (wire, revision)
    required = [(role, kind) for role in ('txt', 'epub', 'pdf', 'cbz')
                for kind in (('progress', 'bookmark') if role == 'cbz' else ('progress', 'bookmark', 'highlight'))]
    require(len(records) == 11 and [(row['role'], row['kind']) for row in records] == required and
            len({row['revision_id'] for row in records}) == 11, 'actual sender cases differ')
    for record in records:
        wire, meta = by_id[record['revision_id']]
        location = wire['payload']['location']; capture = record['capture']
        original = next(row for row in originals if row['role'] == record['role'])
        require(location['parser_version'] == '3.41.0' and record['anchor_version'] == location['anchor_version'] == 2 and
                meta['book_key'] == original['book_key'], 'real retained parser/anchor/original differs')
        require(len(capture['numbers']) == 4 and all(isinstance(v, str) and v.isascii() and v.isdecimal() and int(v) < 2**64 for v in capture['numbers']) and
                len(capture['route']) == 5 and capture['route'][:2] == [original['book_key'], '3.41.0'] and
                len(capture['selectors']) == 3, 'actual capture shape differs')
        for value in capture['selectors']:
            require(value is None or isinstance(value, str) and len(base64.b64decode(value, validate=True)) <= 65536, 'bad actual selector')
        require(int(capture['numbers'][0]) == record['mode'] and
                int(capture['numbers'][3]) >= int(capture['numbers'][2]) and
                (record['kind'] != 'highlight' or int(capture['numbers'][3]) > int(capture['numbers'][2])), 'genuine point/range differs')
    phases = result['phases']; require(len(phases) == 3 and len({row['pid'] for row in phases}) == 3, 'actual reopened processes missing')
    for index, (label, mode) in enumerate((('send', 'send'), ('loopback-receive', 'receive'), ('loopback-reopen', 'receive'))):
        value = load(read(label + '.json')); identity(value, source, run, attempt)
        expected = [mode + ':' + role + ':' + kind for role, kind in required]
        expected += ['send:complete-original-wire-and-ancestor-export' if mode == 'send' else 'receive:actual-owner-resolve-recapture-readonly']
        require(value == phases[index] and value['accepted'] is True and value['mode'] == mode and value['checks'] == expected and
                value['exr_version'] == '3.41.0' and value['actual_android_host_interop_accepted'] is False,
                'actual named sender/receiver results differ')
        if mode == 'receive':
            require(len(value['records']) == 11 and all(row['found'] is True and row['wire_sha256'] == by_id[row['revision_id']][1]['sha256'] for row in value['records']), 'actual receiver FOUND wire differs')
    spec = importlib.util.spec_from_file_location('original_compatibility_contract', ROOT / 'tests/apple_host/record_compatibility/verify.py')
    original = importlib.util.module_from_spec(spec); spec.loader.exec_module(original)
    original.validate(load(read('original-compatibility/result.json')),
                      lambda name: read('original-compatibility/' + name), source, run, attempt)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    if '--inspect-run' in sys.argv:
        target = sys.argv[sys.argv.index('--inspect-run') + 1]
        require(target.isdecimal(), 'bad original run')
        original = fetch('actions/runs/' + target)
        require(original['status'] == 'completed' and original['path'] == '.github/workflows/reader-apple-record-interop.yml', 'not a completed original producer')
        subprocess.run(['git','merge-base','--is-ancestor',original['head_sha'],'HEAD'],check=True)
        matches = [item for item in fetch('actions/runs/' + target + '/artifacts?per_page=100')['artifacts']
                   if item['name'] == 'apple-host-record-interop-' + target + '-' + str(original['run_attempt'])]
        require(len(matches) == 1, 'original artifact absent or duplicate')
        artifact = matches[0]
        require(artifact['workflow_run']['head_sha'] == original['head_sha'] and not artifact['expired'], 'foreign or expired original artifact')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(artifact['id'],stream);stream.seek(0);raw=stream.read()
        require(len(raw)==artifact['size_in_bytes'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==artifact['digest'],'original raw ZIP differs')
        findings=[]
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for info in archive.infolist():
                if info.filename.endswith('reading-requests/request.json'):
                    require(info.file_size<=1024**2,'oversized original request')
                    request=load(archive.read(info))
                    fixed=request.get('capture',{}).get('fixed',{})
                    fields=fixed.get('fields',[])
                    nul_positions={str(index):[offset for offset,value in enumerate(base64.b64decode(field,validate=True)) if value==0]
                                   for index,field in enumerate(fields) if field is not None}
                    findings.append(dict(member=info.filename,request=request,fixed_field_nul_positions=nul_positions))
        out=ROOT/'build/apple-record-interop-summary';out.mkdir(parents=True,exist_ok=True)
        result=dict(accepted=False,diagnostic_only=True,original_source=original['head_sha'],original_run=target,
                    original_attempt=original['run_attempt'],artifact=artifact,original_pending_requests=findings)
        (out/'inspection.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result),flush=True)
        return
    source, run, attempt = os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    out = ROOT / 'build/apple-record-interop-summary'; out.mkdir(parents=True, exist_ok=True)
    summary = dict(accepted=False, source_sha=source, run_id=run, attempt=attempt,
                   actual_android_host_interop_accepted=False, actual_android_peer='pending')
    try:
        metadata = fetch('actions/runs/' + run)
        require(metadata['head_sha'] == source and str(metadata['run_attempt']) == attempt and
                metadata['path'] == '.github/workflows/reader-apple-record-interop.yml', 'workflow identity')
        jobs = fetch('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
        matching = [job for job in jobs if job['name'] == 'native']
        require(len(matching) == 1 and matching[0]['conclusion'] == 'success', 'native producer did not pass')
        matching_artifacts = [item for item in fetch('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
                              if item['name'] == 'apple-host-record-interop-' + run + '-' + attempt]
        require(len(matching_artifacts) == 1, 'artifact absent or duplicate')
        artifact = matching_artifacts[0]
        require(artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == int(run) and
                not artifact['expired'] and datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'artifact identity/expiry')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(artifact['id'], stream); stream.seek(0); raw = stream.read()
        require(len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest'], 'actual ZIP differs')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist(); names = [item.filename for item in infos]
            require(len(names) == len(set(names)) <= 10000 and sum(item.file_size for item in infos) <= 512 * 1024**2, 'unbounded/duplicate ZIP')
            require(all(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name and ':' not in name for name in names), 'unsafe ZIP member')
            def read(name):
                require(name in names and archive.getinfo(name).file_size <= 64 * 1024**2, 'missing or oversized raw member')
                return archive.read(name)
            result = load(read('result.json')); validate(result, read, source, run, attempt)
            for mutation in (dict(accepted=False), dict(source_sha='other'), dict(attempt='other'),
                             dict(actual_android_host_interop_accepted=True), dict(actual_android_peer='accepted'),
                             dict(phases=result['phases'][:-1]), dict(manifest_sha256='0' * 64)):
                bad = copy.deepcopy(result); bad.update(mutation)
                try:
                    validate(bad, read, source, run, attempt)
                except Exception:
                    continue
                raise ValueError('protocol negative admitted')
        summary.update(accepted=True, actual_apple_sender_accepted=True, actual_apple_loopback_accepted=True,
                       native_phases=3, reading_records=11, original_compatibility_phases=18,
                       original_owner_cases_per_sdk=19, protocol_rejections=7,
                       artifact={key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
    except Exception as error:
        summary['failure'] = type(error).__name__ + ': ' + str(error)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    require(summary['accepted'], 'actual sender/loopback verification failed')


if __name__ == '__main__':
    main()
