"""Actions-only: original APK, real UI import, then independent public-API readback.

The APK bytes come from authenticate.py and are installed unchanged (no repackage,
re-sign, class edit, preference injection or forced loading). The application
itself imports through the system picker, turns to page 3 and saves; the
independent C consumer (c08_consumer) then loads the shipped libexreader.so and
reads the original, book list, reading progress and notes back through exr_*.
It is run (a) in the target's own UID through run-as, and (b) as the shell user
against a certified read-only copy, after the first close, after a fresh reopen
and after an offline reopen. Product files are hashed before/after every run.
"""
import argparse
import hashlib
import json
import pathlib
import re
import shlex
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ElementTree
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import common
import validate

PACKAGE = 'org.exreader.host'
ACTIVITY = PACKAGE + '/.MainActivity'
METRIC = re.compile(r'metric \{"event":"page","book":(\d+),"page":(\d+)')
IDENTITY = re.compile(r'^EXReader (\d+\.\d+\.\d+)/(\d+) · (\S+)$')
WORK = '/data/local/tmp/c08'
DATA = '/data/user/0/' + PACKAGE
LIBRARY_MEMBER = 'lib/x86_64/libexreader.so'


class Refusal(Exception):
    pass


def executable_file_ranges(data):
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01':
        raise Refusal('native load identity requires a complete little-endian ELF64')
    offset = struct.unpack_from('<Q', data, 32)[0]
    stride, count = struct.unpack_from('<HH', data, 54)
    if stride < 56 or offset + stride * count > len(data):
        raise Refusal('native ELF program header table is out of bounds')
    ranges = []
    for index in range(count):
        start = offset + index * stride
        kind, flags, file_offset = struct.unpack_from('<IIQ', data, start)
        size = struct.unpack_from('<Q', data, start + 32)[0]
        if kind == 1 and flags & 1 and size:
            ranges.append((file_offset, file_offset + size))
    if not ranges:
        raise Refusal('native library has no executable PT_LOAD segment')
    return ranges


def apk_member(apk, name):
    """(bytes, payload offset in the APK) of a stored member."""
    with zipfile.ZipFile(apk) as archive, open(apk, 'rb') as raw:
        item = archive.getinfo(name)
        if item.compress_type != zipfile.ZIP_STORED:
            raise Refusal(name + ' is not a stored (direct-mapped) APK member')
        raw.seek(item.header_offset)
        header = raw.read(30)
        name_bytes, extra_bytes = struct.unpack_from('<HH', header, 26)
        return archive.read(item), item.header_offset + 30 + name_bytes + extra_bytes


def mapped_executable(maps, installed_apk, member_ranges):
    """Executable mappings of the installed base.apk that cover every PT_LOAD of the member."""
    rows = []
    for line in maps.splitlines():
        parts = line.split(None, 5)
        if len(parts) == 6 and 'x' in parts[1] and parts[5].strip().startswith(installed_apk):
            low, high = (int(value, 16) for value in parts[0].split('-'))
            offset = int(parts[2], 16)
            rows.append((offset, offset + high - low, line))
    covered = bool(member_ranges) and all(
        any(begin <= want_begin and end >= want_end for begin, end, _ in rows)
        for want_begin, want_end in member_ranges)
    return covered, [line for _, _, line in rows]


