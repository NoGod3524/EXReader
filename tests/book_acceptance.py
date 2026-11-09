"""Measure external full books; persist identities/metrics, never source bytes."""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import struct
from book_formats import bind, call, parts, load, text, navigation, SDK, P, N, Bitmap, records
from run_realbooks import Options, pixel_hash

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def measure(sdk, entry, root, font_path, output):
    path=root/entry['filename']; row=dict(entry); row.update(sha256=digest(path),bytes=path.stat().st_size)
    p=P(); font=P(); pages=chars=0; image_paths=set(); started=time.perf_counter()
    try:
        call(sdk,'publication_open',str(path.resolve()).encode(),c.byref(p))
        row['parts']=parts(sdk,p); row['toc_entries']=len(navigation(sdk,p))
        call(sdk,'font_open',str(font_path.resolve()).encode(),c.byref(font))
        config=sdk.layout_config_defaults();config.page=Options(720,1040,36,28,1.5,10)
        config.document_css=1; config.embedded_fonts=1
        for part in range(row['parts']):
            d,_=load(sdk,p,part); chars+=len(text(sdk,d)); n=N(); resources=sdk.document_resources(d,c.byref(n))
            for i,r in enumerate(resources[:n.value]):
                if r.media_type in (b'image/png',b'image/jpeg',b'image/gif') and r.path not in image_paths:
                    data=P();size=N();bitmap=Bitmap()
                    call(sdk,'document_resource',d,i,c.byref(data),c.byref(size))
                    call(sdk,'image_decode',data,size,c.byref(bitmap)); assert bitmap.width and bitmap.height
                    sdk.bitmap_free(c.byref(bitmap));sdk.free(data);image_paths.add(r.path)
            pager=P();call(sdk,'pager_create',d,font,c.byref(config),c.byref(pager))
            while True:
                page=P();call(sdk,'pager_next',pager,c.byref(page))
                if not page:break
                if not pages:
                    bitmap=Bitmap();call(sdk,'render_page_color',page,sdk.layout_font(page),0,c.byref(bitmap))
                    pixels=c.string_at(bitmap.pixels,bitmap.stride*bitmap.height)
                    row['first_screen_nonblank']=len(set(pixels))>2
                    row['first_screen_pixel_sha256']=pixel_hash(bitmap)
                    if entry.get('screenshot'):
                        call(sdk,'bitmap_write_png',c.byref(bitmap),str((output/entry['screenshot']).resolve()).encode())
                    sdk.bitmap_free(c.byref(bitmap))
                pages+=1;sdk.layout_free(page)
            sdk.pager_free(pager);sdk.document_free(d)
        row.update(status='ok',page_count=pages,character_count=chars,decoded_images=len(image_paths))
    except Exception as e:
        row.update(status='error',error=str(e),page_count=pages,character_count=chars)
    finally:
        if p:sdk.publication_free(p)
        if font:sdk.font_free(font)
    row['seconds']=round(time.perf_counter()-started,3)
    print(row['filename'],row['status'],pages,chars,flush=True)
    return row

def codecs(root, probe):
    result=[]
    for name in ['pg11.mobi','pg84.mobi','pg1661.mobi','pg11-huff.azw3','pg84-huff.azw3']:
        path=root/name; actual=root/(name+'.native.raw'); ref=root/(name+'.reference.raw')
        native=json.loads(subprocess.check_output([str(probe.resolve()),'decode',str(path),str(actual)]))
        oracle=json.loads(subprocess.check_output(['node',str(Path(__file__).with_name('book_reference.mjs')),
            str(root/'mobi.js'),str(path),str(ref)]))
        data=actual.read_bytes(); expected=ref.read_bytes(); assert data==expected,(name,len(data),len(expected))
        row=dict(filename=name,compression=native['compression'],decoded_bytes=len(data),
                 declared_bytes=native['declared_bytes'],reference_decoded_bytes=len(expected),
                 bytes_equal=True,sha256=hashlib.sha256(data).hexdigest(),records_equal=native['record_bytes']==oracle['record_bytes'])
        if name.endswith('.mobi'):
            section=re.split(br'<mbp:pagebreak\b[^>]*>',data,flags=re.I)[0]
            ref_section=re.split(br'<mbp:pagebreak\b[^>]*>',expected,flags=re.I)[0]
            row.update(section=0,section_bytes=len(section),reference_section_bytes=len(ref_section),section_sha256=hashlib.sha256(section).hexdigest())
        else:
            rs=records(path.read_bytes());h=rs[0];fdst=rs[struct.unpack_from('>I',h,192)[0]]
            count=struct.unpack_from('>I',fdst,8)[0]
            extents=[struct.unpack_from('>II',fdst,12+i*8) for i in range(count)]
            row.update(fdst_ranges=extents,body_bytes=extents[0][1],auxiliary_bytes=len(data)-extents[0][1],
                       matches_fdst=len(data)==extents[-1][1],matches_declared_body=native['declared_bytes']==extents[0][1])
        result.append(row)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--samples',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--library',type=Path,required=True);ap.add_argument('--probe',type=Path,required=True);ap.add_argument('--font',type=Path,required=True)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=True);sdk=bind(SDK(args.library.resolve()))
    manifest=json.loads((args.samples/'acceptance-manifest.json').read_text(encoding='utf-8'))
    measurements=[measure(sdk,b,args.samples,args.font,args.output) for b in manifest]
    report=dict(library_sha256=digest(args.library),font_sha256=digest(args.font),layout=dict(width=720,height=1040,font_size=28),books=measurements,
                codec_comparisons=codecs(args.samples,args.probe),reference=json.loads((args.samples/'foliate-reference.json').read_text()))
    (args.output/'samples.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert all(b['status']=='ok' and b['page_count'] and b['first_screen_nonblank'] for b in measurements)
