# SPDX-License-Identifier: MIT
"""Rank the archived benchmark and run targeted attribution on a MinGW/Ninja build."""
import argparse
import ctypes as c
import gzip
import json
import math
import os
from pathlib import Path
import random
import re
import statistics as stats
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from bench_real_doc import Bitmap, Error, Page, digest_file, hash_active_rgba, wait_idle

ARCHIVE = ROOT / 'evidence/pdfjs-large-doc-20261118'
CONTENT = ROOT / 'evidence/real-doc-throughput-20261118/page-content.json'
CASES = {'real-mixed-120': (), 'image-heavy-100': (71, 90, 100),
         'vector-heavy-100': (66, 90, 100)}
MODES = ('full', 'images', 'paths', 'text', 'groups', 'shading', 'clip')
WIDTH = 1200


def load(path):
    if path.suffix == '.gz':
        return json.loads(gzip.decompress(path.read_bytes()))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def archived():
    report = load(ARCHIVE / 'results.json')
    content = load(CONTENT)
    cohorts = load(ARCHIVE / 'cohorts.json')
    output = {}
    for label in CASES:
        key = f'{label}@{WIDTH}'
        case = report['cases'][key]
        pdf = ROOT / f'tests/fixtures/pdf-large/{label}.pdf'
        assert digest_file(pdf) == content[label]['sha256'] == case['input_sha256']
        repeats = [load(ARCHIVE / f'raw/{label}-w{WIDTH}-r{r}-exreader.json') for r in range(3)]
        exact_p95 = stats.median(rep['p95_ms'] for rep in repeats)
        rows = []
        for entry, inventory, pdfjs in zip(case['exreader']['per_page'], content[label]['pages'],
                                           case['pdfjs']['per_page'], strict=True):
            page = entry['page']
            assert page == inventory['page'] == pdfjs['page']
            samples = [rep['pages'][page - 1] for rep in repeats]
            assert stats.median(p['p50_ms'] for p in samples) == entry['p50_ms']
            if inventory['soft_mask_axial_shadings'] and inventory['axial_shadings']:
                cohort = 'gradient+smask'
            elif label == 'image-heavy-100' and page >= 71:
                cohort = 'synthetic multi-image'
            elif label == 'vector-heavy-100' and page >= 66:
                cohort = 'synthetic dense vector'
            else:
                cohort = 'image (no gradient)' if inventory['image_draws'] else 'other'
            rows.append({**inventory, **entry, 'cohort': cohort, 'pdfjs_ms': pdfjs['p50_ms'],
                         'cold_ms': stats.median(p['first_render_ms'] for p in samples),
                         'repeat_p50_ms': [p['p50_ms'] for p in samples],
                         'samples_above_repeat_p95': [sum(t > rep['p95_ms'] for t in p['render_ms'])
                                                      for p, rep in zip(samples, repeats)]})
        for cohort, expected in cohorts[key].items():
            members = [r for r in rows if ({'synthetic multi-image': 'image (no gradient)',
                                          'synthetic dense vector': 'other'}.get(r['cohort'], r['cohort'])) == cohort]
            assert len(members) == expected['pages']
            assert abs(sum(r['p50_ms'] for r in members) - expected['exreader_ms']) < 0.11
        rows.sort(key=lambda row: (-row['p50_ms'], row['page']))
        threshold = rows[len(rows) - math.ceil(.95 * len(rows))]['p50_ms']
        output[label] = {
            'archived_p95_ms': exact_p95,
            'archived_pdfjs_p95_ms': case['pdfjs']['p95_ms_median'],
            'page_p95_ms': threshold,
            'page_total_ms': sum(row['p50_ms'] for row in rows),
            'ranked_pages': rows,
        }
    return output


