# SPDX-License-Identifier: MIT
import argparse
import json
import os
from pathlib import Path
import shutil
from contract import BINARIES,REPORTS,RAW,SANITIZER,digest,validate,validate_files
assert os.environ.get('GITHUB_ACTIONS')=='true','Actions only'
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
manifest=dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],runner_os=os.environ['RUNNER_OS'],accepted=False,files={},problems=[])
try:
 sources={};suffix='.exe' if os.name=='nt' else ''
 for name in ['composition-c','composition-cxx','reviewed-flow']:
  sources[name]=Path('build/fresh/build')/(name+suffix);sources[name+'-relocated']=Path('build/relocated/build')/(name+suffix)
 suites=json.loads((out/'original/suites.json').read_text())
 for suite in suites['suites']:sources.update({name:Path(path) for name,path in suite['binaries'].items()})
 (out/'binaries').mkdir(exist_ok=True)
 for name in BINARIES:shutil.copyfile(sources[name],out/'binaries'/name)
 for path in REPORTS+RAW+['binaries/'+name for name in BINARIES]+(SANITIZER if os.environ['RUNNER_OS']=='Linux' else []):
  data=(out/path).read_bytes();manifest['files'][path]=dict(bytes=len(data),sha256=digest(data))
 docs,binary_hashes=validate_files(manifest,lambda path:(out/path).read_bytes())
 manifest['named_results']=validate(docs,binary_hashes,manifest['source_sha'],manifest['run_id'],manifest['attempt'],manifest['runner_os']);manifest['accepted']=True
except Exception as e:manifest['problems'].append(str(e))
(out/'bundle.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest));raise SystemExit(0 if manifest['accepted'] else 1)