class Driver:
    def __init__(self, apk, fixture, output, contract, inventory):
        self.apk = pathlib.Path(apk)
        self.fixture = pathlib.Path(fixture)
        self.output = pathlib.Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.contract = contract
        self.inventory = inventory
        self.checks = []
        self.observed = {'preferences_injected': False, 'apk_modified': False}
        self.expect = {'format': contract['fixture']['format'], 'title_stem': contract['fixture']['title_stem'],
                       'sha256': contract['fixture']['sha256'], 'bytes': contract['fixture']['bytes'],
                       'page': contract['expected_page'], 'notes': []}
        self.stages = []

    # ---- plumbing -------------------------------------------------------
    def adb(self, *args, timeout=300, check=True, binary=False):
        process = subprocess.run(['adb', *map(str, args)], timeout=timeout,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = process.stdout if binary else process.stdout.decode('utf-8', 'replace')
        if check and process.returncode != 0:
            raise Refusal('adb %s failed (%d): %s' % (' '.join(map(str, args)), process.returncode,
                                                      text[-2000:] if not binary else '<binary>'))
        return text

    def adb_code(self, *args, timeout=300):
        process = subprocess.run(['adb', *map(str, args)], timeout=timeout,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return process.returncode, process.stdout, process.stderr

    def shell(self, *args, **kwargs):
        return self.adb('shell', shlex.join(map(str, args)), **kwargs)

    def run_as(self, *args, **kwargs):
        return self.adb('exec-out', shlex.join(['run-as', PACKAGE, *map(str, args)]), binary=True, **kwargs)

    def check(self, name, passed, observed=None, detail=None, mandatory=True):
        self.checks.append({'name': name, 'pass': bool(passed), 'observed': observed,
                            'detail': detail, 'mandatory': mandatory})
        print(json.dumps({'check': name, 'pass': bool(passed), 'mandatory': mandatory,
                          'observed': observed}, default=str)[:3000], flush=True)
        if mandatory and not passed:
            raise Refusal('C08 refusal: ' + name + ' — ' + json.dumps(observed, default=str)[:1500])

    def wait(self, label, function, timeout, interval=1.0):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = function()
            if last:
                return last
            time.sleep(interval)
        raise Refusal('timed out waiting for ' + label + '; last=' + str(last))

    def save(self, name, data):
        path = self.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data) if isinstance(data, bytes) else path.write_text(data, encoding='utf-8')
        return path

    # ---- UI -------------------------------------------------------------
    def dump(self, tag='ui'):
        for _ in range(4):
            self.shell('uiautomator', 'dump', '/data/local/tmp/c08-ui.xml', check=False)
            data = self.adb('exec-out', 'cat', '/data/local/tmp/c08-ui.xml', check=False, binary=True)
            if data.startswith(b'<?xml'):
                self.save('ui/%s.xml' % tag, data)
                return ElementTree.fromstring(data)
            time.sleep(1)
        raise Refusal('uiautomator could not produce a usable hierarchy dump')

    @staticmethod
    def nodes(tree):
        return [{'text': node.get('text', ''), 'id': node.get('resource-id', ''),
                 'class': node.get('class', ''), 'bounds': node.get('bounds', ''),
                 'description': node.get('content-desc', ''), 'clickable': node.get('clickable', '')}
                for node in tree.iter('node')]

    @staticmethod
    def center(bounds, fx=0.5, fy=0.5):
        found = re.match(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]', bounds or '')
        if not found:
            return None
        x1, y1, x2, y2 = map(int, found.groups())
        return int(x1 + (x2 - x1) * fx), int(y1 + (y2 - y1) * fy)

    def tap_node(self, predicate, label, tag, timeout=60):
        def find():
            rows = self.nodes(self.dump(tag))
            for row in rows:
                if predicate(row) and row['bounds']:
                    return row
            return None
        row = self.wait(label, find, timeout, 2.0)
        point = self.center(row['bounds'])
        self.shell('input', 'tap', point[0], point[1])
        return row

    def focus(self):
        return self.shell('dumpsys', 'window', check=False)

    def focused_package(self):
        for line in self.focus().splitlines():
            if 'mCurrentFocus' in line:
                return line.strip()
        return ''

    def metrics(self):
        text = self.adb('logcat', '-d', '-v', 'threadtime', '-t', '8000')
        return [{'book': int(row.group(1)), 'page': int(row.group(2))} for row in METRIC.finditer(text)]

    def start(self):
        return self.shell('am', 'start', '-W', '-n', ACTIVITY)

    def screenshot(self, name):
        self.save('screenshots/%s.png' % name, self.adb('exec-out', 'screencap', '-p', binary=True))

    # ---- product read-only snapshot --------------------------------------
    def snapshot(self):
        listing = self.run_as('sh', '-c', "find . -type f -exec stat -c '%n %s %Y' {} +").decode('utf-8', 'replace')
        files = {}
        for line in listing.splitlines():
            parts = line.rsplit(' ', 2)
            if len(parts) != 3 or not parts[0].startswith('./'):
                continue
            path = parts[0][2:]
            data = self.run_as('cat', path, check=False)
            files[path] = {'size': int(parts[1]), 'mtime': int(parts[2]),
                           'cat_bytes': len(data), 'sha256': common.sha256_bytes(data)}
        return files

    # ---- consumer ----------------------------------------------------------
    def provision_consumer(self):
        consumer = pathlib.Path('build/c08-consumer/c08_consumer')
        self.adb('shell', 'rm -rf %s; mkdir -p %s/lib %s/copy' % (WORK, WORK, WORK))
        self.adb('push', str(consumer), WORK + '/c08_consumer')
        self.shell('chmod', '755', WORK, WORK + '/lib', WORK + '/c08_consumer')
        data, _ = apk_member(self.apk, LIBRARY_MEMBER)
        library = self.output / 'libexreader.so'
        library.write_bytes(data)
        self.adb('push', str(library), WORK + '/lib/libexreader.so')
        self.shell('chmod', '755', WORK + '/lib/libexreader.so')
        self.observed['consumer'] = {
            'binary_sha256': common.sha256_file(consumer), 'bytes': consumer.stat().st_size,
            'extracted_library_sha256': common.sha256_bytes(data), 'extracted_library_bytes': len(data),
            'build': common.read_json('build/c08-consumer/consumer-build.json')}
        self.observed['consumer_library_stage_match'] = [
            {'path': row['path'], 'equals_apk_member': row['sha256'] == common.sha256_bytes(data)}
            for row in self.inventory['sdk_stage']['libs']]

    def identities(self):
        """UID, SELinux context and program origin for each execution mode."""
        shell = self.adb('shell', 'id; echo; cat /proc/self/attr/current; echo; getenforce').strip()
        run_as = self.adb('shell', 'run-as %s sh -c "id; echo; cat /proc/self/attr/current; echo; getenforce"'
                          % PACKAGE, check=False).strip()
        run_as_exec = self.adb('shell', 'run-as %s ls -ldZ %s %s/c08_consumer' % (PACKAGE, WORK, WORK),
                               check=False).strip()
        listing = self.adb('shell', 'ls -ldZ %s %s/c08_consumer %s/lib/libexreader.so' % (WORK, WORK, WORK),
                           check=False).strip()
        self.observed['identities'] = {'shell': shell, 'run_as': run_as, 'run_as_work_listing': run_as_exec,
                                       'work_listing': listing,
                                       'target_data_listing': self.adb(
                                           'shell', 'run-as %s ls -ldZ . files files/library.db' % PACKAGE,
                                           check=False).strip()}

    def consumer_attempt(self, label, command, raw_name):
        code, out, err = self.adb_code(*command, timeout=300)
        self.save('consumer/%s.stdout' % raw_name, out)
        self.save('consumer/%s.stderr' % raw_name, err)
        row = {'attempt': label, 'exit': code, 'stderr': err.decode('utf-8', 'replace')[-600:]}
        report = None
        for line in reversed(out.decode('utf-8', 'replace').splitlines()):
            if line.startswith('{'):
                try:
                    report = json.loads(line)
                except ValueError as error:
                    row['json_error'] = str(error)
                break
        row['report'] = report
        row['stdout_head'] = out.decode('utf-8', 'replace')[:400] if report is None else None
        return row

    def library_variants(self, installed_apk):
        return [('apk-direct-map', installed_apk + '!/' + LIBRARY_MEMBER),
                ('extracted-copy', WORK + '/lib/libexreader.so')]

    def run_consumers(self, stage, installed_apk):
        before = self.snapshot()
        result = {'stage': stage, 'modes': {}}
        # (a) same UID: the consumer is executed as the target application's own UID.
        attempts = []
        for variant, library in self.library_variants(installed_apk):
            attempts.append(dict(self.consumer_attempt(
                'run-as:' + variant,
                ['exec-out', 'run-as', PACKAGE, WORK + '/c08_consumer', 'same-uid-' + variant, library,
                 DATA + '/files/library.db'], '%s-run-as-%s' % (stage, variant)), variant=variant))
            report = attempts[-1]['report']
            if report and not validate.validate(report, self.expect):
                break
        result['modes']['same_uid_run_as'] = attempts
        # (b) certified read-only copy: shell UID, copy made with the target's own cat.
        copy_dir = '%s/copy/%s' % (WORK, stage)
        self.adb('shell', 'rm -rf %s; mkdir -p %s' % (copy_dir, copy_dir))
        copied = {}
        for suffix in ('', '-wal', '-shm', '-journal'):
            name = 'files/library.db' + suffix
            data = self.run_as('sh', '-c', 'if [ -f %s ]; then cat %s; fi' % (name, name))
            if data:
                local = self.output / 'copies' / stage / ('library.db' + suffix)
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(data)
                self.adb('push', str(local), copy_dir + '/library.db' + suffix)
                copied['library.db' + suffix] = {'bytes': len(data), 'sha256': common.sha256_bytes(data)}
        self.shell('chmod', '444', *[copy_dir + '/' + name for name in copied])
        self.shell('chmod', '555', copy_dir)
        result['copy'] = copied
        attempts = []
        for variant, library in self.library_variants(installed_apk):
            attempts.append(dict(self.consumer_attempt(
                'shell-copy:' + variant,
                ['exec-out', WORK + '/c08_consumer', 'readonly-copy-' + variant, library,
                 copy_dir + '/library.db'], '%s-copy-%s' % (stage, variant)), variant=variant))
            report = attempts[-1]['report']
            if report and not validate.validate(report, self.expect):
                break
        result['modes']['shell_readonly_copy'] = attempts
        after = self.snapshot()
        copy_after = {}
        for name in copied:
            data = self.adb('exec-out', 'cat', copy_dir + '/' + name, binary=True)
            copy_after[name] = {'bytes': len(data), 'sha256': common.sha256_bytes(data)}
        result['snapshot_unchanged'] = before == after
        result['snapshot_changed_paths'] = sorted(path for path in set(before) | set(after)
                                                  if before.get(path) != after.get(path))
        result['snapshot_files'] = len(after)
        result['copy_unchanged'] = copy_after == copied
        self.stages.append(result)
        return result

    def judge(self, stage, result, expect):
        outcome = {}
        for mode, attempts in result['modes'].items():
            decided = None
            for attempt in attempts:
                report = attempt['report']
                reasons = validate.validate(report, expect) if report else ['no JSON report (exit %s): %s' % (
                    attempt['exit'], attempt.get('stdout_head') or attempt['stderr'])]
                attempt['refusals'] = reasons
                if not reasons and decided is None:
                    decided = {'variant': attempt['variant'], 'values': validate.normalize(report),
                               'loaded_from': report.get('loaded_from'), 'sdk_version': report.get('sdk_version'),
                               'abi_version': report.get('abi_version')}
            outcome[mode] = decided
        result['outcome'] = outcome
        return outcome

    # ---- scenario ---------------------------------------------------------
    def run(self):
        contract = self.contract
        apk_sha = common.sha256_file(self.apk)
        props = {name: self.shell('getprop', name).strip() for name in (
            'ro.build.version.sdk', 'ro.product.cpu.abi', 'ro.build.fingerprint', 'ro.boot.qemu',
            'sys.boot_completed', 'ro.debuggable')}
        self.observed['emulator'] = props
        self.check('emulator_is_virtual_api34_x86_64',
                   props['ro.build.version.sdk'] == '34' and props['ro.product.cpu.abi'] == 'x86_64'
                   and props['ro.boot.qemu'] == '1' and props['sys.boot_completed'] == '1', props)
        listed = self.shell('pm', 'list', 'packages', PACKAGE).strip()
        self.check('clean_profile_before_install', listed == '', {'pm_list': listed})

        install = self.adb('install', '-r', '-t', str(self.apk))
        self.check('install_reported_success', 'Success' in install, {'install': install.strip()})
        installed_path = re.match(r'package:(.+)', self.shell('pm', 'path', PACKAGE).strip())
        if not installed_path:
            raise Refusal('pm path did not report an installed base APK')
        installed_apk = installed_path.group(1).strip()
        installed = self.adb('exec-out', 'cat', installed_apk, binary=True)
        self.observed['installed'] = {'path': installed_apk, 'bytes': len(installed),
                                      'sha256': common.sha256_bytes(installed)}
        self.check('installed_bytes_equal_original_apk',
                   common.sha256_bytes(installed) == apk_sha and len(installed) == self.apk.stat().st_size,
                   {'apk_sha256': apk_sha, 'installed': self.observed['installed']})

        self.provision_consumer()
        self.identities()

        self.shell('logcat', '-c')
        self.start()
        self.wait('the host process', lambda: self.shell('pidof', PACKAGE, check=False).strip(), 120)
        self.wait('the shelf', lambda: any(row['id'] == PACKAGE + ':id/import_button'
                                           for row in self.nodes(self.dump('launch'))), 120, 2.0)
        self.screenshot('01-launch')

        # ---- real UI import through the system picker ----------------------
        fixture_sha = common.sha256_file(self.fixture)
        self.check('fixture_bytes_match_contract',
                   fixture_sha == contract['fixture']['sha256']
                   and self.fixture.stat().st_size == contract['fixture']['bytes'],
                   {'sha256': fixture_sha, 'bytes': self.fixture.stat().st_size})
        device_name = contract['fixture']['device_name']
        self.adb('push', str(self.fixture), '/sdcard/Download/' + device_name)
        self.shell('am', 'broadcast', '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
                   '-d', 'file:///sdcard/Download/' + device_name, check=False)
        time.sleep(2)
        self.tap_node(lambda row: row['id'] == PACKAGE + ':id/import_button', 'the Import button', 'import-1')
        picker = self.wait('the system document picker',
                           lambda: 'documentsui' in self.focused_package().lower() and self.focused_package(),
                           60)
        self.observed['picker_focus'] = picker
        self.screenshot('02-picker')

        def picker_file():
            rows = self.nodes(self.dump('picker'))
            for row in rows:
                if row['text'] == device_name and row['bounds']:
                    return row
            for row in rows:  # navigate to Downloads when the picker opened elsewhere
                if row['description'] in ('Show roots', 'Show Roots') and row['bounds']:
                    point = self.center(row['bounds'])
                    self.shell('input', 'tap', point[0], point[1])
                    time.sleep(1)
                    for root in self.nodes(self.dump('picker-roots')):
                        if root['text'] == 'Downloads' and root['bounds']:
                            target = self.center(root['bounds'])
                            self.shell('input', 'tap', target[0], target[1])
                            time.sleep(2)
                            break
            return None
        row = self.wait('the staged file in the picker', picker_file, 90, 2.0)
        point = self.center(row['bounds'])
        self.shell('input', 'tap', point[0], point[1])
        time.sleep(2)
        if 'documentsui' in self.focused_package().lower():
            for label in ('Open', 'OPEN', 'Select', 'SELECT'):
                nodes = [item for item in self.nodes(self.dump('picker-confirm')) if item['text'] == label]
                if nodes:
                    point = self.center(nodes[0]['bounds'])
                    self.shell('input', 'tap', point[0], point[1])
                    break
        self.wait('the picker to hand control back to the host',
                  lambda: PACKAGE in self.focused_package(), 60)
        self.observed['import_path'] = 'host import button -> system picker -> picked ' + device_name
        shelf = self.wait('the imported title on the shelf',
                          lambda: next((item for item in self.nodes(self.dump('shelf'))
                                        if contract['fixture']['title_stem'] in item['text'] and item['bounds']), None),
                          300, 3.0)
        self.observed['shelf_row'] = shelf
        self.check('book_imported_through_real_ui', True, {'row': shelf})
        self.screenshot('03-shelf')

        # ---- open, turn to page 3, annotate when the UI allows -----------------
        self.shell('logcat', '-c')
        point = self.center(shelf['bounds'])
        self.shell('input', 'tap', point[0], point[1])
        opened = self.wait('the reader to render the book',
                           lambda: next(iter(self.metrics()), None), 180)
        book_id = opened['book']
        self.observed['ui_book_id'] = book_id
        pages = [opened['page']]
        reader = next((item for item in self.nodes(self.dump('reader')) if item['id'] == PACKAGE + ':id/reader_view'), None)
        self.check('reader_view_present', reader is not None, {'reader': reader})
        while pages[-1] < contract['expected_page'] and len(pages) < 8:
            target = self.center(reader['bounds'], 0.85, 0.5)
            self.shell('input', 'tap', target[0], target[1])
            advanced = self.wait('a page turn', lambda: next(
                (item for item in self.metrics() if item['book'] == book_id and item['page'] > pages[-1]), None), 90)
            pages.append(advanced['page'])
        self.observed['pages'] = pages
        self.check('turned_to_page_3', pages[-1] == contract['expected_page'], {'pages': pages})
        self.screenshot('04-page-3')
        self.annotate(reader)
        self.screenshot('05-after-annotation-attempt')
        self.observed['expected_notes'] = list(self.expect['notes'])

        maps_pid = self.shell('pidof', PACKAGE).strip()
        maps = self.run_as('cat', '/proc/%s/maps' % maps_pid).decode('utf-8', 'replace')
        self.save('proc-maps-host.txt', maps)

        # ---- close through the application, then read back --------------------
        self.close_app('first')
        stage1 = self.run_consumers('1-after-first-close', installed_apk)
        outcome1 = self.judge('1', stage1, self.expect)
        self.record_stage('1_first_close', stage1, outcome1)

        # ---- fresh reopen (online): restored by the application itself ----------
        self.shell('logcat', '-c')
        self.start()
        restored = self.wait('the fresh reopen to restore the book', lambda: next(
            (item for item in self.metrics() if item['book'] == book_id), None), 240)
        self.observed['fresh_reopen_page'] = restored
        self.check('fresh_reopen_restores_page_3', restored['page'] == contract['expected_page'], restored)
        self.screenshot('06-fresh-reopen')
        self.close_app('fresh')
        stage2 = self.run_consumers('2-after-fresh-reopen', installed_apk)
        outcome2 = self.judge('2', stage2, self.expect)
        self.record_stage('2_fresh_reopen', stage2, outcome2)

        # ---- offline reopen ---------------------------------------------------------
        self.shell('cmd', 'connectivity', 'airplane-mode', 'enable')
        self.shell('svc', 'wifi', 'disable')
        self.shell('svc', 'data', 'disable')
        time.sleep(3)
        offline = {'airplane_mode_on': self.shell('settings', 'get', 'global', 'airplane_mode_on').strip(),
                   'wifi_on': self.shell('settings', 'get', 'global', 'wifi_on').strip(),
                   'mobile_data': self.shell('settings', 'get', 'global', 'mobile_data').strip()}
        ping = subprocess.run(['adb', 'shell', 'ping', '-c', '1', '-W', '2', '8.8.8.8'],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        offline['ping_exit'] = ping.returncode
        self.observed['offline'] = offline
        self.check('device_offline', offline['airplane_mode_on'] == '1' and offline['wifi_on'] == '0'
                   and ping.returncode != 0, offline)
        self.shell('logcat', '-c')
        self.start()
        reopened = self.wait('the offline reopen to restore the book', lambda: next(
            (item for item in self.metrics() if item['book'] == book_id), None), 240)
        self.observed['offline_reopen_page'] = reopened
        self.check('offline_reopen_restores_page_3', reopened['page'] == contract['expected_page'], reopened)
        self.screenshot('07-offline-reopen')
        self.close_app('offline')
        stage3 = self.run_consumers('3-after-offline-reopen', installed_apk)
        outcome3 = self.judge('3', stage3, self.expect)
        self.record_stage('3_offline_reopen', stage3, outcome3)

        self.finish(installed_apk, book_id)

    def annotate(self, reader):
        """Create one real annotation through the UI; any failure is recorded, never faked."""
        record = {'attempted': True, 'created': False}
        self.observed['annotation'] = record
        try:
            select = next(item for item in self.nodes(self.dump('annotate-0'))
                          if item['id'] == PACKAGE + ':id/select_button')
            point = self.center(select['bounds'])
            self.shell('input', 'tap', point[0], point[1])
            time.sleep(1)
            a = self.center(reader['bounds'], 0.25, 0.3)
            b = self.center(reader['bounds'], 0.7, 0.3)
            self.shell('input', 'swipe', a[0], a[1], b[0], b[1], 700)
            time.sleep(1)
            annotate = next((item for item in self.nodes(self.dump('annotate-1'))
                             if item['id'] == PACKAGE + ':id/annotate_button' and item['bounds']), None)
            if annotate is None:
                record['reason'] = 'no annotate button after the selection drag'
                return
            point = self.center(annotate['bounds'])
            self.shell('input', 'tap', point[0], point[1])
            time.sleep(1)
            field = next((item for item in self.nodes(self.dump('annotate-2'))
                          if item['id'] == PACKAGE + ':id/note_comment'), None)
            if field is None:
                record['reason'] = 'no annotation comment field'
                return
            point = self.center(field['bounds'])
            self.shell('input', 'tap', point[0], point[1])
            self.shell('input', 'text', 'c08note')
            time.sleep(1)
            save = next((item for item in self.nodes(self.dump('annotate-3')) if item['text'].lower() == 'save'), None)
            if save is None:
                record['reason'] = 'no Save button in the annotation dialog'
                return
            point = self.center(save['bounds'])
            self.shell('input', 'tap', point[0], point[1])
            time.sleep(3)
            label = next((item['text'] for item in self.nodes(self.dump('annotate-4'))
                          if item['id'] == PACKAGE + ':id/notes_button'), '')
            record['notes_button'] = label
            if 'Notes (1)' in label:
                record['created'] = True
                self.expect['notes'] = ['c08note']
            else:
                record['reason'] = 'the notes counter did not reach 1'
        except (Refusal, StopIteration) as error:
            record['reason'] = 'annotation UI step failed: %s' % error
        finally:
            self.check('annotation_created_through_ui', record['created'], record, mandatory=False)

    def close_app(self, label):
        """Let the application settle through its own lifecycle, then close it."""
        self.shell('input', 'keyevent', 'KEYCODE_HOME')
        time.sleep(3)
        self.shell('am', 'force-stop', PACKAGE)
        stopped = self.shell('pidof', PACKAGE, check=False).strip()
        self.check('application_closed_' + label, stopped == '', {'pidof': stopped})

    def record_stage(self, name, result, outcome):
        copy_ok = result['copy_unchanged']
        no_write = result['snapshot_unchanged']
        self.check('product_snapshot_unchanged_by_consumer_' + name, no_write,
                   {'changed': result['snapshot_changed_paths'], 'files': result['snapshot_files']})
        self.check('readonly_copy_unchanged_' + name, copy_ok, {'copy': result['copy']})
        summary = {mode: bool(decided) for mode, decided in outcome.items()}
        self.observed.setdefault('readback_by_stage', {})[name] = summary
        # The values must be real API output from at least one independent route.
        self.check('public_api_readback_' + name, any(summary.values()),
                   {'summary': summary,
                    'refusals': {mode: [attempt.get('refusals') for attempt in attempts]
                                 for mode, attempts in result['modes'].items()}})

    def finish(self, installed_apk, book_id):
        # The same values every time, and in each route that passed.
        routes = {}
        for stage in self.stages:
            for mode, decided in stage['outcome'].items():
                if decided:
                    routes.setdefault(mode, []).append(decided['values'])
        stable = {mode: all(values == rows[0] for values in rows) for mode, rows in routes.items()}
        self.observed['route_values'] = routes
        self.check('values_stable_across_close_fresh_reopen_and_offline_reopen',
                   bool(stable) and all(stable.values()) and all(len(rows) == 3 for rows in routes.values()),
                   {'stable': stable, 'stages': {mode: len(rows) for mode, rows in routes.items()}})
        for mode in ('same_uid_run_as', 'shell_readonly_copy'):
            self.check('route_' + mode + '_read_all_three_stages', mode in routes and len(routes[mode]) == 3,
                       {'mode': mode, 'stages': len(routes.get(mode, []))}, mandatory=False)

        # Library provenance: the object the consumer actually loaded is the installed APK member.
        member, payload = apk_member(self.apk, LIBRARY_MEMBER)
        ranges = [(payload + begin, payload + end) for begin, end in executable_file_ranges(member)]
        provenance = {'apk_member_sha256': common.sha256_bytes(member), 'apk_payload_offset': payload,
                      'executable_ranges': ranges}
        self.observed['library_provenance'] = provenance
        device_apk = self.save('installed-base.apk', self.adb('exec-out', 'cat', installed_apk, binary=True))
        installed_member = common.sha256_bytes(apk_member(device_apk, LIBRARY_MEMBER)[0])
        self.check('consumer_library_is_installed_apk_member',
                   installed_member == common.sha256_bytes(member), dict(provenance, installed_member=installed_member))
        allowed = {installed_apk + '!/' + LIBRARY_MEMBER: 'installed base.apk member, direct-mapped',
                   WORK + '/lib/libexreader.so': 'copy of the installed base.apk member'}
        loaded = {}
        for stage in self.stages:
            for mode, decided in stage['outcome'].items():
                if decided:
                    loaded.setdefault(decided['loaded_from'], []).append((stage['stage'], mode, decided['variant']))
        self.observed['loaded_library_paths'] = {path: allowed.get(path) for path in loaded}
        self.check('consumer_loaded_only_the_installed_sdk_library',
                   bool(loaded) and all(path in allowed for path in loaded),
                   {'loaded': loaded, 'allowed': allowed})

        # Diagnostic cross-check only: SQL is never API evidence.
        self.diagnostic_sql(book_id)

        log = self.adb('logcat', '-d', '-v', 'threadtime', '-t', '8000', binary=True)
        self.save('logcat-last.txt', log)
        text = log.decode('utf-8', 'replace')
        fatal = [line for line in text.splitlines()
                 if ('FATAL EXCEPTION' in line and PACKAGE in line) or ('ANR in ' + PACKAGE) in line]
        self.check('no_fatal_process_state', not fatal, {'fatal': fatal[:6]})
        self.check('no_preference_injection_or_apk_modification',
                   not self.observed['preferences_injected'] and not self.observed['apk_modified'],
                   {'preferences_injected': False, 'apk_modified': False})

    def diagnostic_sql(self, book_id):
        import sqlite3
        data = self.run_as('cat', 'files/library.db', check=False)
        rows = None
        if data.startswith(b'SQLite format 3'):
            path = self.save('diagnostic/library.db', data)
            try:
                connection = sqlite3.connect('file:%s?mode=ro' % path.as_posix(), uri=True)
                rows = [list(map(str, row)) for row in connection.execute('SELECT * FROM book_progress LIMIT 5')]
                connection.close()
            except sqlite3.DatabaseError as error:
                rows = 'unreadable: %s' % error
        self.observed['diagnostic_sql_book_progress'] = {'rows': rows, 'role': 'diagnostic_only_not_api_evidence'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=pathlib.Path, default=pathlib.Path('tests/reader_next_c08/contract.json'))
    parser.add_argument('--inventory', type=pathlib.Path, default=pathlib.Path('build/c08-authenticate/inventory.json'))
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/c08-emulator'))
    args = parser.parse_args()
    common.require_actions()
    contract = common.read_json(args.contract)
    inventory = common.read_json(args.inventory)
    driver = Driver(inventory['apk']['path'], contract['fixture']['file'], args.output, contract, inventory)
    accepted, failure, trace = False, None, None
    try:
        driver.run()
        accepted = True
    except Refusal as error:
        failure = str(error)
    except Exception as error:
        import traceback
        failure = '%s: %s' % (type(error).__name__, error)
        trace = traceback.format_exc()[-4000:]
    finally:
        result = {'identity': common.identity(), 'apk': inventory['apk'], 'checks': driver.checks,
                  'checks_total': len(driver.checks),
                  'checks_passed': sum(1 for check in driver.checks if check['pass']),
                  'mandatory_failed': [check['name'] for check in driver.checks
                                       if check['mandatory'] and not check['pass']],
                  'stages': driver.stages, 'observed': driver.observed,
                  'accepted': accepted, 'failure': failure, 'failure_trace': trace,
                  'scope': 'API34 default x86_64 emulator, debug original APK, independent C ABI consumer'}
        common.write_json(args.output / 'emulator-report.json', result)
        print(json.dumps({'accepted': accepted, 'checks': len(driver.checks), 'failure': failure}), flush=True)
    if not accepted:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
