"""Strict actual-source-pair, process, raw request and binary binding."""
import configparser
import copy
import hashlib
import json
import re
from run import BASE, OLD_HOST, OLD_SDK, NEW_SDK


def validate(value, source, run, attempt):
    assert value['accepted'] is True and not value['problems']
    assert value['source_sha'] == source and str(value['run_id']) == str(run) and str(value['attempt']) == str(attempt)
    assert (value['base'], value['old_host'], value['old_sdk'], value['new_sdk']) == (BASE, OLD_HOST, OLD_SDK, NEW_SDK)
    assert value['complete_product'] is value['host_ui_compatibility_claimed'] is False
    assert set(value['programs']) == {'old', 'new'}
    for name, version, owner, sdk in [('old', '3.40.0', OLD_HOST, OLD_SDK), ('new', '3.41.0', source, NEW_SDK)]:
        program = value['programs'][name]
        assert (program['runtime_version'], program['sdk_version'], program['host_source'], program['sdk_source']) == (version, version, owner, sdk)
        for key in ('binary_sha256', 'map_sha256', 'backend_source_sha256', 'records_source_sha256'):
            assert re.fullmatch('[0-9a-f]{64}', program[key])
    expected = {writer + '-to-' + reader + '-' + kind
                for writer, reader in [('old', 'old'), ('new', 'new'), ('old', 'new'), ('new', 'old')]
                for kind in ('txt', 'epub', 'pdf', 'cbz')}
    expected.update(writer + '-to-' + reader + '-' + kind + '-' + stage
                    for writer, reader, kinds in [('old', 'old', ['txt']), ('new', 'new', ['txt']),
                                                  ('old', 'new', ['txt', 'epub', 'pdf', 'cbz'])]
                    for kind in kinds for stage in ('before', 'after'))
    assert len(value['cases']) == 28 and {case['name'] for case in value['cases']} == expected
    for case in value['cases']:
        if case['kind'] == 'reopen':
            assert case['writer_process']['accepted'] is True and case['wire_copies_unchanged'] is True
            assert case['original_wire_count'] == len(case['original_wire_sha256']) >= 8
            outcome = case['reader_process']
            if case['reverse_observation']:
                assert (case['writer'], case['reader']) == ('new', 'old')
                if outcome['accepted'] is False:
                    assert outcome['exit'] == 1 and outcome['rejection_stage'] == 'actual-record-jump'
            else:
                assert outcome['accepted'] is True
        else:
            assert case['kind'] == 'kill-retry' and case['killed_by'] == 'SIGKILL' and case['no_auto_replay'] is True
            assert case['original_parser'] == value['programs'][case['writer']]['runtime_version']
            assert re.fullmatch('[0-9a-f]{32}', case['original_revision']) and re.fullmatch('[0-9a-f]{64}', case['request_sha256'])
            assert case['first_created'] == (1 if case['boundary'] == 'before' else 0) and case['second_created'] == 0
            assert case['first_retry']['accepted'] is case['second_retry']['accepted'] is True
            assert case['boundary_observation'] == ('before-product-commit' if case['boundary'] == 'before' else 'after-product-commit-before-pending-clear')


