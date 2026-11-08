"""Remeasure the historical real PDF samples; retain failures and per-page metadata."""
import argparse,json,sys,ctypes as c
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'/'regress')); sys.path.insert(0,str(ROOT/'tests'))
from run_realbooks import SDK,Error,Bitmap,FixedOptions,pixel_hash,file_hash
from measure_pdf_deepening import Match
parser=argparse.ArgumentParser()
for name in ('dll','font','manifest','output'): parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args()
sdk=SDK(args.dll.resolve()); ptr=c.c_void_p; size=c.c_size_t
for name,result,arguments in [('fixed_page_text',c.c_int,[ptr,size,ptr,c.POINTER(ptr),c.POINTER(Error)]),('fixed_text_string',ptr,[ptr,c.POINTER(size)]),('document_search',c.c_int,[ptr,size,c.c_char_p,ptr,c.POINTER(Match),c.POINTER(Error)]),('fixed_text_select',c.c_int,[ptr,size,size,ptr,c.POINTER(ptr),c.POINTER(size),c.POINTER(Error)]),('free',None,[ptr])]:
 f=getattr(sdk.dll,'exr_'+name);f.restype=result;f.argtypes=arguments;setattr(sdk,name,f)
font=ptr();sdk.check('font_open',str(args.font.resolve()).encode(),c.byref(font))
corpus=json.loads(args.manifest.read_text())
rows=[]
for sample in corpus.get('books',corpus.get('samples',[])):
 if not sample['id'].startswith('pdf-'): continue
 o=FixedOptions();o.struct_size=c.sizeof(o);o.fallback_font=font
 d=ptr();e=Error();p=Path(sample['path']);r={'id':sample['id'],'sha256':file_hash(p),'path':str(p),'pages':[]}
 r['without_password']=sdk.fixed_open(str(p).encode(),c.byref(o),c.byref(d),c.byref(e));sdk.fixed_free(d);d=ptr()
 if 'encrypted' in sample['id']:
  pw=c.create_string_buffer(b'format-test');o.pdf_password=c.cast(pw,ptr);o.pdf_password_size=11
 r['open']=sdk.fixed_open(str(p).encode(),c.byref(o),c.byref(d),c.byref(e));r['open_error']=e.message.decode(errors='replace')
 if not r['open']:
  n=size();sdk.fixed_pages(d,c.byref(n));r['page_count']=n.value
  for page in range(n.value):
   t=ptr();q={'page':page};q['text_status']=sdk.fixed_page_text(d,page,None,c.byref(t),c.byref(e));q['characters']=None
   if not q['text_status']:
    nb=size();data=c.string_at(sdk.fixed_text_string(t,c.byref(nb)),nb.value);q['characters']=len(data.decode());q['utf8_bytes']=nb.value
    sel=ptr();nc=size();q['selection_status']=sdk.fixed_text_select(t,0,len(data.decode()[0].encode()),None,c.byref(sel),c.byref(nc),c.byref(e));q['selected_regions']=nc.value;sdk.free(sel)
   elif q['text_status']==12: q['characters']=0
   sdk.fixed_text_free(t)
   # Natural publication scale capped at 480 pixels.
   pages=sdk.fixed_pages(d,c.byref(n));g=pages[page].geometry
   scale=480/max(g.bounds[2]-g.bounds[0],g.bounds[3]-g.bounds[1])/g.unit_scale
   b=Bitmap();q['render_status']=sdk.fixed_render(d,page,scale,None,c.byref(b),c.byref(e))
   if not q['render_status']: q['pixel_sha256']=pixel_hash(b);q['size']=[b.width,b.height]
   sdk.bitmap_free(c.byref(b));r['pages'].append(q)
  m=Match();r['search_status']=sdk.document_search(d,0,b'the',None,c.byref(m),c.byref(e));r['search_hits']=int(m.start!=c.c_size_t(-1).value)
  r['search_match']={k:getattr(m,k) for k,_ in Match._fields_}
  sdk.fixed_free(d)
 rows.append(r);print(r['id'],r['open'],r.get('page_count'),flush=True)
args.output.write_text(json.dumps({'dll_sha256':file_hash(args.dll),'font_sha256':file_hash(args.font),'driver_sha256':file_hash(__file__),'samples':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
sdk.font_free(font)
