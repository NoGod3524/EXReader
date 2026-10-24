# SPDX-License-Identifier: MIT
"""Actions-only export from the public SDK into private immutable files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser()
    for name in ('consumer', 'fixtures', 'output'): p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = a.output.resolve(); out.mkdir(parents=True)
    done = subprocess.run([str(a.consumer.resolve()), str(a.fixtures.resolve()), str(out / 'work')],
                          capture_output=True, text=True, encoding='utf-8', timeout=90)
    (out / 'consumer.log').write_text(done.stdout + '\n' + done.stderr, encoding='utf-8')
    print(done.stdout); print(done.stderr); assert done.returncode == 0, 'original export consumer refused'
    report = json.loads(done.stdout.splitlines()[-1])
    assert report['accepted'] is True and report['count'] == 14 and len(set(report['checks'])) == 14
    manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
    originals = {}
    for role in ('txt', 'epub', 'pdf', 'cbz'):
        entry = manifest[role]; exported = out / 'work' / ('导出-' + entry['file'])
        data = exported.read_bytes()
        assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256']
        originals[role] = entry
    report.update(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  consumer_sha256=hashlib.sha256(a.consumer.read_bytes()).hexdigest(), originals=originals,
                  sdk_changed=False, schema_changed=False, host_ui_accepted=False, webdav_roundtrip_accepted=False)
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8'); print(json.dumps(report))


if __name__ == '__main__': main()
