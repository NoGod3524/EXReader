#!/usr/bin/env python3
"""Optional development oracle against an externally built libhyphen. Not an SDK dependency."""
# SPDX-License-Identifier: MIT
import argparse
import ctypes as c
import hashlib
import json
import random
import subprocess
import tempfile
from pathlib import Path
from check_hyphen_reference import Error, Input


def literal_oracle(rules,word):
    """Slow literal overlay, independent of the native packed tries and work queue.
    This oracle's generated input uses ASCII letters/anchors plus separator cases.
    """
    levels=[{'patterns':[],'no':[]},{'patterns':[],'no':[]}];level=0;explicit=False
    for line in rules.splitlines():
        line=line.split('%',1)[0].split('#',1)[0].strip()
        fields=line.split();
        if not fields or fields[0]=='UTF-8':continue
        if fields[0]=='NEXTLEVEL': level=1;explicit=True;continue
        if fields[0] in ('LEFTHYPHENMIN','RIGHTHYPHENMIN','COMPOUNDLEFTHYPHENMIN','COMPOUNDRIGHTHYPHENMIN'):
            levels[level][fields[0]]=int(fields[1]);continue
        if fields[0]=='NOHYPHEN': levels[level]['no']=fields[1].split(',') if len(fields)>1 else [];continue
        letters='';weights=[0]
        for cp in line:
            if cp.isascii() and cp.isdigit():weights[-1]=int(cp)
            else:letters+=cp;weights.append(0)
        levels[level]['patterns'].append((letters,weights))
    if not explicit:
        ordinary=levels[0];levels=[{'patterns':[(cp,[1,1]) for cp in "-'–’"], 'no':list("-'–’"),
            'LEFTHYPHENMIN':ordinary.get('LEFTHYPHENMIN',0),'RIGHTHYPHENMIN':ordinary.get('RIGHTHYPHENMIN',0),
            'COMPOUNDLEFTHYPHENMIN':ordinary.get('COMPOUNDLEFTHYPHENMIN',0) or ordinary.get('LEFTHYPHENMIN',0) or 3,
            'COMPOUNDRIGHTHYPHENMIN':ordinary.get('COMPOUNDRIGHTHYPHENMIN',0) or ordinary.get('RIGHTHYPHENMIN',0) or 3},ordinary]
    root=levels[0];left=root.get('LEFTHYPHENMIN',0) or 2;right=root.get('RIGHTHYPHENMIN',0) or 2
    cl=root.get('COMPOUNDLEFTHYPHENMIN',0);cr=root.get('COMPOUNDRIGHTHYPHENMIN',0);points=set();leaves=[];raw_candidates=set()
    def overlay(part,patterns):
        text='.'+part+'.';scores=[0]*(len(text)+1)
        for letters,weights in patterns:
            for start in range(len(text)-len(letters)+1):
                if text.startswith(letters,start):
                    for i,value in enumerate(weights):scores[start+i]=max(scores[start+i],value)
        return {i for i in range(1,len(part)) if scores[i+1]&1}
    def visit(first,last):
        cuts=sorted(first+i for i in overlay(word[first:last],root['patterns']))
        if cuts:
            points.update(cuts);raw_candidates.update(cuts);edges=[first,*cuts,last]
            for lo,hi in zip(edges,edges[1:]):visit(lo,hi)
        else:
            leaves.append((first,last))
            raw=overlay(word[first:last],levels[1]['patterns']);raw_candidates.update(first+i for i in raw)
            points.update(first+i for i in raw if (first==0 or i>=cl) and (last==len(word) or last-first-i>=cr))
    visit(0,len(word))
    points={i for i in points if i>=left and len(word)-i>=right}
    forbidden=set()
    for sequence in root['no']:
        for start in range(len(word)-len(sequence)+1):
            if word.startswith(sequence,start):forbidden.update((start,start+len(sequence)))
    points-=forbidden
    # libhyphen's right-minimum loop excludes vector index 0: short ASCII
    # leaves may retain their first boundary even when it violates crhmin.
    allowed_reference_extras={lo+1 for lo,hi in leaves if hi<len(word) and hi-lo>1 and hi-lo-1<cr
        and lo+1 in raw_candidates and word[lo].isascii() and lo+1>=left and len(word)-(lo+1)>=right and lo+1 not in forbidden}
    if 1 in raw_candidates and word[0].isascii() and left<=1 and len(word)-1<right and 1 not in forbidden: allowed_reference_extras.add(1)
    return {len(word[:i].encode()) for i in points},{len(word[:i].encode()) for i in allowed_reference_extras}

