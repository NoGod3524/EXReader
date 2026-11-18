# SPDX-License-Identifier: MIT
"""Apply the same fail-closed idle gate to each PDF.js sweep."""
import argparse
import gzip
import json
import subprocess
from pathlib import Path

from capture import ROOT, core_times, gate

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('node_deps', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--core', type=int)
    args = parser.parse_args()
    pdf = ROOT / 'tests/fixtures/pdf-large/image-heavy-100.pdf'
    with subprocess.Popen(['node', str(HERE / 'pdfjs_scopes.cjs'), str(args.node_deps.resolve()),
                           str(pdf), str(args.runs)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, text=True) as child:
        sample = None
        activity = []
        if args.core is not None:
            import psutil
            process = psutil.Process(child.pid)
            process.cpu_affinity([args.core])

            def child_seconds():
                t = process.cpu_times()
                return t.user+t.system

        for line in child.stdout:
            if line.strip() == '@gate':
                busy = gate(args.core)
                print(f'PDF.js gate {busy:.2f}%', flush=True)
                if args.core is not None:
                    start, start_process = core_times(args.core), child_seconds()
                child.stdin.write(f'{busy}\n')
                child.stdin.flush()
            elif line.strip() == '@done':
                accept = True
                if args.core is not None:
                    idle, total = (e-s for e,s in zip(core_times(args.core), start))
                    background = (max(0, 100*(total-idle-child_seconds()+start_process)/total)
                                  if total > 0 else None)
                    accept = background is not None and background <= 15
                    activity.append({'core_background': background, 'accepted': accept})
                    if not accept:
                        print('PDF.js pinned CPU gate closed during capture. Retrying.', flush=True)
                child.stdin.write('ok\n' if accept else 'retry\n')
                child.stdin.flush()
            elif line.startswith('@{'):
                sample = json.loads(line[1:])
                child.stdin.close()
        if child.wait() or sample is None:
            raise RuntimeError('PDF.js capture failed')
    sample.update(core=args.core, post_gate=activity)
    args.out.write_bytes(gzip.compress(json.dumps(sample).encode(), mtime=0))


if __name__ == '__main__':
    main()
