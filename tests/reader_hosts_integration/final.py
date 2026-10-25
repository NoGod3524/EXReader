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
import zlib
import struct

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

    def bytes(self, tail, limit):
        info = self.info(tail)
        require(info.file_size <= limit, 'member exceeds declared bound: ' + tail)
        with self.zip.open(info) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) == info.file_size and len(raw) <= limit, 'member size differs: ' + tail)
        return raw

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


def authenticate_cbz(bundle, report, source, run, attempt):
    """Bind real renderer observations, pinned source pixels and crash request."""
    stem = 'android-cbz-reading/'
    require(report['cbz_reading_ui_accepted'] is True and report['performance_accepted'] is False and
            report['complete_product'] is False and report['talkback_speech_accepted'] is False, 'CBZ scope differs')
    require([p['phase'] for p in report['phases']] == ['first', 'retry', 'reopen'], 'CBZ phases differ')
    native = bundle.report(stem + 'native/result.json');identity(native, source, run, attempt)
    require(native['accepted'] is True and native['same_actual_renderer_doc_for_paint_and_public_resolve'] is True and
            native['single_original_shared_sdk'] is True and native['no_new_product_sqlite_or_sdk'] is True and
            len(native['checks']) == 2, 'CBZ actual renderer or shared SDK proof missing')
    manifest = bundle.report(stem + 'fixtures/manifest.json');plan = manifest['cbz_expected']
    ids, colors = ['001.png', '002.png', '003.png'], [[40, 80, 215], [110, 80, 145], [180, 80, 75]]
    require(plan['page_ids'] == ids and plan['rgb'] == colors and plan['text_bytes'] == plan['text_regions'] == 0 and
            plan['plan_precedes_sdk_read'] is True, 'CBZ predeclared input plan differs')
    comic = [row for row in manifest['books'] if row['role'] == 'cbz']
    require(len(comic) == 1, 'CBZ input identity absent or duplicated');comic = comic[0]
    data = bundle.bytes(stem + 'fixtures/' + comic['file'], 16 * 1024 * 1024)
    require(len(data) == comic['bytes'] and hashlib.sha256(data).hexdigest() == comic['sha256'], 'CBZ input bytes differ')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        require(archive.namelist() == ids, 'CBZ original page names differ')
        for index, name in enumerate(ids):
            require(archive.getinfo(name).file_size <= 32768, 'oversized pinned CBZ image')
            png = archive.read(name);require(png.startswith(b'\x89PNG\r\n\x1a\n'), 'invalid fixture PNG')
            at, compressed, header = 8, b'', None
            while at < len(png):
                require(len(png) - at >= 12, 'truncated fixture PNG')
                size = struct.unpack('>I', png[at:at + 4])[0];kind = png[at + 4:at + 8]
                require(size <= len(png) - at - 12, 'oversized PNG chunk')
                chunk = png[at + 8:at + 8 + size]
                require(struct.unpack('>I', png[at + 8 + size:at + 12 + size])[0] ==
                        zlib.crc32(kind + chunk) & 0xffffffff, 'fixture PNG CRC differs')
                if kind == b'IHDR':header = struct.unpack('>IIBBBBB', chunk)
                if kind == b'IDAT':compressed += chunk
                at += size + 12
            require(at == len(png) and header == (60, 80, 8, 2, 0, 0, 0), 'fixture PNG geometry differs')
            expected = (b'\x00' + bytes(colors[index]) * 60) * 80
            decoder = zlib.decompressobj();pixels = decoder.decompress(compressed, len(expected) + 1)
            require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and pixels == expected,
                    'original CBZ image pixels differ from the plan')
    key = 'cbz:' + comic['sha256'];observations = []
    for phase in report['phases']:
        require(phase == bundle.report(stem + 'ui/' + phase['phase'] + '-report.json'), 'CBZ phase copy differs')
        pages = phase['actual_pages'];require(pages, 'CBZ rendered pages absent')
        for page in pages:
            index = page['index'];require(type(index) is int and 0 <= index < 3, 'CBZ page index differs')
            red, green, blue = colors[index];argb = 0xff000000 | red << 16 | green << 8 | blue
            require(page['page_id'] == ids[index] and page['argb'] == page['expected_argb'] == argb and
                    page['source_key'] == key and page['renderer'] != 0 and page['text_bytes'] == 0,
                    'CBZ actual renderer pixels/source/page differ')
        observations.extend(phase['observations'])
    first = report['phases'][0]['actual_pages'][:3]
    require([p['index'] for p in first] == [0, 1, 2] and len({p['renderer'] for p in first}) == 1, 'CBZ changed paint document')
    require(len(report['captures']) == len(observations) and len(report['sources']) == 21, 'CBZ captures/source reads missing')
    for capture in report['captures']:
        png = bundle.bytes(stem + 'ui/captures/' + capture['phase'] + '-' + capture['name'] + '.png', 16 * 1024 * 1024)
        require(png.startswith(b'\x89PNG\r\n\x1a\n') and len(png) == capture['bytes'] and
                hashlib.sha256(png).hexdigest() == capture['sha256'], 'CBZ screen capture differs')
    for item in report['sources']:
        data = bundle.bytes(stem + 'fixtures/' + item['file'], 16 * 1024 * 1024)
        require(len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'], 'CBZ source read differs')
    raw = bundle.bytes(stem + 'ui/killed-pending-request.json', 2 * 1024 * 1024)
    pending = json.loads(raw);kill = report['real_postcommit_kill']
    require(kill['actual_postcommit_gate'] is True and kill['pid_before_stop'] and not kill['pid_after_stop'] and
            kill['request_bytes'] == len(raw) and kill['request_sha256'] == hashlib.sha256(raw).hexdigest() and
            pending['revision'] == kill['revision_id'] and pending['annotation'] == kill['annotation_id'] and
            pending['book'] == key and pending['body'] == 'CBZ lost response exact request', 'CBZ original crash request differs')
    require(len(report['process_stops']) == 3 and all(s['requested'] and not s['pid_after_stop'] for s in report['process_stops']),
            'CBZ did not really stop its processes')


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
                        'tests/reader_android_navigation', 'tests/reader_android_search',
                        'tests/reader_windows_navigation', 'tests/reader_android_preferences',
                        'tests/reader_android_cbz_reading'], check=True)
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
                ('reader-windows-search-summary', 'same-source native Windows search artifact authentication', 'winsearch-summary/verified.json')):
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
                navigation = bundle.report('winnav-summary/verified.json');identity(navigation, source, run, attempt)
                require(navigation.get('accepted') is True and navigation.get('problems') == [] and
                        navigation.get('navigation_ui_checks') == 31 and navigation.get('original_f2_checks') == 130 and
                        navigation.get('protocol_rejections') == 33 and navigation.get('original_f1_strict_preserved') is True and
                        navigation['consumer_sha256'] == report['consumer_sha256'] and
                        navigation['review_sha256'] == report['review_sha256'], 'Windows directory or original search proof missing')
                result['scopes']['windows_navigation'] = True

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

        android, _ = open_bundle('reader-android-cbz-reading', 'android')
        for feature, total, phases in (('reading', 16, 3), ('search', 15, 2), ('navigation', 18, 2), ('preferences', 17, 3), ('cbz_reading', 10, 3)):
            report = android.report('android-%s/ui/result.json' % feature.replace('_', '-'));identity(report, source, run, attempt)
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
            if feature == 'cbz_reading':
                authenticate_cbz(android, report, source, run, attempt)
            if feature == 'preferences':
                require(report['page_colors_accepted'] is False and report['talkback_speech_accepted'] is False,
                        'Android settings falsely grant page colors or speech')
                stops = report['process_stops']
                require(len(stops) == phases and all(not p['pid_after_stop'] for p in stops), 'Android settings real stops missing')
                for phase in report['phases']:
                    require(phase['page_colors_accepted'] is False, 'Android phase falsely grants colors')
                    if phase['phase'] in ('first', 'night'):
                        gap = phase['retained_color_failure']
                        require(gap['accepted'] is False and gap['actual_corner_rgba'] != gap['requested_background_rgba'] and
                                gap['user_css_attempted'] and gap['public_api_gap'], 'Android color gap was hidden')
        result['scopes']['android_reading_search_navigation_emulator'] = True
        result['scopes']['android_preferences_controls_emulator'] = True
        result['scopes']['android_cbz_reading_emulator'] = True
        result['scopes']['android_page_colors'] = False
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
