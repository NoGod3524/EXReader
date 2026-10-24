#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only GTK product performance sampler.

Every measurement starts from a real X11 key event delivered by xdotool and ends
at the frozen host's own synchronous observation write, timestamped by an
inotify watcher. Screenshots, AT-SPI and observation-file polling never stand in
for the frame clock, and no sample is dropped, trimmed or re-run away.
"""
import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from observe import Host, SampleError, Watch, command

KINDS = ('shelf_search_open_turn', 'shelf_search_variants', 'resume_turn', 'import_probe')
TURNS = {'shelf_search_open_turn': (6, 2), 'shelf_search_variants': (2, 1), 'resume_turn': (4, 1)}
IMPORTS_PER_LAUNCH = 3
IMPORT_KEY_SLOTS = 8
IMPORT_FILES = 4
IMPORT_BYTES = 6 * 1024 * 1024
IMPORT_BLOCK_LINES = 2000
IMPORT_TURNS = 2
WINDOW_WIDTH, WINDOW_HEIGHT = 1040, 820
SCREEN = '1440x900x24'
COLD_LAUNCHES = (0, 8, 16, 24)
LONG_INDEX = 0
AUTHOR_QUERY = '%_!'
MISSING_QUERY = 'No such book'


def settled(state):
    host = state['host']
    return not host.get('busy', 0) and not host.get('saving', 0)


def shelf_ready(state):
    host = state['host']
    return (host.get('books') == 50 and not host.get('shelf_loading') and
            not host.get('shelf_restoring') and settled(state))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def folder_bytes(folder):
    return sum(path.stat().st_size for path in Path(folder).rglob('*') if path.is_file())


class Sampler:
    def __init__(self, arguments):
        self.arguments = arguments
        self.output = arguments.output.resolve()
        self.payload = arguments.payload.resolve()
        self.binary = self.payload / 'bin' / 'exreader-linux'
        self.font = self.payload / 'Reader.otf'
        self.profile = self.output / 'profile'
        self.profile_import = self.output / 'profile-import'
        self.plan = []
        self.results = []
        self.slots = {}
        self.launches = []
        self.handles = []
        self.kind = ''
        self.launch = -1
        self.launch_stamp = None
        self.environment = {}
        self.corpus = {}
        self.import_paths = []
        self.import_ring = 0
        self.last_book = 0
        self.long_id = 0

    # ---- bookkeeping -------------------------------------------------
    def expect(self, metric, group=''):
        slot = self.slots.get(metric, 0)
        self.slots[metric] = slot + 1
        handle = {'launch': self.launch, 'metric': metric, 'slot': slot, 'group': group, 'status': 'pending'}
        self.plan.append({'launch': self.launch, 'metric': metric, 'slot': slot, 'group': group})
        self.handles.append(handle)
        return handle

    def record(self, handle, outcome, start=None, end=None, event=None, note=''):
        row = {'launch': handle['launch'], 'kind': self.kind, 'metric': handle['metric'],
               'slot': handle['slot'], 'group': handle['group'], 'outcome': outcome, 'note': note}
        stamp = self.launch_stamp
        if start is not None and end is not None and stamp is not None:
            row['start_ms'] = round((start - stamp) * 1000.0, 3)
            row['end_ms'] = round((end - stamp) * 1000.0, 3)
            row['latency_ms'] = round((end - start) * 1000.0, 3)
        if event is not None:
            host = event['state']['host']
            row['sequence'] = host.get('sequence')
            row['painted_generation'] = host.get('painted_generation')
        handle['status'] = outcome
        self.results.append(row)
        if outcome == 'ok':
            print('SAMPLE launch=%02d %s slot=%d latency_ms=%s' % (
                row['launch'], row['metric'], row['slot'], row.get('latency_ms')), flush=True)
        else:
            print('SAMPLE-FAILURE launch=%02d %s slot=%d outcome=%s %s' % (
                row['launch'], row['metric'], row['slot'], outcome, note), flush=True)

    def await_state(self, host, watch, predicate, timeout, since=0, what='host state'):
        index, event = watch.wait(predicate, timeout, since)
        if index is None:
            raise SampleError('waiting for %s: %s (host %s)' % (
                what, event, 'alive' if host.alive() else 'exited %s' % host.process.poll()))
        return index, event

    def current_paint(self, watch):
        latest = watch.latest()
        return 0 if latest is None else latest['state']['host'].get('painted_generation', 0)

    def first_paint(self, watch, previous, start_index, end_index, timeout):
        for index in range(start_index, end_index + 1):
            if watch.event(index)['state']['host'].get('painted_generation', 0) > previous:
                return index, watch.event(index), None
        index, event = watch.wait(
            lambda state: state['host'].get('painted_generation', 0) > previous, timeout, end_index + 1)
        if index is None:
            return None, None, event
        return index, event, None

    # ---- environment and corpus --------------------------------------
    def cpu_model(self):
        try:
            for line in Path('/proc/cpuinfo').read_text().splitlines():
                if line.lower().startswith('model name'):
                    return line.split(':', 1)[1].strip()
        except OSError:
            pass
        return platform.processor()

    def memory_kb(self):
        try:
            for line in Path('/proc/meminfo').read_text().splitlines():
                if line.startswith('MemTotal:'):
                    return int(line.split()[1])
        except OSError:
            pass
        return None

    def tool_version(self, *args):
        try:
            return command(*args, timeout=30)
        except (subprocess.SubprocessError, OSError):
            return None

    def write_environment(self):
        (self.output / 'environment.json').write_text(json.dumps(self.environment, indent=2) + '\n')

    def collect_environment(self):
        keep = ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_WORKFLOW', 'GITHUB_JOB',
                'RUNNER_OS', 'RUNNER_ARCH', 'RUNNER_NAME', 'ImageOS', 'ImageVersion', 'DISPLAY')
        self.environment = {
            'schema': 1,
            'source_sha': os.environ['GITHUB_SHA'],
            'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
            'screen': SCREEN,
            'window': {'width': WINDOW_WIDTH, 'height': WINDOW_HEIGHT},
            'runner': {
                'os': platform.system(), 'kernel': platform.release(), 'arch': platform.machine(),
                'python': platform.python_version(), 'nproc': os.cpu_count(),
                'cpu_model': self.cpu_model(), 'memory_kb': self.memory_kb(),
                'gtk': self.tool_version('pkg-config', '--modversion', 'gtk+-3.0'),
                'openbox': (self.tool_version('openbox', '--version') or '').splitlines() or None,
                'xdotool': self.tool_version('xdotool', '--version'),
                'xclip': self.tool_version('xclip', '-version'),
                'xvfb': shutil.which('Xvfb'),
                'variables': {name: os.environ.get(name) for name in keep},
            },
            'payload': {
                'path': str(self.payload),
                'files': sum(1 for path in self.payload.rglob('*') if path.is_file()),
                'bytes': folder_bytes(self.payload),
                'binary_bytes': self.binary.stat().st_size if self.binary.exists() else None,
                'binary_sha256': sha256_file(self.binary) if self.binary.exists() else None,
                'font_bytes': self.font.stat().st_size if self.font.exists() else None,
                'font_sha256': sha256_file(self.font) if self.font.exists() else None,
                'build_json_sha256': (sha256_file(self.payload.parent / 'build.json')
                                      if (self.payload.parent / 'build.json').exists() else None),
            },
            'command': sys.argv,
            'cold_launches': list(COLD_LAUNCHES),
        }
        tarball = getattr(self.arguments, 'tarball', None)
        package = {'path': str(tarball) if tarball is not None else None, 'exists': False,
                   'tarball_bytes': None, 'tarball_sha256': None, 'cwd': str(Path.cwd())}
        if tarball is not None:
            path = Path(tarball)
            package['exists'] = path.exists()
            if package['exists']:
                package['tarball_bytes'] = path.stat().st_size
                package['tarball_sha256'] = sha256_file(path)
        self.environment['package'] = package
        # Host state lives beside the evidence directory: GTK, dbus and the window
        # manager write hidden files into HOME, and the evidence bundle must contain
        # exactly the files the artifact upload keeps.
        state = self.output.parent / 'perf-host-state'
        host_environment = {
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'DISPLAY': os.environ.get('DISPLAY', ':99'),
            'HOME': str(state / 'home'),
            'XDG_RUNTIME_DIR': str(state / 'runtime'),
            'XDG_CACHE_HOME': str(state / 'cache'),
            'XDG_CONFIG_HOME': str(state / 'config'),
            'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8',
            'GDK_BACKEND': 'x11',
        }
        for name, mode in (('HOME', 0o755), ('XDG_RUNTIME_DIR', 0o700), ('XDG_CACHE_HOME', 0o755),
                           ('XDG_CONFIG_HOME', 0o755)):
            Path(host_environment[name]).mkdir(parents=True, exist_ok=True)
            os.chmod(host_environment[name], mode)
        self.environment['host_environment'] = host_environment
        self.write_environment()

    def seed(self):
        database = self.profile / 'library.sqlite'
        self.profile.mkdir(parents=True, exist_ok=True)
        corpus_path = self.output / 'corpus.json'
        before = time.monotonic()
        process = subprocess.run([str(self.arguments.seed), str(database), str(corpus_path)],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3600)
        elapsed = (time.monotonic() - before) * 1000.0
        if process.returncode != 0:
            raise SampleError('seeding failed: %s' % process.stdout.decode()[-2000:])
        self.corpus = json.loads(corpus_path.read_text())
        self.long_id = self.corpus['originals'][LONG_INDEX]['id']
        self.environment['seed'] = {
            'elapsed_ms': round(elapsed, 3),
            'stdout': process.stdout.decode().strip().splitlines()[-1:],
            'corpus_sha256': sha256_file(corpus_path),
            'seed_sha256': sha256_file(self.arguments.seed),
            'library_bytes': database.stat().st_size,
            'library_sha256': sha256_file(database),
        }
        self.write_environment()
        if self.corpus.get('books') != 2202 or not self.long_id:
            raise SampleError('seed corpus is not the fixed 2202 originals: %r' % self.corpus.get('books'))
        print('SEED books=%d first_id=%d long_id=%d long_bytes=%d elapsed_ms=%.1f' % (
            self.corpus['books'], self.corpus['first_id'], self.long_id,
            self.corpus['long_book_bytes'], elapsed), flush=True)

    def make_import_corpus(self):
        folder = self.output / 'import-corpus'
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(IMPORT_FILES):
            path = folder / ('import-%02d.txt' % index)
            lines = ['Shelf import file %02d unique header for the input responsiveness probe.\n' % index]
            for line in range(IMPORT_BLOCK_LINES):
                lines.append('Import file %02d paragraph %05d keeps deterministic bytes so every run '
                             'measures the same import workload.\n' % (index, line))
            block = ''.join(lines).encode()
            written = 0
            with path.open('wb') as handle:
                while written < IMPORT_BYTES:
                    chunk = block[:min(len(block), IMPORT_BYTES - written)]
                    handle.write(chunk)
                    written += len(chunk)
            self.import_paths.append(path)
        (self.output / 'import-corpus.json').write_text(json.dumps(
            [{'path': path.name, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
             for path in self.import_paths], indent=2) + '\n')

    def calibrate(self):
        samples = []
        for _ in range(20):
            stamp = time.monotonic()
            command('xdotool', 'getmouselocation', timeout=30)
            samples.append((time.monotonic() - stamp) * 1000.0)
        samples.sort()
        report = {'tool': 'xdotool getmouselocation', 'count': len(samples),
                  'min_ms': round(samples[0], 3), 'median_ms': round(samples[len(samples) // 2], 3),
                  'max_ms': round(samples[-1], 3),
                  'note': 'Injection commands are timed from just before xdotool starts; this per-command '
                          'overhead is included in every end-to-end sample.'}
        (self.output / 'calibration.json').write_text(json.dumps(report, indent=2) + '\n')

    # ---- launch helpers ---------------------------------------------
    def apply_cache(self, index):
        record = {'requested': 'cold' if index in COLD_LAUNCHES else 'warm', 'drop': None}
        if index in COLD_LAUNCHES:
            done = subprocess.run(['sudo', '-n', 'sh', '-c', 'sync; echo 3 > /proc/sys/vm/drop_caches'],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
            record['drop'] = {'returncode': done.returncode, 'output': done.stdout.decode()[-400:]}
            record['effective'] = 'cold' if done.returncode == 0 else 'warm'
        else:
            record['effective'] = 'warm'
        return record

    def write_settings(self, profile, book):
        (profile / 'reader.ini').write_text(
            '[reader]\nbook=%d\nfont=24\nzoom=100\n[shelf]\nquery=\ntop_key=\nselected_key=\n'
            'top_offset=0\n' % book)

    def prepare_import_profile(self):
        if self.profile_import.exists():
            shutil.rmtree(self.profile_import)
        shutil.copytree(self.profile, self.profile_import)

    # ---- measurement primitives -------------------------------------
    def search(self, host, watch, text, predicate, metric):
        handle = self.expect(metric)
        latest = watch.latest()
        queries = latest['state']['host'].get('shelf_queries', 0) if latest else 0
        try:
            host.press('ctrl+f')
            host.press('ctrl+a')
            since = watch.mark()
            stamp = host.paste(text) if text else host.press('BackSpace')
            index, event = self.await_state(
                host, watch,
                lambda state: (state['host'].get('shelf_queries', 0) > queries
                               and not state['host'].get('shelf_restoring')
                               and settled(state) and predicate(state)),
                180, since, 'query %r' % text)
        except SampleError as error:
            self.record(handle, 'failed', note=str(error))
            return None
        self.record(handle, 'ok', start=stamp, end=event['at'], event=event, note='query=%r' % text)
        return event

    def open_selected(self, host, watch, expected_id):
        applied = self.expect('open_book_applied')
        painted = self.expect('open_book_painted')
        previous = self.current_paint(watch)
        try:
            since = watch.mark()
            host.press('F2')
            self.await_state(host, watch, lambda state: bool(state['shelf'].get('selected_key')),
                             60, since, 'shelf row selection')
            since = watch.mark()
            stamp = host.press('Return')
            index, event = self.await_state(
                host, watch,
                lambda state: (state['host'].get('book') == expected_id
                               and state['host'].get('reader_visible') == 1 and settled(state)),
                300, since, 'reader frame for book %d' % expected_id)
        except SampleError as error:
            self.record(applied, 'failed', note=str(error))
            self.record(painted, 'failed', note=str(error))
            return None
        self.record(applied, 'ok', start=stamp, end=event['at'], event=event)
        paint_index, paint_event, detail = self.first_paint(watch, previous, since, index, 180)
        if paint_index is None:
            self.record(painted, 'failed', start=stamp, end=event['at'],
                        note='frame applied without a real paint: %s' % detail)
            return event
        self.record(painted, 'ok', start=stamp, end=paint_event['at'], event=paint_event)
        return event

    def page_turn(self, host, watch, direction, expected_page, previous):
        metric = 'page_turn_forward' if direction > 0 else 'page_turn_backward'
        handle = self.expect(metric)
        since = watch.mark()
        try:
            stamp = host.press('F4' if direction > 0 else 'F3')
            index, event = self.await_state(
                host, watch,
                lambda state: state['host'].get('page') == expected_page and settled(state),
                180, since, 'page %d' % expected_page)
        except SampleError as error:
            self.record(handle, 'failed', note=str(error))
            return None
        paint_index, paint_event, detail = self.first_paint(watch, previous, since, index, 180)
        if paint_index is None:
            self.record(handle, 'failed', start=stamp, end=event['at'],
                        note='page applied without a real paint: %s' % detail)
            return None
        self.record(handle, 'ok', start=stamp, end=paint_event['at'], event=paint_event,
                    note='page=%d' % expected_page)
        return paint_event

    def turns(self, host, watch, forwards, backwards):
        latest = watch.latest()
        if latest is None:
            raise SampleError('no observation before the page turns')
        page = latest['state']['host'].get('page', 0)
        previous = self.current_paint(watch)
        for _ in range(forwards):
            event = self.page_turn(host, watch, 1, page + 1, previous)
            if event is None:
                return
            page += 1
            previous = self.current_paint(watch)
        for _ in range(backwards):
            event = self.page_turn(host, watch, -1, page - 1, previous)
            if event is None:
                return
            page -= 1
            previous = self.current_paint(watch)

    # ---- scenarios ---------------------------------------------------
    def start_host(self, host):
        host.find_window()
        host.activate()

    def scenario_shelf(self, index, host, watch, kind):
        handle = self.expect('startup_shelf_rows',
                             'first_publication' if index == 0 else 'warm_catalog')
        timeout = 600 if index == 0 else 300
        try:
            index_state, event = self.await_state(host, watch, shelf_ready, timeout, 0,
                                                  'first bounded shelf page')
        except SampleError as error:
            self.record(handle, 'failed', note=str(error))
            return
        self.record(handle, 'ok', start=self.launch_stamp, end=event['at'], event=event,
                    note='books=%s' % event['state']['host'].get('books'))
        key_handle = self.expect('startup_key_response')
        move_handle = self.expect('shelf_selection_move')
        try:
            self.start_host(host)
            since = watch.mark()
            stamp = host.press('F2')
            index_state, event = self.await_state(host, watch, lambda state: True, 120, since,
                                                  'response to the first key')
            self.record(key_handle, 'ok', start=self.launch_stamp, end=event['at'], event=event,
                        note='injected_at_ms=%.1f' % ((stamp - self.launch_stamp) * 1000.0))
            before = watch.latest()['state']['shelf'].get('selected_key')
            since = watch.mark()
            stamp = host.press('Down')
            index_state, event = self.await_state(
                host, watch,
                lambda state: state['shelf'].get('selected_key') not in (None, '', before),
                120, since, 'keyboard row selection move')
            self.record(move_handle, 'ok', start=stamp, end=event['at'], event=event)
        except (SampleError, subprocess.SubprocessError) as error:
            for pending in (key_handle, move_handle):
                if pending['status'] == 'pending':
                    self.record(pending, 'failed', note=str(error))
            return
        long_id = self.long_id
        title = 'Shelf %04d' % LONG_INDEX
        unique = lambda state: (state['host'].get('books') == 1
                                and state['host'].get('shelf_first_id') == long_id)
        if kind == 'shelf_search_open_turn':
            if self.search(host, watch, title, unique, 'search_title_unique') is None:
                return
        else:
            if self.search(host, watch, AUTHOR_QUERY,
                           lambda state: (state['host'].get('books') == 50
                                          and bool(state['host'].get('shelf_after'))),
                           'search_author_literal') is None:
                return
            if self.search(host, watch, MISSING_QUERY,
                           lambda state: state['host'].get('books') == 0, 'search_empty') is None:
                return
            if self.search(host, watch, '',
                           lambda state: state['host'].get('books') == 50, 'search_clear') is None:
                return
            if self.search(host, watch, title, unique, 'search_title_unique') is None:
                return
        if self.open_selected(host, watch, long_id) is None:
            return
        self.turns(host, watch, *TURNS[kind])

    def scenario_resume_turn(self, index, host, watch, book):
        applied = self.expect('resume_frame_applied')
        painted = self.expect('resume_frame_painted')
        try:
            index_state, event = self.await_state(
                host, watch,
                lambda state: (state['host'].get('book') == book
                               and state['host'].get('reader_visible') == 1 and settled(state)),
                600, 0, 'resumed reader frame for book %d' % book)
        except SampleError as error:
            self.record(applied, 'failed', note=str(error))
            self.record(painted, 'failed', note=str(error))
            return
        self.record(applied, 'ok', start=self.launch_stamp, end=event['at'], event=event,
                    note='page=%s' % event['state']['host'].get('page'))
        paint_index, paint_event, detail = self.first_paint(watch, 0, 0, index_state, 300)
        if paint_index is None:
            self.record(painted, 'failed', start=self.launch_stamp, end=event['at'],
                        note='resumed frame without a real paint: %s' % detail)
            return
        self.record(painted, 'ok', start=self.launch_stamp, end=paint_event['at'], event=paint_event)
        try:
            self.start_host(host)
        except (SampleError, subprocess.SubprocessError) as error:
            print('LAUNCH-NOTE %02d activation failed: %s' % (index, error), flush=True)
            return
        self.turns(host, watch, *TURNS['resume_turn'])

    def import_keys(self, host, watch, book_before):
        for slot in range(IMPORT_KEY_SLOTS):
            handle = self.expect('import_input_response')
            latest = watch.latest()
            if latest is None or latest['state']['host'].get('busy') != 1:
                self.record(handle, 'not_observed',
                            note='slot %d started after the import worker finished' % slot)
                continue
            since = watch.mark()
            try:
                stamp = host.press('F4')
            except subprocess.SubprocessError as error:
                self.record(handle, 'failed', note='key injection failed: %s' % error)
                continue
            index, event = watch.wait(
                lambda state: (state['host'].get('busy') == 1
                               and state['host'].get('book') == book_before), 60, since)
            if index is None:
                self.record(handle, 'failed',
                            note='no busy observation for the injected key: %s' % event)
                continue
            self.record(handle, 'ok', start=stamp, end=event['at'], event=event,
                        note='same book and worker busy; the main loop answered the key')

    def import_resize(self, host, watch, book_before):
        """Real resize during the import. The frozen host answers a resize with an
        allocation observation; its repaint behaviour is not guaranteed, so this
        metric records the main-loop answer and reports whether a paint followed."""
        handle = self.expect('import_resize_response')
        latest = watch.latest()
        if latest is None or latest['state']['host'].get('busy') != 1:
            self.record(handle, 'not_observed', note='import finished before the resize probe')
            return
        if latest['state']['host'].get('reader_visible') != 1:
            self.record(handle, 'not_observed',
                        note='the reader is not mapped during this import, so no allocation target')
            return
        previous = self.current_paint(watch)
        before_sequence = latest['state']['host'].get('sequence')
        since = watch.mark()
        stamp = time.monotonic()
        try:
            host.resize(WINDOW_WIDTH + 40, WINDOW_HEIGHT)
        except subprocess.SubprocessError as error:
            self.record(handle, 'failed', note='resize failed: %s' % error)
            return
        index, event = watch.wait(lambda state: True, 60, since)
        painted = 0
        sequence = before_sequence
        if index is not None:
            painted = event['state']['host'].get('painted_generation', 0) - previous
            sequence = event['state']['host'].get('sequence')
        try:
            host.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        except subprocess.SubprocessError:
            pass
        if index is None:
            self.record(handle, 'failed', note='no observation after the resize: %s' % event)
            return
        self.record(handle, 'ok', start=stamp, end=event['at'], event=event,
                    note='resize answered during the import; book=%s sequence=%s->%s paint_delta=%d' % (
                        book_before, before_sequence, sequence, painted))

    def scenario_import(self, index, host, watch):
        handle = self.expect('startup_shelf_rows', 'warm_catalog')
        try:
            index_state, event = self.await_state(host, watch, shelf_ready, 300, 0,
                                                  'first bounded shelf page')
        except SampleError as error:
            self.record(handle, 'failed', note=str(error))
            return
        self.record(handle, 'ok', start=self.launch_stamp, end=event['at'], event=event,
                    note='books=%s' % event['state']['host'].get('books'))
        try:
            self.start_host(host)
        except (SampleError, subprocess.SubprocessError) as error:
            print('LAUNCH-NOTE %02d activation failed: %s' % (index, error), flush=True)
            return
        for attempt in range(IMPORTS_PER_LAUNCH):
            path = self.import_paths[self.import_ring % len(self.import_paths)]
            self.import_ring += 1
            completion = self.expect('import_complete')
            before = watch.latest()
            book_before = before['state']['host'].get('book', 0) if before else 0
            since = watch.mark()
            try:
                stamp = host.open_import_dialog(path)
                busy_index, busy_event = self.await_state(
                    host, watch, lambda state: state['host'].get('busy') == 1, 180, since,
                    'import worker start')
            except (SampleError, subprocess.SubprocessError) as error:
                self.record(completion, 'failed', note=str(error))
                continue
            self.import_keys(host, watch, book_before)
            if attempt:
                self.import_resize(host, watch, book_before)
            try:
                done_index, done_event = self.await_state(
                    host, watch,
                    lambda state: (settled(state) and state['host'].get('reader_visible') == 1
                                   and state['host'].get('book') not in (0, book_before)),
                    300, busy_index, 'import completion')
            except SampleError as error:
                self.record(completion, 'failed', note=str(error))
                continue
            self.record(completion, 'ok', start=stamp, end=done_event['at'], event=done_event,
                        note='file=%s bytes=%d book=%s' % (path.name, path.stat().st_size,
                                                           done_event['state']['host'].get('book')))
            try:
                self.await_state(host, watch,
                                 lambda state: state['host'].get('reader_visible') == 1 and settled(state),
                                 300, done_index, 'reader frame after import')
            except SampleError:
                pass
        self.turns(host, watch, IMPORT_TURNS, 0)

    # ---- one launch --------------------------------------------------
    def launch_once(self, index):
        kind = KINDS[index % len(KINDS)]
        self.kind = kind
        self.launch = index
        self.handles = []
        entry_book = 0
        if kind == 'resume_turn':
            entry_book = self.last_book or self.long_id
        folder = self.output / 'raw' / ('launch-%02d' % index)
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        cache = self.apply_cache(index)
        profile = self.profile_import if kind == 'import_probe' else self.profile
        if kind == 'import_probe':
            self.prepare_import_profile()
        self.write_settings(profile, entry_book)
        watch = Watch(folder, 'state.ini')
        host = Host(self.binary, self.font, profile, folder,
                    dict(self.environment['host_environment']), index)
        record = {'launch': index, 'kind': kind, 'entry': 'reader' if entry_book else 'shelf',
                  'profile': profile.name, 'cache': cache, 'entry_book': entry_book,
                  'state_file': str((folder / 'state.ini').relative_to(self.output)),
                  'log_file': str((folder / 'application.log').relative_to(self.output))}
        self.launch_stamp = None
        try:
            self.launch_stamp = host.launch()
            record['pid'] = host.pid
            if kind == 'import_probe':
                self.scenario_import(index, host, watch)
            elif kind == 'resume_turn':
                self.scenario_resume_turn(index, host, watch, entry_book)
            else:
                self.scenario_shelf(index, host, watch, kind)
        except SampleError as error:
            record['failure'] = str(error)
            print('LAUNCH-FAILURE %02d %s: %s' % (index, kind, error), flush=True)
        except (subprocess.SubprocessError, OSError) as error:
            record['failure'] = 'process error: %s' % error
            print('LAUNCH-FAILURE %02d %s: %s' % (index, kind, error), flush=True)
        finally:
            for handle in list(self.handles):
                if handle['status'] == 'pending':
                    self.record(handle, 'missing', note='planned sample was never observed')
            try:
                record['geometry'] = host.geometry() if host.window else None
            except (subprocess.SubprocessError, OSError) as error:
                record['geometry'] = None
                record['geometry_error'] = str(error)
            try:
                record['vm_hwm_kb'] = host.hwm_kb()
                record['vm_rss_kb'] = host.rss_kb()
                record['threads'] = host.threads()
            except OSError as error:
                record['status_error'] = str(error)
            try:
                (folder / 'window-tree.txt').write_text(host.window_tree())
                record['window_tree_sha256'] = sha256_file(folder / 'window-tree.txt')
            except (subprocess.SubprocessError, OSError) as error:
                record['window_tree_sha256'] = None
                record['window_tree_error'] = str(error)
            try:
                record['process_exit'] = host.close()
            except (subprocess.SubprocessError, OSError) as error:
                record['process_exit'] = None
                record['close_error'] = str(error)
                host.kill()
            host.close_log()
            watch.close()
            events = list(watch.events)
            record['observation_failure'] = watch.failure
            record['state_writes'] = len(events)
            paints, seen = [], 0
            for event in events:
                value = event['state']['host'].get('painted_generation', 0)
                if value > seen:
                    paints.append(round((event['at'] - self.launch_stamp) * 1000.0, 3))
                    seen = value
            record['paint_offsets_ms'] = paints
            record['paint_count'] = len(paints)
            if events:
                record['final_state'] = events[-1]['state']
                record['last_book'] = events[-1]['state']['host'].get('book', 0) or 0
            if record.get('last_book'):
                self.last_book = record['last_book']
            if (folder / 'application.log').exists():
                record['log_bytes'] = (folder / 'application.log').stat().st_size
                record['log_sha256'] = sha256_file(folder / 'application.log')
            try:
                record['settings_sha256'] = sha256_file(profile / 'reader.ini')
                record['library_sha256'] = sha256_file(profile / 'library.sqlite')
                catalog = profile / 'library.sqlite.product.sqlite'
                record['catalog_sha256'] = sha256_file(catalog) if catalog.exists() else None
            except OSError as error:
                record['settings_error'] = str(error)
            print('LAUNCH %02d %s entry=%s exit=%s hwm_kb=%s paints=%d state_writes=%d cache=%s' % (
                index, kind, record['entry'], record['process_exit'], record.get('vm_hwm_kb'),
                record['paint_count'], record['state_writes'], cache['effective']), flush=True)
            self.launches.append(record)

    # ---- driver ------------------------------------------------------
    def run(self):
        self.output.mkdir(parents=True)
        (self.output / 'raw').mkdir(parents=True, exist_ok=True)
        self.collect_environment()
        self.seed()
        self.make_import_corpus()
        self.calibrate()
        for index in range(self.arguments.launches):
            self.launch_once(index)
        (self.output / 'driver-state.json').write_text(json.dumps(
            {'launches_started': len(self.launches),
             'launches_planned': self.arguments.launches}, indent=2) + '\n')
        self.write_evidence()

    def write_evidence(self):
        samples = {'schema': 1, 'source_sha': os.environ['GITHUB_SHA'],
                   'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                   'samples': self.results, 'plan': self.plan}
        (self.output / 'samples.json').write_text(json.dumps(samples, indent=2) + '\n')
        columns = ['launch', 'kind', 'metric', 'slot', 'group', 'outcome', 'start_ms', 'end_ms',
                   'latency_ms', 'sequence', 'painted_generation', 'note']
        with (self.output / 'samples.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            for row in self.results:
                writer.writerow(row)
        (self.output / 'launches.json').write_text(json.dumps(
            {'schema': 1, 'launches': self.launches}, indent=2) + '\n')
        (self.output / 'plan.json').write_text(json.dumps(
            {'launches': self.arguments.launches, 'kinds': list(KINDS),
             'turns': TURNS, 'imports_per_launch': IMPORTS_PER_LAUNCH,
             'import_key_slots': IMPORT_KEY_SLOTS, 'import_bytes': IMPORT_BYTES,
             'import_turns': IMPORT_TURNS, 'cold_launches': list(COLD_LAUNCHES),
             'metrics': {name: count for name, count in sorted(self.slots.items())},
             'plan': self.plan}, indent=2) + '\n')
        bundle = {}
        for path in sorted(self.output.rglob('*')):
            if not path.is_file() or path.name == 'bundle.json':
                continue
            bundle[str(path.relative_to(self.output))] = {'bytes': path.stat().st_size,
                                                          'sha256': sha256_file(path)}
        (self.output / 'bundle.json').write_text(json.dumps(
            {'schema': 1, 'files': bundle}, indent=2) + '\n')
        print('EVIDENCE ' + json.dumps({'launches': len(self.launches), 'samples': len(self.results),
                                        'planned': len(self.plan), 'metrics': len(self.slots)}),
              flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--launches', type=int, default=32)
    parser.add_argument('--tarball', type=Path)
    arguments = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('Run the GTK performance sampler on a GitHub Actions Linux runner')
    if arguments.launches < 30:
        parser.error('At least 30 independent launches are required')
    if arguments.output.exists():
        parser.error('Choose a new evidence directory')
    Sampler(arguments).run()


if __name__ == '__main__':
    main()
