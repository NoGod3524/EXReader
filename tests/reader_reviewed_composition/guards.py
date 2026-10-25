# SPDX-License-Identifier: MIT
"""Actions-only immutable ordinary-merge boundary guard."""
import json
import importlib.util
import os
import re
import subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
START='e4356a6e13223469fdf3b2f3d5171a6e99ab10a6'
MERGE='b143a861ef951a90c99e9c136cec47395aa700d2'
DELIVERIES={
 'cloud-import':'0d07d23bf53cd288de7a0af152d48553c18be241',
 'bulk-organization':'757249aaed9a1dc6be981354f6af97e813233f04',
 'link-policy':'4175e1de8e61ebc68dc4a1313e32408a4956f1c7',
 'jump-history':'561208ede9e85263c98e9563470349c7fa39ccb5',
 'keyboard-actions':'74804bbfff63fdc65d3e07037a8138cefff1cf75',
 'book-information':'723cd5e7f9849fe050f2159a9f3a125848cdbec4',
 'sync-status-view':'0bcb4d06bbeab6dd844954b19ee979e4bede50bd',
 'account-profiles':'a0746156b37db7cd750fb805899a616ef2c6a80f'}
def git(*a):return subprocess.check_output(['git',*a],text=True).strip()
assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
for sha in [START,MERGE,*DELIVERIES.values()]:subprocess.run(['git','merge-base','--is-ancestor',sha,'HEAD'],check=True)
for module,sha in DELIVERIES.items():
 assert git('rev-parse','HEAD:apps/reader/'+module)==git('rev-parse',sha+':apps/reader/'+module),module
for folder in ('apps','examples','extras'):
 assert git('rev-parse','HEAD:'+folder)==git('rev-parse',MERGE+':'+folder),folder
REVIEW_BASE='386b2cdf5071ccde299c04f5941eaee69c9b77bd'
G1_COMMON='a826a65c9c66e43620eff61b49cb79f941a3c953'
subprocess.run(['git','merge-base','--is-ancestor',REVIEW_BASE,'HEAD'],check=True)
for module,test in [('thumbnails','reader_thumbnails'),('reading-commands','reader_reading_commands'),
                    ('annotation-view','reader_annotation_view'),('annotation-export','reader_annotation_export'),
                    ('local-downloads','reader_local_downloads')]:
 for path in ['apps/reader/'+module,'tests/'+test]:
  assert git('rev-parse','HEAD:'+path)==git('rev-parse',REVIEW_BASE+':'+path)==git('rev-parse',G1_COMMON+':'+path),path
assert git('rev-parse','HEAD:tests/reader_g1_integration')==git('rev-parse',G1_COMMON+':tests/reader_g1_integration')
paths=git('diff','--name-only',MERGE,'HEAD').splitlines()
allowed=('tests/reader_reviewed_composition/', '.github/workflows/reader-reviewed-composition.yml','docs/READER-REVIEWED-COMPOSITION.md','docs/validation/reader-reviewed-composition.json')
assert all(p.startswith(allowed[0]) or p in allowed[1:] for p in paths),paths
chain=git('rev-list','--first-parent',START+'..'+MERGE).splitlines()
assert len(chain)==8
assert [git('rev-parse',sha+'^2') for sha in reversed(chain)]==list(DELIVERIES.values())
assert all(len(git('show','-s','--format=%P',sha).split())==2 for sha in chain)
# Reuse the original adapter guard's exact semantic rules and negative controls.
# Its standalone path allowlist is replaced only by the stricter T05 merge/tree
# boundary above; production source rules still run on this actual checkout.
spec=importlib.util.spec_from_file_location('cloud_guard',Path('tests/reader_webdav_import/check_guards.py'))
cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud)
cloud_controls=cloud.selftest();cloud_sources=sorted(p for p in Path('apps/reader/cloud-import').rglob('*') if p.suffix in ('.c','.h'));assert len(cloud_sources)>=2
joined=''
for path in cloud_sources:
 text=path.read_text(encoding='utf-8');joined+=text
 assert not [p for p in cloud.FORBIDDEN if re.search(p,text) and not (p=='Authorization' and path.suffix=='.h')],str(path)
assert all(re.search(pattern,joined) for pattern,_ in cloud.BOUNDARY)
assert 'EXR_SIDELOAD_STREAM_LIMIT' in joined and 'EXR_SIDELOAD_MEMORY_LIMIT' in joined
p=Path('build/composition/source-guard.json');p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],start=START,merge_point=MERGE,deliveries=DELIVERIES,merge_chain=list(reversed(chain)),paths=paths,cloud_adapter_source_guard=True,cloud_source_controls=cloud_controls,accepted=True),indent=2)+'\n')
print(p.read_text())
