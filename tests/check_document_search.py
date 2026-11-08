# SPDX-License-Identifier: MIT
"""Real-book search oracle, native anchor/glyph jumps, and cold/warm timings.
Run from repository root: python -X utf8 tests/check_document_search.py BUILD_DLL OUTPUT_JSON
Uses the local, uncommitted corpus paths; emits offsets/counts/hashes, never book bodies.
"""
import ctypes as c
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/regress'))
from run_realbooks import SDK,Error,Config,file_hash

class Part(c.Structure):
    _fields_=[('id',c.c_char_p),('path',c.c_char_p),('title',c.c_char_p),('linear',c.c_int)]
class Position(c.Structure):
    _fields_=[('part',c.c_size_t),('offset',c.c_size_t)]
class Hit(c.Structure):
    _fields_=[('found',c.c_int),('part',c.c_size_t),('offset',c.c_size_t),('length',c.c_size_t)]
class Target(c.Structure):
    _fields_=[('part',c.c_size_t),('fragment',c.c_char_p),('offset',c.c_size_t)]
class Location(c.Structure):
    _fields_=[('part',c.c_size_t),('offset',c.c_size_t),('state',c.c_int)]
class Anchor(c.Structure):
    _fields_=[('start',c.c_size_t),('end',c.c_size_t)]+[(x,c.c_void_p) for x in ['exact','prefix','suffix','chapter']]
class Match(c.Structure):
    _fields_=[('state',c.c_int),('start',c.c_size_t),('end',c.c_size_t)]
class Glyph(c.Structure):
    _fields_=([(x,c.c_size_t) for x in ['start','end']]+[(x,c.c_uint32) for x in ['codepoint','glyph']]+
      [(x,c.c_float) for x in ['x','baseline','advance','size']]+[(x,c.c_size_t) for x in ['page','node']]+
      [(x,c.c_uint32) for x in ['color','flags']]+[(x,c.c_float) for x in ['clip_left','clip_right','line_height']]+
      [(x,c.c_size_t) for x in ['cluster_start','cluster_end']]+[('boundaries',c.c_uint),('font_index',c.c_size_t)]+
      [(x,c.c_float) for x in ['offset_x','offset_y']]+[('bidi_level',c.c_uint)])
class Page(c.Structure):
    _fields_=[(x,c.c_size_t) for x in ['start','end','line_start','line_count','box_start','box_count']]
CALLBACK=c.CFUNCTYPE(c.c_int,c.c_void_p,c.POINTER(Hit))
FOLD=str.maketrans({i:i+32 for i in [*range(65,91),*range(0xc0,0xd7),*range(0xd8,0xdf)]})

class SearchSDK(SDK):
    def __init__(self,path):
        super().__init__(path)
        ptr,size,err=c.c_void_p,c.c_size_t,c.POINTER(Error)
        signatures={
          'publication_search_all':(c.c_int,[ptr,c.c_char_p,c.c_uint,ptr,ptr,ptr,c.POINTER(size),err]),
          'publication_search':(c.c_int,[ptr,Position,c.c_char_p,c.c_uint,ptr,c.POINTER(Hit),err]),
          'document_text':(ptr,[ptr,c.POINTER(size)]),
          'publication_locate':(c.c_int,[ptr,c.POINTER(Target),c.POINTER(Location),err]),
          'anchor_create':(c.c_int,[ptr,size,size,c.POINTER(Anchor),err]),
          'anchor_resolve':(c.c_int,[ptr,c.POINTER(Anchor),c.POINTER(Match),err]),
          'anchor_free':(None,[c.POINTER(Anchor)]),
          'layout_create_ex':(c.c_int,[ptr,ptr,c.POINTER(Config),c.POINTER(ptr),err]),
          'layout_glyphs':(c.POINTER(Glyph),[ptr,c.POINTER(size)]),
          'layout_pages':(c.POINTER(Page),[ptr,c.POINTER(size)]),
        }
        for name,(result,args) in signatures.items():
            fn=getattr(self.dll,'exr_'+name);fn.restype,fn.argtypes=result,args;setattr(self,name,fn)
    def open(self,book):
        p=c.c_void_p();self.check('publication_open',book['path'].encode(),c.byref(p));return p
    def search(self,p,q,collect=True):
        hits=[]
        @CALLBACK
        def receive(_,r):
            h=r.contents;hits.append((h.part,h.offset,h.length));return 1
        count=c.c_size_t();start=time.perf_counter_ns()
        self.check('publication_search_all',p,q.encode(),0,receive if collect else None,None,None,c.byref(count))
        elapsed=(time.perf_counter_ns()-start)/1e6
        return count.value,hits,elapsed
    def texts(self,p):
        n=c.c_size_t();parts=c.cast(self.publication_parts(p,c.byref(n)),c.POINTER(Part));texts={}
        for i in range(n.value):
            if parts[i].linear:
                doc=c.c_void_p();self.check('publication_load',p,i,c.byref(doc));size=c.c_size_t();ptr=self.document_text(doc,c.byref(size));texts[i]=c.string_at(ptr,size.value);self.document_free(doc)
        return texts

def oracle(texts,query):
    q=query.translate(FOLD).encode();hits=[]
    for part,raw in texts.items():
        body=raw.decode().translate(FOLD).encode();at=0
        while (at:=body.find(q,at))>=0:
            hits.append((part,at,len(q)));at+=1
    return hits

