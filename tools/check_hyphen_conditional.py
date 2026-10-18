#!/usr/bin/env python3
"""Independent conditional-compound oracle. External libhyphen is test-only."""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import ctypes as c
import hashlib
import json
import random
import subprocess
import tempfile
from pathlib import Path
from check_hyphen_replacements import Native


def parse(token):
    raw, sep, suffix = token.partition('/')
    letters = ''; weights = [0]; change = None
    for cp in raw:
        if cp.isascii() and cp.isdigit(): weights[-1] = int(cp)
        else: letters += cp; weights.append(0)
    if sep:
        text, first, size = suffix.split(','); before, after = text.split('=')
        first = int(first) - 1 + int(letters.startswith('.'))
        change = (first, first + int(size), before, after)
    return letters, weights, change


def literal(root, leaf, source, left=1, right=1, cl=0, cr=0, forbidden=()):
    """Brute-force matching of immutable text/source-span tuples, recursively.
    Generated spelling is indivisible when projecting back to the original word.
    ASCII is deliberate: native tests cover Unicode normalization/graphemes.
    """
    result = {}
    def overlay(text, patterns):
        word = '.' + ''.join(cp for cp, _, _ in text) + '.'
        scores = [0] * (len(word)+1); choices = [None] * len(scores)
        for letters, weights, change in patterns:
            for i in range(len(word)-len(letters)+1):
                if not word.startswith(letters, i): continue
                for k, weight in enumerate(weights):
                    candidate = (i+change[0]-1, i+change[1]-1, *change[2:]) if change and weight&1 else None
                    if weight > scores[i+k]: scores[i+k] = weight; choices[i+k] = candidate
                    elif weight&1 and weight == scores[i+k]:
                        old = choices[i+k]
                        choices[i+k] = None if old is None or candidate is None else old if old == candidate else False
        return [(i, choices[i+1]) for i in range(1, len(text)) if scores[i+1]&1]
    def visit(text, begin, end):
        edges = {0:begin, len(text):end}
        # Whole original intervals must lie exclusively to either side.
        for i in range(1, len(text)):
            hi = max(item[2] for item in text[:i]); lo = min(item[1] for item in text[i:])
            if hi == lo and begin < hi < end: edges[i] = hi
        def valid(patterns):
            rows = []
            for i, change in overlay(text, patterns):
                if i not in edges or not begin < edges[i] < end: continue
                if change:
                    a,b,before,after = change
                    change = (edges[a],edges[b],before,after) if a in edges and b in edges and edges[a]<=edges[i]<=edges[b] else False
                rows.append((i,edges[i],change))
            return rows
        cuts = valid(root)
        if cuts:
            first = begin
            for index, point, change in cuts:
                result[point] = change
                if change:
                    a,b,before,after = change
                    # Equivalent original spelling retains each source boundary.
                    child = [(cp,i,i+1) for i,cp in enumerate(source[first:point],first)] if before == source[a:point] else (
                        [(cp,i,i+1) for i,cp in enumerate(source[first:max(first,a)],first)] + [(cp,max(first,a),point) for cp in before])
                else: child = [(cp,i,i+1) for i,cp in enumerate(source[first:point],first)]
                visit(child,first,point); first = point
            visit(text[cuts[-1][0]:],first,end)
        else:
            for _, point, change in valid(leaf):
                if (begin == 0 or point-begin >= cl) and (end == len(source) or end-point >= cr): result[point] = change
    visit([(cp,i,i+1) for i,cp in enumerate(source)],0,len(source))
    for seq in forbidden:
        for i in range(len(source)-len(seq)+1):
            if source.startswith(seq,i): result.pop(i,None); result.pop(i+len(seq),None)
    return [(i,*(result[i] or (i,i,'',''))) for i in sorted(result)
            if left<=i<=len(source)-right and result[i] is not False]


