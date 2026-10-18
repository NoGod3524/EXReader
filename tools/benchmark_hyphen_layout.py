#!/usr/bin/env python3
"""Fresh-process enabled/disabled pagination measurements; dictionaries stay external.
Example: python tools/benchmark_hyphen_layout.py BENCHMARK FONT OUTPUT --dictionary FILE --language en-US --drop-compound-minima
The projection flag removes only COMPOUND*HYPHENMIN metadata, not compound patterns.
"""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED, ZIP_DEFLATED
from run_benchmarks import make_epub, validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary',type=Path);parser.add_argument('font',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--dictionary',type=Path,required=True);parser.add_argument('--language',required=True)
    parser.add_argument('--drop-compound-minima',action='store_true')
    parser.add_argument('--runs',type=int,default=3);args=parser.parse_args()
    if not 1<=args.runs<=20: parser.error('runs must be in 1..20')
    data=args.dictionary.read_bytes();patterns=data;removed=[]
    if args.drop_compound_minima:
        lines=data.decode('utf-8').splitlines()
        removed=[x for x in lines if x.startswith(('COMPOUNDLEFTHYPHENMIN ', 'COMPOUNDRIGHTHYPHENMIN '))]
        patterns=('\n'.join(x for x in lines if x not in removed)+'\n').encode()
    args.output.mkdir(parents=True,exist_ok=True);book=args.output/'hyphen-1048576.epub'
    make_epub(book,1,1048576,True)
    with ZipFile(book) as archive: files={n:archive.read(n) for n in archive.namelist()}
    # Input language must select the supplied dictionary, including regional tags.
    from xml.sax.saxutils import escape
    files['OPS/package.opf']=files['OPS/package.opf'].replace(b'<dc:language>en</dc:language>',
        ('<dc:language>'+escape(args.language)+'</dc:language>').encode())
    # A single large chapter, explicit opt-in, unchanged between the two modes.
    content=files['OPS/c0.xhtml'].replace(b'<body>',b'<body style="hyphens:auto">')
    content=content.replace(b'<p>',b'<p style="width:360px">')
    files['OPS/c0.xhtml']=content
    with ZipFile(book,'w') as archive:
        for name,value in files.items():
            info=ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=ZIP_STORED if name=='mimetype' else ZIP_DEFLATED
            info.external_attr=0o100644<<16;archive.writestr(info,value)
    report={'platform':platform.platform(),'runs_per_case':args.runs,'disk_cache':'uncontrolled',
      'font_sha256':hashlib.sha256(args.font.read_bytes()).hexdigest(),
      'binary_sha256':hashlib.sha256(args.binary.read_bytes()).hexdigest(),
      'input_sha256':hashlib.sha256(book.read_bytes()).hexdigest(),'dictionary_language':args.language,
      'dictionary_sha256':hashlib.sha256(data).hexdigest(),'portable_sha256':hashlib.sha256(patterns).hexdigest(),
      'removed_metadata':removed,'scope':'Same 1 MiB text-only EPUB, first 65 pages; dictionary construction included in first-visible time. File read from stdin excluded.','cases':{}}
    for enabled in (False,True):
        records=[];name='enabled' if enabled else 'disabled'
        for index in range(args.runs):
            command=[str(args.binary.resolve()),str(book.resolve()),str(args.font.resolve()),'--paging','--max-pages','64']
            if enabled: command+=['--hyphens',args.language]
            result=subprocess.run(command,input=patterns if enabled else None,capture_output=True,timeout=120)
            if result.returncode: raise RuntimeError(result.stderr.decode('utf-8'))
            record=json.loads(result.stdout);validate(record)
            assert record['hyphenation_enabled']==enabled and bool(record['generated_glyph_count'])==enabled
            (args.output/f'{name}-{index+1}.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
            records.append(record)
        keys=('first_visible_total_ms','peak_rss_bytes','turn_total_p50_ms','turn_total_p95_ms','hyphen_dictionary_load_ms','hyphen_dictionary_payload_bytes','generated_glyph_count')
        report['cases'][name]={key:statistics.median(x[key] for x in records) for key in keys}
        print(name,report['cases'][name])
    (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': main()
