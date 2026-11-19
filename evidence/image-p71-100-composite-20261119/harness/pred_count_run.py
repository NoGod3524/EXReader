# SPDX-License-Identifier: MIT
"""Run pred_probe.dll over image-heavy-100 p71-100 @1200 (untimed) and verify pixel equality."""
import ctypes as c, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'evidence' / 'slides-gradient-20261118'))
from paired_sweep import NativeDocument, digest_file

base = Path(sys.argv[1]).resolve()
probe = Path(sys.argv[2]).resolve()
out = Path(sys.argv[3]).resolve()
pdf = ROOT / 'tests/fixtures/pdf-large/image-heavy-100.pdf'

A, B = NativeDocument(base, pdf, 1200), NativeDocument(probe, pdf, 1200)
lib = B.library
buf = (c.c_ulonglong * 32)()
lib.pred_read.argtypes = [c.POINTER(c.c_ulonglong)]

names = {
    0: 's3_total',
    1: 's3_opaque_fullcov',
    2: 's3_opaque_in_full_span',
    3: 's3_nonopaque_fullcov',
    4: 's3_nonopaque_in_full_span',
    5: 's3_nonopaque_repeat_color_dst',
    6: 's3_nonopaque_same_color_any_dst',
    7: 's3_partial_cov',
    8: 's4_total',
    9: 's4_opaque_fullcov',
    10: 's4_opaque_in_full_span',
    11: 's4_nonopaque_fullcov',
    12: 's4_nonopaque_in_full_span',
    13: 's4_nonopaque_repeat_dst_in_run',
    14: 's4_nonopaque_compute_in_run',
    15: 's4_nonopaque_repeat_across_runs',
    16: 's4_partial_cov',
    17: 's4_runs_opaque',
    18: 's4_runs_nonopaque',
    20: 'rows_total',
    21: 'rows_full_span_nonempty',
    22: 'rows_full_span_pixels',
    23: 'rows_total_pixels',
}

pages, total, mismatched, pixels = [], {v: 0 for v in names.values()}, [], 0
for p in range(70, 100):
    _, ra = A.render(p, True, None)
    lib.pred_reset()
    _, rb = B.render(p, True, None)
    lib.pred_read(buf)
    row = {'page': p + 1, **{v: int(buf[k]) for k, v in names.items()}}
    pages.append(row)
    pixels += len(ra) * 1200
    for k in total:
        total[k] += row[k]
    if ra != rb:
        mismatched.append(p + 1)

A.close()
B.close()

res = {
    'pdf_sha256': digest_file(pdf),
    'base_sha256': digest_file(base),
    'probe_sha256': digest_file(probe),
    'pages': [71, 100],
    'width': 1200,
    'compared_pixels': pixels,
    'mismatched_pages': mismatched,
    'total': total,
    'per_page': pages,
}
out.write_text(json.dumps(res, indent=1) + '\n')
print(json.dumps(total, indent=1))
print('mismatched:', mismatched, 'pixels:', pixels)
for pg in pages[:6]:
    print(
        f"p{pg['page']}: "
        f"s3_tot={pg['s3_total']} s3_op={pg['s3_opaque_in_full_span']} s3_rep={pg['s3_nonopaque_repeat_color_dst']} | "
        f"s4_tot={pg['s4_total']} s4_op={pg['s4_opaque_in_full_span']} "
        f"s4_rep={pg['s4_nonopaque_repeat_dst_in_run']} s4_cmp={pg['s4_nonopaque_compute_in_run']}"
    )
