"""Actions-only synthetic originals from frozen licensed repository fixtures."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
out = Path(sys.argv[1]); out.mkdir(parents=True)
root = Path('tests/fixtures')
names = ['sample.txt','sample.html','sample.fb2','sample.epub','sample.docx','sample.rtf','sample.mobi','pdf-public-text.pdf','comic.cbz']
manifest = []
for fmt, name in enumerate(names, 1):
    target = out / ('book.' + ['txt','html','fb2','epub','docx','rtf','mobi','pdf','cbz'][fmt-1])
    shutil.copyfile(root / name, target)
    data = target.read_bytes()
    manifest.append({'format':fmt,'name':target.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(out/'large.txt').write_bytes(b'Original export streaming line.\n' * 100000)
(out/'changed.txt').write_text('Distinct original, same untrusted title.\n',encoding='utf-8')
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
