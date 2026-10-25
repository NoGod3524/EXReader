"""Strict Actions-only authentication of the S15 artifacts and adversarial rejection."""
import copy
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import fetch, pages, download_artifact_zip, require

REQUIRED = set(json.loads(Path('tests/reader_next_s15/cases.json').read_text()))
PLATFORMS = [('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022'), ('macOS', 'macos-15')]
FROZEN_CHECKS = {'frozen_sdk_340_install_identity', 'frozen_sdk_default_pin_accepted',
                 'frozen_sdk_explicit_341_refused', 'frozen_sdk_c_abi_link',
                 'frozen_sdk_original_byte_identity', 'frozen_sdk_existing_target_not_overwritten'}
EXT = ['txt', 'html', 'fb2', 'epub', 'docx', 'rtf', 'mobi', 'pdf', 'cbz']
FROZEN = ['sample.txt', 'sample.html', 'sample.fb2', 'sample.epub', 'sample.docx',
          'sample.rtf', 'sample.mobi', 'pdf-public-text.pdf', 'comic.cbz']


def object_pairs(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate JSON key ' + key)
        out[key] = value
    return out


def load(raw): return json.loads(raw, object_pairs_hook=object_pairs)


def validate(report, members, platform, source, run, attempt):
    require(type(report['run_id']) is int and type(report['attempt']) is int, 'integer report run identity')
    require(report['accepted'] is True and report['source_sha'] == source and report['run_id'] == run
            and report['attempt'] == attempt, 'report identity/outcome')
    require(report['platform'] == platform and report['system_share_ui'] is False
            and report['six_devices'] is False, 'platform/scope')
    require(report['sdk_version'] == '3.41.0' and report['sdk_abi'] == 1 and report['module_pin'] == '3.41.0',
            'approved SDK 3.41/ABI1 graph')
    expected = REQUIRED | ({'windows_actual_locked_cleanup_failure'} if platform == 'Windows'
                           else {'posix_real_midstream_write_failure'})
    require(set(report['checks']) == expected and len(report['checks']) == len(expected) == report['count'],
            'exact named cases')
    require(not report['failures'], 'failures present')
    require(set(report['binary_identities']) == {'probe', 'c_consumer', 'module'}, 'binary identity roles')
    used = set()
    for role, identity in report['binary_identities'].items():
        member = identity['member']
        require(member not in used and member in members, 'missing/duplicate binary binding'); used.add(member)
        data = members[member]
        require(len(data) == identity['bytes'] > 0 and hashlib.sha256(data).hexdigest() == identity['sha256'],
                'actual binary digest ' + role)
        require(member.startswith('s15-evidence/binaries/'), 'binary member scope')
        if role == 'module':
            require(data.startswith(b'!<arch>\n') and data == members.get('s15-stage/lib/' + member.split('/')[-1]),
                    'actual installed static module binding')
        else:
            require(data[:4] in ({b'\x7fELF'} if platform == 'Linux' else
                                 {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe',
                                  b'\xbe\xba\xfe\xca'} if platform == 'macOS' else {data[:4]}),
                    'native executable format')
            if platform == 'Windows': require(data[:2] == b'MZ', 'native PE executable')
    # Install-graph negatives were real refusals at this source.
    graph = load(members['s15-evidence/graph.json'])
    require(graph['accepted'] is True and graph['platform'] == platform, 'install graph accepted')
    require(graph['sdk'] == {'version': '3.41.0', 'abi': 1}, 'install graph SDK identity')
    for name in ('sdk_default_pin_refused_by_341_install', 'sdk_unsupported_pin_refused',
                 'consumer_without_exact_sdk_refused', 'mixed_sdk_graph_refused'):
        case = graph['cases'][name]
        require(case['refused'] is True and case['exit'] != 0 and all(case['markers'].values()),
                'install graph refusal ' + name)
    require(graph['cases']['relabelled_graph_resolves_as_340']['refused'] is False, 'relabelled graph control')
    require(graph['relabel']['archives'], 'relabel archive binding')
    # Nine non-streamed originals, then the three streamed storage paths.
    nine = report['cases']['nine']['items']
    require(len(nine) == 9 and {r['format'] for r in nine} == set(range(1, 10)), 'nine original modules')
    require(all(r['committed'] == 1 and r['created'] == 1 and len(r['hash']) == 64 and r['bytes'] > 0 for r in nine),
            'nine real outputs')
    for r in nine:
        ext = EXT[r['format'] - 1]
        original = members['s15-fixtures/book.' + ext]
        require(original == (Path('tests/fixtures') / FROZEN[r['format'] - 1]).read_bytes(),
                'original bound to frozen source fixture')
        final = members['s15-evidence/nine/' + r['hash'] + '.' + ext]
        require(final == original and len(final) == r['bytes'] and hashlib.sha256(final).hexdigest() == r['hash'],
                'actual original/final bytes')
    for name, counterpart, fixture in (('stream-cbz', 9, 'comic.cbz'), ('stream-epub', 4, 'sample.epub'),
                                       ('stream-pdf', 8, 'pdf-public-text.pdf')):
        item = report['cases'][name]['items'][0]
        require(item['hash'] == nine[counterpart - 1]['hash'], name + ' differs from the non-streamed original')
        require(members['s15-evidence/' + name + '/' + item['hash'] + '.' + fixture.split('.')[-1]]
                == (Path('tests/fixtures') / fixture).read_bytes(), name + ' streamed bytes')
    # The unchanged sideload exporter is an independent byte oracle.
    item = report['cases']['sideload']['items'][0]
    oracle = members['s15-evidence/sideload/sideload-oracle.cbz']
    require(oracle == (Path('tests/fixtures') / 'comic.cbz').read_bytes(), 'sideload oracle bytes')
    require(report['cases']['sideload']['sideload_bytes'] == len(oracle), 'sideload oracle size')
    require(item['hash'] == hashlib.sha256(oracle).hexdigest(), 'module and sideload original differ')
    before = {p.removeprefix('s15-evidence/before/'): v for p, v in members.items() if p.startswith('s15-evidence/before/')}
    after = {p.removeprefix('s15-evidence/after/'): v for p, v in members.items() if p.startswith('s15-evidence/after/')}
    require(before == after and len(before) == 17, 'public SDK/product invariant snapshots')
    require(before.get('history.json') and before.get('outbox.txt') and before.get('sdk.txt'), 'raw invariant names')
    require(members.get('s15-consumer/original-export-link.map')
            and b'reader_original_export' in members['s15-consumer/original-export-link.map'], 'module link binding')
    require(members.get('s15-logs/source.txt', b'').decode().strip() == source, 'raw source binding')
    return True


def validate_frozen(report, members, source, run, attempt):
    require(report['accepted'] is True and report['source_sha'] == source and report['run_id'] == run
            and report['attempt'] == attempt, 'frozen report identity')
    require(report['platform'] == 'Linux' and report['sdk'] == {'version': '3.40.0', 'abi': 1}, 'frozen SDK identity')
    require(set(report['checks']) == FROZEN_CHECKS and report['count'] == len(FROZEN_CHECKS), 'frozen named cases')
    require(not report['failures'], 'frozen failures present')
    require(report['cases']['module_default_pin_accepted']['refused'] is False, 'frozen default pin rejected')
    require(report['cases']['explicit_341_refused']['refused'] is True, 'frozen graph accepted the 3.41 pin')
    require(report['cases']['consumer_configure']['refused'] is False, 'frozen consumer configure')
    original = members['s15-frozen-work/fixture.txt']
    require(original == (Path('tests/fixtures') / 'sample.txt').read_bytes(), 'frozen fixture bytes')
    digest = hashlib.sha256(original).hexdigest()
    exported = members['s15-frozen-work/export/' + digest + '.txt']
    require(exported == original, 'frozen exported original bytes')
    require(members.get('s15-frozen-logs/source.txt', b'').decode().strip() == source, 'frozen source binding')
    return True


def unpack(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist(); names = [x.filename for x in infos]
        require(len(names) == len(set(names)), 'duplicate ZIP member')
        require(all(not n.startswith('/') and '..' not in n.split('/') and '\\' not in n for n in names),
                'unsafe ZIP path')
        require(sum(x.file_size for x in infos) < 1024 * 1024 * 1024, 'unbounded ZIP')
        members = {x.filename: z.read(x) for x in infos if not x.is_dir()}
    require('s15-evidence/result.json' in members or 's15-frozen-work/frozen.json' in members, 'missing report')
    return members


def rejections(report, members, platform, source, run, attempt):
    passed = []
    changes = [('wrong_source', lambda r: r.update(source_sha='0' * 40)),
               ('wrong_attempt', lambda r: r.update(attempt=attempt + 1)),
               ('missing_case', lambda r: r['checks'].pop()),
               ('duplicate_case', lambda r: r['checks'].append(r['checks'][0])),
               ('false_success', lambda r: r.update(accepted=False)),
               ('wrong_platform', lambda r: r.update(platform='other')),
               ('wrong_sdk_version', lambda r: r.update(sdk_version='3.40.0')),
               ('missing_module', lambda r: r['binary_identities'].pop('module'))]
    for name, mutate in changes:
        altered = copy.deepcopy(report); mutate(altered)
        try: validate(altered, members, platform, source, run, attempt)
        except (ValueError, KeyError): passed.append(name)
        else: raise ValueError('verifier accepted ' + name)
    for name, member in [('tampered_binary', report['binary_identities']['probe']['member']),
                         ('tampered_module', report['binary_identities']['module']['member']),
                         ('tampered_original', 's15-fixtures/book.txt'),
                         ('tampered_graph', 's15-evidence/graph.json'),
                         ('changed_history', 's15-evidence/after/history.json')]:
        altered = dict(members); altered[member] = altered[member] + b'!'
        if member == 's15-evidence/graph.json':
            broken = json.loads(members[member]); broken['cases']['mixed_sdk_graph_refused']['refused'] = False
            altered[member] = json.dumps(broken).encode()
        try: validate(report, altered, platform, source, run, attempt)
        except (ValueError, KeyError): passed.append(name)
        else: raise ValueError('verifier accepted ' + name)
    try: load('{"source_sha":"a","source_sha":"b"}')
    except ValueError: passed.append('duplicate_json_key')
    else: raise ValueError('duplicate JSON accepted')
    for name, entries in [('duplicate_zip', [('s15-evidence/result.json', b'{}')] * 2),
                          ('missing_report', [('x', b'1')]),
                          ('unsafe_zip', [('../evil', b'1'), ('s15-evidence/result.json', b'{}')])]:
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            for path, value in entries: z.writestr(path, value)
        try: unpack(data.getvalue())
        except ValueError: passed.append(name)
        else: raise ValueError('verifier accepted ' + name)
    return passed


def artifact_bytes(artifact, source, run, attempt, expected_name):
    require(artifact['name'] == expected_name and not artifact['expired'] and artifact['size_in_bytes'] > 0,
            'artifact name/bytes for ' + expected_name)
    require(artifact['workflow_run']['id'] == run and artifact['workflow_run']['head_sha'] == source,
            'artifact source/run for ' + expected_name)
    require(datetime.datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00'))
            > datetime.datetime.now(datetime.timezone.utc), 'artifact expiry for ' + expected_name)
    with tempfile.TemporaryFile() as stream:
        download_artifact_zip(artifact['id'], stream)
        stream.seek(0); data = stream.read()
    digest = hashlib.sha256(data).hexdigest()
    require(len(data) == artifact['size_in_bytes'] and artifact['digest'] == 'sha256:' + digest,
            'actual ZIP bytes/digest for ' + expected_name)
    return data, digest


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source = os.environ['GITHUB_SHA']; run = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT']); out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    summary = {'accepted': False, 'source_sha': source, 'run_id': run, 'attempt': attempt,
               'artifacts': [], 'jobs': [], 'rejections': {}, 'binaries': {}, 'frozen': {},
               'failures': [], 'system_share_ui': False, 'six_devices': False}
    try:
        run_data = fetch(f'actions/runs/{run}')
        require(run_data['head_sha'] == source and run_data['run_attempt'] == attempt
                and run_data['path'] == '.github/workflows/reader-next-s15.yml', 'run identity')
        jobs = pages(f'actions/runs/{run}/attempts/{attempt}/jobs', 'jobs')
        artifacts = pages(f'actions/runs/{run}/artifacts', 'artifacts')
        require(len({a['name'] for a in artifacts}) == len(artifacts) == len({a['id'] for a in artifacts}),
                'duplicate artifacts')
        for platform, runner in PLATFORMS:
            name = f'reader-next-s15-{platform}-{run}-{attempt}'
            matching = [a for a in artifacts if a['name'] == name]
            require(len(matching) == 1, 'unique artifact ' + name)
            artifact = matching[0]
            matching = [j for j in jobs if j['name'] == f'original export 3.41 ({runner})']
            require(len(matching) == 1, 'unique completed job for ' + platform)
            job = matching[0]
            require(job['head_sha'] == source and job['run_attempt'] == attempt and job['status'] == 'completed'
                    and job['conclusion'] == 'success', 'same-source successful producer')
            data, digest = artifact_bytes(artifact, source, run, attempt, name)
            members = unpack(data)
            report = load(members['s15-evidence/result.json'])
            validate(report, members, platform, source, run, attempt)
            summary['rejections'][platform] = rejections(report, members, platform, source, run, attempt)
            summary['binaries'][platform] = report['binary_identities']
            summary['jobs'].append({k: job[k] for k in ('id', 'name', 'status', 'conclusion', 'head_sha', 'run_attempt')})
            summary['artifacts'].append({'id': artifact['id'], 'name': artifact['name'],
                                         'size_in_bytes': artifact['size_in_bytes'],
                                         'digest': artifact['digest'], 'zip_sha256': digest,
                                         'expires_at': artifact['expires_at']})
        frozen_name = f'reader-next-s15-frozen-340-{run}-{attempt}'
        matching = [a for a in artifacts if a['name'] == frozen_name]
        require(len(matching) == 1, 'unique frozen artifact')
        matching_jobs = [j for j in jobs if j['name'] == 'frozen 3.40 default graph (ubuntu-22.04)']
        require(len(matching_jobs) == 1, 'unique frozen job')
        job = matching_jobs[0]
        require(job['head_sha'] == source and job['run_attempt'] == attempt and job['status'] == 'completed'
                and job['conclusion'] == 'success', 'frozen producer success')
        data, digest = artifact_bytes(matching[0], source, run, attempt, frozen_name)
        members = unpack(data)
        report = load(members['s15-frozen-work/frozen.json'])
        validate_frozen(report, members, source, run, attempt)
        summary['frozen'] = {'report': {k: report[k] for k in ('sdk', 'checks', 'count')},
                             'artifact': {'id': matching[0]['id'], 'name': matching[0]['name'],
                                          'size_in_bytes': matching[0]['size_in_bytes'],
                                          'digest': matching[0]['digest'], 'zip_sha256': digest,
                                          'expires_at': matching[0]['expires_at']},
                             'job': {k: job[k] for k in ('id', 'name', 'status', 'conclusion', 'head_sha', 'run_attempt')}}
        summary['jobs'].append(summary['frozen']['job'])
        summary['artifacts'].append(summary['frozen']['artifact'])
        summary['accepted'] = True
    except Exception as exc:
        summary['failures'].append(repr(exc))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__':
    main()
