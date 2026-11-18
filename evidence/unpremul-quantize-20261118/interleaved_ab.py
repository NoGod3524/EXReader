"""In-process A/B: both DLLs loaded in one process, alternating AB/BA on every page render.

Copied from evidence/dense-vector-throughput-20261118/interleaved_ab.py. Each
page is rendered back to back by A and B (order alternating per page and
round), so other lanes' load lands on both arms of a pair. Reports per-page
median and minimum for each arm and the median of per-pair (B-A) differences.

usage: python -X utf8 interleaved_ab.py A.dll B.dll fixture.pdf width reps out.json
"""
import ctypes as c, json, os, statistics, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from benchmark_pdf_blend import Bitmap, Error
from benchmark_pdf_rect import Page
from bench_engine import cpu_busy_percent, cpu_times


def load(path):
    os.add_dll_directory(str(Path(path).resolve().parent))
    e = c.CDLL(str(Path(path).resolve()))
    e.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    e.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    e.exr_fixed_pages.restype = c.POINTER(Page)
    e.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
    e.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    return e


a_path, b_path, pdf, width, reps, out = sys.argv[1:7]
width, reps = int(width), int(reps)
arms = {}
for tag, path in (('A', a_path), ('B', b_path)):
    e = load(path); d = c.c_void_p(); err = Error()
    assert e.exr_fixed_open(os.fsencode(pdf), None, c.byref(d), c.byref(err)) == 0
    arms[tag] = (e, d, err)
n = c.c_size_t(); pages = arms['A'][0].exr_fixed_pages(arms['A'][1], c.byref(n))
scales = {}
for i in range(n.value):
    g = pages[i].geometry; bw = g.bounds[3] - g.bounds[1] if g.rotation % 180 else g.bounds[2] - g.bounds[0]
    scales[i] = width / (bw * g.unit_scale)


def render(tag, i):
    e, d, err = arms[tag]; b = Bitmap(); t = time.perf_counter_ns()
    assert e.exr_fixed_render(d, i, scales[i], None, c.byref(b), c.byref(err)) == 0
    dt = (time.perf_counter_ns() - t) / 1e6; e.exr_bitmap_free(c.byref(b)); return dt


for i in scales: render('A', i); render('B', i)  # cold
before = cpu_times()
samples = {i: {'A': [], 'B': []} for i in scales}
for r in range(reps):
    for i in scales:
        for tag in (('A', 'B') if (r + i) % 2 == 0 else ('B', 'A')):
            samples[i][tag].append(render(tag, i))
machine_busy = cpu_busy_percent(before, cpu_times())
rows = []
for i, s in samples.items():
    diffs = [b - a for a, b in zip(s['A'], s['B'])]
    rows.append({'page': i + 1, 'a_p50_ms': statistics.median(s['A']), 'b_p50_ms': statistics.median(s['B']),
                 'a_min_ms': min(s['A']), 'b_min_ms': min(s['B']), 'paired_delta_ms': statistics.median(diffs)})
sums = {k: sum(r[k] for r in rows) for k in ('a_p50_ms', 'b_p50_ms', 'a_min_ms', 'b_min_ms', 'paired_delta_ms')}
res = {'pdf': pdf, 'width': width, 'pages': n.value, 'reps': reps, 'machine_busy_percent': round(machine_busy, 2),
       **{'sum_' + k: v for k, v in sums.items()},
       'paired_delta_percent': 100 * sums['paired_delta_ms'] / sums['a_p50_ms'],
       'min_delta_percent': 100 * (sums['b_min_ms'] - sums['a_min_ms']) / sums['a_min_ms'], 'per_page': rows}
Path(out).write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
print(f'{Path(pdf).name}@{width} x{reps} busy={machine_busy:.0f}%: A p50 {sums["a_p50_ms"]:.1f} B {sums["b_p50_ms"]:.1f} ms; '
      f'paired {res["paired_delta_percent"]:+.2f}%; min A {sums["a_min_ms"]:.1f} B {sums["b_min_ms"]:.1f} ({res["min_delta_percent"]:+.2f}%)', flush=True)
