#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only C02 measurement of the actual compact GTK product host.

Reuses the event-driven G11 sampler (tests/reader_perf_gtk, imported read-only):
real X11 keys from xdotool, end points from the host's own synchronous
observation write timestamped by inotify. This driver only changes what the
corpus is (500 and 5000 originals), which launch kinds run (the compact host
does not auto-resume, so the resume kind is dropped) and how rows are written
(the common C02 sample schema). One invocation is one independent round.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'reader_perf_gtk'))
import common as K  # noqa: E402
import sample as S  # noqa: E402
from observe import SampleError  # noqa: E402

KINDS = ('shelf_search_open_turn', 'shelf_search_variants', 'import_probe')
S.KINDS = KINDS
S.COLD_LAUNCHES = (0, 4, 8)
S.IMPORTS_PER_LAUNCH = 2
S.IMPORT_BYTES = 4 * 1024 * 1024


def cpu_model():
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.lower().startswith('model name'):
                return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return 'unknown'


def cpu_mhz():
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.lower().startswith('cpu mhz'):
                return float(line.split(':', 1)[1])
    except (OSError, ValueError):
        pass
    return None


def cache_kb():
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.lower().startswith('cache size'):
                return int(line.split(':', 1)[1].split()[0])
    except (OSError, ValueError, IndexError):
        pass
    return None


