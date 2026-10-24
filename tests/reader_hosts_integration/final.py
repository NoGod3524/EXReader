"""Same-attempt host authentication; palette failures remain actual failures."""
import ast
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require

WORKFLOW = '.github/workflows/reader-hosts-integration.yml'
PALETTE = {'light_foreground_and_background_change_page_pixels',
           'dark_theme_and_palette_change_page_pixels'}
GTK_JOB = 'GTK G03 G04 reading records and retained native suites'
PALETTE_STEP = 'Actual settings controls geometry pixels gestures portal and persistence'


def stream_sha256(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
    return digest.hexdigest()


def identity(report, source, run, attempt):
    require(report.get('source_sha') == source and str(report.get('run_id')) == str(run) and
            str(report.get('attempt')) == str(attempt), 'foreign report source/run/attempt')


def named(report, total, flag, count_key, pass_key='pass', allowed_failures=frozenset(), expected=None):
    rows = report.get('checks')
    require(isinstance(rows, list) and len(rows) == total and report.get(count_key) == total,
            'missing or miscounted checks')
    require(all(isinstance(row, dict) and isinstance(row.get('name'), str) and
                type(row.get(pass_key)) is bool for row in rows), 'malformed named checks')
    names = [row['name'] for row in rows]
    require(len(set(names)) == total and (expected is None or set(names) == set(expected)),
            'duplicate or substituted checks')
    failed = {row['name'] for row in rows if row[pass_key] is False}
    require(failed <= allowed_failures, 'new actual host failures: ' + repr(sorted(failed)))
    require(report.get(flag) is (not failed), 'acceptance flag contradicts actual checks')
    return sorted(failed)


def gtk_record_names():
    # Read only literal test names, never import a producer that can run a host.
    source = ROOT / 'tests/reader_gtk_reading_records/check_ui.py'
    nodes = ast.walk(ast.parse(source.read_text(encoding='utf-8')))
    names = [node.args[0].value for node in nodes if isinstance(node, ast.Call) and
             isinstance(node.func, ast.Name) and node.func.id == 'record' and node.args and
             isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)]
    names += ['unsafe_row_%d_cannot_jump_edit_delete_or_restore' % i for i in (1, 2, 3)]
    require(len(names) == len(set(names)) == 30, 'pinned GTK record test names changed')
    return names


def declaration(path, key):
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == key for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('missing fixed test contract: ' + key)


class Bundle:
    def __init__(self, meta):
        self.meta = meta
        self.stream = tempfile.TemporaryFile()
        try:
            require(not meta['expired'] and 0 < meta['size_in_bytes'] <= 512 * 1024 * 1024 and
                    datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
                    'empty, expired or oversized artifact')
            download_artifact_zip(meta['id'], self.stream)
            require(self.stream.tell() == meta['size_in_bytes'], 'downloaded ZIP size differs')
            self.stream.seek(0)
            digest = stream_sha256(self.stream)
            require(meta['digest'] == 'sha256:' + digest, 'downloaded ZIP digest differs')
            self.stream.seek(0)
            self.zip = zipfile.ZipFile(self.stream)
            infos = self.zip.infolist()
            require(len(infos) <= 30000 and len({i.filename for i in infos}) == len(infos) and
                    sum(i.file_size for i in infos) <= 1024 * 1024 * 1024, 'unbounded or duplicate ZIP')
            for info in infos:
                path = PurePosixPath(info.filename)
                require(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename and
                        ':' not in info.filename, 'unsafe artifact member')
        except BaseException:
            self.stream.close()
            raise

    def info(self, tail):
        matches = [i for i in self.zip.infolist() if i.filename == tail or i.filename.endswith('/' + tail)]
        require(len(matches) == 1 and not matches[0].is_dir(), 'missing or duplicate member: ' + tail)
        return matches[0]

    def report(self, tail):
        info = self.info(tail)
        require(info.file_size <= 8 * 1024 * 1024, 'report exceeds bounded JSON size')
        with self.zip.open(info) as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        require(len(raw) == info.file_size and len(raw) <= 8 * 1024 * 1024, 'JSON size differs')
        report = json.loads(raw)
        require(isinstance(report, dict), 'report is not an object')
        return report

    def close(self):
        self.zip.close();self.stream.close()


