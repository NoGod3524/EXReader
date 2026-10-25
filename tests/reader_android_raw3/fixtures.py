"""Actions only: original real four-format fixtures plus the pinned genuine NUL PDF."""
import hashlib
import json
import os
from pathlib import Path
import shutil
assert os.environ.get('GITHUB_ACTIONS')=='true'
source=Path('build/android-page-theme/fixtures')
target=Path('build/android-raw3/fixtures');target.mkdir(parents=True,exist_ok=True)
manifest=json.loads((source/'manifest.json').read_text())
manifest['books']=[row for row in manifest['books'] if row['role'] in ('txt','epub','pdf','cbz')]
assert len(manifest['books'])==4
for row in manifest['books']:
    original=Path('tests/fixtures/pdf-public-text.pdf') if row['role']=='pdf' else source/row['file']
    body=original.read_bytes()
    if row['role']=='pdf':
        assert len(body)==8845 and hashlib.sha256(body).hexdigest()=='5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    shutil.copyfile(original,target/row['file'])
    row['bytes']=len(body);row['sha256']=hashlib.sha256(body).hexdigest()
(target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
