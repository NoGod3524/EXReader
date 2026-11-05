"""Actions-only pinned archive grammar observation; no criterion changes or native admission."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'f25ce471ce057c3181eb81853e6912350a1b5fed'
TREE = '303060019705b60728bb45467c1c6f93c13a6c0f'
BRANCH = 'codex/reader-sync-ios-archive-diagnostic-20261029'
SCRIPT = 'tests/reader_sync_ios_archive_diagnostic_20261029.py'
WORKFLOW = '.github/workflows/reader-sync-ios-archive-diagnostic-20261029.yml'
ORIGINAL_BRANCH = 'codex/reader-sync-public-hash-20261029'
ORIGINAL_WORKFLOW = '.github/workflows/reader-sync-public-hash-20261029.yml'
RUN = 40833911771
JOB = 123314193565
PIN = dict(id=12881237625, name='sync-public-hash-iphone-40833911771-1',
           size_in_bytes=34276768,
           digest='sha256:fb4aa0e29a22f4a50df1f321721f3a262ba47f4acac375850f871371e321c8e3')
ORIGINAL_ROOT = '/Users/runner/work/EXReader/EXReader'
PREFIX = 'build/f06/iphonesimulator-build/'
PAIRS = {
    'built': dict(path=PREFIX + 'product-build/reading-state/libreader_reading_state_codec.a',
                  bytes=33608, sha256='3f9e7d9158334a73360bbc480d6a14bf069404d5fc7bb4bde2fefb187d654f62'),
    'installed': dict(path=PREFIX + 'product/lib/libreader_reading_state_codec.a',
                      bytes=33608, sha256='0263850f19ce0ad5b1312a1403e58253b839e6ca04e5b989dc6bdc2d6e6c5ee2')}
PUBLIC = 'tests/reader_public_boundary_v1_20261028/run.py'
PUBLIC_SHA = '7752eeca7f45aaa22adbb5881fa93459448a66550181a6ca9e6376bfece92325'
OUT = ROOT / 'build/sync-ios-archive-diagnostic'
EXPECTED_REFUSAL = 'noncanonical BSD name alignment/padding'


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
    require(os.environ.get('GITHUB_REF_NAME') == BRANCH and os.environ.get('GITHUB_EVENT_NAME') == 'push' and
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
            'original union producer bytes differ')
    require(sha(ROOT / PUBLIC) == PUBLIC_SHA, 'frozen public criterion differs')
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


def frozen():
    spec = importlib.util.spec_from_file_location('pinned_public_archive_criterion', ROOT / PUBLIC)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe_archive(raw):
    """Bounded framing observations, NEVER an alternative acceptance parser."""
    result = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), frames=[], framing_complete=False)
    try:
        require(0 < len(raw) <= 16 * 1024**2 and raw.startswith(b'!<arch>\n'), 'bounded ordinary archive required')
        offset = 8
        while offset < len(raw):
            require(len(result['frames']) < 32, '32-frame diagnostic ceiling')
            header = raw[offset:offset + 60]
            row = dict(ordinal=len(result['frames']), header_offset=offset, header_hex=header.hex())
            result['frames'].append(row)
            require(len(header) == 60 and header[58:] == b'`\n', 'truncated or malformed frame header')
            fields = {}
            for label, begin, end, base in (('timestamp', 16, 28, 10), ('uid', 28, 34, 10),
                    ('gid', 34, 40, 10), ('mode', 40, 48, 8), ('size', 48, 58, 10)):
                field = header[begin:end]
                fields[label] = dict(raw_hex=field.hex())
                pattern = rb'[0-7]+ *' if base == 8 else rb'[0-9]+ *'
                require(re.fullmatch(pattern, field) is not None, 'unsupported numeric frame field: ' + label)
                value = int(field, base)
                spelling = (format(value, 'o') if base == 8 else str(value)).encode()
                fields[label].update(value=value, canonical=field == spelling.ljust(len(field), b' '))
            row['fields'] = fields
            match = re.fullmatch(rb'#1/([1-9][0-9]*) *', header[:16])
            require(match is not None, 'unsupported non-BSD name frame')
            length = int(match[1]); size = fields['size']['value']; start = offset + 60; end = start + size
            row.update(extended_name_bytes=length, data_offset=start, member_bytes=size, member_end=end)
            require(0 < length <= 256 and length < size and end <= len(raw), 'bounded extended name/member extent')
            extended = raw[start:start + length]; name = extended.split(b'\0', 1)[0]
            padding = (-(start + len(name))) % 8
            row.update(extended_name_hex=extended.hex(), name_prefix_hex=name.hex(),
                name_ascii=name.decode('ascii') if all(32 <= c < 127 for c in name) else None,
                name_prefix_bytes=len(name), trailing_name_bytes=length - len(name),
                trailing_name_all_nul=extended[len(name):] == b'\0' * (length - len(name)),
                strict_expected_padding=padding,
                strict_name_alignment_matches=bool(name) and length == len(name) + padding and extended == name + b'\0' * padding,
                name_length_field_canonical=header[:16] == ('#1/' + str(length)).encode().ljust(16, b' '),
                payload_offset=start + length, payload_bytes=size - length,
                payload_sha256=hashlib.sha256(raw[start + length:end]).hexdigest(),
                outer_padding_hex=raw[end:end + size % 2].hex())
            require(raw[end:end + size % 2] == b'\n' * (size % 2), 'outer frame padding differs')
            offset = end + size % 2
        require(offset == len(raw) and result['frames'], 'archive frame extent differs')
        result['framing_complete'] = True
    except (ValueError, OverflowError) as error:
        result['framing_error'] = str(error)[:1024]
    return result


def compare_bytes(before, after):
    first = []; count = 0
    for index, (a, b) in enumerate(zip(before, after)):
        if a != b:
            count += 1
            if len(first) < 32: first.append(index)
    return dict(exact_equal=before == after, built_bytes=len(before), installed_bytes=len(after),
        different_common_bytes=count, first_different_offsets=first, length_difference=len(after) - len(before),
        all_bytes_outside_offset_24_through_35_equal=len(before) == len(after) and before[:24] == after[:24] and before[36:] == after[36:],
        criterion_admission=False)


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
            run['workflow_id'] == 400305015 and run['event'] == 'push' and
            run['status'] == 'completed' and run['conclusion'] == 'failure', 'original run not terminal pinned failure')
    jobs = pages(f'actions/runs/{RUN}/attempts/1/jobs', 'jobs')
    selected = [j for j in jobs if j['id'] == JOB and j['name'] == 'boundary-iphone']
    require(len(selected) == 1, 'unique original iPhone job required')
    job = selected[0]
    require(job['run_id'] == RUN and job['head_sha'] == BASE and job['status'] == 'completed' and
            job['conclusion'] == 'failure', 'original iPhone job identity differs')
    for name, conclusion in (
            ('Original F06 SDK342 profile and actual relocated entries, PURE remains OFF', 'success'),
            ('Public C/C++ and unchanged selector/C06 assertions on actual native targets', 'success'),
            ('Capture installed archives, make dependency files, native maps and entries', 'failure')):
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
        require(len(names) <= 20000 and sum(i.file_size for i in names.values()) <= 2 * 1024**3,
                'bounded original file count/expanded bytes exceeded')
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
        require(all(report[k] == v for k, v in ident.items()) and report['target'] == 'iphone' and
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
        require(all(build[k] == v for k, v in ident.items()) and build['target'] == 'iphone' and
                build['source'] == source and build['hash_prefix'] == ORIGINAL_ROOT + '/build/sync-public-hash/hash-stage',
                'original workspace/build identity differs')
        result['original_source_verified'] = True
        result['stage'] = 'exact_original_reading_state_pair'
        pairs = [p for p in report.get('built_installed_archive_comparison', []) if p.get('owner') == 'reading-state']
        require(len(pairs) == 1, 'exact original failed owner pair missing/ambiguous')
        pair = pairs[0]
        result['pair'] = dict(owner='reading-state', originals={}, observations={}, frozen_parser={}, byte_comparison=None)
        retained = result['pair']; values = {}
        for role, pin in PAIRS.items():
            name = pin['path']
            require(pair[role] == name and pair[role + '_bytes'] == pin['bytes'] and
                    pair[role + '_sha256'] == pin['sha256'], 'original failed pair claim differs')
            require(name in names and names[name].file_size == pin['bytes'] and
                    inventory['files'][name]['symlink_target'] is None, 'exact plain archive member missing')
            raw = archive.read(name)
            require(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'pinned original pair bytes differ')
            values[role] = raw
            retained['originals'][role] = dict(pin)
            # Save bounded raw geometry before attempting the frozen strict parser.
            retained['observations'][role] = observe_archive(raw)
        before, after = values['built'], values['installed']
        retained['byte_comparison'] = compare_bytes(before, after)
        require(retained['byte_comparison']['different_common_bytes'] == pair['different_common_bytes'] == 1 and
                retained['byte_comparison']['first_different_offsets'] == pair['first_different_offsets'] == [33] and
                retained['byte_comparison']['length_difference'] == pair['length_difference'] == 0, 'printed original difference differs')
        module = frozen()
        for role, raw in values.items():
            try:
                index, objects = module.bsd_index_archive(raw)
                retained['frozen_parser'][role] = dict(accepted=True, index=index, ordered_objects=objects)
            except AssertionError as error:
                retained['frozen_parser'][role] = dict(accepted=False, error=str(error)[:1024])
        try:
            accepted = module.installed_archive_equivalence(before, after, 'iphone')
            retained['unchanged_criterion'] = dict(accepted=True, result=accepted)
        except AssertionError as error:
            retained['unchanged_criterion'] = dict(accepted=False, error=str(error)[:1024])
        for role in values:
            require(retained['observations'][role]['framing_complete'], 'bounded raw framing incomplete: ' + role)
            require(retained['frozen_parser'][role] == dict(accepted=False, error=EXPECTED_REFUSAL), 'unexpected frozen strict grammar outcome')
        require(retained['unchanged_criterion'] == dict(accepted=False, error=EXPECTED_REFUSAL), 'original criterion refusal changed')
        left, right = (retained['observations'][role]['frames'] for role in ('built', 'installed'))
        retained['ordered_frame_name_and_payloads_equal'] = [
            (r['extended_name_hex'], r['payload_bytes'], r['payload_sha256']) for r in left] == [
            (r['extended_name_hex'], r['payload_bytes'], r['payload_sha256']) for r in right]
        retained['strict_alignment_mismatch_ordinals'] = {
            role: [r['ordinal'] for r in retained['observations'][role]['frames'] if not r['strict_name_alignment_matches']]
            for role in values}
        result['scope'] = 'One pinned original ReadingState build/install pair; raw bounded geometry only, never a replacement archive criterion'
        require('sha256:' + sha(upload) == PIN['digest'], 'original download changed during observation')
        result['diagnostic_complete'] = True
        result['stage'] = 'complete'


def synthetic_archive(extra_name_nuls=0):
    """Small in-memory Actions fixture, never substituted for original bytes."""
    raw = b'!<arch>\n'
    for name, payload in ((b'__.SYMDEF SORTED', b'index-fixture'), (b'owner.o', b'object-fixture')):
        start = len(raw) + 60
        padding = (-(start + len(name))) % 8 + (extra_name_nuls if name == b'owner.o' else 0)
        extended = name + b'\0' * padding
        size = len(extended) + len(payload)
        header = ('#1/' + str(len(extended))).encode().ljust(16, b' ') + b'1'.ljust(12, b' ') + b'0'.ljust(6, b' ') * 2
        header += b'100644'.ljust(8, b' ') + str(size).encode().ljust(10, b' ') + b'`\n'
        raw += header + extended + payload + b'\n' * (size % 2)
    return raw


class Controls(unittest.TestCase):
    def test_canonical_fixture_and_timestamp_only(self):
        raw = synthetic_archive(); observed = observe_archive(raw)
        self.assertTrue(observed['framing_complete'])
        self.assertTrue(all(r['strict_name_alignment_matches'] for r in observed['frames']))
        module = frozen(); module.bsd_index_archive(raw)
        changed = raw[:24] + b'2'.ljust(12, b' ') + raw[36:]
        comparison = compare_bytes(raw, changed)
        self.assertEqual(comparison['different_common_bytes'], 1)
        self.assertTrue(comparison['all_bytes_outside_offset_24_through_35_equal'])
        self.assertFalse(comparison['criterion_admission'])
        self.assertEqual(module.installed_archive_equivalence(raw, changed, 'iphone')['mode'], 'iphonesimulator-first-bsd-index-timestamp')

    def test_nonminimal_name_padding_is_observed_not_admitted(self):
        raw = synthetic_archive(8); observed = observe_archive(raw)
        self.assertTrue(observed['framing_complete'])
        self.assertFalse(observed['frames'][1]['strict_name_alignment_matches'])
        self.assertTrue(observed['frames'][1]['trailing_name_all_nul'])
        with self.assertRaisesRegex(AssertionError, EXPECTED_REFUSAL): frozen().bsd_index_archive(raw)
        changed = raw[:24] + b'2'.ljust(12, b' ') + raw[36:]
        with self.assertRaisesRegex(AssertionError, EXPECTED_REFUSAL): frozen().installed_archive_equivalence(raw, changed, 'iphone')

    def test_truncated_extent_and_malformed_numeric_refuse(self):
        raw = synthetic_archive()
        for bad in (raw[:20], raw[:-3], raw[:56] + b'bad       ' + raw[66:]):
            observed = observe_archive(bad)
            self.assertFalse(observed['framing_complete'])
            self.assertIn('framing_error', observed)

    def test_bounded_name_and_frame_count(self):
        raw = synthetic_archive()
        bad = raw[:8] + b'#1/257'.ljust(16, b' ') + raw[24:]
        self.assertFalse(observe_archive(bad)['framing_complete'])
        repeated = raw + raw[8:] * 16
        observed = observe_archive(repeated)
        self.assertFalse(observed['framing_complete']); self.assertEqual(len(observed['frames']), 32)

    def test_payload_difference_not_hidden_and_offsets_bounded(self):
        raw = synthetic_archive(); changed = raw[:-2] + bytes([raw[-2] ^ 1]) + raw[-1:]
        self.assertFalse(compare_bytes(raw, changed)['all_bytes_outside_offset_24_through_35_equal'])
        with self.assertRaises(AssertionError): frozen().installed_archive_equivalence(raw, changed, 'iphone')
        compared = compare_bytes(bytes(100), bytes([1]) * 100)
        self.assertEqual(compared['different_common_bytes'], 100)
        self.assertEqual(len(compared['first_different_offsets']), 32)
        self.assertFalse(compare_bytes(raw, raw + b'x')['all_bytes_outside_offset_24_through_35_equal'])

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
                  archive_criterion_changed=False, native_rebuilt=False, host_provider_proof=False,
                  combined_named_boundaries=False, f07_accepted=False, archive_pair_admitted=False)
    try:
        inspect(result)
    except Exception as error:
        result['failure'] = dict(type=type(error).__name__, message=str(error)[:1024])
        raise
    finally:
        rendered = json.dumps(result, indent=2, sort_keys=True) + '\n'
        require(len(rendered.encode()) <= 256 * 1024, 'bounded diagnostic JSON ceiling')
        (OUT / 'report.json').write_text(rendered)
        print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
