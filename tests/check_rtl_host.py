#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual WM_KEYDOWN left/right through the offscreen native host driver."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name in ('arabic-journey', 'arabic-library', 'hebrew-journey', 'progression-ltr'):
        folder = (args.output / name).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        source = ROOT / 'tests/fixtures/rtl' / (name + '.epub')
        title = ('hebrew-journey' if name == 'progression-ltr' else name) + ' (original test book)'
        forward, back = ('right', 'left') if name == 'progression-ltr' else ('left', 'right')
        steps = '\n'.join([f'import|{source}', f'open|{title}', 'check|page|1', 'state|initial',
                            f'probe_key|{forward}', 'check|page|2', 'state|after_forward',
                            f'probe_key|{back}', 'check|page|1', 'state|after_back', 'quit', ''])
        script = folder / 'steps.txt'
        script.write_text(steps, encoding='utf-8')
        completed = subprocess.run([str(args.binary.resolve()), '--offscreen', '--drive', str(script),
                                    '--evidence', str(folder), '--data', str(folder / 'data'),
                                    '--font', 'C:/Windows/Fonts/arial.ttf'], timeout=90,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        log = (folder / 'drive.log').read_text(encoding='utf-8')
        passed = '\tFAIL\t' not in log and any(row.startswith('DONE\t') and '\tPASS\t' in row for row in log.splitlines())
        results.append(dict(book=name, next_key=forward, return_code=completed.returncode, passed=passed))
        print(name, passed, flush=True)
    (args.output / 'result.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    return 0 if all(row['passed'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