def build_probe(build, scratch):
    build, scratch = build.resolve(), scratch.resolve()
    ninja = (build / 'build.ninja').read_text(encoding='utf-8')
    rule = re.search(r'^build libexreader.dll .*?Release (.*?) \|.*?^  LINK_LIBRARIES = (.*)$',
                     ninja, re.M | re.S)
    objects = rule[1]
    # LINK_LIBRARIES is a single Ninja variable line.
    libraries = rule[2].splitlines()[0]
    source = build / 'CMakeCache.txt'
    compiler = next(line.split('=', 1)[1] for line in source.read_text().splitlines()
                    if line.startswith('CMAKE_C_COMPILER:'))
    original = (ROOT / 'src/pdf_objects.c').read_text(encoding='utf-8')
    layout = original[original.index('typedef struct { size_t offset;'):original.index('typedef struct { exr_pdf_file *file;')]
    (scratch / 'pdf_file_layout.h').write_text('#include "pdf_crypto.h"\n' + layout, encoding='utf-8')
    obj = scratch / 'tail-probe.o'
    subprocess.run([compiler, '-O3', '-DEXR_STATIC', '-c', str(HERE / 'probe.c'), '-o', str(obj),
                    '-I' + str(ROOT / 'src'), '-I' + str(ROOT / 'include'), '-I' + str(scratch),
                    '-I' + re.search(r'-isystem ([^\s]+/freetype-src/include)', ninja)[1]], check=True)
    wrappers = re.findall(r'\b__wrap_(\w+)\(', (HERE / 'probe.c').read_text(encoding='utf-8'))
    rsp = scratch / 'tail-probe.rsp'
    rsp.write_text(f'"{obj.as_posix()}" {objects} {libraries}', encoding='utf-8')
    dll = scratch / 'tail-probe.dll'
    subprocess.run([compiler, '-shared', '-static-libgcc', '-static', 'exreader.def', '-o', str(dll),
                    *[f'-Wl,--wrap={name}' for name in wrappers], '@' + str(rsp)], cwd=build, check=True)
    return dll


class PageTrace(c.Structure):
    _fields_ = [(name, c.c_size_t) for name in (
        'font_hits font_misses font_evictions font_entries font_bytes font_opens face_opens '
        'clip_calls mask_builds draw_walks reader_changes clip_allocations clip_reuses clip_fast'
    ).split()] + [('mask_ms', c.c_double)]


class ImageTrace(c.Structure):
    _fields_ = [(name, c.c_size_t) for name in (
        'hits misses bytes entries evictions matte_bypasses wide_bypasses state_bypasses'
    ).split()] + [('decode_ms', c.c_double)]


class Document:
    def __init__(self, engine, pdf):
        self.engine = engine
        for name, args in {
            'exr_fixed_open': [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)],
            'exr_fixed_pages': [c.c_void_p, c.POINTER(c.c_size_t)],
            'exr_fixed_render': [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)],
            'exr_bitmap_free': [c.POINTER(Bitmap)], 'exr_fixed_free': [c.c_void_p],
            'tail_begin': [c.c_int, c.c_int], 'tail_document': [],
            'tail_read': [c.POINTER(PageTrace), c.POINTER(ImageTrace)],
        }.items():
            getattr(engine, name).argtypes = args
        engine.exr_fixed_pages.restype = c.POINTER(Page)
        self.ptr, self.error = c.c_void_p(), Error()
        engine.tail_document()
        engine.tail_begin(0, 0)
        self.check(engine.exr_fixed_open(str(pdf).encode('utf-8'), None, c.byref(self.ptr), c.byref(self.error)))
        count = c.c_size_t()
        pages = engine.exr_fixed_pages(self.ptr, c.byref(count))
        self.scales = []
        for i in range(count.value):
            geom = pages[i].geometry
            bounds = geom.bounds
            native_w = bounds[3] - bounds[1] if geom.rotation % 180 else bounds[2] - bounds[0]
            self.scales.append(WIDTH / (native_w * geom.unit_scale))

    def check(self, status):
        if status:
            raise RuntimeError(f'{status}: {self.error.message.decode("utf-8", errors="replace")}')

    def close(self):
        self.engine.exr_fixed_free(self.ptr)
        self.engine.tail_document()

    def render(self, page, mode='full', trace=False, checksum=False, timed=False):
        self.engine.tail_begin(MODES.index(mode), trace)
        bitmap = Bitmap()
        if timed:
            start = time.perf_counter_ns()
        status = self.engine.exr_fixed_render(self.ptr, page - 1, self.scales[page - 1], None,
                                              c.byref(bitmap), c.byref(self.error))
        elapsed = (time.perf_counter_ns() - start) / 1e6 if timed else None
        try:
            self.check(status)
            assert bitmap.width == WIDTH and bitmap.channels == 4 and bitmap.pixels
            result = {}
            if timed:
                result['ms'] = elapsed
            if checksum:
                result['sha256'] = hash_active_rgba(bitmap)[0]
            if trace:
                p, i = PageTrace(), ImageTrace()
                self.engine.tail_read(c.byref(p), c.byref(i))
                result['page_trace'] = {name: getattr(p, name) for name, _ in p._fields_}
                result['images'] = {name: getattr(i, name) for name, _ in i._fields_}
            return result
        finally:
            self.engine.exr_bitmap_free(c.byref(bitmap))


def idle():
    busy = wait_idle(15, 900)
    if busy is None:
        raise SystemExit('CPU idle gate timed out at 15%. Retry the capture.')
    return round(busy, 2)


