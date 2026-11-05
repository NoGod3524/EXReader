"""Actions-only pinned cache inspection; no selector changes or native admission."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'f25ce471ce057c3181eb81853e6912350a1b5fed'
TREE = '303060019705b60728bb45467c1c6f93c13a6c0f'
BRANCH = 'codex/reader-sync-public-hash-cache-diagnostic-20261029'
SCRIPT = 'tests/reader_sync_public_hash_cache_diagnostic_20261029.py'
WORKFLOW = '.github/workflows/reader-sync-public-hash-cache-diagnostic-20261029.yml'
ORIGINAL_BRANCH = 'codex/reader-sync-public-hash-20261029'
ORIGINAL_WORKFLOW = '.github/workflows/reader-sync-public-hash-20261029.yml'
RUN = 40833911771
JOB = 123314193573
PIN = dict(id=12879963967, name='sync-public-hash-android-40833911771-1',
           size_in_bytes=69520521,
           digest='sha256:9fa61b42bd9976c77bbee6129abfde9c0a64b8e7a2a2bfe67d3d8786680bbb77')
ORIGINAL_ROOT = '/home/runner/work/EXReader/EXReader'
HOME = ORIGINAL_ROOT + '/examples/android/app/src/main/cpp'
PREFIX = 'examples/android/app/.cxx/'
OUT = ROOT / 'build/sync-public-hash-cache-diagnostic'
KEYS = ('ANDROID_ABI', 'ANDROID_PLATFORM', 'ANDROID_STL', 'CMAKE_HOME_DIRECTORY',
        'CMAKE_CACHEFILE_DIR', 'CMAKE_TOOLCHAIN_FILE', 'CMAKE_SYSTEM_PROCESSOR',
        'EXR_HOST_SDK_VERSION', 'EXR_READER_SELECTOR_BYTES_CANDIDATE')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def guard():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions-only execution')
    require(os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'wrong repository')
    require(os.environ.get('GITHUB_REF_NAME') == BRANCH and
            os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'one named branch attempt only')
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    require(git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'checkout SHA differs')
    require(git('rev-parse', BASE + '^{tree}') == TREE, 'original tree differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    expected = {SCRIPT: 'A', WORKFLOW: 'A'}
    actual = {p: status for status, p in
              (row.split('\t') for row in git('diff', '--name-status', BASE, 'HEAD').splitlines())}
    require(actual == expected, 'exact two additive diagnostic paths required')
    require(not git('status', '--porcelain', '--untracked-files=no'), 'tracked source changed')
    require(sha(ROOT / 'tests/reader_sync_public_hash_20261029/run.py') ==
            '7ee993ec746b5410315c637aaa3cdcb3b9d21cf8c0cd61df1bf6f5741ca845f3',
            'original rejecting selector bytes differ')
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'], original_source_sha=BASE,
                original_run_id=RUN, original_attempt=1,
                diagnostic_source={p: sha(ROOT / p) for p in expected})


def helper():
    # This module comes from checked-out, unchanged original Git source, not ZIP payload.
    path = ROOT / 'tests/reader_original_hash_boundary_20261029/package_contract.py'
    spec = importlib.util.spec_from_file_location('pinned_hash_safe_zip', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cache_rows(raw, member):
    require(member.startswith(PREFIX) and member.endswith('/CMakeCache.txt'), 'wrong cache member')
    require(len(raw) <= 2 * 1024 * 1024, 'cache resource limit')
    text = raw.decode('utf-8')
    require(all(ord(c) >= 32 or c in '\t\r\n' for c in text) and '\x7f' not in text,
            'unsupported control character in cache')
    rows = {key: [] for key in KEYS}
    for number, raw_line in enumerate(text.splitlines(keepends=True), 1):
        line = raw_line.removesuffix('\n').removesuffix('\r')
        for key in KEYS:
            if not (line.startswith(key + ':') or line.startswith(key + '=')):
                continue
            require(len(raw_line) <= 4096 and all(ord(c) >= 32 or c in '\r\n' for c in raw_line)
                    and '\x7f' not in raw_line, 'unsafe or oversized selected cache row')
            match = re.fullmatch(re.escape(key) + r':([A-Z_]+)=(.*)', line)
            require(match is not None, 'malformed selected cache row')
            require(len(rows[key]) < 16, 'selected cache row count limit')
            rows[key].append(dict(line_number=number, raw_line=raw_line,
                                  type=match[1], value=match[2]))
    # Exactly reproduce read_text universal-newline spelling for the original
    # regex/literal check. Lexical path comparison is diagnostic only: never
    # pretend to replay the original filesystem's Path.resolve/symlink state.
    universal = text.replace('\r\n', '\n').replace('\r', '\n')
    homes = re.findall(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$', universal, re.M)
    normalized = []
    for value in homes:
        require(len(value) <= 4096, 'home value limit')
        normalized.append(posixpath.normpath(value) if value.startswith('/') and
                          '\\' not in value and ':' not in value else None)
    literal = 'ANDROID_ABI:STRING=x86_64' in universal
    abi_values = [row['value'] for row in rows['ANDROID_ABI']]
    return dict(path=member, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                rows=rows, counts={k: len(v) for k, v in rows.items()},
                original_literal_abi_substring=literal,
                original_home_regex_values=homes, lexical_home_normalized=normalized,
                lexical_home_matches_expected=(normalized == [HOME]),
                home_exact_matches_expected=(homes == [HOME]),
                abi_value_only_matches=(abi_values == ['x86_64']),
                lexical_original_candidate=(normalized == [HOME] and literal),
                original_physical_resolve_replayed=False)


def artifact_identity(artifact):
    require(all(artifact.get(k) == v for k, v in PIN.items()), 'pinned artifact metadata differs')
    require(artifact['expired'] is False and artifact['workflow_run']['id'] == RUN and
            artifact['workflow_run']['head_sha'] == BASE and
            artifact['workflow_run']['head_branch'] == ORIGINAL_BRANCH, 'artifact source/run differs')


def inspect(result):
    sys.path.insert(0, str(ROOT / 'tools'))
    from check_parallel_integration import fetch, pages, download_artifact_zip
    result['stage'] = 'provider_identity'
    run = fetch(f'actions/runs/{RUN}/attempts/1')
    require(run['id'] == RUN and run['run_attempt'] == 1 and run['head_sha'] == BASE and
            run['head_branch'] == ORIGINAL_BRANCH and run['path'] == ORIGINAL_WORKFLOW and
            run['status'] == 'completed' and run['conclusion'] == 'failure', 'original run not terminal pinned failure')
    jobs = pages(f'actions/runs/{RUN}/attempts/1/jobs', 'jobs')
    selected = [j for j in jobs if j['id'] == JOB and j['name'] == 'boundary-android']
    require(len(selected) == 1, 'unique original Android job required')
    job = selected[0]
    require(job['head_sha'] == BASE and job['status'] == 'completed' and
            job['conclusion'] == 'failure', 'original Android job identity differs')
    for name, conclusion in (
            ('Build exact installed SDK and package', 'success'),
            ('Run reactivecircus/android-emulator-runner@v2', 'failure'),
            ('Capture APK, installed archives and actual compiler dependency graph', 'failure')):
        step = [s for s in job['steps'] if s['name'] == name]
        require(len(step) == 1 and step[0]['conclusion'] == conclusion, 'original step state differs')
    artifacts = pages(f'actions/runs/{RUN}/artifacts', 'artifacts')
    selected = [a for a in artifacts if a['id'] == PIN['id'] or a['name'] == PIN['name']]
    require(len(selected) == 1, 'ambiguous pinned original artifact')
    artifact = selected[0]
    artifact_identity(artifact)
    stamp = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(stamp(job['started_at']) <= stamp(artifact['created_at']) <= stamp(job['completed_at']) and
            stamp(artifact['expires_at']) > datetime.now(timezone.utc), 'original producer time/expiry differs')
    result['original_artifact'] = {k: artifact[k] for k in PIN}
    result['original_job_id'] = JOB
    result['stage'] = 'original_upload'
    upload = OUT / 'original-upload.zip'
    with upload.open('w+b') as stream:
        download_artifact_zip(PIN['id'], output=stream)
    require(upload.stat().st_size == PIN['size_in_bytes'] and
            'sha256:' + sha(upload) == PIN['digest'], 'original upload bytes differ')
    result['original_upload_verified'] = True
    with zipfile.ZipFile(upload) as archive:
        names = helper().safe_members(archive)
        require('inventory.json' in names and names['inventory.json'].file_size <= 16 * 1024**2,
                'outer inventory missing/oversized')
        inventory = unique_json(archive.read('inventory.json'))
        ident = dict(source_sha=BASE, run_id=str(RUN), attempt='1')
        require(all(inventory.get(k) == v for k, v in ident.items()), 'original inventory identity differs')
        require({n for n, i in names.items() if not i.is_dir()} == set(inventory['files']) | {'inventory.json'},
                'complete original member inventory differs')
        result['stage'] = 'all_original_file_hashes'
        for name, record in inventory['files'].items():
            digest = hashlib.sha256(); size = 0
            with archive.open(name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block); size += len(block)
            require(size == record['bytes'] and digest.hexdigest() == record['sha256'], 'original retained file bytes differ')
        report = inventory['report']
        require(all(report[k] == v for k, v in ident.items()) and report['target'] == 'android' and
                report['capture_complete'] is False and report['named_boundary_accepted'] is False and
                report['f07_accepted'] is False, 'original failure was relabeled')
        result['original_file_count'] = len(inventory['files'])
        result['all_original_files_verified'] = True
        result['stage'] = 'original_source'
        def small_json(name):
            require(name in names and names[name].file_size <= 2 * 1024**2, 'metadata size limit')
            return unique_json(archive.read(name))
        source = small_json('build/sync-public-hash/source.json')
        lock = unique_json((ROOT / 'tests/reader_sync_public_hash_20261029/source_lock.json').read_bytes())
        paths = set(lock['adopted']) | set(lock['public_packet']) | set(lock['owner']) | set(lock['added'])
        require(len(paths) == 53 and source['authorized_paths_sha256'] == {p: sha(ROOT / p) for p in paths} and
                all(source[k] == v for k, v in ident.items()) and source['source_scope_passed'] is True and
                source['configured_runner_minutes'] == 725 and source['f07_accepted'] is False,
                'original 53-path source projection differs')
        build = small_json('build/sync-public-hash/build.json')
        require(all(build[k] == v for k, v in ident.items()) and build['target'] == 'android' and
                build['source'] == source and build['hash_prefix'] == ORIGINAL_ROOT + '/build/sync-public-hash/hash-stage',
                'original workspace/build identity differs')
        result['original_source_verified'] = True
        result['stage'] = 'all_actual_cxx_caches'
        caches = sorted(n for n, i in names.items() if not i.is_dir() and n.startswith(PREFIX) and
                        n.endswith('/CMakeCache.txt'))
        require(1 <= len(caches) <= 16, 'actual retained cxx cache count outside diagnostic bound')
        result['caches'] = []
        for name in caches:
            require(names[name].file_size <= 2 * 1024**2 and
                    inventory['files'][name]['symlink_target'] is None, 'cache size/alias limit')
            result['caches'].append(cache_rows(archive.read(name), name))
        result['retained_cache_count'] = len(caches)
        result['lexical_original_candidate_count'] = sum(c['lexical_original_candidate'] for c in result['caches'])
        result['scope'] = 'All retained actual .cxx cache files; no proof that absent original files were captured'
        result['diagnostic_complete'] = True
        result['stage'] = 'complete'


class Controls(unittest.TestCase):
    def row(self, value):
        return cache_rows(value.encode(), PREFIX + 'Debug/a/x86_64/CMakeCache.txt')

    def test_typed_value_not_selector_admission(self):
        for kind, literal in [('STRING', True), ('UNINITIALIZED', False)]:
            row = self.row(f'ANDROID_ABI:{kind}=x86_64\nCMAKE_HOME_DIRECTORY:INTERNAL={HOME}\n')
            self.assertEqual(row['original_literal_abi_substring'], literal)
            self.assertTrue(row['abi_value_only_matches'])
            self.assertEqual(row['rows']['ANDROID_ABI'][0]['type'], kind)
            self.assertFalse(row['original_physical_resolve_replayed'])

    def test_duplicate_missing_wrong_home_and_raw_newlines(self):
        raw = 'ANDROID_ABI:STRING=x86_64\r\nANDROID_ABI:STRING=arm64-v8a\r\n'
        row = self.row(raw + 'CMAKE_HOME_DIRECTORY:INTERNAL=/wrong\r\n')
        self.assertEqual(row['counts']['ANDROID_ABI'], 2)
        self.assertEqual(row['rows']['ANDROID_ABI'][0]['raw_line'], raw.splitlines(keepends=True)[0])
        self.assertFalse(row['abi_value_only_matches']); self.assertFalse(row['lexical_home_matches_expected'])
        self.assertEqual(self.row('')['counts']['ANDROID_ABI'], 0)

    def test_malformed_selected_rows_and_caps(self):
        for raw in ('ANDROID_ABI=x86_64', 'ANDROID_ABI:STRING=a\x00b',
                    'ANDROID_ABI:STRING=' + 'x' * 4096, 'ANDROID_ABI:STRING=x\n' * 17):
            with self.assertRaises(ValueError): self.row(raw)

    def test_json_duplicate_and_artifact_mutations(self):
        with self.assertRaises(ValueError): unique_json('{"a":1,"a":2}')
        good = dict(PIN, expired=False, workflow_run=dict(id=RUN, head_sha=BASE, head_branch=ORIGINAL_BRANCH))
        artifact_identity(good)
        for key, value in [('id', 1), ('digest', 'sha256:' + '0' * 64), ('size_in_bytes', 1)]:
            with self.assertRaises(ValueError): artifact_identity(dict(good, **{key: value}))

    def test_unsafe_zip_alias_and_parent(self):
        for paths in [('x/A', 'x/a'), ('../bad',), ('x', 'x/a')]:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                for name in paths: archive.writestr(name, b'no execution')
            buffer.seek(0)
            with zipfile.ZipFile(buffer) as archive:
                with self.assertRaises(ValueError): helper().safe_members(archive)


def main():
    ident = guard()
    if sys.argv[1:] == ['--self-test']:
        unittest.main(argv=[sys.argv[0]], verbosity=2)
        return
    require(not sys.argv[1:], 'unsupported arguments')
    OUT.mkdir(parents=True, exist_ok=False)
    result = dict(ident, diagnostic_complete=False, original_upload_verified=False,
                  all_original_files_verified=False, original_source_verified=False,
                  selector_repaired=False, native_rebuilt=False, host_provider_proof=False,
                  combined_named_boundaries=False, f07_accepted=False, installed_android_sync_runtime=False)
    try:
        inspect(result)
    except Exception as error:
        result['failure'] = dict(type=type(error).__name__, message=str(error)[:1024])
        raise
    finally:
        (OUT / 'report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
