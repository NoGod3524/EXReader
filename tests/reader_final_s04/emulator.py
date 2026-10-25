"""Actions-only install, launch and offline reopen of the authenticated APK.

The APK bytes come from authenticate.py (sealed artifact digest); this driver
never rebuilds or repackages it. It proves a clean pre-install profile, the
installed package identity, the actually loaded native SDK, a real import of the
original fixture, a persisted reading record, and a cold reopen with the network
disabled.
"""
import argparse
import json
import os
import pathlib
import re
import shlex
import shutil
import sqlite3
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ElementTree
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import common
import expectations

PACKAGE = 'org.exreader.host'
ACTIVITY = PACKAGE + '/.MainActivity'
METRIC = re.compile(r'metric \{"event":"page","book":(\d+),"page":(\d+)')
IDENTITY = re.compile(r'^EXReader (\d+\.\d+\.\d+)/(\d+) · (\S+)$')


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
            if file_offset + size > len(data):
                raise Refusal('native executable segment is out of bounds')
            ranges.append((file_offset, file_offset + size))
    if not ranges:
        raise Refusal('native library has no executable PT_LOAD segment')
    return ranges


def apk_executable_ranges(apk, libraries):
    result = {}
    with zipfile.ZipFile(apk) as archive, open(apk, 'rb') as raw:
        for library in libraries:
            item = archive.getinfo('lib/x86_64/' + library)
            if item.compress_type != zipfile.ZIP_STORED or item.compress_size != item.file_size:
                raise Refusal('direct-mapped native library is not a stored APK member')
            raw.seek(item.header_offset)
            header = raw.read(30)
            if len(header) != 30 or header[:4] != b'PK\x03\x04':
                raise Refusal('invalid native APK local member header')
            name_bytes, extra_bytes = struct.unpack_from('<HH', header, 26)
            payload = item.header_offset + 30 + name_bytes + extra_bytes
            result[library] = [(payload + begin, payload + end)
                               for begin, end in executable_file_ranges(archive.read(item))]
    return result


def loaded_native_mappings(text, installed_apk, libraries):
    rows = []
    for line in text.splitlines():
        parts = line.split(None, 5)
        if len(parts) != 6 or 'x' not in parts[1]:
            continue
        address = parts[0].split('-')
        if len(address) != 2:
            continue
        try:
            span = int(address[1], 16) - int(address[0], 16)
            offset = int(parts[2], 16)
        except ValueError:
            continue
        if span > 0:
            rows.append((parts[5], offset, offset + span, line))
    loaded = {}
    package_dir = installed_apk.rsplit('/', 1)[0] + '/'
    for library, expected in libraries.items():
        named = [line for path, _, _, line in rows
                 if path.startswith(package_dir) and path.endswith('/' + library)]
        apk_rows = [(begin, end, line) for path, begin, end, line in rows if path == installed_apk]
        covered = bool(expected) and all(any(begin <= wanted_begin and end >= wanted_end
                                            for begin, end, _ in apk_rows)
                                        for wanted_begin, wanted_end in expected)
        loaded[library] = named or ([line for begin, end, line in apk_rows
                                    if any(begin <= a and end >= b for a, b in expected)]
                                   if covered else [])
    return loaded