def ablate(engine, pdf, fixture, label, selected):
    randomizer = random.Random(20261118)
    ranked = fixture['ranked_pages']
    tail = [r['page'] for r in ranked if r['p50_ms'] > min(fixture['archived_p95_ms'], fixture['page_p95_ms'])]
    # Compare like-for-like slides and sample the two other hotspot cohorts from #250.
    targets = sorted(set(selected) if selected else set(tail) | set(CASES[label]) | {1, 2, 5, 10})
    if any(page < 1 or page > len(ranked) for page in targets):
        raise ValueError('Page outside fixture')
    doc = Document(engine, pdf)
    try:
        assert len(doc.scales) == len(ranked)
        hashes = {r['page']: r['rgba_sha256'] for r in ranked}
        results = {}
        gate = idle()
        for page in targets:
            full = doc.render(page, checksum=True)['sha256']
            assert full == hashes[page], (label, page, full, hashes[page])
            samples = {mode: [] for mode in MODES}
            changed = {}
            order = []
            for rep in range(7):
                modes = list(MODES)
                randomizer.shuffle(modes)
                order.append(modes)
                for mode in modes:
                    data = doc.render(page, mode, checksum=(rep == 6), timed=True)
                    samples[mode].append(data['ms'])
                    if rep == 6:
                        changed[mode] = data['sha256'] != full
            assert not changed['full']
            results[page] = {'cpu_percent': gate, 'samples_ms': samples, 'pixels_changed': changed, 'order': order}
            print(f'{label} p{page} ablation', flush=True)
        return results
    finally:
        doc.close()


def cache(engine, pdf, rounds, ranked):
    doc = Document(engine, pdf)
    try:
        results = []
        expected = {r['page']: r['rgba_sha256'] for r in ranked}
        assert len(doc.scales) == len(expected)
        gate = idle()
        for iteration in range(rounds):
            pages = []
            for page in range(1, len(doc.scales) + 1):
                row = doc.render(page, trace=True, checksum=(iteration == 0))
                if iteration == 0:
                    assert row.pop('sha256') == expected[page], (pdf.stem, page)
                pages.append(row)
            results.append({'cpu_percent': gate if iteration == 0 else None, 'pages': pages})
            print(f'{pdf.stem} cache round {iteration + 1}/{rounds}', flush=True)
        return results
    finally:
        doc.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    binary = ap.add_mutually_exclusive_group()
    binary.add_argument('--build', type=Path)
    binary.add_argument('--dll', type=Path)
    ap.add_argument('--scratch', type=Path, default=ROOT / 'build/perf')
    ap.add_argument('--out', type=Path, default=HERE)
    ap.add_argument('--mode', choices=('rank', 'ablate', 'cache'), required=True)
    ap.add_argument('--case', choices=CASES, action='append')
    ap.add_argument('--page', type=int, action='append', help='Restrict ablation to given pages of one fixture')
    ap.add_argument('--rounds', type=int, default=6)
    ap.add_argument('--cache-mib', type=int, default=64)
    args = ap.parse_args()
    if args.page and (args.mode != 'ablate' or len(args.case or []) != 1):
        ap.error('--page requires ablate and exactly one --case')
    args.out.mkdir(parents=True, exist_ok=True)
    rank = archived()
    if args.mode == 'rank':
        save(args.out / 'ranked-pages.json', rank)
        return
    if not (args.build or args.dll):
        ap.error('ablate and cache require --build or --dll')
    args.scratch.mkdir(parents=True, exist_ok=True)
    dll = (args.dll or build_probe(args.build, args.scratch)).resolve()
    os.environ['EXR_PDF_IMAGE_CACHE_BYTES'] = str(args.cache_mib * 1024**2)
    os.environ['EXR_PDF_IMAGE_PROFILE'] = '1' if args.mode == 'cache' else '0'
    os.environ.pop('EXR_BUFFER_POOL', None)
    with os.add_dll_directory(str(dll.parent)):
        engine = c.CDLL(str(dll))
        for label in args.case or CASES:
            pdf = ROOT / f'tests/fixtures/pdf-large/{label}.pdf'
            data = (ablate(engine, pdf, rank[label], label, args.page) if args.mode == 'ablate'
                    else cache(engine, pdf, args.rounds, rank[label]['ranked_pages']))
            suffix = f'cache-{args.cache_mib}mib' if args.mode == 'cache' else 'ablation'
            result = {'probe_sha256': digest_file(dll), 'fixture_sha256': digest_file(pdf), 'data': data}
            if args.mode == 'cache':
                payload = json.dumps(result, separators=(',', ':')).encode()
                (args.out / f'{label}-{suffix}.json.gz').write_bytes(gzip.compress(payload, mtime=0))
            else:
                save(args.out / f'{label}-{suffix}.json', result)


if __name__ == '__main__':
    main()