def prepared(rules,perl,preprocessor):
    """libhyphen requires its documented substring preprocessing. Merge duplicate
    rule weights first to preserve this SDK's explicit max-weight input contract.
    The native matcher and literal oracle use the unprocessed original rules.
    """
    levels=[([],{}),([],{})];level=0;explicit=False
    for line in rules.splitlines():
        line=line.split('%',1)[0].split('#',1)[0].strip()
        fields=line.split()
        if not fields or fields[0]=='UTF-8':continue
        if fields[0]=='NEXTLEVEL':level=1;explicit=True;continue
        if fields[0] in ('LEFTHYPHENMIN','RIGHTHYPHENMIN','COMPOUNDLEFTHYPHENMIN','COMPOUNDRIGHTHYPHENMIN','NOHYPHEN'):
            levels[level][0].append(line);continue
        letters='';weights=[0]
        for cp in line:
            if cp.isascii() and cp.isdigit():weights[-1]=int(cp)
            else:letters+=cp;weights.append(0)
        old=levels[level][1].get(letters,[0]*len(weights));levels[level][1][letters]=[max(a,b) for a,b in zip(weights,old)]
    result=[]
    with tempfile.TemporaryDirectory(prefix='exreader-hyphen-prepare-') as temporary:
        for index,(metadata,patterns) in enumerate(levels[:2 if explicit else 1]):
            source=Path(temporary)/'input.pat';output=Path(temporary)/'output.pat'
            lines=[''.join(str(weights[i])+cp for i,cp in enumerate(letters))+str(weights[-1]) for letters,weights in patterns.items()]
            source.write_text('\n'.join(lines)+'\n',encoding='utf-8')
            subprocess.run([str(perl),str(preprocessor.resolve()),str(source),str(output)],stdout=subprocess.DEVNULL,check=True,timeout=30)
            if index:result.append('NEXTLEVEL')
            result.extend(metadata);result.append(output.read_text(encoding='utf-8'))
    return '\n'.join(result)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('library',type=Path);p.add_argument('reference',type=Path,nargs='?')
    p.add_argument('--dictionary-dir',type=Path);p.add_argument('--output',type=Path);p.add_argument('--preprocessor',type=Path);p.add_argument('--perl',default='perl');a=p.parse_args();ptr=c.c_void_p;error=Error()
    if a.reference and not a.preprocessor:p.error('external reference requires --preprocessor')
    if a.dictionary_dir and not a.reference:p.error('--dictionary-dir requires external reference')
    native=c.CDLL(str(a.library.resolve()));ref=c.CDLL(str(a.reference.resolve())) if a.reference else None
    native.exr_hyphenator_create_patterns.argtypes=[c.POINTER(Input),c.c_size_t,c.c_size_t,ptr,c.POINTER(ptr),c.POINTER(Error)]
    native.exr_hyphenator_breaks.argtypes=[ptr,c.c_char_p,c.c_char_p,c.c_size_t,ptr,ptr,c.POINTER(Error)]
    native.exr_hyphenator_free.argtypes=[ptr]
    if ref:
        ref.hnj_hyphen_load_data.argtypes=[c.c_char_p,c.c_size_t];ref.hnj_hyphen_load_data.restype=ptr
        ref.hnj_hyphen_hyphenate3.argtypes=[ptr,c.c_char_p,c.c_int,ptr,ptr,ptr,ptr,ptr,c.c_int,c.c_int,c.c_int,c.c_int]
        ref.hnj_hyphen_free.argtypes=[ptr]
    checked=0;strict_minimum_differences=0;real_reports=[]
    def compare(rules,words):
        nonlocal checked,strict_minimum_differences
        data=('UTF-8\n'+rules+'\n').encode();buffer=c.create_string_buffer(data)
        source=Input(c.sizeof(Input),b'und',c.cast(buffer,ptr),len(data),0,0);h=ptr()
        assert native.exr_hyphenator_create_patterns(c.byref(source),1,0,None,c.byref(h),c.byref(error))==0,error.message
        reference=None
        if ref:
            reference_data=('UTF-8\n'+prepared(rules,a.perl,a.preprocessor)+'\n').encode()
            reference=ref.hnj_hyphen_load_data(reference_data,len(reference_data));assert reference
        try:
            for word in words:
                text=word.encode();actual=(c.c_ubyte*(len(text)+1))();expected=c.create_string_buffer(len(text)+5)
                assert native.exr_hyphenator_breaks(h,b'und',text,len(text),actual,None,c.byref(error))==0,error.message
                got={i for i,x in enumerate(actual) if x}
                specified,known_extras=literal_oracle(rules,word)
                assert got==specified,('literal oracle',rules,word,specified,got)
                if ref:
                    assert ref.hnj_hyphen_hyphenate3(reference,text,len(text),expected,None,None,None,None,0,0,0,0)==0
                    positions={len(word[:i+1].encode()) for i,x in enumerate(expected.raw[:len(word)]) if x&1}
                    assert not (specified-positions) and positions-specified<=known_extras,('reference',rules,word,positions,got)
                    strict_minimum_differences+=positions!=specified
                checked+=1
        finally:
            native.exr_hyphenator_free(h)
            if ref:ref.hnj_hyphen_free(reference)
    inner='\n'.join(cp+'1' for cp in 'abcdefghxy')
    for left in range(4):
        for right in range(4):
            compare(f'LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nCOMPOUNDLEFTHYPHENMIN {left}\nCOMPOUNDRIGHTHYPHENMIN {right}\nabcd1efgh\n.ab1cd.\nNEXTLEVEL\n'+inner,['abcdefgh','abcdefghabcdefgh','xabcdabcdefghy'])
    for no in ['xy','x','y','x,y','xy,ab','-']:
        compare('LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nNOHYPHEN '+no+'\nNEXTLEVEL\n'+inner,['abxycd','abxyabxycd'])
    for metadata in ['', 'LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\n', 'COMPOUNDLEFTHYPHENMIN 2\nCOMPOUNDRIGHTHYPHENMIN 3\n']:
        compare(metadata+'a1',['aaaaaaaa',"aaaa'aaaa",'aaaa-aaaa','aaaa–aaaa','aaaa’aaaa'])
    rng=random.Random(180327)
    for round in range(100):
        levels=[]
        for level in range(2):
            patterns=[]
            for _ in range(25):
                letters=''.join(rng.choice('abc') for _ in range(rng.randint(1,5)))
                if rng.randrange(3)==0: letters='.'+letters
                if rng.randrange(3)==0: letters+='.'
                patterns.append(''.join(str(rng.randrange(4))+cp for cp in letters)+str(rng.randrange(4)))
            levels.append('\n'.join(patterns))
        rules=f'LEFTHYPHENMIN {rng.randint(1,3)}\nRIGHTHYPHENMIN {rng.randint(1,3)}\nCOMPOUNDLEFTHYPHENMIN {rng.randrange(4)}\nCOMPOUNDRIGHTHYPHENMIN {rng.randrange(4)}\n'
        if round%3==0: rules+='NOHYPHEN ab,cc\n'
        rules+=levels[0]+'\nNEXTLEVEL\n'+levels[1]
        words=[''.join(rng.choice('abc') for _ in range(rng.randint(2,14))) for _ in range(100)]
        compare(rules,words)
    if a.dictionary_dir:
        samples={
            'en_US':'hyphenation dictionary international computer typography compatibility university',
            'fr':'bibliothèque lecture international extraordinaire représentation typographie université',
            'es':'biblioteca lectura internacional extraordinario representación tipografía universidad',
            'it_IT':'biblioteca lettura internazionale rappresentazione straordinario università italiano',
            'ru_RU':'библиотека чтение международный представление университет типография русский'}
        for language,sample in samples.items():
            path=a.dictionary_dir/('hyph_'+language+'.dic');data=path.read_bytes();buffer=c.create_string_buffer(data)
            source=Input(c.sizeof(Input),b'und',c.cast(buffer,ptr),len(data),0,0);h=ptr()
            assert native.exr_hyphenator_create_patterns(c.byref(source),1,0,None,c.byref(h),c.byref(error))==0,(language,error.message)
            prepared_data=('UTF-8\n'+prepared(data.decode('utf-8'),a.perl,a.preprocessor)+'\n').encode()
            reference=ref.hnj_hyphen_load_data(prepared_data,len(prepared_data));assert reference
            words=sample.split();cases=set(words)
            cases.update(left+separator+right for left in words for right in words for separator in ["-","'","–","’"])
            try:
                for word in sorted(cases):
                    text=word.encode();actual=(c.c_ubyte*(len(text)+1))();expected=c.create_string_buffer(len(text)+5)
                    assert native.exr_hyphenator_breaks(h,b'und',text,len(text),actual,None,c.byref(error))==0,error.message
                    assert ref.hnj_hyphen_hyphenate3(reference,text,len(text),expected,None,None,None,None,0,0,0,0)==0
                    positions={len(word[:i+1].encode()) for i,x in enumerate(expected.raw[:len(word)]) if x&1}
                    got={i for i,x in enumerate(actual) if x}
                    assert positions==got,(language,word,positions,got)
                real_reports.append({'language':language,'queries':len(cases),'input_sha256':hashlib.sha256(data).hexdigest(),'input_projection':[],'reference_projection':'official substring preprocessing'})
            finally:native.exr_hyphenator_free(h);ref.hnj_hyphen_free(reference)
    report={'reference':'external libhyphen plus independent literal overlay' if ref else 'independent literal overlay','seed':180327,'queries':checked,'unchanged_real_dictionaries':real_reports,'strict_minimum_reference_differences':strict_minimum_differences,
        'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest(),'reference_sha256':hashlib.sha256(a.reference.read_bytes()).hexdigest() if ref else None,
        'preprocessor_sha256':hashlib.sha256(a.preprocessor.read_bytes()).hexdigest() if ref else None,
        'reference_input':'max-merge duplicate patterns then official substring preprocessing; literal/native inputs unchanged' if ref else 'not used'}
    if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
if __name__=='__main__':main()