def main():
    dll=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sdk=SearchSDK(dll)
    books=json.loads((ROOT/'tools/regress/corpus.json').read_text())['books'];by_id={b['id']:b for b in books}
    queries={
      'hongloumeng-24264':['賈寶玉','女媧氏','Gutenberg','24264','2021'],
      'a-raisin-in-the-sun':['Brustein','Nemiroff','Les Blancs','1994','80744'],
      'kusamakura-japanese-vertical-writing':['夏目漱石','Natsume','Sadder','75891','0213'],
    }
    result={'dll_sha256':file_hash(dll),'counts':[],'jumps':[],'performance':{},'oracle':'independent Python limited-fold bytes.find, overlapping; context review printed to console'}
    reviewed=[[18,1,98,2,1],[4,10,5,2,1],[5,1,1,1,1]]
    pubs={};bodies={}
    for book_index,(bid,qs) in enumerate(queries.items()):
        p=pubs[bid]=sdk.open(by_id[bid]);texts=bodies[bid]=sdk.texts(p)
        for query_index,q in enumerate(qs):
            n,hits,ms=sdk.search(p,q);expected=oracle(texts,q);assert hits==expected,(bid,q,n,len(expected))
            assert n==reviewed[book_index][query_index]
            result['counts'].append({'reviewed':reviewed[book_index][query_index],'book':bid,'query':q,'engine':n,'oracle':len(expected),'equal':True})
            print(bid,q,n,flush=True)
            for part,at,length in hits:
                raw=texts[part];before=raw[:at].decode()[-12:];after=raw[at+length:].decode()[:12]
                print(' ',part,at,repr(before+'['+raw[at:at+length].decode()+']'+after))
    font=c.c_void_p();fontpath=ROOT/'../EXReader-Windows-delivery-20261104/payload/Reader.otf';sdk.check('font_open',str(fontpath.resolve()).encode(),c.byref(font))
    cfg=sdk.layout_config_defaults();cfg.page.width=720;cfg.page.height=1040;cfg.page.margin=36;cfg.page.font_size=28;cfg.page.line_height=1.5;cfg.page.paragraph_spacing=10
    for bid,q,needed in [('hongloumeng-24264','賈寶玉',8),('a-raisin-in-the-sun','Nemiroff',6),('kusamakura-japanese-vertical-writing','住み',6)]:
        p=pubs[bid];_,hits,_=sdk.search(p,q);assert len(hits)>=needed;cache={}
        for index in [round(i*(len(hits)-1)/(needed-1)) for i in range(needed)]:
            part,at,length=hits[index]
            if part not in cache:
                doc=c.c_void_p();layout=c.c_void_p();sdk.check('publication_load',p,part,c.byref(doc));sdk.check('layout_create_ex',doc,font,c.byref(cfg),c.byref(layout));cache[part]=(doc,layout)
            doc,layout=cache[part];target=Target(part,None,at);loc=Location();sdk.check('publication_locate',p,c.byref(target),c.byref(loc));assert loc.part==part and loc.offset==at
            anchor=Anchor();match=Match();sdk.check('anchor_create',doc,at,at+length,c.byref(anchor));sdk.check('anchor_resolve',doc,c.byref(anchor),c.byref(match));assert match.state==1 and match.start==at and match.end==at+length
            ng=c.c_size_t();gs=sdk.layout_glyphs(layout,c.byref(ng));glyphs=[gs[i] for i in range(ng.value) if gs[i].cluster_start<=at<gs[i].cluster_end and not gs[i].flags&4];assert glyphs
            np=c.c_size_t();pages=sdk.layout_pages(layout,c.byref(np));g=glyphs[0];assert pages[g.page].start<=at<pages[g.page].end
            raw=bodies[bid][part];assert raw[at:at+length].decode().translate(FOLD)==q.translate(FOLD)
            result['jumps'].append({'book':bid,'part':part,'offset':at,'length':length,'page':g.page,'glyph_codepoint':g.codepoint,'vertical':bool(g.flags&128),'located':True,'anchor':True,'glyph':True});sdk.anchor_free(c.byref(anchor))
        for doc,layout in cache.values():sdk.layout_free(layout);sdk.document_free(doc)
    sdk.font_free(font)
    # Each cold trial creates a fresh publication. Open time is outside the API timer.
    hong=by_id['hongloumeng-24264'];warm=pubs[hong['id']]
    for q in ['的','賈寶玉']:
        cold=[];cached=[];counts=[]
        for _ in range(3):
            p=sdk.open(hong);n,_,ms=sdk.search(p,q,False);counts.append(n);cold.append(ms);sdk.publication_free(p)
            _,_,ms=sdk.search(warm,q,False);cached.append(ms)
        result['performance'][q]={'hits':counts[0],'cold_ms':cold,'cold_median_ms':statistics.median(cold),'warm_ms':cached,'warm_median_ms':statistics.median(cached),'passes_200ms':max(cold)<=200}
    result['count_checks']=len(result['counts']);result['jump_checks']=len(result['jumps']);result['vertical_jumps']=sum(x['vertical'] for x in result['jumps'])
    for p in pubs.values():sdk.publication_free(p)
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['counts','jumps']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
