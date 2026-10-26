"""S18 layout adapter for the unchanged S16 independent bindings.

Linux/Windows call the original function. The macOS copy below differs only in
its name and native magic predicate; all nine-role, report, archive, header,
projection and capability-symbol decisions are retained verbatim.
"""
import copy
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    's18_original_s16_artifacts', ROOT / 'tests/reader_next_s16/check_artifacts.py')
_original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_original)
json_load, entry, original_projection = _original.json_load, _original.entry, _original.original_projection
MACHO_MAGIC = {
    b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
    b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca',
}


def complete_bindings(archive, result, platform, overrides=None):
    if platform == 'macOS':
        return _mac_complete_bindings(archive, result, platform, overrides)
    return _original.complete_bindings(archive, result, platform, overrides)


def _mac_complete_bindings(archive, result, platform, overrides=None):
    """Recompute default compatibility and all executable/archive bindings."""
    def get(path):
        return (overrides or {}).get(path, archive.read(entry(archive, path)))
    def need(ok, message):
        if not ok:
            raise ValueError(message)
    suffix = '.exe' if platform == 'Windows' else ''
    expected = {
        'raw_probe': 'build/raw-consumer/s16-raw-probe',
        'raw_c_consumer': 'build/raw-consumer/s16-c-consumer',
        'default_c_consumer': 'build/default-consumer/s16-c-consumer',
        'original_probe': 'build/original-default-consumer/jump-history-probe',
        'original_c_consumer': 'build/original-default-consumer/jump-history-c-consumer',
        'baseline_probe': 'build/original-baseline-consumer/jump-history-probe',
        'baseline_c_consumer': 'build/original-baseline-consumer/jump-history-c-consumer',
        'original_raw_probe': 'build/original-raw-consumer/jump-history-probe',
        'original_raw_c_consumer': 'build/original-raw-consumer/jump-history-c-consumer',
    }
    need(set(result['programs']) == set(expected), 'exact nine native program roles')
    binaries = {}
    for role, stem in expected.items():
        record = result['programs'][role]
        path = stem + suffix
        data = get(path)
        need(record.get('member') == path and record.get('bytes') == len(data) > 0 and
             record.get('sha256') == hashlib.sha256(data).hexdigest(), 'actual program binding: ' + role)
        need(data[:4] in MACHO_MAGIC, 'native executable: ' + role)
        binaries[role] = record
    summaries = {}
    archives = {}
    headers = {}
    context = {key: os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')}
    need((result.get('source_sha'), str(result.get('run_id')), str(result.get('run_attempt')), result.get('platform')) ==
         (context['GITHUB_SHA'], context['GITHUB_RUN_ID'], context['GITHUB_RUN_ATTEMPT'], platform),
         'complete producer result identity')
    for family, stage, probe, consumer in (
            ('original-baseline', 'baseline', 'baseline_probe', 'baseline_c_consumer'),
            ('original-default', 'default', 'original_probe', 'original_c_consumer'),
            ('original-raw', 'raw', 'original_raw_probe', 'original_raw_c_consumer')):
        summary = json_load(get('evidence/' + family + '/summary.json'))
        report_bytes = get('evidence/' + family + '/report.json')
        report = json_load(report_bytes)
        checks = report['checks']
        names = [check['name'] for check in checks]
        need(all(summary['identity'].get(key) == value for key, value in context.items()) and
             summary.get('platform') == platform, 'original suite full identity: ' + family)
        need(summary.get('jump_history_module_accepted') is True and not summary.get('problems') and
             summary.get('checks_failed') == 0 and summary.get('checks_total') == len(checks) >= 149 and
             len(names) == len(set(names)) and all(check.get('pass') is True for check in checks),
             'complete original suite: ' + family)
        need(summary.get('report_sha256') == hashlib.sha256(report_bytes).hexdigest() and
             summary.get('probe_sha256') == binaries[probe]['sha256'] and
             summary.get('c_consumer_sha256') == binaries[consumer]['sha256'], 'suite program/report: ' + family)
        for key in ('cases', 'lifecycle', 'books', 'moves', 'sdk_version', 'parser_version',
                    'jump_history_version', 'reading_state_version', 'revisions_version'):
            need(summary.get(key) == report.get(key), 'suite projection differs from actual report: ' + key)
        header = get('families/' + stage + '-stage/include/reader_jump_history.h')
        library = 'reader_jump_history.lib' if platform == 'Windows' else 'libreader_jump_history.a'
        data = get('families/' + stage + '-stage/lib/' + library)
        need(data.startswith(b'!<arch>\n') and summary['installed']['library_sha256'] == hashlib.sha256(data).hexdigest()
             and summary['installed']['header_sha256'] == hashlib.sha256(header).hexdigest(),
             'actual installed header/archive: ' + stage)
        headers[stage], archives[stage], summaries[stage] = header, data, summary
    need(original_projection(summaries['baseline']) == original_projection(summaries['default']),
         'recomputed baseline/default equivalence')
    need(headers['default'] == headers['raw'], 'same capability-guarded installed header')
    before, after = (headers[key].decode('utf-8').splitlines() for key in ('baseline', 'default'))
    inserted = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes():
        need(tag in ('equal', 'insert'), 'baseline header line modified')
        if tag == 'insert':
            inserted.extend(after[j1:j2])
    need(0 < len(inserted) <= 70 and 'EXR_READER_SELECTOR_BYTES_CANDIDATE' in '\n'.join(inserted),
         'bounded guarded pure header insertions')
    for symbol in (b'reader_jh_commit_fixed_v3', b'reader_jh_commit_wire_raw_v3', b'reader_rs_decode_raw_v3'):
        need(symbol not in archives['default'] and symbol in archives['raw'], 'actual archive capability symbols')
    return {'program_roles': sorted(binaries), 'default_equals_baseline_recomputed': True,
            'default_archive_no_raw_symbols_recomputed': True, 'original_suites': 3}


def _read(archive, path):
    return archive.read(entry(archive, 's16/' + path))


def verify(archive, platform, certificate):
    result = json_load(_read(archive, 'result.json'))
    proof = complete_bindings(archive, result, platform)
    summary = json_load(_read(archive, 'evidence/raw/summary.json'))
    raw = _read(archive, 'evidence/raw/report.json')
    report = json_load(raw)
    probe = _read(archive, 'build/raw-consumer/s16-raw-probe' + ('.exe' if platform == 'Windows' else ''))
    problems = _original.check_problems(report, summary)
    problems += _original.binding_problems(certificate, summary, raw, probe)
    if summary.get('checks_total') != 162:
        problems.append('the raw-install consumer must retain all 162 checks')
    default = json_load(_read(archive, 'evidence/default/summary.json'))
    if (default.get('accepted') is not True or default.get('problems') or
            default.get('checks_total') != 21 or default.get('checks_failed') != 0 or
            default.get('mode') != 'default' or
            (default.get('installed') or {}).get('jump_history_version') != '0.1.0'):
        problems.append('the default-install consumer is not accepted')
    context = {key: os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')}
    if (not all(default.get('identity', {}).get(key) == value for key, value in context.items()) or
            default.get('platform') != platform):
        problems.append('the default-install consumer identity differs from this run')
    for stage, candidate in (('raw', summary), ('default', default)):
        library = 'reader_jump_history.lib' if platform == 'Windows' else 'libreader_jump_history.a'
        header = _read(archive, 'families/' + stage + '-stage/include/reader_jump_history.h')
        archive_bytes = _read(archive, 'families/' + stage + '-stage/lib/' + library)
        installed = candidate.get('installed') or {}
        if (installed.get('header_sha256') != hashlib.sha256(header).hexdigest() or
                installed.get('library_sha256') != hashlib.sha256(archive_bytes).hexdigest() or
                installed.get('library') != library):
            problems.append('the ' + stage + ' consumer does not bind the actual installed library/header')
        c_checks = candidate.get('c_checks') or []
        probe_checks = candidate.get('probe_checks') or []
        checks = c_checks + probe_checks
        names = [[check.get('name') for check in group] for group in (c_checks, probe_checks)]
        if (candidate.get('checks_total') != len(checks) or
                any(len(group) != len(set(group)) for group in names) or
                candidate.get('c_checks_total') != len(c_checks) or
                candidate.get('probe_checks_total') != len(probe_checks) or
                any(check.get('pass') is not True for check in checks)):
            problems.append('the ' + stage + ' consumer named checks differ from its totals')
    if summary.get('probe_checks') != report.get('checks'):
        problems.append('the raw consumer named checks differ from the actual probe report')
    if report.get('checks_total') != len(report.get('checks', [])) or report.get('failures') != 0:
        problems.append('the raw probe actual check count or failures differ')
    for key in ('cases_total', 'moves', 'cases', 'lifecycle', 'no_write', 'raw_semantics'):
        if summary.get(key) != report.get(key):
            problems.append('the raw summary projection differs from the actual report: ' + key)
    if problems:
        raise ValueError(problems)
    return proof


def mutations(archive, platform):
    """The original nine role bindings + three archive bytes + three suite identities."""
    result = json_load(_read(archive, 'result.json'))
    complete_bindings(archive, result, platform)
    outcomes = []

    def refused(name, candidate, overrides=None):
        try:
            complete_bindings(archive, candidate, platform, overrides)
        except ValueError as error:
            outcomes.append({'name': name, 'rejected': True, 'reason': str(error)})
            return
        raise ValueError('accepted original S16 semantic mutation: ' + name)

    for role in result['programs']:
        altered = copy.deepcopy(result)
        altered['programs'][role]['sha256'] = '0' * 64
        refused('program:' + role, altered)
    library = 'reader_jump_history.lib' if platform == 'Windows' else 'libreader_jump_history.a'
    for stage in ('baseline', 'default', 'raw'):
        path = 'families/' + stage + '-stage/lib/' + library
        refused('archive:' + stage, result, {path: b'!<arch>\ncorrupt'})
    for family in ('original-baseline', 'original-default', 'original-raw'):
        path = 'evidence/' + family + '/summary.json'
        altered = json_load(_read(archive, path))
        altered['identity']['GITHUB_SHA'] = '0' * 40
        refused('summary-source:' + family, result, {path: json.dumps(altered).encode()})
    if len(outcomes) != 15:
        raise ValueError(('original S16 mutation count', len(outcomes)))
    return outcomes

