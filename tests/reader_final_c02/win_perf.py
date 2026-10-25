#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only C02 measurement of the actual compact Windows product host.

The compact EXReaderProduct.exe (EXR_READER_WINDOWS_COMPACT=ON) is launched as
an independent process for every sample. Steps are delivered to its real Win32
controls and the resulting UI state is read back from the same controls, using
the unchanged Host/op_* primitives of tests/reader_perf_windows (imported
read-only). Nothing is measured in-process and no frame time is claimed: every
value is an external end-to-end control-state latency.

One invocation is one independent round for two shelf sizes (500 and 5000
originals, each seeded by the installed public SDK, never mixed).
"""
import argparse
import json
import math
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'reader_perf_windows'))
import common as K  # noqa: E402

if os.name == 'nt':
    import perf_windows as PW  # noqa: E402
    import winreg  # noqa: E402
else:  # pragma: no cover - the self-check of the shared rules runs elsewhere
    PW = None

WM_COMMAND = 0x0111
COMPACT_SHELF, COMPACT_MORE = 46001, 46003
COLD_BUDGET_S = 3600
LONG_TITLE = 'Shelf 0000'
AUTHOR_QUERY = 'Author %_!'

PLAN = {
    'cold': {'start_window': 1, 'start_first_rows': 1, 'start_interactive': 1,
             'ui_roundtrip_idle': 30, 'shelf_scroll_page': 1, 'search_author': 1,
             'search_clear': 1, 'search_title': 1, 'open_book': 1, 'page_turn': 8,
             'ui_roundtrip_reading': 8, 'back_to_library': 1},
    'resume': {'start_window': 1, 'resume_restored': 1, 'page_turn': 4, 'ui_roundtrip_reading': 4},
    'import': {'start_window': 1, 'start_first_rows': 1, 'start_interactive': 1,
               'import_complete': 1, 'post_import_search': 1},
}
PLAN['warm'] = PLAN['cold']
COHORT_ORDER = ('cold', 'warm', 'resume', 'import')


def author_rows(size):
    return min(50, -(-size // 17))


def cpu_identity():
    model = platform.processor()
    mhz = None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            model = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
            mhz = int(winreg.QueryValueEx(key, '~MHz')[0])
    except OSError:
        pass
    return model, mhz


def make_txt_import(directory, index, size_bytes=4 << 20):
    """Deterministic multi-line TXT whose shelf title is its file stem."""
    path = directory / ('Perf Import %04d.txt' % index)
    header = 'Perf Import %04d\n' % index
    unit = (header + ''.join('Perf Import %04d line %04d keeps the import worker busy while '
                             'input continues.\n' % (index, line) for line in range(512))).encode()
    written = 0
    with path.open('wb') as handle:
        while written < size_bytes:
            handle.write(unit)
            written += len(unit)
    return path


class Round:
    def __init__(self, arguments):
        self.arguments = arguments
        self.out = arguments.output.resolve()
        self.work = self.out.parent / (self.out.name + '-work')
        self.exe = arguments.exe.resolve()
        self.font = arguments.font.resolve()
        self.seed = arguments.seed.resolve()
        self.rows = []
        self.launches = []
        self.memory = []
        self.corpora = {}
        self.identity = None
        self.model, self.mhz = cpu_identity()
        self.logical = os.cpu_count()

    # -- identity -------------------------------------------------------
    def identity_for(self, size):
        stratum = K.cpu_stratum('windows', self.model, self.logical)
        return {'platform': 'windows', 'round': self.arguments.round,
                'consumer_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'job': os.environ.get('GITHUB_JOB', ''),
                'program_sha256': PW.sha256(self.exe), 'program_bytes': self.exe.stat().st_size,
                'font_sha256': PW.sha256(self.font),
                'seed_sha256': PW.sha256(self.seed),
                'producer_source': self.arguments.producer_source,
                'sdk_version': self.arguments.sdk_version,
                'ui_variant': 'EXR_READER_WINDOWS_COMPACT=ON',
                'stratum': stratum['id'], 'shelf_size': size}

    def environment(self):
        system = PW.SYSTEM_INFO()
        PW.K.GetSystemInfo(PW.C.byref(system))
        memory = PW.MEMORYSTATUSEX()
        memory.dwLength = PW.C.sizeof(PW.MEMORYSTATUSEX)
        PW.K.GlobalMemoryStatusEx(PW.C.byref(memory))
        return {'schema': K.SCHEMA, 'platform': 'windows', 'round': self.arguments.round,
                'cpu': {'model': self.model, 'mhz_nominal': self.mhz, 'logical_processors': self.logical,
                        'stratum': K.cpu_stratum('windows', self.model, self.logical)},
                'memory_total_bytes': int(memory.ullTotalPhys),
                'os': {'platform': platform.platform(), 'version': platform.version(),
                       'windows_version': list(sys.getwindowsversion())},
                'display': PW.display_identity(),
                'runner': {name: os.environ.get(name, '') for name in
                           ('RUNNER_OS', 'RUNNER_ARCH', 'RUNNER_NAME', 'ImageOS', 'ImageVersion',
                            'GITHUB_WORKFLOW', 'GITHUB_JOB')},
                'python': platform.python_version(),
                'memory_definition': K.RSS_DEFINITION['windows'],
                'percentile_definition': 'nearest rank: value at rank ceil(p*n/100) of the sorted samples',
                'measurement': {'kind': 'external end-to-end native control latency',
                                'frame_time_measured': False,
                                'clock': 'time.perf_counter()',
                                'input': 'SendMessageTimeout/BM_CLICK/WM_SETTEXT/WM_MOUSEWHEEL/WM_COMMAND '
                                         'to the real controls of the running process',
                                'disk_cache_controlled': False, 'background_load_controlled': False}}

    # -- samples --------------------------------------------------------
    def add(self, state, metric, ms, status='ok', note=''):
        slot = state['slots'].get(metric, 0)
        state['slots'][metric] = slot + 1
        self.rows.append(K.sample_row(state['identity'], state['launch'], state['cohort'], metric, slot,
                                      status, ms, note))

    # -- corpus ---------------------------------------------------------
    def prepare(self, size):
        folder = self.work / ('n%d' % size)
        template = folder / 'template'
        if folder.exists():
            shutil.rmtree(folder)
        template.mkdir(parents=True)
        corpus = folder / 'corpus.json'
        done = subprocess.run([str(self.seed), str(template / 'library.sqlite'), str(corpus), str(size)],
                              capture_output=True, timeout=1800)
        if done.returncode != 0:
            raise PW.MeasurementFault('seed failed: ' + done.stderr.decode('utf-8', 'replace'))
        manifest = K.read_json(corpus)
        K.require(manifest['books'] == size and len(manifest['originals']) == size, 'seed size differs')
        shutil.copyfile(corpus, self.out / ('corpus-n%d.json' % size))
        prep = {'size': size, 'seed_stdout': done.stdout.decode().strip(),
                'corpus_sha256': PW.sha256(corpus), 'library_sha256': PW.sha256(template / 'library.sqlite')}
        # One unmeasured launch builds the product catalog; then read it back.
        host = PW.Host(self.exe, self.font, template, self.out / 'logs' / ('prep-n%d-catalog.log' % size))
        try:
            prep['catalog_first_screen'] = PW.op_first_screen(host, COLD_BUDGET_S)
        finally:
            prep['catalog_peak'] = host.close()
        database = template / 'library.sqlite.product.sqlite'
        K.require(database.exists(), 'product catalog was not created')
        with sqlite3.connect(str(database)) as connection:
            titles = [row[0] for row in connection.execute(
                "SELECT title FROM reader_books WHERE format='txt' ORDER BY title")]
        K.require(titles == ['Shelf %04d' % number for number in range(size)],
                  'product catalog differs from the %d seeded originals (%d rows)' % (size, len(titles)))
        prep['catalog_rows'] = len(titles)
        prep['catalog_sha256'] = PW.sha256(database)
        # Reading profile: open the long book once and move two pages so the
        # compact host has a restorable position.
        reading = folder / 'reading'
        shutil.copytree(template, reading)
        host = PW.Host(self.exe, self.font, reading, self.out / 'logs' / ('prep-n%d-reading.log' % size))
        try:
            PW.op_first_screen(host, COLD_BUDGET_S)
            opened = PW.op_open(host, LONG_TITLE)
            key = opened['key']
            for _ in range(2):
                key = PW.op_page_turn(host, key)['to']
            time.sleep(1.0)
            prep['reading_key'] = key
        finally:
            prep['reading_peak'] = host.close()
        self.corpora[size] = {'folder': folder, 'template': template, 'reading': reading,
                              'reading_key': key, 'prep': prep}
        K.write_json(self.out / ('prepare-n%d.json' % size), prep)

    # -- one launch -----------------------------------------------------
    def profile_for(self, size, cohort, launch_id):
        corpus = self.corpora[size]
        if cohort == 'resume':
            return corpus['reading'], 'shared-reading-profile'
        profile = corpus['folder'] / 'profiles' / launch_id
        if cohort == 'warm':
            profile = corpus['folder'] / 'profiles' / 'warm-shared'
            if not profile.exists():
                shutil.copytree(corpus['template'], profile)
            return profile, 'shared-warm-profile'
        if profile.exists():
            shutil.rmtree(profile)
        PW.fresh_profile(corpus['template'], profile)
        return profile, 'fresh-sdk-library-copy-catalog-rebuilt'

    def launch(self, size, cohort, index):
        launch_id = 'w%d-n%d-%s-%02d' % (self.arguments.round, size, cohort, index)
        identity = self.identity_for(size)
        state = {'identity': identity, 'launch': launch_id, 'cohort': cohort, 'slots': {}}
        record = {'launch': launch_id, 'cohort': cohort, 'index': index, 'shelf_size': size,
                  'ok': False, 'faults': [], 'started_utc': None, 'pid': None}
        profile, strategy = self.profile_for(size, cohort, launch_id)
        record['profile_strategy'] = strategy
        host = None
        peak = None
        try:
            host = PW.Host(self.exe, self.font, profile, self.out / 'logs' / (launch_id + '.log'))
            record['pid'] = host.process.pid
            record['started_utc'] = host.started_utc
            if cohort == 'resume':
                self.run_resume(host, state, size)
            else:
                marks = self.run_start(host, state)
                if cohort == 'import':
                    self.run_import(host, state, index)
                else:
                    self.run_library_and_reading(host, state, size)
            record['ok'] = True
        except Exception as error:  # noqa: BLE001 - every failure is evidence, not control flow
            record['faults'].append('%s: %s' % (type(error).__name__, error))
        finally:
            if host is not None:
                try:
                    peak = host.close()
                except Exception as error:  # noqa: BLE001
                    record['faults'].append('close: %s' % error)
        recorded = set((row['metric'], row['slot']) for row in self.rows if row['launch'] == launch_id)
        for metric, count in PLAN[cohort].items():
            for slot in range(count):
                if (metric, slot) not in recorded:
                    self.add_missing(state, metric, slot)
        if host is not None:
            self.record_memory(host, peak, identity, launch_id, size, record)
        if cohort in ('cold', 'import') and profile.exists():
            shutil.rmtree(profile, ignore_errors=True)
        self.launches.append(record)
        print('LAUNCH %s ok=%s faults=%s' % (launch_id, record['ok'], record['faults']), flush=True)

    def add_missing(self, state, metric, slot):
        self.rows.append(K.sample_row(state['identity'], state['launch'], state['cohort'], metric, slot,
                                      'missing', None, 'planned sample was never observed'))

    def record_memory(self, host, peak, identity, launch_id, size, record):
        samples = host.sampler.samples
        raw = self.out / 'raw' / 'memory'
        raw.mkdir(parents=True, exist_ok=True)
        K.write_json(raw / (launch_id + '.json'),
                     {'columns': ['t_ms', 'working_set', 'peak_working_set', 'private_usage'],
                      'samples': samples})
        if not samples:
            record['faults'].append('no memory samples')
            return
        peak_ws = max(sample[2] for sample in samples)
        if peak:
            peak_ws = max(peak_ws, peak['peak_working_set_bytes'])
        self.memory.append({'platform': 'windows', 'round': self.arguments.round, 'shelf_size': size,
                            'launch': launch_id, 'cohort': record['cohort'],
                            'rss_final_bytes': int(samples[-1][1]), 'rss_peak_bytes': int(peak_ws),
                            'private_peak_bytes': int(max(sample[3] for sample in samples)),
                            'memory_samples': len(samples)})

    # -- scenarios ------------------------------------------------------
    def run_start(self, host, state):
        marks = PW.op_first_screen(host, COLD_BUDGET_S)
        self.add(state, 'start_window', marks['window_ms'])
        self.add(state, 'start_first_rows', marks['rows_ms'])
        if marks.get('first_screen_interactive_ms') is None:
            self.add(state, 'start_interactive', None, 'failed', 'round trip timed out')
        else:
            self.add(state, 'start_interactive', marks['first_screen_interactive_ms'])
        return marks

    def run_library_and_reading(self, host, state, size):
        for _ in range(PLAN['cold']['ui_roundtrip_idle']):
            self.add(state, 'ui_roundtrip_idle', host.roundtrip(5000))
            time.sleep(0.02)
        self.add(state, 'shelf_scroll_page', PW.op_shelf_next_page(host)['ms'])
        PW.op_reset_top(host)
        expected = author_rows(size)
        found = PW.op_search(
            host, AUTHOR_QUERY,
            lambda app: app.lb_count() == expected and 'Shelf 0017' in app.lb_item(1),
            lambda rows: len(rows) == expected and
            all(number is not None and number % 17 == 0 for number in PW.numbered(rows)))
        self.add(state, 'search_author', found['ms'])
        found = PW.op_search(
            host, '',
            lambda app: app.lb_count() == 50 and 'Shelf 0001' in app.lb_item(1),
            lambda rows: len(rows) == 50 and PW.numbered(rows) == list(range(50)))
        self.add(state, 'search_clear', found['ms'])
        found = PW.op_search(
            host, LONG_TITLE,
            lambda app: app.lb_count() == 1 and LONG_TITLE in app.lb_item(0),
            lambda rows: len(rows) == 1 and LONG_TITLE in rows[0])
        self.add(state, 'search_title', found['ms'])
        opened = PW.op_open(host, LONG_TITLE)
        self.add(state, 'open_book', opened['ms'])
        key = opened['key']
        for _ in range(PLAN['cold']['page_turn']):
            turn = PW.op_page_turn(host, key)
            key = turn['to']
            self.add(state, 'page_turn', turn['ms'])
            self.add(state, 'ui_roundtrip_reading', host.roundtrip(5000))
        started = PW.now_ms()
        host.send(host.window, WM_COMMAND, COMPACT_SHELF)
        books = host.control('books')
        host.poll(lambda: (True,) if PW.U.IsWindowVisible(books) else None, 60, interval=0.003)
        self.add(state, 'back_to_library', PW.now_ms() - started)

    def run_resume(self, host, state, size):
        marks = PW.op_window(host)
        self.add(state, 'start_window', marks['window_ms'])
        expected = self.corpora[size]['reading_key']
        resumed = PW.op_resume(host, expected)
        if resumed['verified'] is not True:
            self.add(state, 'resume_restored', resumed['ms'], 'failed',
                     'restored page %r differs from saved %r' % (resumed['key'], expected))
            raise PW.MeasurementFault('restored reading position differs from the saved one')
        self.add(state, 'resume_restored', resumed['ms'])
        key = resumed['key']
        for _ in range(PLAN['resume']['page_turn']):
            turn = PW.op_page_turn(host, key)
            key = turn['to']
            self.add(state, 'page_turn', turn['ms'])
            self.add(state, 'ui_roundtrip_reading', host.roundtrip(5000))
        time.sleep(1.0)
        self.corpora[size]['reading_key'] = key

    def run_import(self, host, state, index):
        # The compact Import button opens the system picker; the existing compact
        # suite drives that picker. Here the expanded panel's own import path is
        # used so the product import worker, not the OS dialog, is timed.
        host.send(host.window, WM_COMMAND, COMPACT_MORE)
        path_control = host.control('path')
        host.poll(lambda: (True,) if PW.U.IsWindowVisible(path_control) else None, 60, interval=0.01)
        fixtures = self.work / 'import-fixtures'
        fixtures.mkdir(parents=True, exist_ok=True)
        fixture = make_txt_import(fixtures, index + 1 + 10 * self.arguments.round)
        title = fixture.stem
        result = PW.op_import(host, fixture, title)
        self.add(state, 'import_complete', result['import_ms'])
        self.add(state, 'post_import_search', result['post_import_search_ms'])
        for sample in result['input_samples']:
            if sample['busy'] and sample['roundtrip_ms'] is not None:
                self.add(state, 'ui_roundtrip_import_busy', sample['roundtrip_ms'])
            elif sample['busy']:
                self.add(state, 'ui_roundtrip_import_busy', None, 'failed', 'round trip timed out')

    # -- driver ---------------------------------------------------------
    def run(self):
        self.out.mkdir(parents=True)
        (self.out / 'logs').mkdir()
        K.write_json(self.out / 'environment.json', self.environment())
        sizes = [int(item) for item in self.arguments.sizes.split(',')]
        if self.arguments.round == 2:
            sizes.reverse()
        counts = {'cold': self.arguments.cold, 'warm': self.arguments.warm,
                  'resume': self.arguments.resume, 'import': self.arguments.imports}
        for size in sizes:
            self.prepare(size)
            for cohort in COHORT_ORDER:
                for index in range(counts[cohort]):
                    self.launch(size, cohort, index)
        for size in sizes:
            K.write_json(self.out / ('identity-n%d.json' % size), self.identity_for(size))
        K.write_json(self.out / 'samples.json', {'schema': K.SCHEMA, 'rows': self.rows})
        K.write_json(self.out / 'launches.json', {'schema': K.SCHEMA, 'launches': self.launches})
        K.write_json(self.out / 'memory.json', {'schema': K.SCHEMA, 'records': self.memory})
        K.write_json(self.out / 'plan.json', {'schema': K.SCHEMA, 'sizes': sizes, 'plan': PLAN,
                                              'launch_counts': counts})
        K.write_json(self.out / 'bundle.json', K.bundle_for(self.out))
        failed = [row for row in self.rows if row['status'] != 'ok']
        print('ROUND-EVIDENCE rows=%d not_ok=%d launches=%d failed_launches=%d' % (
            len(self.rows), len(failed), len(self.launches),
            sum(1 for launch in self.launches if not launch['ok'])), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--round', type=int, choices=(1, 2), required=True)
    parser.add_argument('--sizes', default='500,5000')
    parser.add_argument('--cold', type=int, default=4)
    parser.add_argument('--warm', type=int, default=4)
    parser.add_argument('--resume', type=int, default=4)
    parser.add_argument('--imports', type=int, default=3)
    parser.add_argument('--producer-source', required=True)
    parser.add_argument('--sdk-version', required=True)
    arguments = parser.parse_args()
    if os.name != 'nt' or os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('run the Windows C02 driver on a GitHub Actions Windows runner')
    if arguments.output.exists():
        parser.error('choose a new evidence directory')
    Round(arguments).run()


if __name__ == '__main__':
    main()
