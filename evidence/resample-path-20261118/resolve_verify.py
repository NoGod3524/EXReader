"""Serial post-rebase A/B, rejecting captures overlapping foreign jobs."""
from pathlib import Path
import json, subprocess, sys, time
import psutil

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'resolve-256'
stage = sys.argv[1]
A, B = OUT / 'main.dll', OUT / f'{stage}.dll'
events = []

def foreign(launched=()):
    process = psutil.Process()
    own = {p.pid for p in process.parents() + process.children(recursive=True)} | {process.pid} | set(launched)
    found = []
    for p in psutil.process_iter(['name']):
        if p.pid not in own and p.info['name'].lower().startswith(('python', 'gcc', 'cc1', 'ninja', 'cmake', 'ctest', 'exreader-')):
            found.append(p.pid)
    return found

def run(args):
    while True:
        while foreign():
            print('Waiting for foreign build/benchmark:', foreign(), flush=True)
            time.sleep(10)
        process = subprocess.Popen(args, cwd=ROOT)
        overlapping_pids = set()
        while process.poll() is None:
            # The child can exit between poll() and process enumeration. Keep
            # its known PID excluded even after it leaves children().
            overlapping_pids.update(foreign({process.pid}))
            time.sleep(.5)
        overlap = bool(overlapping_pids)
        events.append({'command': list(map(str, args)), 'exit': process.returncode,
                       'overlap': overlap, 'overlapping_pids': sorted(overlapping_pids)})
        (OUT / f'{stage}-events.json').write_text(json.dumps(events, indent=2))
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, args)
        if not overlap:
            return
        output = Path(args[-1])
        if output.suffix == '.json' and output.exists():
            output.rename(output.with_name(f'{output.stem}-rejected-{len(events)}.json'))
        print('Rejected overlapping capture; retrying', flush=True)

py = [sys.executable, '-X', 'utf8']
run(py + ['evidence/resample-path-20261118/interleaved_ab.py', str(A), str(B),
          'tests/fixtures/pdf-large/image-heavy-100.pdf', '1200', '71', '100', '9', str(OUT / f'{stage}-cohort.json')])
run(py + ['evidence/resample-path-20261118/gated_pairs.py', '--library-a', str(A), '--library-b', str(B),
          '--input', 'tests/fixtures/pdf-large/image-heavy-100.pdf', '--widths', '1200', '--runs', '5',
          '--repeat', '4', '--idle-timeout', '60', '--out', str(OUT / f'{stage}-paired.json')])
if stage == 'final':
    run(py + ['evidence/dense-vector-throughput-20261118/verify_pixels.py', str(A), str(B), str(OUT / 'final-pixels.json')])
    # Correctness runs serially after all timings.
    with (OUT / 'final-ctest.txt').open('w') as log:
        subprocess.run(['ctest', '--test-dir', 'build/perf', '--output-on-failure', '-j', '4'], cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
print(stage, 'verification complete', flush=True)
