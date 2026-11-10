"""Five predeclared full repetitions and one real +25% black-boy fault; no retry.

Run after refresh_baseline.py; the baseline is never changed by qualification.
Local qualification does not grant CI eligibility.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from sample import ROOT, read, write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('baseline', 'build', 'font', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--sdk-build', type=Path)
    p.add_argument('--sdk', type=Path)
    p.add_argument('--manifest', type=Path, default=ROOT / 'tools/regress/corpus.json')
    p.add_argument('--cpu', type=int)
    p.add_argument('--local', action='store_true')
    p.add_argument('--journal', type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    log = args.journal or args.output.parent / 'PERFGATE-FINAL-OUT.txt'
    records = []
    baseline = read(args.baseline)
    for number in range(1, 7):
        name = f'repeat-{number}' if number <= 5 else 'positive-25'
        folder = args.output / name
        cmd = [sys.executable, str(ROOT / 'tools/perf/sample.py'), '--output', str(folder)]
        for key in ('build', 'font', 'sdk_build', 'sdk', 'manifest', 'cpu'):
            if getattr(args, key) is not None:
                cmd += ['--' + key.replace('_', '-'), str(getattr(args, key))]
        if number == 6:
            cmd += ['--fault-book', 'black-boy']
        with (args.output / (name + '-capture.txt')).open('w', encoding='utf-8') as out:
            capture_exit = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT).returncode
        cmd = [sys.executable, str(ROOT / 'tools/perf/gate.py'), str(args.baseline), str(folder),
               '--output', str(args.output / (name + '-gate.json'))]
        # The fault is explicitly qualification evidence, never a production pass.
        if args.local or number == 6:
            cmd += ['--local']
        with (args.output / (name + '-gate.txt')).open('w', encoding='utf-8') as out:
            gate_exit = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT).returncode
        result = read(args.output / (name + '-gate.json'))
        capture = read(folder / 'capture.json') if (folder / 'capture.json').exists() else {}
        same_code = all(capture.get(k) == baseline[k] for k in ('probe_sha256', 'sdk_sha256', 'source_trees'))
        records.append({'name': name, 'capture_exit': capture_exit, 'gate_exit': gate_exit,
                        'same_code': same_code,
                        **{k: result.get(k) for k in ('status', 'worst_cycle_ratio', 'worst_wall_ratio', 'failed_books', 'invalid_evidence')}})
        write(args.output / 'results.json', records)
        with log.open('a', encoding='utf-8') as out:
            out.write(f'[{datetime.now(timezone.utc).isoformat()}] {name}: {records[-1]}\n')
        print(records[-1], flush=True)
    ok = (all(r['same_code'] for r in records) and
          all(r['capture_exit'] == 0 and r['gate_exit'] == 0 for r in records[:5]) and
          records[-1]['capture_exit'] == 0 and records[-1]['gate_exit'] == 1 and
          'black-boy' in records[-1]['failed_books'])
    positive = read(args.output / 'positive-25-gate.json')
    injection = next((b['injected_fraction'] for b in positive.get('books', []) if b['id'] == 'black-boy'), 0)
    ok = ok and .25 <= injection < .26
    write(args.output / 'qualification.json', {'passed': ok, 'local_only': args.local, 'results': records})
    return int(not ok)


if __name__ == '__main__':
    sys.exit(main())