class Reference:
    def __init__(self,path,preprocessor,perl):
        self.dll=c.CDLL(str(path.resolve()));self.preprocessor=preprocessor;self.perl=perl;p=c.c_void_p
        self.dll.hnj_hyphen_load_data.argtypes=[c.c_char_p,c.c_size_t];self.dll.hnj_hyphen_load_data.restype=p
        self.dll.hnj_hyphen_hyphenate3.argtypes=[p,c.c_char_p,c.c_int,p,p,p,p,p,c.c_int,c.c_int,c.c_int,c.c_int]
        self.dll.hnj_hyphen_free.argtypes=[p];self.dll.hnj_free.argtypes=[p]
    def query(self,root,leaf,word):
        result=['UTF-8','LEFTHYPHENMIN 1','RIGHTHYPHENMIN 1']
        with tempfile.TemporaryDirectory(prefix='exreader-conditional-') as temporary:
            src=Path(temporary)/'input.pat';out=Path(temporary)/'output.pat'
            for index,patterns in enumerate((root,leaf)):
                src.write_text('\n'.join(patterns)+'\n',encoding='utf-8')
                subprocess.run([self.perl,str(self.preprocessor.resolve()),str(src),str(out),'UTF-8'],stdout=subprocess.DEVNULL,check=True,timeout=30)
                if index:result.append('NEXTLEVEL')
                result.extend(out.read_text(encoding='utf-8').splitlines()[1:])
        data=('\n'.join(result)+'\n').encode();d=self.dll.hnj_hyphen_load_data(data,len(data));assert d
        p=c.c_void_p;rep=c.POINTER(p)();pos=c.POINTER(c.c_int)();cut=c.POINTER(c.c_int)();text=word.encode();output=c.create_string_buffer(len(text)+5)
        try:
            assert self.dll.hnj_hyphen_hyphenate3(d,text,len(text),output,None,c.byref(rep),c.byref(pos),c.byref(cut),0,0,0,0)==0
            rows=[]
            for i,value in enumerate(output.raw[:len(text)]):
                if not value&1:continue
                point=i+1;first=last=point;before=after=''
                if rep and rep[i]:
                    first=point-pos[i];last=first+cut[i];before,after=c.string_at(rep[i]).decode().split('=')
                rows.append((point,first,last,before,after))
            return rows
        finally:
            if rep:
                for i in range(len(text)):
                    if rep[i]:self.dll.hnj_free(rep[i])
                self.dll.hnj_free(rep)
            if pos:self.dll.hnj_free(pos)
            if cut:self.dll.hnj_free(cut)
            self.dll.hnj_hyphen_free(d)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('library',type=Path);p.add_argument('--reference',type=Path)
    p.add_argument('--preprocessor',type=Path);p.add_argument('--perl',default='perl');p.add_argument('--output',type=Path);a=p.parse_args()
    if a.reference and not a.preprocessor:p.error('--reference requires --preprocessor')
    native=Native(a.library);reference=Reference(a.reference,a.preprocessor,a.perl) if a.reference else None
    rng=random.Random(180329);queries=external=opportunities=unicode_queries=0
    def compare(root,leaf,words,cl=0,cr=0,forbidden=(),external_check=False,unicode_check=False):
        nonlocal queries,external,opportunities,unicode_queries
        metadata=f'UTF-8\nLEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nCOMPOUNDLEFTHYPHENMIN {cl}\nCOMPOUNDRIGHTHYPHENMIN {cr}\n'
        if forbidden:metadata+='NOHYPHEN '+','.join(forbidden)+'\n'
        rules=metadata+'\n'.join(root)+'\nNEXTLEVEL\n'+'\n'.join(leaf)+'\n';h=native.create(rules.encode())
        try:
            for word in words:
                expected=literal(list(map(parse,root)),list(map(parse,leaf)),word,cl=cl,cr=cr,forbidden=forbidden)
                actual=native.query(h,word);assert expected==actual,(rules,word,expected,actual)
                queries+=1;opportunities+=len(actual)
                if reference and external_check:
                    got=reference.query(root,leaf,word);assert got==expected,('libhyphen',rules,word,expected,got);external+=1
        finally:native.dll.exr_hyphenator_free(h)
        if unicode_check:
            dictionary=str.maketrans({'a':'é','b':'α','c':'𐐨','x':'ﬃ','y':'ß','z':'中'})
            original=str.maketrans({'a':'é','b':'α','c':'𐐨','x':'ﬃ','y':'ß','z':'中'})
            h=native.create(rules.translate(dictionary).encode())
            try:
                for word in words:
                    expected=literal(list(map(parse,root)),list(map(parse,leaf)),word,cl=cl,cr=cr,forbidden=forbidden)
                    offsets=[len(word[:i].translate(original).encode()) for i in range(len(word)+1)]
                    projected=[(offsets[p],offsets[s],offsets[e],b.translate(dictionary),a.translate(dictionary)) for p,s,e,b,a in expected]
                    actual=native.query(h,word.translate(original));assert projected==actual,('Unicode projection',rules,word,projected,actual)
                    unicode_queries+=1
            finally:native.dll.exr_hyphenator_free(h)
    compare(['efg1hijk/gg=h,3,2','.abcd1efgg.'],['.ab1cd.','.hi1jk.'],['abcdefghijk'],external_check=True)
    # Random whole-word boundary rewrites enable otherwise unreachable anchored
    # left-stem rules. Keep reference cases away from its minimum/depth quirks.
    for round in range(120):
        word=''.join(rng.sample('abcdefghijklmnopqrstuv',rng.randrange(10,21)))
        point=rng.randrange(5,len(word)-3);first=rng.randrange(3,point+1);last=min(len(word),point+rng.randrange(3))
        before=''.join(rng.choice('xyz') for _ in range(rng.randrange(5)));after=rng.choice(('', 'x', 'yz'))
        restored=word[:first]+before;inner=rng.randrange(1,first)
        root=['.'+word[:point]+'1'+word[point:]+'./'+before+'='+after+f',{first+1},{last-first}',
              '.'+restored[:inner]+'1'+restored[inner:]+'.']
        leaf=['.'+word[point:point+2]+'1'+word[point+2:]+'.']
        # libhyphen treats cut=0 as a default extent and clamps a restored left
        # stem to word_size-1. Those cases retain our explicit source semantics.
        compare(root,leaf,[word],external_check=round<50 and last>first and len(restored)<len(word))
        # Nested spellings, overlap/conflict resolution and generated interiors.
        root+=['.'+restored[:inner-1]+'3'+restored[inner-1:]+'./x=,1,'+str(len(restored))] if inner>2 else []
        for cl,cr in ((0,0),(1,2),(3,1)):
            compare(root,leaf,[word,word+word,'a'+word],cl,cr,('ab',) if round%3==0 else ())
    for round in range(120):
        levels=[]
        for level in range(2):
            tokens=[]
            for _ in range(16):
                word=''.join(rng.choice('abc') for _ in range(rng.randrange(2,6)));point=rng.randrange(1,len(word))
                raw=('.' if rng.randrange(3)==0 else '')+word[:point]+str(rng.choice((1,3,5)))+word[point:]+('.' if rng.randrange(3)==0 else '')
                if rng.randrange(3):
                    first=rng.randrange(point+1);last=rng.randrange(point,len(word)+1)
                    raw+='/'+''.join(rng.choice('abc') for _ in range(rng.randrange(4)))+'='+rng.choice(('','a','bc'))+f',{first+1},{last-first}'
                tokens.append(raw)
            levels.append(tokens)
        for _ in range(30):
            word=''.join(rng.choice('abc') for _ in range(rng.randrange(2,20)))
            compare(*levels,[word],cl=round%3,cr=round%4,unicode_check=round%3==0)
    report={'seed':180329,'generated_queries':queries,'unicode_queries':unicode_queries,'opportunities':opportunities,'external_queries':external,
            'external_scope':'ASCII anchored conditional left stems; cut>0 and restored stem shorter than parent; documented substring preprocessing',
            'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest()}
    if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
