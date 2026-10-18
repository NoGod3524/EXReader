#!/usr/bin/env python3
"""Check original-byte dictionary breaks across official canonical-equivalent forms.
Uses pinned Unicode 17 fixture/data and Python standard library; no system Unicode oracle.
"""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import generate_unicode as shared
from check_hyphen_reference import Error, Input


def main():
    root=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('library',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--cache-dir',type=Path,default=root/'build/unicode-cache');a=p.parse_args()
    data=shared.source_data('UnicodeData.txt',a.cache_dir,root/'tests/fixtures/unicode',False)
    categories={};ranges=[];first=None
    for line in data.decode().splitlines():
        f=line.split(';');cp=int(f[0],16);categories[cp]=f[2]
        if f[1].endswith(', First>'): first=cp
        elif f[1].endswith(', Last>'): ranges.append((first,cp,f[2]));first=None
    def word_scalar(cp):
        category=categories.get(cp)
        if category is None: category=next((v for lo,hi,v in ranges if lo<=cp<=hi),'')
        return category.startswith(('L','M'))
    fixture=root/'tests/fixtures/unicode/NormalizationTest.txt';raw=fixture.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='5019ffd530751a741900c849c0e010332f142a3612234639bd200b82138a87db'
    cases=set()
    for line in raw.decode().splitlines():
        if not line or line[0] in '#@': continue
        fields=line.split(';');forms=tuple(tuple(int(x,16) for x in f.split()) for f in fields[:3])
        if len(set(forms))==1 or not all(word_scalar(cp) for form in forms for cp in form): continue
        cases.add(forms)
    dll=c.CDLL(str(a.library.resolve()));pointer=c.c_void_p;error=Error()
    dll.exr_hyphenator_create_patterns.argtypes=[c.POINTER(Input),c.c_size_t,c.c_size_t,pointer,c.POINTER(pointer),c.POINTER(Error)]
    dll.exr_hyphenator_breaks.argtypes=[pointer,c.c_char_p,c.c_char_p,c.c_size_t,pointer,pointer,c.POINTER(Error)]
    dll.exr_hyphenator_free.argtypes=[pointer]
    count=0
    for forms in sorted(cases):
        strings=[''.join(map(chr,form)) for form in forms]
        pattern=('.'+strings[1]+'1z.').encode();buffer=c.create_string_buffer(pattern)
        source=Input(c.sizeof(Input),b'und',c.cast(buffer,pointer),len(pattern),1,1);h=pointer()
        assert dll.exr_hyphenator_create_patterns(c.byref(source),1,0,None,c.byref(h),c.byref(error))==0,error.message
        try:
            for text in strings:
                source=text.encode();word=source+b'z';out=(c.c_ubyte*(len(word)+1))()
                assert dll.exr_hyphenator_breaks(h,b'und',word,len(word),out,None,c.byref(error))==0,(text,error.message)
                actual={i for i,value in enumerate(out) if value}
                assert actual=={len(source)},(text.encode('unicode_escape'),actual,len(source))
                count+=1
        finally: dll.exr_hyphenator_free(h)
    report={'unicode_version':'17.0.0','normalization_fixture_sha256':hashlib.sha256(raw).hexdigest(),
      'canonical_word_cases':len(cases),'original_byte_break_queries':count,
      'scope':'Letter/mark c1/c2/c3 canonical forms with appended z and explicit boundary. NFC core full conformance is a separate native test.',
      'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest()}
    if a.output: a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
if __name__=='__main__': main()