def self_test():
    require(stream_sha256(io.BytesIO(b'abc')) ==
            'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
            'stream hash differs from the published SHA-256 vector')
    report = dict(accepted=True, source_sha='s', run_id=1, attempt=2, count=2,
                  checks=[dict(name='one', **{'pass': True}), dict(name='two', **{'pass': True})])
    def validate(candidate):
        identity(candidate, 's', 1, 2)
        named(candidate, 2, 'accepted', 'count', expected=['one', 'two'])
    validate(report)
    controls = [dict(source_sha='x'), dict(run_id=3), dict(attempt=4), dict(accepted=False),
                dict(count=1), dict(checks=report['checks'][:1]),
                dict(checks=[report['checks'][0]] * 2),
                dict(checks=[dict(name='one', **{'pass': True}), dict(name='replacement', **{'pass': True})]),
                dict(checks=[dict(name='one', **{'pass': False}), report['checks'][1]]),
                dict(checks=[dict(name='one', **{'pass': 1}), report['checks'][1]])]
    for change in controls:
        bad = copy.deepcopy(report);bad.update(change)
        try:
            validate(bad)
        except ValueError:
            continue
        raise ValueError('host protocol accepted a negative control')
    known = copy.deepcopy(report);known['accepted'] = False;known['checks'][1]['pass'] = False
    require(named(known, 2, 'accepted', 'count', allowed_failures={'two'}) == ['two'],
            'actual retained failure disappeared')
    known['accepted'] = True
    try:
        named(known, 2, 'accepted', 'count', allowed_failures={'two'})
    except ValueError:
        pass
    else:
        raise ValueError('retained failure became a pass')
    print(json.dumps({'host_protocol_rejections': len(controls) + 1}))


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    if sys.argv[1:] == ['--self-test']:
        self_test();return 0
    validator_source, validation_run = os.environ['GITHUB_SHA'], int(os.environ['GITHUB_RUN_ID'])
    diagnostic = len(sys.argv) == 3 and sys.argv[1] == '--inspect-run'
    if diagnostic:
        require(sys.argv[2].isdigit(), 'invalid diagnostic run identity')
        target = fetch('actions/runs/%d' % int(sys.argv[2]))
        source, run, attempt = target['head_sha'], target['id'], target['run_attempt']
        subprocess.run(['git', 'merge-base', '--is-ancestor', source, validator_source], check=True)
        subprocess.run(['git', 'diff', '--exit-code', source, validator_source, '--',
                        'src', 'include', 'cmake', 'CMakeLists.txt', 'apps', 'examples', 'extras',
                        'tests/reader_gtk_reading_records', 'tests/reader_android_reading',
                        'tests/reader_android_navigation', 'tests/reader_android_search'], check=True)
    else:
        require(len(sys.argv) == 1, 'unknown verifier arguments')
        source, run, attempt = validator_source, validation_run, int(os.environ['GITHUB_RUN_ATTEMPT'])
    output = Path('build/hosts-summary');output.mkdir(parents=True, exist_ok=True)
    result = dict(accepted=False, source_sha=source, run_id=run, attempt=attempt, problems=[], artifacts=[],
                  scopes={}, retained_failures=[], complete_product=False, performance_accepted=False,
                  screen_reader_speech_accepted=False, physical_device_accepted=False,
                  apple_host_accepted=False, six_target_product_accepted=False, cycle_complete=False)
    result.update(diagnostic_only=diagnostic, validator_source=validator_source, validation_run_id=validation_run)
    bundles = []
    try:
        metadata = fetch('actions/runs/%d' % run)
        require(metadata['head_sha'] == source and metadata['run_attempt'] == attempt and metadata['path'] == WORKFLOW,
                'wrong workflow identity')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run, attempt), 'jobs')
        if not diagnostic:
            needs = json.loads(os.environ['RESULTS'])
            require(set(needs) == {'compose', 'aggregate', 'search', 'summary', 'gtk', 'android'}, 'missing upstream job group')
            require(all(needs[key]['result'] == 'success' for key in needs if key != 'gtk'), 'a mandatory producer failed')
        artifacts = pages('actions/runs/%d/artifacts' % run, 'artifacts')

        def open_bundle(stem, job_name, palette_job=False):
            matches = [j for j in jobs if j['name'] == job_name]
            require(len(matches) == 1 and matches[0]['head_sha'] == source, 'wrong producer: ' + job_name)
            job = matches[0]
            require(job['status'] == 'completed', 'producer not complete')
            exceptions = {PALETTE_STEP} if palette_job else set()
            for step in job['steps']:
                require(step['conclusion'] == 'success' or step['name'] in exceptions,
                        'failed/skipped required step: ' + step['name'])
            require(job['conclusion'] in ('success', 'failure') if palette_job else job['conclusion'] == 'success',
                    'producer failed: ' + job_name)
            name = '%s-%d-%d' % (stem, run, attempt)
            found = [a for a in artifacts if a['name'] == name]
            require(len(found) == 1 and found[0]['workflow_run']['head_sha'] == source and
                    found[0]['workflow_run']['id'] == run, 'wrong artifact identity: ' + name)
            bundle = Bundle(found[0]);bundles.append(bundle)
            result['artifacts'].append({key: found[0][key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            return bundle, job

        for stem, job_name, leaf in (
                ('reader-module-composition-report', 'strict same-source composition report', 'result.json'),
                ('reader-windows-search-summary', 'same-source native Windows search artifact authentication', 'verified.json')):
            bundle, _ = open_bundle(stem, job_name)
            report = bundle.report(leaf);identity(report, source, run, attempt)
            require(report.get('accepted') is True and report.get('problems') == [], 'strict summary did not accept')
            if stem == 'reader-module-composition-report':
                require(set(report['platforms']) == {'linux', 'windows', 'macos'}, 'missing composed platform')
                require(all(p['g1_initial']['accepted'] and p['g1_relocated']['accepted'] for p in report['platforms'].values()),
                        'original integrated judges incomplete')
                result['scopes']['three_desktop_composition'] = True
            else:
                require(report.get('original_ui158') == 158 and report.get('original_f1_checks') == 264 and
                        report.get('protocol_rejections') == 23, 'Windows retained scopes missing')
                result['scopes']['windows_search'] = True

        gtk, gtk_job = open_bundle('reader-gtk-reading-records', GTK_JOB, palette_job=True)
        records = gtk.report('records-ui/report.json');identity(records, source, run, attempt)
        named(records, 30, 'reading_records_scope_passed', 'checks_total', pass_key='passed', expected=gtk_record_names())
        require(records.get('checks_failed') == 0 and not records.get('error'), 'GTK record failure')
        program = records['program_sha256']
        package = gtk.info('account-package/EXReader-Linux.tar.gz')
        with gtk.zip.open(package) as stream, tarfile.open(fileobj=stream, mode='r|gz') as archive:
            binaries, members, unpacked = 0, 0, 0
            for member in archive:
                members += 1;unpacked += member.size
                require(members <= 10000 and unpacked <= 512 * 1024 * 1024 and
                        0 <= member.size <= 128 * 1024 * 1024, 'GTK package exceeds bounded tar size')
                if member.name.endswith('/bin/exreader-linux'):
                    require(member.isfile() and member.size <= 128 * 1024 * 1024, 'bad GTK binary member')
                    with archive.extractfile(member) as binary:
                        require(stream_sha256(binary) == program, 'GTK report binary differs')
                    binaries += 1
            require(binaries == 1, 'GTK packaged binary missing or duplicate')
        for tail, count, flag in (('gtk-search-ui/result.json', 30, 'search_scope_passed'),
                                  ('gtk-navigation-ui/result.json', 29, 'navigation_scope_passed')):
            report = gtk.report(tail);identity(report, source, run, attempt)
            named(report, count, flag, 'count')
            require(report['program_sha256'] == program, 'GTK suite used another binary')
        settings = gtk.report('preferences-ui/result.json');identity(settings, source, run, attempt)
        failures = named(settings, 35, 'accepted', 'count', allowed_failures=PALETTE)
        require(settings['program_sha256'] == program and settings['failed'] == len(failures) and
                settings['passed'] == 35 - len(failures) and settings['diagnostic_only'] is False,
                'GTK settings identity/counts differ')
        require(gtk_job['conclusion'] == ('failure' if failures else 'success'), 'GTK job hides actual failures')
        result['retained_failures'] = failures
        result['scopes'].update(gtk_reading_records=True, gtk_search=True, gtk_navigation=True,
                                gtk_preferences=not failures)

        android, _ = open_bundle('reader-android-reading', 'android')
        for feature, total, phases in (('reading', 16, 3), ('search', 15, 2), ('navigation', 18, 2)):
            report = android.report('android-%s/ui/result.json' % feature);identity(report, source, run, attempt)
            require(report['accepted'] is True and report['checks'] == total and len(report['phases']) == phases and
                    report['api'] == 34 and report['abi'] == 'x86_64' and report['physical_device'] is False,
                    'Android scope differs')
            expected = declaration(ROOT / ('tests/reader_android_%s/run_ui.py' % feature), 'expected')
            require({p['phase'] for p in report['phases']} == set(expected) and
                    len({p['pid'] for p in report['phases']}) == phases, 'Android phases did not use separate processes')
            for phase in report['phases']:
                identity(phase, source, run, attempt)
                named(phase, len(expected[phase['phase']]), 'passed', 'count', expected=expected[phase['phase']])
            if feature == 'reading':
                require(report['real_postcommit_kill'], 'real kill/retry evidence absent')
        result['scopes']['android_reading_search_navigation_emulator'] = True
        result['accepted'] = not failures and not diagnostic
    except Exception as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    finally:
        for bundle in bundles:
            bundle.close()
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return 0 if result['accepted'] or (diagnostic and not result['problems']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