def authenticate(raw, source, run, attempt):
    root = 'gtk-record-compatibility-evidence/'
    guard = json.loads(raw('gtk-record-compatibility-guard.json'))
    assert guard['accepted'] is True and guard['source_sha'] == source and str(guard['run_id']) == str(run) and str(guard['attempt']) == str(attempt)
    assert (guard['base'], guard['old_host'], guard['old_sdk'], guard['new_sdk']) == (BASE, OLD_HOST, OLD_SDK, NEW_SDK)
    value = json.loads(raw(root + 'result.json'))
    validate(value, source, run, attempt)
    mutations = [('source_sha', 'foreign'), ('run_id', '0'), ('attempt', '0'), ('old_host', source),
                 ('old_sdk', NEW_SDK), ('new_sdk', OLD_SDK), ('base', 'wrong'), ('accepted', False),
                 ('complete_product', True), ('host_ui_compatibility_claimed', True), ('cases', []), ('programs', {})]
    for key, replacement in mutations:
        changed = copy.deepcopy(value);changed[key] = replacement
        try:
            validate(changed, source, run, attempt)
        except (AssertionError, KeyError):
            continue
        raise AssertionError('compatibility protocol accepted ' + key)
    programs = value['programs']
    for program in programs.values():
        assert hashlib.sha256(raw(root + program['binary'], 64 * 1024 * 1024)).hexdigest() == program['binary_sha256']
        assert hashlib.sha256(raw(root + program['map'], 8 * 1024 * 1024)).hexdigest() == program['map_sha256']
    for mode in ('first', 'resumed', 'routes', 'graphs'):
        log = raw(root + 'old-original-' + mode + '.log').decode()
        assert re.search(r'reading-records backend checks=\d+ process=' + mode + r' passed', log)

    def process(record, program, *, retry=None, original_parser=None, revision=None):
        log = raw(root + record['log'])
        assert hashlib.sha256(log).hexdigest() == record['log_sha256']
        if not record['accepted']:
            assert b'compatibility check failed: actual GTK jump independently proves FOUND and emits accepted frame' in log
            return
        data = raw(root + record['report'])
        assert hashlib.sha256(data).hexdigest() == record['report_sha256']
        report = json.loads(data)
        assert report['accepted'] is True and report['runtime_version'] == program['runtime_version']
        assert report['check_count'] == record['checks'] == len(report['checks']) and record['checks'] > 15
        assert all(row['passed'] is True for row in report['checks'])
        names = [row['name'] for row in report['checks']]
        assert 'actual linked SDK runtime version exact' in names
        assert 'real GTK owner opens profile in new process' in names
        assert 'public stored original block byte identical' in names
        if retry is not None:
            assert report['created'] == retry and report['retained_parser'] == original_parser and report['retained_revision'] == revision
            assert 'new host open never auto-replays original uncertain request' in names
            assert 'retry product wire byte identical to original durable capture request' in names
        if report['mode'] in ('verify', 'retry'):
            assert 'actual GTK jump independently proves FOUND and emits accepted frame' in names
            assert 'accepted actual GTK session publicly recaptures original selector' in names
        return report

    reverse = {}
    for case in value['cases']:
        writer, reader = programs[case['writer']], programs[case['reader']]
        if case['kind'] == 'reopen':
            written = process(case['writer_process'], writer)
            assert written['mode'] == 'seed'
            if case['format'] in ('epub', 'pdf'):
                assert 'old process retains real public v1 revision' in [row['name'] for row in written['checks']]
            process(case['reader_process'], reader)
            for name, digest in case['original_wire_sha256'].items():
                assert re.fullmatch('[0-9a-f]{32}\.json', name)
                folder = case['writer_process']['report'].rsplit('/', 1)[0]
                assert hashlib.sha256(raw(root + folder + '/' + name)).hexdigest() == digest
            if case['reverse_observation']:
                reverse[case['format']] = case['reader_process']['accepted']
        else:
            original = raw(root + case['original_request'])
            assert hashlib.sha256(original).hexdigest() == case['request_sha256']
            config = configparser.ConfigParser(interpolation=None);config.read_string(original.decode())
            assert config['request']['parser'] == case['original_parser'] and config['request']['revision'] == case['original_revision']
            process(case['first_retry'], reader, retry=case['first_created'], original_parser=case['original_parser'], revision=case['original_revision'])
            process(case['second_retry'], reader, retry=0, original_parser=case['original_parser'], revision=case['original_revision'])
    return dict(accepted=True, old_host=OLD_HOST, old_sdk=OLD_SDK, new_sdk=NEW_SDK,
                runtime_versions={key: item['runtime_version'] for key, item in programs.items()},
                binary_sha256={key: item['binary_sha256'] for key, item in programs.items()},
                reopened_cases=16, real_kill_cases=12, protocol_rejections=len(mutations),
                reverse_old_actual_acceptance=reverse, complete_product=False)
