"""Measure the controlled 4 x 2 PDF corpus through public APIs and PyMuPDF.
No PDF bytes, extracted text, or publication screenshots are written to evidence.
"""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'/'regress'))
from run_realbooks import SDK, Error, Bitmap, FixedOptions, pixel_hash, file_hash
import pymupdf

class Match(c.Structure):
    _fields_ = [(s,c.c_size_t) for s in ('start','end','start_page','start_offset','end_page','end_offset')]
class Region(c.Structure):
    _fields_ = [('start',c.c_size_t),('end',c.c_size_t),('quad',c.c_double*8),('flags',c.c_uint)]
class Security(c.Structure):
    _fields_ = [('struct_size',c.c_size_t)]+[(s,c.c_uint) for s in ('encrypted','revision','key_bits','owner_authenticated','permissions','metadata_encrypted')]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--dll',type=Path,required=True)
    parser.add_argument('--font',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--previews',type=Path,required=True)
    args=parser.parse_args()
    sdk=SDK(args.dll.resolve()); ptr=c.c_void_p; size=c.c_size_t; err=c.POINTER(Error)
    signatures={
      'fixed_page_text':(c.c_int,[ptr,size,ptr,c.POINTER(ptr),err]),
      'fixed_text_string':(ptr,[ptr,c.POINTER(size)]),
      'fixed_text_select':(c.c_int,[ptr,size,size,ptr,c.POINTER(ptr),c.POINTER(size),err]),
      'fixed_character_at':(c.c_int,[ptr,size,c.c_double,c.c_double,ptr,c.POINTER(Region),c.POINTER(c.c_uint32),err]),
      'document_search':(c.c_int,[ptr,size,c.c_char_p,ptr,c.POINTER(Match),err]),
      'free':(None,[ptr]),
    }
    for name,(result,arguments) in signatures.items():
        f=getattr(sdk.dll,'exr_'+name); f.restype=result; f.argtypes=arguments; setattr(sdk,name,f)
    font=ptr(); error=Error(); sdk.check('font_open',str(args.font.resolve()).encode(),c.byref(font))
    report={'dll_sha256':file_hash(args.dll),'font_sha256':file_hash(args.font),
            'driver_sha256':file_hash(__file__),'pymupdf_version':pymupdf.__version__,
            'region_size':c.sizeof(Region),'match_size':c.sizeof(Match),
            'offset_contract':'UTF-8; zero-based pages; concatenated provider-order text; no page separators','samples':[]}
    args.previews.mkdir(parents=True,exist_ok=True)
    for sample in json.loads(args.manifest.read_text()):
        p=Path(sample['path']); item={k:v for k,v in sample.items() if k!='password'}
        assert file_hash(p)==sample['sha256']
        options=FixedOptions(); options.struct_size=c.sizeof(options); options.fallback_font=font
        security=Security(); security.struct_size=c.sizeof(security); options.pdf_security=c.cast(c.byref(security),ptr)
        d=ptr()
        item['open_without_password']=sdk.fixed_open(str(p).encode(),c.byref(options),c.byref(d),c.byref(error))
        sdk.fixed_free(d); d=ptr()
        password=sample.get('password','').encode(); pw=c.create_string_buffer(password)
        if password:
            wrong=c.create_string_buffer(b'wrong'); options.pdf_password=c.cast(wrong,ptr); options.pdf_password_size=5
            item['open_wrong_password']=sdk.fixed_open(str(p).encode(),c.byref(options),c.byref(d),c.byref(error)); sdk.fixed_free(d); d=ptr()
        options.pdf_password=c.cast(pw,ptr); options.pdf_password_size=len(password)
        item['open_status']=sdk.fixed_open(str(p).encode(),c.byref(options),c.byref(d),c.byref(error))
        item['open_error']=error.message.decode(errors='replace')
        item['security']={s:getattr(security,s) for s,_ in Security._fields_ if s!='struct_size'}
        ref=pymupdf.open(p)
        if ref.needs_pass: assert ref.authenticate(sample.get('password',''))
        item['reference_pages']=len(ref); item['pages']=[]
        if not item['open_status']:
            count=size(); sdk.fixed_pages(d,c.byref(count)); item['page_count']=count.value
            assert count.value==sample['expected_pages']==len(ref)
            for page in range(count.value):
                t=ptr(); n=size(); row={'page':page}
                row['text_status']=sdk.fixed_page_text(d,page,None,c.byref(t),c.byref(error))
                row['text_error']=error.message.decode(); row['characters']=0; row['utf8_bytes']=0
                row['reference_characters']=len(ref[page].get_text().rstrip('\n'))
                row['selection_status']=None; row['selected_regions']=0
                if not row['text_status']:
                    data=c.string_at(sdk.fixed_text_string(t,c.byref(n)),n.value)
                    row['utf8_bytes']=n.value; row['characters']=len(data.decode()); row['text_sha256']=hashlib.sha256(data).hexdigest()
                    assert data.decode()==ref[page].get_text().rstrip('\n')
                    selected=ptr(); selected_count=size(); end=len(data.decode()[0].encode())
                    row['selection_status']=sdk.fixed_text_select(t,0,end,None,c.byref(selected),c.byref(selected_count),c.byref(error)); row['selected_regions']=selected_count.value
                    sdk.free(selected)
                else:
                    assert row['text_status']==12 and not t
                    r=Region(); cp=c.c_uint32()
                    row['coordinate_status']=sdk.fixed_character_at(d,page,25,25,None,c.byref(r),c.byref(cp),c.byref(error))
                sdk.fixed_text_free(t)
                bitmap=Bitmap(); row['render_status']=sdk.fixed_render(d,page,1,None,c.byref(bitmap),c.byref(error))
                if not row['render_status']:
                    row['size']=[bitmap.width,bitmap.height]; row['pixel_sha256']=pixel_hash(bitmap)
                    pixels=b''.join(c.string_at(bitmap.pixels+y*bitmap.stride,bitmap.width*4) for y in range(bitmap.height))
                    sdk_image=pymupdf.Pixmap(pymupdf.csRGB,bitmap.width,bitmap.height,pixels,True)
                    reference=ref[page].get_pixmap(alpha=True)
                    assert row['size']==[reference.width,reference.height]
                    # Compare independently rasterized RGB over white (alpha in reference is transparent).
                    ref_white=ref[page].get_pixmap(alpha=False)
                    reference_pixels=ref_white.samples
                    delta=sum(abs(pixels[i*4+k]-reference_pixels[i*3+k]) for i in range(bitmap.width*bitmap.height) for k in range(3))
                    row['reference_rgb_mean_absolute_error']=round(delta/(bitmap.width*bitmap.height*3),5)
                    for key, data, channels in [('ink',pixels,4),('reference_ink',reference_pixels,3)]:
                        points=[i for i in range(bitmap.width*bitmap.height) if min(data[i*channels:i*channels+3])<192]
                        row[key+'_pixels']=len(points)
                        row[key+'_bbox']=[min(i%bitmap.width for i in points),min(i//bitmap.width for i in points),
                                          max(i%bitmap.width for i in points),max(i//bitmap.width for i in points)]
                    ratio=row['ink_pixels']/row['reference_ink_pixels']
                    row['render_correct']=(row['reference_rgb_mean_absolute_error']<2 and .5<ratio<2 and
                        all(abs(a-b)<=2 for a,b in zip(row['ink_bbox'],row['reference_ink_bbox'])))
                    if page==0:
                        sdk_image.save(str(args.previews/(sample['id']+'-sdk.png')))
                        ref_white.save(str(args.previews/(sample['id']+'-reference.png')))
                    sdk.bitmap_free(c.byref(bitmap))
                item['pages'].append(row)
            m=Match(); query=b'alpha' if sample['id'] in ('text-a','encrypted-password','mixed-a') else b'gamma' if sample['id']=='mixed-b' else b'caf\xc3\xa9'
            item['search_status']=sdk.document_search(d,0,query,None,c.byref(m),c.byref(error))
            item['search_query']=query.decode(); item['search_match']={s:getattr(m,s) for s,_ in Match._fields_}
            item['search_hits']=int(m.start!=c.c_size_t(-1).value)
            item['characters']=sum(row['characters'] for row in item['pages'])
            item['selection_usable_pages']=sum(row['selection_status']==0 and row['selected_regions']>0 for row in item['pages'])
            item['render_correct_pages']=sum(row.get('render_correct',False) for row in item['pages'])
            sdk.fixed_free(d)
        ref.close(); report['samples'].append(item)
        print(sample['id'],item['open_status'],item.get('page_count'),item.get('characters'),item.get('render_correct_pages'),flush=True)
    sdk.font_free(font)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert len(report['samples'])==8
    assert all(x['open_status']==0 and x['render_correct_pages']==x['page_count'] for x in report['samples'])
    assert report['samples'][-2]['open_without_password']==10
    assert report['samples'][-1]['open_without_password']==0

if __name__=='__main__': main()
