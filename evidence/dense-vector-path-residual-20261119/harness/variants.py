# SPDX-License-Identifier: MIT
"""Build the omission PDFs for vector-heavy-100 pages 66-100.

Reuses the archived edit rules unchanged: evidence/twocells-attribution-20261118/variants.py
plus the fill/stroke rules from evidence/dense-vector-439-20261118/harness.patch.
Paint omissions keep path construction and end the path with 'n'; the clip edit drops
'W' and keeps its geometry. 'absent' is a byte copy of the original (identity control).
Usage: variants.py <class> ...   (writes ../_work/vector-heavy-100-<class>.pdf, ../operator-audit.json)
"""
import json, shutil, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'evidence/twocells-attribution-20261118'))
import variants as v
from pypdf import PdfReader

v.CLASSES['fill'] = (rb'(?<=\s)(?:f|B\*)(?=\s|$)', lambda m: {b'f': b'n', b'B*': b'S'}[m[0]], {b'f': b'n', b'B*': b'S'})
v.CLASSES['stroke'] = (rb'(?<=\s)(?:S|B\*)(?=\s|$)', lambda m: {b'S': b'n', b'B*': b'f*'}[m[0]], {b'S': b'n', b'B*': b'f*'})
WORK = HERE.parent / '_work'
pdf = ROOT / 'tests/fixtures/pdf-large/vector-heavy-100.pdf'
pages = range(65, 100)
WORK.mkdir(exist_ok=True)
audit_path = HERE.parent / 'operator-audit.json'
manifest = json.loads(audit_path.read_text()) if audit_path.exists() else \
    dict(fixture=v.sha(pdf), pages=[66, 100], before=v.audit(PdfReader(pdf), pages), variants={})
for name in sys.argv[1:]:
    out = WORK / f'{pdf.stem}-{name}.pdf'
    if name == 'absent':
        shutil.copyfile(pdf, out)
        manifest['variants'][name] = dict(sha256=v.sha(out), unique_page_edits=0)
        continue
    r = v.build(pdf, pages, name, out)
    manifest['variants'][name] = r
    print(name, {k: x for k, x in r.items() if k != 'after'}, flush=True)
audit_path.write_text(json.dumps(manifest, separators=(',', ':')) + '\n')