class CompactSampler(S.Sampler):
    def __init__(self, arguments, size):
        super().__init__(arguments)
        self.size = size
        self.author_rows = min(50, -(-size // 17))

    def seed(self):
        database = self.profile / 'library.sqlite'
        self.profile.mkdir(parents=True, exist_ok=True)
        corpus_path = self.output / 'corpus.json'
        before = time.monotonic()
        process = subprocess.run([str(self.arguments.seed), str(database), str(corpus_path), str(self.size)],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3600)
        elapsed = (time.monotonic() - before) * 1000.0
        if process.returncode != 0:
            raise SampleError('seeding failed: %s' % process.stdout.decode()[-2000:])
        self.corpus = json.loads(corpus_path.read_text())
        self.long_id = self.corpus['originals'][S.LONG_INDEX]['id']
        self.environment['seed'] = {
            'elapsed_ms': round(elapsed, 3), 'stdout': process.stdout.decode().strip().splitlines()[-1:],
            'corpus_sha256': S.sha256_file(corpus_path), 'seed_sha256': S.sha256_file(self.arguments.seed),
            'library_bytes': database.stat().st_size, 'library_sha256': S.sha256_file(database),
            'books': self.size}
        self.write_environment()
        if self.corpus.get('books') != self.size or not self.long_id:
            raise SampleError('seed corpus is not the fixed %d originals: %r' % (
                self.size, self.corpus.get('books')))
        print('SEED books=%d long_id=%d elapsed_ms=%.1f' % (self.size, self.long_id, elapsed), flush=True)

    def scenario_shelf(self, index, host, watch, kind):
        """The G11 shelf scenario with the author-search expectation sized to the corpus."""
        handle = self.expect('startup_shelf_rows', 'first_publication' if index == 0 else 'warm_catalog')
        try:
            _, event = self.await_state(host, watch, S.shelf_ready, 600 if index == 0 else 300, 0,
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
            _, event = self.await_state(host, watch, lambda state: True, 120, since,
                                        'response to the first key')
            self.record(key_handle, 'ok', start=self.launch_stamp, end=event['at'], event=event,
                        note='injected_at_ms=%.1f' % ((stamp - self.launch_stamp) * 1000.0))
            before = watch.latest()['state']['shelf'].get('selected_key')
            since = watch.mark()
            stamp = host.press('Down')
            _, event = self.await_state(
                host, watch, lambda state: state['shelf'].get('selected_key') not in (None, '', before),
                120, since, 'keyboard row selection move')
            self.record(move_handle, 'ok', start=stamp, end=event['at'], event=event)
        except (SampleError, subprocess.SubprocessError) as error:
            for pending in (key_handle, move_handle):
                if pending['status'] == 'pending':
                    self.record(pending, 'failed', note=str(error))
            return
        long_id = self.long_id
        title = 'Shelf %04d' % S.LONG_INDEX
        unique = lambda state: (state['host'].get('books') == 1  # noqa: E731
                                and state['host'].get('shelf_first_id') == long_id)
        if kind == 'shelf_search_open_turn':
            if self.search(host, watch, title, unique, 'search_title_unique') is None:
                return
        else:
            expected = self.author_rows
            if self.search(host, watch, S.AUTHOR_QUERY,
                           lambda state: state['host'].get('books') == expected,
                           'search_author_literal') is None:
                return
            if self.search(host, watch, S.MISSING_QUERY,
                           lambda state: state['host'].get('books') == 0, 'search_empty') is None:
                return
            if self.search(host, watch, '', lambda state: state['host'].get('books') == 50,
                           'search_clear') is None:
                return
            if self.search(host, watch, title, unique, 'search_title_unique') is None:
                return
        if self.open_selected(host, watch, long_id) is None:
            return
        self.turns(host, watch, *S.TURNS[kind])


def program_version(binary):
    done = subprocess.run([str(binary), '--version'], capture_output=True, timeout=60, text=True)
    return done.stdout.strip()


def convert(sampler, identity, rows, memory, launches):
    size = identity['shelf_size']
    for launch in sampler.launches:
        launch_id = 'g%d-n%d-%02d' % (identity['round'], size, launch['launch'])
        entry = dict(launch, launch_id=launch_id, shelf_size=size)
        launches.append(entry)
        hwm, rss = launch.get('vm_hwm_kb'), launch.get('vm_rss_kb')
        if hwm and rss:
            memory.append({'platform': 'gtk', 'round': identity['round'], 'shelf_size': size,
                           'launch': launch_id, 'cohort': launch['kind'],
                           'rss_final_bytes': int(rss) * 1024, 'rss_peak_bytes': int(hwm) * 1024,
                           'private_peak_bytes': None})
    for row in sampler.results:
        launch_id = 'g%d-n%d-%02d' % (identity['round'], size, row['launch'])
        rows.append(K.sample_row(identity, launch_id, row['kind'], row['metric'], row['slot'],
                                 row['outcome'], row.get('latency_ms'), row.get('note', '')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tarball', type=Path)
    parser.add_argument('--round', type=int, choices=(1, 2), required=True)
    parser.add_argument('--sizes', default='500,5000')
    parser.add_argument('--launches', type=int, default=12)
    parser.add_argument('--producer-source', required=True)
    parser.add_argument('--sdk-source', required=True)
    arguments = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('run the GTK C02 driver on a GitHub Actions Linux runner')
    if arguments.output.exists():
        parser.error('choose a new evidence directory')
    output = arguments.output.resolve()
    output.mkdir(parents=True)
    binary = arguments.payload.resolve() / 'bin' / 'exreader-linux'
    sizes = [int(item) for item in arguments.sizes.split(',')]
    if arguments.round == 2:
        sizes.reverse()
    rows, memory, launches = [], [], []
    model = cpu_model()
    logical = os.cpu_count()
    base = {'platform': 'gtk', 'round': arguments.round, 'consumer_sha': os.environ['GITHUB_SHA'],
            'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
            'job': os.environ.get('GITHUB_JOB', ''), 'program_sha256': S.sha256_file(binary),
            'program_bytes': binary.stat().st_size, 'producer_source': arguments.producer_source,
            'sdk_source': arguments.sdk_source, 'sdk_version': program_version(binary),
            'ui_variant': 'EXR_READER_GTK_COMPACT=ON',
            'stratum': K.cpu_stratum('gtk', model, logical)['id']}
    K.write_json(output / 'environment.json', {
        'schema': K.SCHEMA, 'platform': 'gtk', 'round': arguments.round,
        'cpu': {'model': model, 'mhz_reported': cpu_mhz(), 'cache_kb': cache_kb(),
                'logical_processors': logical, 'stratum': K.cpu_stratum('gtk', model, logical)},
        'memory_definition': K.RSS_DEFINITION['gtk'],
        'percentile_definition': 'nearest rank: value at rank ceil(p*n/100) of the sorted samples',
        'measurement': {'kind': 'real X11 key to host observation write (inotify)', 'frame_time_measured': False,
                        'frame_evidence': 'painted_generation increments only; no frame-clock timestamps',
                        'kinds': list(KINDS), 'launches_per_size': arguments.launches}})
    for size in sizes:
        identity = dict(base, shelf_size=size)
        sub = argparse.Namespace(payload=arguments.payload, seed=arguments.seed, launches=arguments.launches,
                                 output=output / 'raw' / ('n%d' % size), tarball=arguments.tarball)
        sampler = CompactSampler(sub, size)
        try:
            sampler.run()
        except Exception as error:  # noqa: BLE001 - kept as evidence; coverage then fails honestly
            print('SIZE-FAILURE n%d: %s: %s' % (size, type(error).__name__, error), flush=True)
            K.write_json(output / ('size-failure-n%d.json' % size),
                         {'size': size, 'error': '%s: %s' % (type(error).__name__, error)})
        K.write_json(output / ('identity-n%d.json' % size), identity)
        convert(sampler, identity, rows, memory, launches)
    K.write_json(output / 'samples.json', {'schema': K.SCHEMA, 'rows': rows})
    K.write_json(output / 'launches.json', {'schema': K.SCHEMA, 'launches': launches})
    K.write_json(output / 'memory.json', {'schema': K.SCHEMA, 'records': memory})
    K.write_json(output / 'plan.json', {'schema': K.SCHEMA, 'sizes': sizes, 'kinds': list(KINDS),
                                        'launches_per_size': arguments.launches})
    K.write_json(output / 'bundle.json', K.bundle_for(output))
    bad = [row for row in rows if row['status'] != 'ok']
    print('ROUND-EVIDENCE rows=%d not_ok=%d launches=%d' % (len(rows), len(bad), len(launches)), flush=True)


if __name__ == '__main__':
    main()
