# SPDX-License-Identifier: MIT
"""Peak working set per arm: each 1200 px fixture in fresh processes, AB, BA, AB."""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
from paired_sweep import digest_file

a, b, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
tmp = Path(__file__).resolve().parents[1]/'_work'/'rss-raw'
tmp.mkdir(parents=True, exist_ok=True)
res = {'dll_sha256': {'A': digest_file(a), 'B': digest_file(b)}, 'working_sets': {}}
for name, pages in (('image-heavy-100', 100), ('real-mixed-120', 120), ('vector-heavy-100', 100)):
    res['working_sets'][name] = []
    for order in ('AB', 'BA', 'AB'):
        row = {}
        for tag in order:
            dll = a if tag == 'A' else b
            o = tmp/f'{name}-{len(res["working_sets"][name])}-{tag}.json'
            subprocess.run([sys.executable, str(ROOT/'tools/bench_real_doc.py'), '--library', str(dll), '--input',
                            str(ROOT/f'tests/fixtures/pdf-large/{name}.pdf'), '--expect-pages', str(pages),
                            '--child-width', '1200', '--runs', '1', '--child-out', str(o)], check=True)
            row[tag] = json.loads(o.read_text())['peak_rss_bytes']
        res['working_sets'][name].append(row)
        print(name, order, row, flush=True)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(res, indent=1)+'\n')
