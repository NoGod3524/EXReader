# SPDX-License-Identifier: MIT
"""Summarize the probe trace for vector-heavy-100 pages 1-10 (second pass of the full input)."""
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAW = Path(__file__).with_name('raw')


def parse(text):
    pages = []
    for line in text.splitlines():
        event, *fields = line.split()
        record = {}
        for field in fields:
            k, v = field.split('=')
            record[k] = float(v) if '.' in v else int(v)
        if event == 'PAGE':
            pages.append(defaultdict(list, page=record['index']))
        elif pages:
            pages[-1][event].append(record)
    return pages


def summarize(case='full'):
    pages = parse(gzip.decompress((RAW / f'probe-{case}.txt.gz').read_bytes()).decode())
    passes = len(pages) // 10
    pages = pages[-10:]  # last pass
    out = dict(case=case, passes=passes, per_page=[], totals={})
    tot = Counter()
    for p in pages:
        cls = p['CLASSES'][0]
        row = dict(page=p['page'], **{k: v for k, v in cls.items()})
        cp = p['CANVASPATH']
        row['canvas_paths'] = len(cp)
        row['canvas_compound'] = sum(r['compound'] for r in cp)
        row['canvas_fill_only'] = sum(r['flags'] == 1 for r in cp)
        row['canvas_stroke_only'] = sum(r['flags'] == 2 for r in cp)
        row['canvas_path_ms'] = sum(r['ms'] for r in cp)
        pdfpath = p['PDFPATH']
        row['pdf_paths_top'] = sum(r['depth'] == 0 for r in pdfpath)
        row['pdf_path_segs_top'] = sum(r['segs'] for r in pdfpath if r['depth'] == 0)
        scans = p['SCAN']
        row['scan_calls'] = len(scans)
        row['scan_eligible_rows'] = sum(r['rows'] for r in scans if r['eligible'])
        row['scan_rows'] = sum(r['rows'] for r in scans)
        row['scan_reused'] = sum(r['reused'] for r in scans)
        row['scan_tested'] = sum(r['tested'] for r in scans)
        row['scan_active'] = sum(r['active'] for r in scans)
        row['rect_calls'] = len(p['RECT'])
        row['rect_rows'] = sum(r['rows'] for r in p['RECT'])
        clips = p['CLIP']
        row['clips'] = len(clips)
        row['clips_identity'] = sum(r['identity'] for r in clips)
        row['clip_ms'] = sum(r['ms'] for r in clips)
        paints = p['PAINT']
        row['paint_calls'] = len(paints)
        row['paint_axial_rows'] = sum(r['axial_rows'] for r in paints)
        row['paint_generic_rows'] = sum(r['generic_rows'] for r in paints)
        row['paint_pixels'] = sum(r['pixels'] for r in paints)
        row['paint_reused'] = sum(r['reused'] for r in paints)
        masks = p['MASK']
        row['mask_builds'] = len(masks)
        row['mask_raster_ms'] = sum(r['raster_ms'] for r in masks)
        row['mask_extract_ms'] = sum(r['extract_ms'] for r in masks)
        row['mask_repeat_rows'] = sum(r['repeat_rows'] for r in masks)
        row['mask_rows'] = sum(r['rows'] for r in masks)
        raster = p['RASTER']
        row['mask_prep_ms'] = sum(r['prep_ms'] for r in raster)
        row['mask_content_ms'] = sum(r['content_ms'] for r in raster)
        row['mask_end_ms'] = sum(r['end_ms'] for r in raster)
        row['attr'] = p['ATTR']
        row['form_groups'] = len(p['FORM_GROUP'])
        out['per_page'].append(row)
        for k, v in row.items():
            if isinstance(v, (int, float)) and k != 'page':
                tot[k] += v
    out['totals'] = dict(tot)
    return out


if __name__ == '__main__':
    result = {case: summarize(case) for case in (sys.argv[1:] or ['full'])}
    (RAW / 'probe-summary.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    for case, data in result.items():
        print(case, 'passes', data['passes'])
        for k, v in sorted(data['totals'].items()):
            print(f'  {k} = {v:.3f}' if isinstance(v, float) else f'  {k} = {v}')
