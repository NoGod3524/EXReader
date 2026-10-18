#!/usr/bin/env python3
"""Fresh-process table layout measurements, including expensive full-height alignment."""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED, ZIP_DEFLATED
from run_benchmarks import validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary',type=Path);parser.add_argument('font',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--runs',type=int,default=3)
    parser.add_argument('--check-memory',action='store_true',help='Fail if full-height alignment adds more than 64 MiB over the fixed top-aligned case')
    args=parser.parse_args()
    if not 1<=args.runs<=20:parser.error('runs must be in 1..20')
    fixture=Path(__file__).resolve().parents[1]/'tests/fixtures/table-fragments-large-fixed.epub'
    with ZipFile(fixture) as archive:base={n:archive.read(n) for n in archive.namelist()}
    args.output.mkdir(parents=True,exist_ok=True)
    report={'platform':platform.platform(),'runs':args.runs,'binary_sha256':hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        'font_sha256':hashlib.sha256(args.font.read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'scope':'1 MiB in one cell, first 65 pages; fresh processes, sequential; disk cache and background load uncontrolled',
        'cases':{}}
    for name in ('fixed','auto','middle','bottom'):
        folder=args.output/name;folder.mkdir(exist_ok=True);files=dict(base);book=folder/'table-1048576.epub'
        if name=='auto':files['chapter.xhtml']=files['chapter.xhtml'].replace(b';table-layout:fixed',b'')
        if name in ('middle','bottom'):files['chapter.xhtml']=files['chapter.xhtml'].replace(b'<td>Peer</td>',f'<td style="vertical-align:{name}">Peer</td>'.encode())
        with ZipFile(book,'w') as archive:
            for key,data in files.items():
                info=ZipInfo(key,(2026,1,1,0,0,0));info.compress_type=ZIP_STORED if key=='mimetype' else ZIP_DEFLATED
                archive.writestr(info,data)
        records=[]
        for index in range(args.runs):
            result=subprocess.run([str(args.binary.resolve()),str(book.resolve()),str(args.font.resolve()),'--paging','--max-pages','64'],capture_output=True,timeout=120)
            if result.returncode:raise RuntimeError(result.stderr.decode('utf-8'))
            record=json.loads(result.stdout);validate(record);assert record['page_count']==65
            (folder/f'run-{index+1}.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');records.append(record)
        keys=('first_visible_total_ms','peak_rss_bytes','turn_total_p50_ms','turn_total_p95_ms','glyph_count')
        value={key:statistics.median(r[key] for r in records) for key in keys}
        value['input_sha256']=hashlib.sha256(book.read_bytes()).hexdigest();report['cases'][name]=value;print(name,value,flush=True)
    if args.check_memory:report['alignment_peak_ceiling_bytes']=report['cases']['fixed']['peak_rss_bytes']+64*1024*1024
    (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

    if args.check_memory:
        for name in ('middle','bottom'):
            if report['cases'][name]['peak_rss_bytes']>report['alignment_peak_ceiling_bytes']:
                raise RuntimeError(f'{name} alignment retained more than 64 MiB above the fixed top-aligned baseline')


if __name__=='__main__':main()
