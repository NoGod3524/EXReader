# SPDX-License-Identifier: MIT
"""Summarize admitted timing sweeps. Sweep zero is untimed warmup and parity."""
import argparse
import gzip
import json
import statistics as st
from pathlib import Path


def load(path):
    with gzip.open(path, 'rt') as stream:
        return json.load(stream)


def comparison(sweeps, first, last):
    pages = [str(i) for i in range(first, last+1)]
    a, b = [[sum(sweep[side][p]['ns'] for p in pages)/1e6 for sweep in sweeps]
            for side in (0, 1)]
    changes = [(y/x-1)*100 for x, y in zip(a, b)]
    return {
        'a_sweep_ms': a, 'b_sweep_ms': b,
        'a_sum_page_p50_ms': sum(st.median(s[0][p]['ns'] for s in sweeps) for p in pages)/1e6,
        'b_sum_page_p50_ms': sum(st.median(s[1][p]['ns'] for s in sweeps) for p in pages)/1e6,
        'a_call_p50_ms': st.median(s[0][p]['ns'] for s in sweeps for p in pages)/1e6,
        'b_call_p50_ms': st.median(s[1][p]['ns'] for s in sweeps for p in pages)/1e6,
        'median_paired_percent': st.median(changes), 'paired_percent': changes,
        'faster_sweeps': sum(y < x for x, y in zip(a, b)),
    }


def native_scopes(sweeps):
    rows = []
    for sweep in sweeps:
        probes = [page['probe'] for page in sweep[1].values()]
        images = [row for probe in probes for row in probe[1:]]
        assert len(images) == 90 and sum(i[32] for i in images) == 48
        assert all(i[20] and i[23] == 0 and i[31] and i[11] == 1 for i in images)
        row = {
            'clip_callback_ms': sum(p[0][1] for p in probes)/1e6,
            'image_load_ms': sum(p[0][7] for p in probes)/1e6,
            'image_draw_ms': sum(i[0] for i in images)/1e6,
        }
        assert sum(p[0][10] for p in probes) == 90
        for name, masked in [('masked', 1), ('unmasked', 0)]:
            subset = [i for i in images if i[32] == masked]
            for metric, indexes in (('draw_ms', (0,)), ('setup_ms', (2,)), ('row_prep_ms', (3,)),
                                    ('sampled_color_ms', (4,)), ('sampled_mask_ms', (5,)),
                                    ('sampled_resolve_blend_ms', (6,))):
                row[f'{name}_{metric}'] = sum(i[k] for i in subset for k in indexes)/1e6
            for metric, index in (('sampled_color_calls', 13), ('sampled_mask_calls', 14),
                                  ('sampled_pixels', 17), ('prepared_rows', 12)):
                row[f'{name}_{metric}'] = sum(i[index] for i in subset)
        rows.append(row)
    return {'sweeps': rows, 'medians': {key: st.median(r[key] for r in rows) for key in rows[0]}}


def pdfjs_scopes(sweeps):
    rows = []
    for sweep in sweeps:
        pages = list(sweep[1].values())
        images = [i for p in pages for i in p['images']]
        assert len(images) == 90 and sum(i['kind'] == 3 for i in images) == 48
        row = {'clip_callback_ms': sum(sum(p['clip']) for p in pages)/1e6}
        for name, kind in [('masked', 3), ('unmasked', 2)]:
            subset = [i for i in images if i['kind'] == kind]
            assert len(subset) == (48 if kind == 3 else 42)
            for key in ('total_ns', 'preparation_ns', 'scale_ns', 'draw_ns', 'compose_restore_ns'):
                row[f'{name}_{key[:-3]}_ms'] = sum(i[key] for i in subset)/1e6
        rows.append(row)
    return {'sweeps': rows, 'medians': {key: st.median(r[key] for r in rows) for key in rows[0]}}


def flat_scopes(sweeps):
    rows = []
    for sweep in sweeps:
        pairs = [(a, b) for page in sweep[0]
                 for a, b in zip(sweep[0][page]['probe'][1:], sweep[1][page]['probe'][1:], strict=True)]
        assert len(pairs) == 90 and all(a[18:] == b[18:] for a, b in pairs)
        row = {}
        for name, masked in [('masked', 1), ('unmasked', 0)]:
            for tag, arm in [('a', 0), ('b', 1)]:
                row[f'{name}_{tag}_draw_ms'] = sum(pair[arm][0] for pair in pairs
                                                   if pair[arm][32] == masked)/1e6
            row[f'{name}_saved_ms'] = row[f'{name}_a_draw_ms'] - row[f'{name}_b_draw_ms']
        rows.append(row)
    return {'sweeps': rows, 'medians': {key: st.median(r[key] for r in rows) for key in rows[0]}}


def main(directory):
    summary = {}
    for path in sorted(directory.glob('*.json.gz')):
        if not path.name.startswith(('diagnostic-', 'production-')):
            continue
        data = load(path)
        sweeps = data['sweeps'][1:]
        pages = list(map(int, sweeps[0][0]))
        first, last = min(pages), max(pages)
        cohorts = [(str(first)+'–'+str(last), first, last)]
        if 'heavy' in path.name:
            cohorts += [(label, a, b) for label, a, b in
                        [('slides', 1, 10), ('deck', 11, 40), ('word', 41, 60),
                         ('image-only', 61, 70), ('multi-image', 71, 100)]]
        entry = {name: comparison(sweeps, a, b) for name, a, b in cohorts}
        if path.name.startswith(('diagnostic-scopes', 'diagnostic-sampled')):
            entry['scopes'] = native_scopes(sweeps)
        if path.name.startswith('diagnostic-pdfjs'):
            entry['scopes'] = pdfjs_scopes(sweeps)
        if path.name.startswith('diagnostic-flat'):
            entry['scopes'] = flat_scopes(sweeps)
        summary[path.name.removesuffix('.json.gz')] = entry
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(main(args.directory), indent=2))
