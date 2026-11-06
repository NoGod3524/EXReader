# SPDX-License-Identifier: MIT
"""Summarize SDK line ranges and glyph baselines from check_step3.py output."""
import json
from pathlib import Path
import statistics
import sys


def percentile(values,q):
    values=sorted(values); pos=(len(values)-1)*q
    lo=int(pos); hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(pos-lo)


def summarize(paths):
    counts=[];han=[];ratios=[];margins=[];pages=set();vertical_glyphs=0
    for path in paths:
        d=json.loads(path.read_text(encoding='utf-8'))
        assert d['scale']==1 and d['display']==d['page'] and d['target_dpi']==[96]*4
        assert d['epoch']==d['frame_epoch']
        pages.add((d['part'],d['index']))
        previous=None
        text=d['text'].encode()
        for line in d['lines']:
            start,end,first,n,x,y,width,height=line
            glyphs=d['glyphs'][first:first+n]
            if not glyphs or (height if d['mode'] else width)<.9*d['page'][bool(d['mode'])]:
                continue
            if any(g[7]&(4|2048) or abs(g[6]-d['font'])>.01 for g in glyphs):
                continue
            # Count source Unicode scalars once, not glyphs, bytes or UTF-16 units.
            source=text[start-d['range'][0]:end-d['range'][0]].decode()
            counts.append(len(source));han.append(sum(0x3400<=ord(ch)<=0x9fff or 0x20000<=ord(ch)<=0x323af for ch in source))
            margins.append([d['origin'][0]+x,d['client'][0]-d['origin'][0]-x-width,
                            d['origin'][1]+y,d['client'][1]-d['origin'][1]-y-height])
            g=glyphs[0]
            if previous and g[10]==previous[10] and g[6]==previous[6]:
                ratios.append(abs(g[3 if d['mode'] else 4]-previous[3 if d['mode'] else 4])/g[6])
            previous=g
            vertical_glyphs += sum(bool(g[7]&128) for g in glyphs)
    assert len(paths)>=20 and len(pages)>=20 and counts and ratios
    return {'samples':len(paths),'distinct_pages':len(pages),'valid_lines_or_columns':len(counts),
            'count_median':statistics.median(counts),'count_p5':percentile(counts,.05),'count_p95':percentile(counts,.95),
            'han_median':statistics.median(han),'baseline_ratio':statistics.median(ratios),
            'actual_margins_min_lrtb':[min(m[i] for m in margins) for i in range(4)],
            'geometry_margins_lr':[d['origin'][0],d['client'][0]-d['origin'][0]-d['page'][0]],
            'client':d['client'],'page':d['page'],'dpi':d['dpi'],'native_window_dpi':d['actual_window_dpi'],
            'font_px':d['font'],'scale':d['scale'],'target_dpi':d['target_dpi'],'mode':d['mode'],
            'vertical_glyphs':vertical_glyphs}


def main():
    root=Path(sys.argv[1]);report={}
    for direction in ['horizontal','vertical']:
        report[direction]={label:summarize(sorted((root/direction).glob(label+'-*.json'))) for label in ['1280','2560','125','150']}
    (root/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
