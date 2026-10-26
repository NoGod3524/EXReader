"""New D18 add-only policy; no edits to any existing guard, SDK, owner or test."""
import json, os, subprocess
from common import ROOT, OUT, SEED, identity, digest, write
FILES = {
 '.github/workflows/reader-wave3-d18.yml',
 'tests/reader_wave3_d18/common.py', 'tests/reader_wave3_d18/producer.py',
 'tests/reader_wave3_d18/guard.py', 'tests/reader_wave3_d18/probe.py',
 'tests/reader_wave3_d18/observer.py', 'tests/reader_wave3_d18/run.py',
 'tests/reader_wave3_d18/verify.py',
 'tests/reader_wave3_d18/accessibility/ui/StorageActions.swift',
 'docs/reader-wave3-d18/README.md', 'HANDOFF-RESULT-D18.md',
 'docs/reader-wave3-d18/ROUND1.md','docs/reader-wave3-d18/ROUND2.md','docs/reader-wave3-d18/ROUND3.md'
}
def permitted(rows):
    assert all(state=='A' and path in FILES for state,path in rows), rows
report=identity()
subprocess.run(['git','merge-base','--is-ancestor',SEED,report['source_sha']],check=True)
rows=[line.split('\t') for line in subprocess.check_output(['git','diff','--name-status',SEED,'HEAD'], text=True).splitlines()]
permitted(rows)
negative=[]
for path in ['CMakeLists.txt','include/exr/base.h','examples/apple/HostModel.swift','apps/reader/store/001_catalog.sql','tests/apple_host/make_xcodeproj.rb','tests/reader_dot_wave2/d11/apple/ActionFocusTests.swift','tests/reader_wave3_d18/extra.py']:
    try: permitted([['M',path]])
    except AssertionError: negative.append(path)
    else: raise AssertionError('scope negative accepted')
report.update(seed=SEED, sdk_source='edddc463c06ed5731195cdb8f06b2df6dff7699e', changed=rows,
    files={p:digest(ROOT/p) for _,p in rows}, negative_controls=negative,
    frozen_scope='Every existing seed file remains byte-identical; seed is a candidate, not accepted production BASE',
    source_preflight=True, runtime_accepted=False)
write(OUT/'guard.json',report); print(json.dumps(report),flush=True)