class Driver:
    def __init__(self, apk, fixture, output, derived, fixture_contract):
        self.apk = pathlib.Path(apk)
        self.fixture = pathlib.Path(fixture)
        self.output = pathlib.Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.derived = derived
        self.fixture_contract = fixture_contract
        self.checks = []
        self.observed = {'preferences_injected': False}

    # ---- plumbing ---------------------------------------------------------
    def adb(self, *args, timeout=300, check=True, binary=False):
        process = subprocess.run(['adb', *map(str, args)], timeout=timeout,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = process.stdout if binary else process.stdout.decode('utf-8', 'replace')
        if check and process.returncode != 0:
            raise Refusal('adb %s failed (%d): %s' % (' '.join(map(str, args)), process.returncode,
                                                      text[-2000:] if not binary else '<binary>'))
        return text

    def shell(self, *args, **kwargs):
        return self.adb('shell', shlex.join(map(str, args)), **kwargs)

    def run_as(self, *args, **kwargs):
        return self.adb('exec-out', shlex.join(['run-as', PACKAGE, *map(str, args)]),
                        binary=True, **kwargs)

    def check(self, name, passed, observed=None, detail=None, mandatory=True):
        self.checks.append({'name': name, 'pass': bool(passed), 'observed': observed,
                            'detail': detail, 'mandatory': mandatory})
        print(json.dumps({'check': name, 'pass': bool(passed), 'observed': observed}), flush=True)
        if mandatory and not passed:
            raise Refusal('S04 emulator refusal: ' + name + ' — ' + json.dumps(observed, default=str))

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
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding='utf-8')
        return path

    # ---- UI ---------------------------------------------------------------
    def dump(self):
        for _ in range(3):
            self.shell('uiautomator', 'dump', '/data/local/tmp/s04-ui.xml', check=False)
            data = self.adb('exec-out', 'cat', '/data/local/tmp/s04-ui.xml', check=False, binary=True)
            if data.startswith(b'<?xml'):
                self.save('ui-last.xml', data)
                return ElementTree.fromstring(data)
            time.sleep(1)
        raise Refusal('uiautomator could not produce a usable hierarchy dump')

    @staticmethod
    def nodes(tree):
        rows = []
        for node in tree.iter('node'):
            rows.append({'text': node.get('text', ''), 'id': node.get('resource-id', ''),
                         'class': node.get('class', ''), 'bounds': node.get('bounds', ''),
                         'description': node.get('content-desc', '')})
        return rows

    @staticmethod
    def find(rows, resource):
        for row in rows:
            if row['id'] == resource:
                return row
        return None

    @staticmethod
    def center(bounds, fx=0.5, fy=0.5):
        found = re.match(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]', bounds or '')
        if not found:
            return None
        x1, y1, x2, y2 = map(int, found.groups())
        return int(x1 + (x2 - x1) * fx), int(y1 + (y2 - y1) * fy)

    def logcat(self, clear=False):
        if clear:
            self.shell('logcat', '-c')
            return b''
        return self.adb('logcat', '-d', '-v', 'threadtime', '-t', '6000', binary=True)

    def metrics(self):
        text = self.adb('logcat', '-d', '-v', 'threadtime', '-t', '6000')
        return [{'book': int(row.group(1)), 'page': int(row.group(2))}
                for row in METRIC.finditer(text)]

    def start(self, *extra):
        return self.shell('am', 'start', '-W', '-n', ACTIVITY, *extra)

    def prefs(self):
        data = self.run_as('cat', 'shared_prefs/host.xml', check=False)
        return data

    # ---- scenario ---------------------------------------------------------
    def run(self):
        apk_sha = common.sha256_file(self.apk)
        apk_bytes = self.apk.stat().st_size

        props = {}
        for name in ('ro.build.version.sdk', 'ro.product.cpu.abi', 'ro.build.fingerprint',
                     'ro.product.name', 'ro.boot.qemu', 'ro.boot.qemu.avd_name',
                     'sys.boot_completed', 'ro.debuggable'):
            props[name] = self.shell('getprop', name).strip()
        uptime = self.shell('cat', '/proc/uptime').strip().split()[0]
        self.observed['emulator'] = dict(props, uptime_seconds=float(uptime))
        self.check('emulator_is_virtual_api34_x86_64',
                   props['ro.build.version.sdk'] == '34' and props['ro.product.cpu.abi'] == 'x86_64'
                   and props['ro.boot.qemu'] == '1' and props['sys.boot_completed'] == '1'
                   and float(uptime) < 7200,
                   self.observed['emulator'])

        listed = self.shell('pm', 'list', 'packages', PACKAGE).strip()
        path_before = self.shell('pm', 'path', PACKAGE, check=False).strip()
        self.check('clean_profile_before_install', listed == '' and path_before == '',
                   {'pm_list': listed, 'pm_path': path_before})

        data_before = self.shell('run-as', PACKAGE, 'ls', 'files', check=False)
        self.check('no_app_data_before_install', data_before.strip() == '' or
                   'unknown package' in data_before.lower(), {'run_as_ls': data_before.strip()})

        install = self.adb('install', '-r', '-t', str(self.apk))
        self.check('install_reported_success', 'Success' in install, {'install': install.strip()})
        installed_path = self.shell('pm', 'path', PACKAGE).strip()
        matches = re.match(r'package:(.+)', installed_path)
        if not matches:
            raise Refusal('pm path did not report an installed base APK: ' + installed_path)
        installed_bytes = self.adb('exec-out', 'cat', matches.group(1).strip(), binary=True)
        self.observed['installed'] = {'path': matches.group(1).strip(),
                                      'bytes': len(installed_bytes),
                                      'sha256': common.sha256_bytes(installed_bytes)}
        self.check('installed_bytes_equal_authenticated_apk',
                   len(installed_bytes) == apk_bytes
                   and common.sha256_bytes(installed_bytes) == apk_sha,
                   {'apk': {'bytes': apk_bytes, 'sha256': apk_sha},
                    'installed': self.observed['installed']})

        package = self.shell('dumpsys', 'package', PACKAGE)
        self.save('dumpsys-package.txt', package)
        version = re.search(r'versionCode=(\d+) minSdk=(\d+) targetSdk=(\d+)', package)
        name = re.search(r'versionName=(\S+)', package)
        self.observed['installed_manifest'] = {
            'versionCode': version.group(1) if version else None,
            'minSdk': version.group(2) if version else None,
            'targetSdk': version.group(3) if version else None,
            'versionName': name.group(1) if name else None}
        self.check('installed_version_matches_source',
                   version is not None and name is not None
                   and version.group(1) == self.derived['versionCode']
                   and version.group(2) == self.derived['minSdk']
                   and version.group(3) == self.derived['targetSdk']
                   and name.group(1) == self.derived['versionName'],
                   {'derived': {key: self.derived[key] for key in
                                ('versionCode', 'minSdk', 'targetSdk', 'versionName')},
                    'observed': self.observed['installed_manifest']})

        self.logcat(clear=True)
        started = self.start()
        self.check('cold_launch_reported',
                   'Status: ok' in started or 'Activity:' in started or 'Warning: Activity' in started,
                   {'am_start': started.strip()})
        pid = self.wait('the host process',
                        lambda: self.shell('pidof', PACKAGE, check=False).strip(), 120)
        self.observed['pid'] = pid
        resumed = self.shell('dumpsys', 'activity', 'activities')
        self.save('dumpsys-activities-launch.txt', resumed)
        self.check('resumed_activity_is_host',
                   any(PACKAGE in line and 'ResumedActivity' in line
                       for line in resumed.splitlines()),
                   {'sample': [line.strip() for line in resumed.splitlines()
                               if 'ResumedActivity' in line][:3]})

        def sdk_label():
            try:
                rows = self.nodes(self.dump())
                node = self.find(rows, PACKAGE + ':id/sdk_label')
                if node and node['text']:
                    self.observed['sdk_label_source'] = 'hierarchy'
                    return node['text']
            except Refusal:
                pass
            top = self.shell('dumpsys', 'activity', 'top', check=False)
            found = re.search(r'EXReader \d+\.\d+\.\d+/\d+ · \S+', top)
            if found:
                self.observed['sdk_label_source'] = 'dumpsys activity top'
                return found.group(0)
            return None

        label = self.wait('the native SDK identity label', sdk_label, 180)
        identity = IDENTITY.match(label.strip())
        self.observed['sdk_label'] = label
        self.check('runtime_native_sdk_identity',
                   identity is not None and identity.group(1) == self.derived['sdk_version']
                   and identity.group(3) == 'x86_64',
                   {'label': label, 'derived_version': self.derived['sdk_version']})

        screenshot = self.adb('exec-out', 'screencap', '-p', binary=True)
        self.save('screenshots/01-launch.png', screenshot)

        fixture_sha = common.sha256_file(self.fixture)
        self.check('fixture_bytes_match_contract',
                   fixture_sha == self.fixture_contract['sha256']
                   and self.fixture.stat().st_size == self.fixture_contract['bytes'],
                   {'contract': self.fixture_contract,
                    'observed': {'sha256': fixture_sha, 'bytes': self.fixture.stat().st_size}})

        self.shell('am', 'force-stop', PACKAGE)
        self.shell('run-as', PACKAGE, 'mkdir', '-p', 'files/incoming/exr-import/ready')
        staged = '/data/local/tmp/s04-original.' + self.fixture_contract['extension']
        self.adb('push', str(self.fixture), staged)
        target = 'files/incoming/exr-import/ready/' + fixture_sha + '.' + self.fixture_contract['extension']
        self.shell('run-as', PACKAGE, 'cp', staged, target)
        self.shell('run-as', PACKAGE, 'sh', '-c',
                   'printf %s "s04 original" > ' + target + '.title')
        self.logcat(clear=True)
        self.start()

        def imported():
            data = self.prefs()
            if b'path_' not in data:
                return None
            books = self.run_as('sh', '-c', 'ls files/books 2>/dev/null').decode().split()
            return {'prefs': data, 'books': books}

        state = self.wait('the staged import to become a shelf book', imported, 300)
        prefs = state['prefs']
        self.save('shared_prefs-host.xml', prefs)
        ids = re.findall(rb'name="path_(\d+)"', prefs)
        self.check('import_created_one_book', len(ids) == 1, {'ids': [i.decode() for i in ids],
                                                             'books': state['books']})
        book_id = int(ids[0])
        self.observed['book_id'] = book_id
        copies = {}
        for name in state['books']:
            data = self.run_as('cat', 'files/books/' + name, check=False)
            if data:
                copies[name] = {'bytes': len(data), 'sha256': common.sha256_bytes(data)}
        self.observed['private_copies'] = copies
        try:
            self.wait('the import commit status line',
                      lambda: 'status Imported' in self.adb('logcat', '-d', '-t', '4000', check=False),
                      60)
        except Refusal:
            time.sleep(5)
        self.check('import_preserved_original_bytes',
                   any(row['sha256'] == fixture_sha and row['bytes'] == self.fixture_contract['bytes']
                       for row in copies.values()),
                   {'fixture_sha256': fixture_sha, 'copies': copies})

        self.shell('am', 'force-stop', PACKAGE)
        self.logcat(clear=True)
        self.start()

        def shelf_row():
            rows = self.nodes(self.dump())
            for row in rows:
                if 's04 original' in row['text'] and row['bounds']:
                    return row
            return None

        opened = None
        point = None
        try:
            row = self.wait('the imported book to appear on the shelf', shelf_row, 180)
            point = self.center(row['bounds'])
            self.observed['shelf_row'] = row
        except Refusal:
            try:
                listing = self.find(self.nodes(self.dump()), PACKAGE + ':id/book_list')
                if listing and listing['bounds']:
                    point = self.center(listing['bounds'], 0.5, 0.12)
            except Refusal:
                point = None
        if point:
            self.shell('input', 'tap', point[0], point[1])
            try:
                opened = self.wait('the reader to render the imported book',
                                   lambda: next((row for row in self.metrics() if row['book'] == book_id), None),
                                   180)
                self.observed['open_path'] = 'ui_tap'
            except Refusal:
                opened = None
        if opened is None:
            self.observed['open_path'] = 'not_opened'
        self.check('book_opened_through_host_ui', opened is not None,
                   {'open_path': self.observed.get('open_path')})
        self.observed['first_page'] = opened
        self.check('book_opened_with_native_page', opened['page'] >= 1, opened)

        # EXReader.Pager initializes the SDK JNI library when the first book opens;
        # an empty shelf has loaded only the host bridge. Check both after real use.
        reading_pid = self.shell('pidof', PACKAGE).strip()
        if not re.fullmatch(r'\d+', reading_pid):
            raise Refusal('expected one live host PID after opening the book')
        maps = self.run_as('cat', '/proc/%s/maps' % reading_pid).decode('utf-8', 'replace')
        self.save('proc-maps.txt', maps)
        ranges = apk_executable_ranges(self.apk, ('libexreader_host.so', 'libexreader_jni.so'))
        loaded = loaded_native_mappings(maps, self.observed['installed']['path'], ranges)
        self.check('native_libraries_loaded_from_package',
                   all(loaded.values()),
                   {'pid': reading_pid, 'mapping_rows': loaded, 'apk_executable_file_ranges': ranges})

        page = opened['page']
        pages = [page]
        try:
            reader = self.find(self.nodes(self.dump()), PACKAGE + ':id/reader_view')
        except Refusal:
            reader = None
        turned = 0
        if reader and reader['bounds']:
            point = self.center(reader['bounds'], 0.85, 0.5)
            for _ in range(2):
                if not point:
                    break
                self.shell('input', 'tap', point[0], point[1])
                try:
                    advanced = self.wait('a page turn',
                                         lambda: next((row for row in self.metrics()
                                                       if row['book'] == book_id and row['page'] > pages[-1]), None),
                                         90)
                    pages.append(advanced['page'])
                    turned += 1
                except Refusal:
                    break
        self.observed['pages'] = pages
        self.check('page_turns_rendered', turned >= 1, {'pages': pages, 'turns': turned}, mandatory=False)
        page = pages[-1]
        screenshot = self.adb('exec-out', 'screencap', '-p', binary=True)
        self.save('screenshots/02-reading.png', screenshot)
        try:
            rows = self.nodes(self.dump())
            self.save('ui-reading.xml', ElementTree.tostring(self.dump(), encoding='utf-8'))
            self.check('reader_panel_visible',
                       self.find(rows, PACKAGE + ':id/reader_panel') is not None,
                       {'page_label': (self.find(rows, PACKAGE + ':id/page_label') or {}).get('text')})
        except Refusal as error:
            self.check('reader_panel_visible', False, {'hierarchy': str(error)},
                       'the hierarchy dump was unavailable on this device', mandatory=False)

        progress, database_files = self.pull_progress()
        self.observed['database_files'] = database_files
        self.observed['progress'] = progress
        self.check('reading_record_persisted',
                   not self.observed['preferences_injected']
                   and any(value.get('rows', 0) > 0 for value in progress.values()
                       if isinstance(value, dict)),
                   {'progress': progress, 'database_files': database_files})

        # Selection must have been written by the app; never repair it for acceptance.
        persisted = self.prefs()
        self.save('shared_prefs-before-offline.xml', persisted)
        selection = {node.get('name'): (node.tag, node.get('value'))
                     for node in ElementTree.fromstring(persisted)}
        restore_input = ('app' if selection.get('lastReader') == ('boolean', 'true')
                         and selection.get('lastBook') == ('long', str(book_id))
                         and not self.observed['preferences_injected'] else 'missing_or_injected')
        self.observed['restore_input'] = restore_input
        self.check('app_persisted_reader_selection', restore_input == 'app',
                   {'restore_input': restore_input, 'book_id': book_id,
                    'lastReader': selection.get('lastReader'), 'lastBook': selection.get('lastBook'),
                    'preferences_injected': self.observed['preferences_injected']})

        self.shell('cmd', 'connectivity', 'airplane-mode', 'enable')
        self.shell('svc', 'wifi', 'disable')
        self.shell('svc', 'data', 'disable')
        time.sleep(3)
        offline_state = {'airplane_mode_on': self.shell('settings', 'get', 'global', 'airplane_mode_on').strip(),
                         'wifi_on': self.shell('settings', 'get', 'global', 'wifi_on').strip(),
                         'mobile_data': self.shell('settings', 'get', 'global', 'mobile_data').strip()}
        if offline_state['wifi_on'] != '0':
            self.shell('cmd', 'wifi', 'set-wifi-enabled', 'disabled', check=False)
            time.sleep(3)
            offline_state['wifi_on'] = self.shell('settings', 'get', 'global', 'wifi_on').strip()
        ping = subprocess.run(['adb', 'shell', 'ping', '-c', '1', '-W', '2', '8.8.8.8'],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        offline_state['ping_exit'] = ping.returncode
        self.observed['offline'] = offline_state
        self.check('device_offline',
                   offline_state['airplane_mode_on'] == '1' and offline_state['wifi_on'] == '0'
                   and ping.returncode != 0,
                   offline_state)

        self.shell('am', 'force-stop', PACKAGE)
        stopped = self.shell('pidof', PACKAGE, check=False).strip()
        self.check('process_stopped_before_offline_reopen', stopped == '', {'pidof': stopped})
        self.logcat(clear=True)
        self.start()
        reopened = self.wait('the offline cold reopen to render the reading record',
                             lambda: next((row for row in self.metrics() if row['book'] == book_id), None),
                             240)
        self.observed['offline_reopen_page'] = reopened
        reopen_log = self.adb('logcat', '-d', '-t', '6000')
        self.observed['offline_public_sdk_host_path'] = {
            'handle_open': any('handle open book=%d mode=reflow' % book_id in line
                               for line in reopen_log.splitlines()),
            'source_api': 'MainActivity.openBook -> BookStore.verifySource -> exr_library_source',
            'progress_api': 'MainActivity.openBook -> BookStore.progress -> exr_library_progress_get',
            'independent_public_api_readback': False,
        }
        self.check('offline_reopen_same_reading_record',
                   reopened['page'] == page, {'before': page, 'after': reopened['page']})
        try:
            rows = self.nodes(self.dump())
            self.check('offline_reader_panel_visible',
                       self.find(rows, PACKAGE + ':id/reader_panel') is not None,
                       {'page_label': (self.find(rows, PACKAGE + ':id/page_label') or {}).get('text')})
            self.save('ui-offline.xml', ElementTree.tostring(self.dump(), encoding='utf-8'))
        except Refusal as error:
            self.check('offline_reader_panel_visible', False, {'hierarchy': str(error)},
                       'the hierarchy dump was unavailable on this device', mandatory=False)
        screenshot = self.adb('exec-out', 'screencap', '-p', binary=True)
        self.save('screenshots/03-offline-reopen.png', screenshot)

        after = {}
        for name in state['books']:
            data = self.run_as('cat', 'files/books/' + name, check=False)
            if data:
                after[name] = {'bytes': len(data), 'sha256': common.sha256_bytes(data)}
        self.observed['offline_copies'] = after
        self.check('original_bytes_intact_after_offline_reopen',
                   any(row['sha256'] == fixture_sha for row in after.values()),
                   {'fixture_sha256': fixture_sha, 'copies': after})

        log = self.adb('logcat', '-d', '-v', 'threadtime', '-t', '6000', binary=True)
        self.save('logcat-offline.txt', log)
        text = log.decode('utf-8', 'replace')
        fatal = [line for line in text.splitlines()
                 if ('FATAL EXCEPTION' in line and PACKAGE in line)
                 or 'ANR in ' + PACKAGE in line
                 or ('Process: ' + PACKAGE) in line]
        self.observed['fatal_lines'] = fatal[:10]
        self.check('no_fatal_process_state', not fatal, {'fatal': fatal[:10]})

    def inject_prefs(self, book_id):
        # Diagnostic only; any use must invalidate application-persistence acceptance.
        self.observed['preferences_injected'] = True
        data = self.run_as('cat', 'shared_prefs/host.xml', check=False)
        if not data.startswith(b'<?xml'):
            raise Refusal('the host has no readable shared preferences to restore from')
        tree = ElementTree.fromstring(data)
        wanted = {'lastReader': ('boolean', 'true'), 'lastBook': ('long', str(book_id))}
        for name, (kind, value) in wanted.items():
            node = next((child for child in tree if child.get('name') == name), None)
            if node is None:
                node = ElementTree.SubElement(tree, kind, {'name': name})
            node.set('value', value)
        rendered = ElementTree.tostring(tree, encoding='utf-8')
        path = self.output / 'injected-prefs.xml'
        path.write_bytes(rendered)
        self.adb('push', str(path), '/data/local/tmp/s04-host.xml')
        self.shell('run-as', PACKAGE, 'sh', '-c',
                   'cat /data/local/tmp/s04-host.xml > shared_prefs/host.xml')
        return rendered

    def pull_progress(self):
        """Copy the private database with its WAL sidecars and read it back."""
        evidence = self.output / 'database'
        evidence.mkdir(parents=True, exist_ok=True)
        pulled = {}
        for suffix in ('', '-wal', '-shm'):
            source_path = shlex.quote('files/library.db' + suffix)
            data = self.run_as('sh', '-c', 'if [ -f ' + source_path + ' ]; then cat '
                               + source_path + '; fi')
            if data:
                (evidence / ('library.db' + suffix)).write_bytes(data)
                pulled['library.db' + suffix] = len(data)
        work = self.output / 'database-work'
        work.mkdir(parents=True, exist_ok=True)
        if not (evidence / 'library.db').is_file():
            return {}, pulled
        for name in pulled:
            shutil.copyfile(evidence / name, work / name)
        return self.progress_rows(work / 'library.db'), pulled

    def progress_rows(self, database):
        """Read the copied database, retrying without a stale shm or wal sidecar."""
        attempts = [database.parent]
        for drop in (('library.db-shm',), ('library.db-shm', 'library.db-wal')):
            work = self.output / ('database-work-' + str(len(drop)))
            work.mkdir(parents=True, exist_ok=True)
            for name in ('library.db', 'library.db-wal', 'library.db-shm'):
                source = database.parent / name
                if source.is_file() and name not in drop:
                    shutil.copyfile(source, work / name)
            attempts.append(work)
        failure = None
        for work in attempts:
            try:
                return self.read_progress(work / 'library.db')
            except sqlite3.DatabaseError as error:
                failure = str(error)
        return {'error': failure, 'tables': []}

    @staticmethod
    def read_progress(database):
        result = {}
        connection = sqlite3.connect(str(database))
        try:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            result['tables'] = tables
            for table in ('book_progress', 'epub_progress'):
                if table in tables:
                    count = connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                    sample = [list(map(str, row)) for row in
                              connection.execute('SELECT * FROM ' + table + ' LIMIT 3')]
                    result[table] = {'rows': count, 'sample': sample}
        finally:
            connection.close()
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=pathlib.Path,
                        default=pathlib.Path('docs/reader-final-s04/apk-contract.json'))
    parser.add_argument('--inventory', type=pathlib.Path,
                        default=pathlib.Path('build/s04-authenticate/inventory.json'))
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/s04-emulator'))
    args = parser.parse_args()
    common.require_actions()
    contract = common.read_json(args.contract)
    inventory = common.read_json(args.inventory)
    fixture = contract['fixture']
    derived = expectations.derive(contract['producer']['source_sha'])
    sealed = expectations.check_sealed(contract, derived)
    if not sealed['sealed']:
        raise SystemExit('S04 refuses to run the emulator job without sealed producer source blob ids')
    driver = Driver(inventory['candidate']['path'], fixture['file'], args.output, derived, fixture)
    accepted = False
    failure = None
    trace = None
    try:
        driver.run()
        accepted = True
    except Refusal as error:
        failure = str(error)
    except Exception as error:  # keep an evidence file even for a driver defect
        import traceback
        failure = '%s: %s' % (type(error).__name__, error)
        trace = traceback.format_exc()[-4000:]
    finally:
        result = {'identity': common.identity(),
                  'producer_source': contract['producer']['source_sha'],
                  'apk': {'path': inventory['candidate']['path'],
                          'bytes': inventory['candidate']['bytes'],
                          'sha256': inventory['candidate']['sha256']},
                  'fixture': fixture, 'checks': driver.checks,
                  'checks_total': len(driver.checks),
                  'checks_passed': sum(1 for check in driver.checks if check['pass']),
                  'observed': driver.observed, 'accepted': accepted, 'failure': failure,
                  'failure_trace': trace,
                  'debug_candidate_only': True, 'store_channel': False,
                  'physical_device': False, 'signing_authority': False,
                  'emulator_only': True}
        common.write_json(args.output / 'emulator-report.json', result)
        print(json.dumps({'accepted': accepted, 'checks': len(driver.checks),
                          'failure': failure}), flush=True)
    if not accepted:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
