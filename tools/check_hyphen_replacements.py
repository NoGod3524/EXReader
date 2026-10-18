#!/usr/bin/env python3
"""Independent discretionary-rule oracle; optional external Pyphen data stays outside the SDK."""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import ctypes as c
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from check_hyphen_reference import Error, Input

class Break(c.Structure):
    _fields_=[('point',c.c_size_t),('start',c.c_size_t),('end',c.c_size_t),
      ('before',c.c_char_p),('after',c.c_char_p),('before_size',c.c_size_t),('after_size',c.c_size_t)]


def literal(rules,word):
    """Brute-force literal matching and associative max/ambiguity reduction.
    Generated input is ASCII and contains no compound segmentation directives.
    """
    scores=[0]*(len(word)+1);choices=[None]*(len(word)+1);text='.'+word+'.'
    for token in rules.split():
        raw,sep,suffix=token.partition('/');letters='';weights=[0]
        for cp in raw:
            if cp.isdigit(): weights[-1]=int(cp)
            else: letters+=cp;weights.append(0)
        change=None
        if sep:
            parts=suffix.split(',');before,after=parts[0].split('=')
            base=int(letters.startswith('.'));first=base+int(parts[1])-1;last=first+int(parts[2])
            point=next(i for i in range(first,last+1) if weights[i]&1)
            change=(point,first,last,before,after)
        for start in range(len(text)-len(letters)+1):
            if not text.startswith(letters,start):continue
            for k,value in enumerate(weights):
                point=start+k-1
                if not 0<point<len(word) or value<scores[point]:continue
                candidate=(start+change[1]-1,start+change[2]-1,*change[3:]) if change and k==change[0] else None
                if value>scores[point]:scores[point]=value;choices[point]=candidate
                elif value&1:
                    old=choices[point]
                    if candidate is None or old is None:choices[point]=None
                    elif old is False or old!=candidate:choices[point]=False
    return [(i,*(choices[i] or (i,i,'',''))) for i,value in enumerate(scores) if value&1 and choices[i] is not False]


