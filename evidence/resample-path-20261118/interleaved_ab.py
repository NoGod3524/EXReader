"""In-process A/B: both DLLs loaded in one process, alternating AB/BA on every page render.

usage: python -X utf8 interleaved_ab.py A.dll B.dll fixture.pdf width first last reps out.json
Reports per-page median for each arm and the median of per-pair (B-A) differences.
"""
import ctypes as c, hashlib, json, os, statistics, sys, time
import psutil
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from benchmark_pdf_blend import Bitmap, Error
from benchmark_pdf_rect import Page
from bench_engine import wait_idle


def load(path):
    os.add_dll_directory(str(Path(path).resolve().parent))
    e = c.CDLL(str(Path(path).resolve()))
    e.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    e.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    e.exr_fixed_pages.restype = c.POINTER(Page)
    e.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
    e.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    return e


a_path, b_path, pdf, width, first, last, reps, out = sys.argv[1:9]
width, first, last, reps = int(width), int(first), int(last), int(reps)
arms = {}
for tag, path in (('A', a_path), ('B', b_path)):
    e = load(path); d = c.c_void_p(); err = Error()
    assert e.exr_fixed_open(pdf.encode(), None, c.byref(d), c.byref(err)) == 0
    arms[tag] = (e, d, err)
n = c.c_size_t(); pages = arms['A'][0].exr_fixed_pages(arms['A'][1], c.byref(n))
scales = {}
for i in range(first - 1, last):
    g = pages[i].geometry; bw = g.bounds[3] - g.bounds[1] if g.rotation % 180 else g.bounds[2] - g.bounds[0]
    scales[i] = width / (bw * g.unit_scale)


def render(tag, i):
    e, d, err = arms[tag]; b = Bitmap(); t = time.perf_counter_ns()
    assert e.exr_fixed_render(d, i, scales[i], None, c.byref(b), c.byref(err)) == 0
    dt = (time.perf_counter_ns() - t) / 1e6; e.exr_bitmap_free(c.byref(b)); return dt


def foreign_benchmarks():
    ancestors = {p.pid for p in psutil.Process().parents()} | {os.getpid()}
    found = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = ' '.join(p.info['cmdline'] or [])
            if p.pid not in ancestors and (p.info['name'].lower().startswith(('python', 'gcc', 'cc1', 'ninja', 'cmake', 'ctest', 'exreader-')) or (p.info['name'].lower().startswith('node') and 'bench' in cmd)):
                found.append(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return found

def idle():
    while True:
        if foreign_benchmarks():
            print('Waiting for other benchmark processes', flush=True)
            time.sleep(10)
            continue
        value = wait_idle(15.0, 60.0)
        if value is not None and not foreign_benchmarks():
            return value

gates = []
gate = idle()
for i in scales: render('A', i); render('B', i)  # cold
overlap = threading.Event()
stop_monitor = threading.Event()
def monitor():
    while not stop_monitor.wait(.5):
        if foreign_benchmarks():
            overlap.set()
thread = threading.Thread(target=monitor, daemon=True)
thread.start()
samples = {i: {'A': [], 'B': []} for i in scales}
r = 0
while r < reps:
    gates.append(idle())
    overlap.clear()
    for i in scales:
        for tag in (('A', 'B') if (r + i) % 2 == 0 else ('B', 'A')):
            samples[i][tag].append(render(tag, i))
    if overlap.is_set() or foreign_benchmarks():
        for sample in samples.values():
            sample['A'].pop(); sample['B'].pop()
        print('Rejected overlapping sweep', flush=True)
        continue
    r += 1
stop_monitor.set()
thread.join()
rows = []
for i, s in samples.items():
    diffs = [b - a for a, b in zip(s['A'], s['B'])]
    rows.append({'page': i + 1, 'a_p50_ms': statistics.median(s['A']), 'b_p50_ms': statistics.median(s['B']),
                 'paired_delta_ms': statistics.median(diffs), 'raw_A_ms': s['A'], 'raw_B_ms': s['B']})
sa = sum(r['a_p50_ms'] for r in rows); sb = sum(r['b_p50_ms'] for r in rows); sd = sum(r['paired_delta_ms'] for r in rows)
res = {'pdf': pdf, 'width': width, 'pages': [first, last], 'reps': reps, 'idle_gate': gate, 'sweep_idle_cpu_percent': gates,
       'library_a_sha256': hashlib.sha256(Path(a_path).read_bytes()).hexdigest(),
       'library_b_sha256': hashlib.sha256(Path(b_path).read_bytes()).hexdigest(),
       'pdf_sha256': hashlib.sha256(Path(pdf).read_bytes()).hexdigest(),
       'pair_order': 'AB if (zero_based_sweep + zero_based_page) % 2 == 0 else BA',
       'sum_a_p50_ms': sa, 'sum_b_p50_ms': sb, 'sum_paired_delta_ms': sd, 'per_page': rows}
Path(out).write_text(json.dumps(res, indent=1), encoding='utf-8')
print(f'{Path(pdf).name}@{width} p{first}-{last}: A {sa:.2f} B {sb:.2f} ms ({100*(sb-sa)/sa:+.2f}%), paired delta {sd:+.3f} ms ({100*sd/sa:+.2f}%)')
