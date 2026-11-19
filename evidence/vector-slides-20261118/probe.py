# SPDX-License-Identifier: MIT
"""Record diagnostic events and verify probe pixels against the production DLL."""
import gzip
import json
import os
import subprocess
import sys
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path

from ablate import HERE, NODE, ROOT, RAW, WORK, close, response, sha

PAGES = 10


def pages_in(trace):
    pages = []
    for line in trace.splitlines():
        event, *fields = line.split()
        record = {k: float(v) if '.' in v else int(v)
                  for k, v in (field.split('=') for field in fields)}
        if event == 'PAGE':
            pages.append(defaultdict(list, page=record['index']))
        else:
            pages[-1][event].append(record)
    return pages


def run(main, probe):
    pdf = ROOT / 'tests/fixtures/pdf-large/vector-heavy-100.pdf'
    env = {k: v for k, v in os.environ.items() if not k.startswith('EXR_') and k != 'NODE_OPTIONS'}
    output = {'fixture': sha(pdf), 'main': sha(main), 'probe': sha(probe), 'cases': {}}
    for case in ('full', 'shading-page', 'shading', 'softmask', 'path', 'clip'):
        edited = pdf if case in ('full', 'group') else WORK / f'{pdf.stem}-{case}.pdf'
        trace = WORK / f'probe-{case}.txt'
        with ExitStack() as stack:
            def worker(command, stderr=subprocess.DEVNULL, settings=env):
                child = subprocess.Popen(command, env=settings, stderr=stderr, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, text=True, bufsize=1)
                stack.callback(close, child)
                assert response(child) == 'ready'
                return child

            def request(child, page, flag):
                child.stdin.write(f'{page} {flag}\n')
                child.stdin.flush()
                return json.loads(response(child))

            log = stack.enter_context(trace.open('w', encoding='utf-8'))
            native_cmd = [sys.executable, '-B', str(HERE / 'worker.py')]
            control = worker([*native_cmd, str(main), str(edited)])
            probe_env = env | {'EXR_ATTRIBUTION_SKIP': 'group'} if case == 'group' else env
            diagnostic = worker([*native_cmd, str(probe), str(edited), '--trace'], log, probe_env)
            js = worker(['node', str(HERE / 'worker.cjs'), str(NODE), str(edited)])
            js_pages = [request(js, page, -1) for page in range(PAGES)]
            passes = 2 if case == 'full' else 1
            for sweep in range(passes):
                for page in range(PAGES):
                    pair = (control, diagnostic) if (sweep + page) % 2 == 0 else (diagnostic, control)
                    a, b = [request(arm, page, 1)[1] for arm in pair]
                    assert a == b, (case, sweep, page + 1)
        trace_text = trace.read_text(encoding='utf-8')
        output['cases'][case] = {'pdfjs': js_pages, 'native': pages_in(trace_text), 'passes': passes}
        (RAW / f'probe-{case}.txt.gz').write_bytes(gzip.compress(trace_text.encode(), mtime=0))
        print(case, 'verified', passes * PAGES, 'page hashes', flush=True)
    (RAW / 'runtime-audit.json.gz').write_bytes(gzip.compress(json.dumps(output).encode(), mtime=0))


if __name__ == '__main__':
    run(*(Path(arg).resolve() for arg in sys.argv[1:]))