class Native:
    def __init__(self,path):
        self.dll=c.CDLL(str(path.resolve()));self.error=Error();p=c.c_void_p
        self.dll.exr_hyphenator_create_patterns.argtypes=[c.POINTER(Input),c.c_size_t,c.c_size_t,p,c.POINTER(p),c.POINTER(Error)]
        self.dll.exr_hyphenator_free.argtypes=[p]
        self.dll.exr_hyphenator_memory_size.argtypes=[p];self.dll.exr_hyphenator_memory_size.restype=c.c_size_t
        self.dll.exr_hyphenator_query.argtypes=[p,c.c_char_p,c.c_char_p,c.c_size_t,p,c.POINTER(p),c.POINTER(Error)]
        self.dll.exr_hyphenation_breaks.argtypes=[p,c.POINTER(c.c_size_t)];self.dll.exr_hyphenation_breaks.restype=c.POINTER(Break)
        self.dll.exr_hyphenation_free.argtypes=[p]
        self.dll.exr_hyphenator_breaks.argtypes=[p,c.c_char_p,c.c_char_p,c.c_size_t,p,p,c.POINTER(Error)]
    def create(self,data,left=1,right=1):
        buffer=c.create_string_buffer(data);source=Input(c.sizeof(Input),b'und',c.cast(buffer,c.c_void_p),len(data),left,right);h=c.c_void_p()
        assert self.dll.exr_hyphenator_create_patterns(c.byref(source),1,0,None,c.byref(h),c.byref(self.error))==0,self.error.message
        return h
    def query(self,h,word):
        data=word.encode();result=c.c_void_p()
        assert self.dll.exr_hyphenator_query(h,b'und',data,len(data),None,c.byref(result),c.byref(self.error))==0,self.error.message
        try:
            count=c.c_size_t();items=self.dll.exr_hyphenation_breaks(result,c.byref(count))
            rows=[(x.point,x.start,x.end,x.before[:x.before_size].decode(),x.after[:x.after_size].decode()) for x in items[:count.value]]
        finally:self.dll.exr_hyphenation_free(result)
        bitmap=(c.c_ubyte*(len(data)+1))()
        assert self.dll.exr_hyphenator_breaks(h,b'und',data,len(data),bitmap,None,c.byref(self.error))==0,self.error.message
        ordinary={point for point,first,last,before,after in rows if point==first==last and not before and not after}
        assert {i for i,value in enumerate(bitmap) if value}==ordinary,('bitmap lost substitution semantics',word,rows)
        return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('library',type=Path);p.add_argument('--oracle-dir',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    native=Native(a.library);rng=random.Random(180328);queries=0;rewrites=0
    for round in range(100):
        tokens=[]
        for index in range(20):
            letters=''.join(rng.choice('abc') for _ in range(rng.randint(2,5)));point=rng.randrange(1,len(letters));weight=rng.choice((1,3,5))
            anchored=rng.randrange(5)==0;raw=('.' if anchored else '')+letters[:point]+str(weight)+letters[point:]+('.' if anchored else '')
            if rng.randrange(3):
                first=rng.randrange(point+1);last=rng.randrange(point,len(letters)+1)
                before=''.join(rng.choice('xy') for _ in range(rng.randrange(4)));after=''.join(rng.choice('xy') for _ in range(rng.randrange(4)))
                token=f'{raw}/{before}={after},{first+1},{last-first}'
                tokens.append(token)
                if index%4==0: tokens.append(raw if index%8 else token.replace('/','/z',1))
            else:tokens.append(raw)
        rules='\n'.join(tokens);h=native.create(('UTF-8\n'+rules).encode())
        try:
            for _ in range(50):
                word=''.join(rng.choice('abc') for _ in range(rng.randint(2,16)))
                expected=literal(rules,word);actual=native.query(h,word)
                assert actual==expected,(rules,word,expected,actual)
                queries+=1;rewrites+=sum(point!=first or point!=last or bool(before) or bool(after) for point,first,last,before,after in actual)
        finally:native.dll.exr_hyphenator_free(h)
    report={'reference':'independent literal overlay','seed':180328,'generated_queries':queries,'generated_replacement_opportunities':rewrites,'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest()}
    if a.oracle_dir:
        sys.path.insert(0,str(a.oracle_dir));import pyphen
        root=Path(pyphen.__file__).parent/'dictionaries'
        invalid=root/'hyph_hu_HU.dic';invalid_data=invalid.read_bytes()
        try:unexpected=native.create(invalid_data,0,0)
        except AssertionError:
            rejected_offset=invalid_data.index('.mas5száz8s3zok1ni/sz=3,1,1,14'.encode())
            assert native.error.code==5 and native.error.message.startswith(f'Pattern at byte {rejected_offset}:'.encode())
            assert b'Invalid discretionary range number' in native.error.message
        else:native.dll.exr_hyphenator_free(unexpected);raise AssertionError('malformed raw dictionary accepted')
        report['rejected_external_input']={'language':'hu_HU','input_sha256':hashlib.sha256(invalid_data).hexdigest(),
          'status':'EXR_FORMAT','first_rejected_rule':'.mas5száz8s3zok1ni/sz=3,1,1,14',
          'reason':'extra range argument; file also contains multiple odd rewrite points and adjacent weights'}
        path=root/'hyph_ca.dic';data=path.read_bytes();text=data.decode('utf-8');h=native.create(data,0,0)
        words=set('paral·lel col·lecció intel·ligent novel·la mil·lenni paraŀlel aŀl col·legi català lectura extraordinari'.split())
        keys=[]
        for line in text.splitlines():
            if line.startswith(('%','#')) or ' ' in line or line=='UTF-8' or line=='NEXTLEVEL':continue
            key=re.sub(r'[0-9.]','',line.split('/')[0])
            if key.isalpha() and 2<=len(key)<=30:keys.append(key)
        words.update(rng.choice(keys)+rng.choice(keys) for _ in range(3000))
        oracle=pyphen.Pyphen(filename=path,left=1,right=1,cache=False);matches=0;nonstandard=0
        try:
            for word in sorted(words):
                expected=[]
                for point in oracle.positions(word):
                    pos=int(point);first=last=pos;before=after=''
                    if point.data:
                        replacement,index,cut=point.data;lo=pos+index;hi=lo+cut
                        if lo<=pos<=hi: first,last=lo,hi;before,after=replacement.split('=')
                    expected.append((len(word[:pos].encode()),len(word[:first].encode()),len(word[:last].encode()),before,after))
                actual=native.query(h,word)
                assert actual==expected,('raw Catalan dictionary',word,expected,actual)
                matches+=1;nonstandard+=sum(point!=first or point!=last or bool(before) or bool(after) for point,first,last,before,after in actual)
            report['real_dictionary']={'reference':'Pyphen '+pyphen.__version__,'language':'ca','queries':matches,'replacement_opportunities':nonstandard,
              'input_sha256':hashlib.sha256(data).hexdigest(),'input_projection':[],
              'native_payload_bytes':native.dll.exr_hyphenator_memory_size(h)}
        finally:native.dll.exr_hyphenator_free(h)
    if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
if __name__=='__main__':main()
