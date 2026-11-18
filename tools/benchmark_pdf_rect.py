#!/usr/bin/env python3
"""Local PDF rectangle benchmark and exhaustive active-RGBA comparison (stdlib only)."""
# SPDX-License-Identifier: MIT
import argparse
import ctypes as c
import gzip
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import statistics
import subprocess
import sys
import time
import zlib

from benchmark_pdf_blend import Bitmap, Error


class Geometry(c.Structure):
    _fields_ = [('bounds', c.c_double * 4), ('unit_scale', c.c_double),
                ('rotation', c.c_uint), ('y_down', c.c_uint)]


class Page(c.Structure):
    _fields_ = [('id', c.c_char_p), ('label', c.c_char_p), ('geometry', Geometry)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def percentiles(values):
    ordered = sorted(values)
    return {'p50_ms': statistics.median(ordered),
            'p95_ms': ordered[math.ceil(.95 * len(ordered)) - 1],
            'max_ms': ordered[-1]}


def process_memory_bytes():
    """Return (working_set_bytes, peak_working_set_bytes) for the current process."""
    if os.name == 'nt':
        class PROCESS_MEMORY_COUNTERS(c.Structure):
            _fields_ = [
                ('cb', c.c_ulong),
                ('PageFaultCount', c.c_ulong),
                ('PeakWorkingSetSize', c.c_size_t),
                ('WorkingSetSize', c.c_size_t),
                ('QuotaPeakPagedPoolUsage', c.c_size_t),
                ('QuotaPagedPoolUsage', c.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', c.c_size_t),
                ('QuotaNonPagedPoolUsage', c.c_size_t),
                ('PagefileUsage', c.c_size_t),
                ('PeakPagefileUsage', c.c_size_t),
            ]
        pmc = PROCESS_MEMORY_COUNTERS(cb=c.sizeof(PROCESS_MEMORY_COUNTERS))
        fn = getattr(c.windll.psapi, 'GetProcessMemoryInfo', None) or c.windll.kernel32.K32GetProcessMemoryInfo
        fn.argtypes = [c.c_void_p, c.POINTER(PROCESS_MEMORY_COUNTERS), c.c_ulong]
        fn.restype = c.c_int
        handle = c.c_void_p(c.windll.kernel32.GetCurrentProcess())
        if fn(handle, c.byref(pmc), pmc.cb):
            return int(pmc.WorkingSetSize), int(pmc.PeakWorkingSetSize)
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        return peak, peak
    except Exception:
        return 0, 0


def capture(args):
    # Each width runs in its own process, avoiding DLL search/cache interactions.
    directory = os.add_dll_directory(str(args.library.parent)) if os.name == 'nt' else None
    engine = c.CDLL(str(args.library))
    engine.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    engine.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    engine.exr_fixed_pages.restype = c.POINTER(Page)
    engine.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p,
                                      c.POINTER(Bitmap), c.POINTER(Error)]
    engine.exr_bitmap_write_png.argtypes = [c.POINTER(Bitmap), c.c_char_p, c.POINTER(Error)]
    engine.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    engine.exr_fixed_free.argtypes = [c.c_void_p]
    error = Error()

    def check(status):
        if status:
            raise RuntimeError(f'{status}: {error.message.decode("utf-8", errors="replace")}')

    document = c.c_void_p()
    open_times = []
    for iteration in range(args.runs):
        started = time.perf_counter_ns()
        check(engine.exr_fixed_open(str(args.input).encode('utf-8'), None, c.byref(document), c.byref(error)))
        open_times.append((time.perf_counter_ns() - started) / 1e6)
        if iteration != args.runs - 1:
            engine.exr_fixed_free(document)
            document = c.c_void_p()
    result = {'width': args.child, 'open_ms': statistics.median(open_times),
              'open_ms_samples': open_times, 'rounds': [], 'pages': []}
    try:
        count = c.c_size_t()
        pages = engine.exr_fixed_pages(document, c.byref(count))
        if not pages or count.value != args.expect_pages:
            raise ValueError(f'Expected {args.expect_pages} pages, found {count.value}')
        result['page_count'] = count.value
        for index in range(count.value):
            geometry = pages[index].geometry
            bounds = geometry.bounds
            native_width = bounds[3] - bounds[1] if geometry.rotation % 180 else bounds[2] - bounds[0]
            scale = args.child / (native_width * geometry.unit_scale)
            result['pages'].append({'page': index + 1, 'scale': scale, 'render_ms': []})
        # One complete warmup round, followed by five measured rounds.
        for iteration in range(args.runs + 1):
            times = []
            for page in result['pages']:
                bitmap = Bitmap()
                started = time.perf_counter_ns()
                status = engine.exr_fixed_render(document, page['page'] - 1, page['scale'], None,
                                                 c.byref(bitmap), c.byref(error))
                elapsed = (time.perf_counter_ns() - started) / 1e6
                try:
                    check(status)
                    if bitmap.width != args.child or bitmap.channels != 4 or not bitmap.pixels:
                        raise ValueError(f'Unexpected bitmap: {bitmap.width}x{bitmap.height}/{bitmap.channels}')
                    # Copy/hash/PNG encoding/freeing are outside the render timer.
                    row = bitmap.width * 4
                    pixels = b''.join(c.string_at(bitmap.pixels + y * bitmap.stride, row)
                                      for y in range(bitmap.height))
                    signature = hashlib.sha256(pixels).hexdigest()
                    if iteration == 0:
                        rss_now, rss_peak = process_memory_bytes()
                        page.update(dimensions=[bitmap.width, bitmap.height], rgba_sha256=signature,
                                    first_render_ms=elapsed, rss_bytes=rss_now, peak_rss_bytes=rss_peak)
                    elif signature != page['rgba_sha256']:
                        raise ValueError(f'Pixels changed between rounds on page {page["page"]}')
                    if iteration == 1:
                        stem = args.output / f'{args.child}-page-{page["page"]:03d}'
                        check(engine.exr_bitmap_write_png(c.byref(bitmap), str(stem.with_suffix('.png')).encode('utf-8'),
                                                          c.byref(error)))
                        stem.with_suffix('.rgba.zlib').write_bytes(zlib.compress(pixels))
                    if iteration:
                        page['render_ms'].append(elapsed)
                        times.append(elapsed)
                finally:
                    engine.exr_bitmap_free(c.byref(bitmap))
            if iteration:
                result['rounds'].append(times)
        for page in result['pages']:
            page.update(percentiles(page['render_ms']))
        result.update(percentiles([t for row in result['rounds'] for t in row]))
        worst = max(result['pages'], key=lambda p: p['p50_ms'])
        round_totals = [sum(row) for row in result['rounds']]
        round_wall_p50 = statistics.median(round_totals)
        _, final_peak_rss = process_memory_bytes()
        result.update({
            'worst_page': worst['page'],
            'worst_page_p50_ms': worst['p50_ms'],
            'worst_page_max_ms': max(p['max_ms'] for p in result['pages']),
            'round_wall_ms_p50': round_wall_p50,
            'throughput_pages_per_s': count.value * 1000.0 / round_wall_p50 if round_wall_p50 > 0 else 0.0,
            'peak_rss_bytes': final_peak_rss,
            'first_screen_ms': result['open_ms'] + result['pages'][0]['first_render_ms'],
        })
    finally:
        engine.exr_fixed_free(document)
        if directory:
            directory.close()
    write_json(args.output / f'{args.child}.json', result)


def compare(args):
    before = json.loads((args.before / 'summary.json').read_text(encoding='utf-8'))
    after = json.loads((args.after / 'summary.json').read_text(encoding='utf-8'))
    if before['input_sha256'] != after['input_sha256'] or before['widths'] != after['widths']:
        raise ValueError('Input PDF or widths differ')
    report = {'input_sha256': before['input_sha256'], 'pages': [], 'identical': True}
    for width in before['widths']:
        first, second = before['results'][str(width)], after['results'][str(width)]
        if first['page_count'] != second['page_count']:
            raise ValueError('Page counts differ')
        for a, b in zip(first['pages'], second['pages']):
            if a['dimensions'] != b['dimensions'] or a['page'] != b['page']:
                raise ValueError('Page dimensions or order differ')
            stem = f'{width}-page-{a["page"]:03d}'
            old = zlib.decompress((args.before / (stem + '.rgba.zlib')).read_bytes())
            new = zlib.decompress((args.after / (stem + '.rgba.zlib')).read_bytes())
            if len(old) != len(new) or len(old) != math.prod(a['dimensions']) * 4:
                raise ValueError('Invalid RGBA byte count')
            if hashlib.sha256(old).hexdigest() != a['rgba_sha256'] or hashlib.sha256(new).hexdigest() != b['rgba_sha256']:
                raise ValueError('RGBA snapshot differs from capture signature')
            differences = []
            maximum = 0
            squared = 0
            for offset in range(0, len(old), 4):
                left, right = old[offset:offset + 4], new[offset:offset + 4]
                if left != right:
                    differences.append([offset // 4 % width, offset // 4 // width, left.hex(), right.hex()])
                    deltas = [abs(x - y) for x, y in zip(left, right)]
                    maximum = max(maximum, *deltas)
                    squared += sum(d * d for d in deltas)
            item = {'width': width, 'page': a['page'], 'compared_pixels': len(old) // 4,
                    'different_pixels': len(differences), 'max_channel_delta': maximum,
                    'rgba_rmse': math.sqrt(squared / len(old)),
                    'before_rgba_sha256': hashlib.sha256(old).hexdigest(),
                    'after_rgba_sha256': hashlib.sha256(new).hexdigest()}
            if differences:
                report['identical'] = False
                item['bbox'] = [min(d[0] for d in differences), min(d[1] for d in differences),
                                max(d[0] for d in differences), max(d[1] for d in differences)]
                item['pixel_records'] = stem + '-pixels.json.gz'
                with gzip.open(args.output / item['pixel_records'], 'wt', encoding='utf-8') as handle:
                    json.dump({'columns': ['x', 'y', 'before_rgba', 'after_rgba'], 'pixels': differences}, handle)
            report['pages'].append(item)
            print(f'{stem}: {len(differences)} / {len(old) // 4} pixels differ; max delta {maximum}', flush=True)
    report['compared_pixels'] = sum(p['compared_pixels'] for p in report['pages'])
    report['different_pixels'] = sum(p['different_pixels'] for p in report['pages'])
    write_json(args.output / 'diff.json', report)
    # Nonzero exit prevents silently accepting changed coverage as identity.
    return 0 if report['identical'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    bench = commands.add_parser('capture')
    bench.add_argument('--library', type=Path, required=True)
    bench.add_argument('--input', type=Path, required=True)
    bench.add_argument('--expect-pages', type=int, required=True)
    bench.add_argument('--output', type=Path, required=True)
    bench.add_argument('--widths', type=int, nargs='+', default=[1200, 2400])
    bench.add_argument('--runs', type=int, default=5)
    bench.add_argument('--child', type=int, help=argparse.SUPPRESS)
    diff = commands.add_parser('compare')
    diff.add_argument('--before', type=Path, required=True)
    diff.add_argument('--after', type=Path, required=True)
    diff.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.command == 'compare':
        return compare(args)
    args.library, args.input = args.library.resolve(), args.input.resolve()
    if args.runs < 5 or args.expect_pages < 1 or any(not 1 <= width <= 16384 for width in args.widths):
        parser.error('At least five rounds and positive page count/widths required')
    if args.child:
        capture(args)
        return 0
    summary = {'platform': platform.platform(), 'python': sys.version,
               'input': str(args.input), 'input_sha256': digest(args.input),
               'library': str(args.library), 'library_sha256': digest(args.library),
               'script_sha256': digest(Path(__file__)), 'widths': args.widths, 'runs': args.runs,
               'clock': 'time.perf_counter_ns', 'warmup_rounds': 1,
               'scope': 'exr_fixed_render wall time including bitmap allocation; excludes PNG, hash, free; disk cache and background load uncontrolled',
               'pdfjs_reference': {'source': 'TASK-PDF-FAST-RECT.md supplied measurements, not measured by this script',
                                   'width': 1200, 'first_ms': 13, 'turn_ms': 4}, 'results': {}}
    for width in args.widths:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), 'capture', '--library', str(args.library),
                        '--input', str(args.input), '--expect-pages', str(args.expect_pages),
                        '--output', str(args.output), '--runs', str(args.runs), '--child', str(width)],
                       check=True)
        record = json.loads((args.output / f'{width}.json').read_text(encoding='utf-8'))
        summary['results'][str(width)] = record
        print(f'{width}px: open {record["open_ms"]:.6f} ms; render p50 {record["p50_ms"]:.6f} ms; p95 {record["p95_ms"]:.6f} ms', flush=True)
    write_json(args.output / 'summary.json', summary)
    return 0


if __name__ == '__main__':
    sys.exit(main())
