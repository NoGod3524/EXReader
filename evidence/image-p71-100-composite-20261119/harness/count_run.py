# SPDX-License-Identifier: MIT
"""Per-page predicate counts from the counter-only probe DLL; checks probe bytes == base bytes.

usage: count_run.py <base dll> <probe dll> <out json> [first last]
Untimed; counters only. Each page is rendered once per DLL.
"""
import ctypes as c, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
from paired_sweep import NativeDocument, digest_file
base, probe, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
first, last = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (71, 100)
pdf = ROOT/'tests/fixtures/pdf-large/image-heavy-100.pdf'
A, B = NativeDocument(base, pdf, 1200), NativeDocument(probe, pdf, 1200)
lib = B.library; buf = (c.c_ulonglong*32)()
lib.img_count_read.argtypes = [c.POINTER(c.c_ulonglong)]
names = {0:'s3_calls',1:'s3_alpha255',2:'s3_cov255',3:'s3_P3',4:'s3_dest_opaque',5:'s3_rgba_target',6:'s3_zero_alpha_sum',
         8:'s4_pixels',9:'s4_P4',10:'s4_runs',11:'s4_runs_unclipped_opaque',12:'s4_pixels_unclipped_opaque',13:'rows_clipped',
         14:'rows_unclipped',15:'axis_flat_calls',16:'axis_regular_calls',17:'s4_dest_opaque',18:'s4_rgba_target',19:'s3_cov0_skipped',20:'s4_alpha0',21:'s3_alpha0',22:'s4_identity_blend',23:'s3_identity_blend',25:'overdraw_writes',26:'dead_stores_replaced_by_opaque',27:'untracked_other_target'}
pages, total, mismatched, pixels = [], {k: 0 for k in names.values()}, [], 0
for p in range(first-1, last):
    _, ra = A.render(p, True, None)
    lib.img_count_reset(); _, rb = B.render(p, True, None); lib.img_count_read(buf)
    row = {'page': p+1, **{v: buf[k] for k, v in names.items()}}
    pages.append(row); pixels += len(ra)*1200
    for k in total: total[k] += row[k]
    if ra != rb: mismatched.append(p+1)
    print(row, flush=True)
A.close(); B.close()
res = {'pdf_sha256': digest_file(pdf), 'base_sha256': digest_file(base), 'probe_sha256': digest_file(probe),
       'pages': [first, last], 'width': 1200, 'compared_pixels': pixels, 'mismatched_pages': mismatched,
       'total': total, 'per_page': pages}
out.write_text(json.dumps(res, indent=1)+'\n'); print(json.dumps(total, indent=1), 'mismatched', mismatched)
