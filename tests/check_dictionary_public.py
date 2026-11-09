# SPDX-License-Identifier: MIT
"""Offline public-corpus acceptance. Only metadata, offsets and hashes are saved.

Usage: python -X utf8 tests/check_dictionary_public.py PROBE ENG_ZHO_IFO ENG_FRA_IFO EN_IT_IFO OUTPUT
Downloads and dictionary payloads stay outside version control. Python gzip is
an independent full-data oracle here; the engine always uses its RA block path.
"""
import bisect
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import statistics
import struct
import sys

from check_dictionary import probe


class Text(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self, value): self.parts.append(value)


def normalized(value): return re.sub(r'\s+', '', value).replace('•', '')


class Dictionary:
    def __init__(self, path):
        self.path=path;self.meta=dict(line.split('=',1) for line in path.read_text('utf8').splitlines()[1:] if '=' in line)
        idx=path.with_suffix('.idx');self.idx=idx.read_bytes() if idx.exists() else gzip.decompress(path.with_suffix('.idx.gz').read_bytes())
        self.entries=[];p=0;width=int(self.meta.get('idxoffsetbits','32'))//8
        while p<len(self.idx):
            end=self.idx.index(0,p);word=self.idx[p:end].decode();p=end+1
            offset=int.from_bytes(self.idx[p:p+width],'big');size=int.from_bytes(self.idx[p+width:p+width+4],'big');p+=width+4
            self.entries.append((word,offset,size))
        data=path.with_suffix('.dict');self.data=data.read_bytes() if data.exists() else gzip.decompress(path.with_suffix('.dict.dz').read_bytes())
        self.synonyms=[];syn=path.with_suffix('.syn')
        if syn.exists():
            raw=syn.read_bytes();p=0
            while p<len(raw):
                end=raw.index(0,p);self.synonyms.append((raw[p:end].decode(),int.from_bytes(raw[end+1:end+5],'big')));p=end+5
        self.keys=sorted((word,i) for i,(word,_,_) in enumerate(self.entries));self.words=[w for w,i in self.keys]
        assert len(self.entries)==int(self.meta['wordcount']) and len(self.idx)==int(self.meta['idxfilesize'])
        assert len(self.synonyms)==int(self.meta.get('synwordcount',0))

    def expected(self, word, prefix=False):
        at=bisect.bisect_left(self.words,word);items=[]
        while at<len(self.keys) and (self.words[at].startswith(word) if prefix else self.words[at]==word):
            items.append(self.keys[at][1]);at+=1
        return items[:32]

    def verify(self, row, expected, match):
        assert row['status']==0 and [r['entry_index'] for r in row['results']]==expected,(row['query'],expected,row)
        for r,i in zip(row['results'],expected):
            word,offset,size=self.entries[i];assert r['word']==word and r['match']==match
            raw=self.data[offset:offset+size].decode();parser=Text();parser.feed(raw)
            assert normalized(r['definition'])==normalized(''.join(parser.parts)),(word,repr(r['definition']),raw)
        return {'query':row['query'],'matches':len(expected),'correct':True,
                'definition_sha256':[hashlib.sha256(r['definition'].encode()).hexdigest() for r in row['results']]}


def main():
    exe,zh,fr,it,out=[Path(x).resolve() for x in sys.argv[1:6]];z=Dictionary(zh);f=Dictionary(fr);s=Dictionary(it)
    words=['apple','book','cat','dog','elephant','fish','garden','house','island','journey','king','love','mountain','night','ocean','paper','queen','river','school','table','university','village','water','window','year','zebra','bread','cloud','dream','flower']
    rows=probe(exe,[zh],words);exact=[z.verify(row,z.expected(q),0) for row,q in zip(rows[1:],words)]
    assert all(x['matches'] for x in exact)
    prefixes=[]
    for word in words:
        for n in range(len(word)-1,1,-1):
            q=word[:n]
            if q not in z.words and q not in prefixes:prefixes.append(q);break
        if len(prefixes)==10:break
    prefix=[z.verify(row,z.expected(q,True),1) for row,q in zip(probe(exe,[zh],prefixes)[1:],prefixes)]
    cases=[w.upper() for w in words[:5]]
    case=[z.verify(row,z.expected(q.lower()),3) for row,q in zip(probe(exe,[zh],cases)[1:],cases)]
    # Native .syn shipped by Wiktionary, not synthetic aliases. Skip names that
    # correctly hit the higher-priority exact/prefix stage.
    aliases=[]
    for alias,index in s.synonyms:
        if '\n' in alias or '\r' in alias or s.expected(alias,True):continue
        if alias not in aliases:aliases.append(alias)
        if len(aliases)==10:break
    assert len(aliases)==10
    syn=[]
    for row,q in zip(probe(exe,[it],aliases)[1:],aliases):
        expected=sorted(set(i for alias,i in s.synonyms if alias==q))[:32]
        syn.append(s.verify(row,expected,2))
    merged=probe(exe,[zh,fr],['apple'])[2];assert [r['dictionary_index'] for r in merged['results']]==[0,1]
    assert [r['dictionary'] for r in merged['results']]==[z.meta['bookname'],f.meta['bookname']]
    random_words=['apple','book','cat','dog','elephant','fish','house','love','night','zebra']
    measurements=[]
    # Separate process/open for every cold query; then 100 reads in shuffled
    # alphabetical order. No decompressed-block cache in the engine.
    for q in random_words:
        row=probe(exe,[fr],[q])[1];f.verify(row,f.expected(q),0)
        entry=f.entries[f.expected(q)[0]]
        measurements.append({'word':q,'offset':entry[1],'cold_ms':row['ms'],'blocks':row['blocks'],
            'compressed_bytes':row['compressed_bytes'],'inflated_bytes':row['inflated_bytes']})
        assert row['blocks']==1 and row['inflated_bytes']<=58315
    order=[9,0,7,2,5,1,8,3,6,4];queries=[random_words[i] for _ in range(10) for i in order]
    warm=probe(exe,[fr],queries)[1:]
    for item in measurements:item['warm_median_ms']=statistics.median(r['ms'] for r in warm if r['query']==item['word'])
    metadata=[]
    for d in (z,f,s):
        files={str(p):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in d.path.parent.glob(d.path.stem+'.*') if p.is_file()}
        metadata.append({'path':str(d.path),'ifo':d.meta,'parsed_entries':len(d.entries),'parsed_synonyms':len(d.synonyms),'files':files,
            'engine':probe(exe,[d.path],[])[0]})
    report={'metadata':metadata,'exact':exact,'prefix':prefix,'casefold':case,'synonyms':syn,'random_access':measurements,
        'multi_dictionary':{'correct':True,'groups':[r['dictionary'] for r in merged['results']]},
        'counts':{'exact':'30/30','prefix':'10/10','casefold':'5/5','synonyms':'10/10','random_access':'10/10','multi_dictionary':'2/2'},
        'oracle':'Independent Python big-endian index/syn parser + gzip + HTMLParser; no dictionary payload retained in report.'}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report['counts']));print(json.dumps(measurements,indent=2))


if __name__=='__main__':main()
