"""Actions-only installed codec test and SDK isolation evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reader_reading_state'))
from check_reading_state import sqlite_providers

assert os.environ.get('GITHUB_ACTIONS')=='true'
p=argparse.ArgumentParser()
for name in ('consumer','map','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True)
result=subprocess.run([str(a.consumer.resolve())],capture_output=True,text=True,timeout=30)
(a.output/'consumer.log').write_text(result.stdout+'\n'+result.stderr)
assert result.returncode==0 and 'no SDK linked' in result.stdout
mapping=a.map.read_text(errors='replace');providers=sqlite_providers(mapping)
assert len(providers)==1 and 'reader_catalog_sqlite' in providers[0],providers
assert not re.search(r'\bexr_(?:anchor|library|pager|fixed|publication|document)_\w+',mapping)
assert 'exr_vendor_exr_sqlite' not in mapping
report={**{k:os.environ[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]},
        'accepted':True,'sdk_symbols':False,'sqlite_providers':providers,'consumer_sha256':hashlib.sha256(a.consumer.read_bytes()).hexdigest()}
(a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
