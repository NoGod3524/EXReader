#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""XML parser + independent source-slice oracle for five paragraphs and 10 chunks.
Usage: python -X utf8 tests/check_ssml_realbook.py DLL OUTPUT_DIRECTORY
"""
import ctypes as c
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from check_document_search import SearchSDK, Position
ROOT=Path(__file__).resolve().parents[1]
class Cursor(c.Structure):
    _fields_=[(n,c.c_size_t) for n in ('part','offset','node')]
class Range(c.Structure):
    _fields_=[('start',Position),('end',Position)]
class Sentence(c.Structure):
    _fields_=[('range',Range),('ssml_start',c.c_size_t),('ssml_end',c.c_size_t)]
class Chunk(c.Structure):
    _fields_=[('ssml',c.c_void_p),('size',c.c_size_t),('characters',c.c_size_t),
              ('sentences',c.POINTER(Sentence)),('sentence_count',c.c_size_t),('next',Cursor),('end',c.c_int)]
class Block(c.Structure):
    _fields_=[('start',c.c_size_t),('end',c.c_size_t),('heading',c.c_uint)]

def main():
    sdk=SearchSDK(Path(sys.argv[1]).resolve());out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
    from run_realbooks import Error
    fn=sdk.dll.exr_document_ssml;fn.restype=c.c_int
    fn.argtypes=[c.c_void_p,Cursor,c.c_size_t,c.POINTER(Chunk),c.c_uint,c.c_void_p,c.POINTER(Error)]
    free=sdk.dll.exr_ssml_chunk_free;free.argtypes=[c.POINTER(Chunk)]
    blocks=sdk.dll.exr_document_blocks;blocks.restype=c.POINTER(Block);blocks.argtypes=[c.c_void_p,c.POINTER(c.c_size_t)]
    book=next(b for b in json.loads((ROOT/'tools/regress/corpus.json').read_text(encoding='utf-8'))['books'] if b['id']=='hongloumeng-24264')
    p=sdk.open(book);part=1;doc=c.c_void_p();sdk.check('publication_load',p,part,c.byref(doc))
    size=c.c_size_t();raw=c.string_at(sdk.document_text(doc,c.byref(size)),size.value)
    count=c.c_size_t();entries=blocks(doc,c.byref(count))
    source=[(entries[i].start,entries[i].end) for i in range(count.value)]
    def chunk(cursor,limit):
        result=Chunk();error=Error();status=fn(p,cursor,limit,c.byref(result),0,None,c.byref(error));assert status==0,(status,error.message)
        xml=c.string_at(result.ssml,result.size);tree=ET.fromstring(xml)
        assert tree.tag=='{http://www.w3.org/2001/10/synthesis}speak'
        text=''.join(tree.itertext());assert len(text)==result.characters<=limit
        sentences=tree.findall('.//{http://www.w3.org/2001/10/synthesis}s')
        assert len(sentences)==result.sentence_count
        for i,node in enumerate(sentences):
            item=result.sentences[i];assert ''.join(node.itertext())==raw[item.range.start.offset:item.range.end.offset].decode()
        next_cursor=Cursor(result.next.part,result.next.offset,result.next.node)
        record=dict(characters=len(text),sentences=len(sentences),next=[next_cursor.part,next_cursor.offset,next_cursor.node],xml_bytes=len(xml),xml_valid=True)
        free(c.byref(result));return next_cursor,text,xml,record
    # This Gutenberg EPUB stores whole chapters in very large paragraphs. Use
    # each sampled paragraph's explicit budget; test the default 800 separately.
    eligible=[(a,b) for a,b in source if sum('\u4e00'<=ch<='\u9fff' for ch in raw[a:b].decode())>=20]
    samples=[]
    for i,(a,b) in enumerate(eligible[:5]):
        paragraph=raw[a:b].decode();expected=paragraph
        _,text,xml,record=chunk(Cursor(part,a,0),len(expected))
        assert text==expected
        record.update(start=a,end=a+len(expected.encode()),paragraph_characters=len(paragraph),expected_characters=len(expected),error_percent=abs(len(text)-len(expected))/len(expected)*100)
        (out/f'paragraph-{i+1}.ssml').write_bytes(xml);samples.append(record)
    assert len(samples)==5
    first=raw.index('第一回'.encode());second=raw.index('第二回'.encode())
    expected=''.join(raw[a:b].decode() for a,b in source if first<=a<second);limit=800
    assert 9*limit<len(expected)<=10*limit
    cursor=Cursor(part,first,0);pieces=[];records=[]
    for i in range(10):
        assert cursor.part==part
        cursor,text,xml,record=chunk(cursor,min(limit,len(expected)-i*limit));pieces.append(text);records.append(record)
    actual=''.join(pieces);assert cursor.part==part and cursor.offset in (second-1,second) and actual==expected
    result=dict(book=book['id'],book_sha256=hashlib.sha256(Path(book['path']).read_bytes()).hexdigest(),part=part,
        samples=samples,chunks=dict(chapter='第一回',start=first,end=second,calls=10,max_chars=limit,total_characters=len(actual),source_characters=len(expected),
            source_sha256=hashlib.sha256(expected.encode()).hexdigest(),spoken_sha256=hashlib.sha256(actual.encode()).hexdigest(),
            equal=True,repeated_characters=0,missing_characters=0,records=records))
    (out/'engine.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    sdk.document_free(doc);sdk.publication_free(p);print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
