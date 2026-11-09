"""Public publication/pager contract tests; all generated inputs stay in temp dirs."""
import argparse
import base64
import ctypes as c
import io
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures'
sys.path.insert(0, str(ROOT / 'tools/regress'))
from run_realbooks import SDK, Error, Bitmap

MAX = c.c_size_t(-1).value
P, N = c.c_void_p, c.c_size_t

class Navigation(c.Structure):
    _fields_ = [('parent', N), ('part', N)] + [(x, c.c_char_p) for x in ('label', 'href', 'base', 'role')]

class Resource(c.Structure):
    _fields_ = [(x, c.c_char_p) for x in ('id', 'path', 'media_type', 'properties')]

class Location(c.Structure):
    _fields_ = [('part', N), ('offset', N), ('state', c.c_int)]

def bind(sdk):
    signatures = {
        'publication_open_memory': (c.c_int, [c.c_int, P, N, c.POINTER(P), c.POINTER(Error)]),
        'publication_navigation': (c.c_int, [P, c.POINTER(c.POINTER(Navigation)), c.POINTER(N), c.POINTER(Error)]),
        'document_text': (P, [P, c.POINTER(N)]),
        'document_resources': (c.POINTER(Resource), [P, c.POINTER(N)]),
        'document_resource': (c.c_int, [P, N, c.POINTER(P), c.POINTER(N), c.POINTER(Error)]),
        'document_locate': (c.c_int, [P, c.c_char_p, c.POINTER(Location), c.POINTER(Error)]),
        'image_decode': (c.c_int, [P, N, c.POINTER(Bitmap), c.POINTER(Error)]),
        'bitmap_write_png': (c.c_int, [c.POINTER(Bitmap), c.c_char_p, c.POINTER(Error)]),
        'free': (None, [P]),
    }
    for name, (result, args) in signatures.items():
        f = getattr(sdk.dll, 'exr_' + name)
        f.restype, f.argtypes = result, args
        setattr(sdk, name, f)
    return sdk

def call(sdk, name, *args, expected=0):
    e = Error()
    code = getattr(sdk, name)(*args, c.byref(e))
    assert code == expected, (name, code, e.message.decode(errors='replace'))
    if code:
        assert e.code == code and e.message
    return e.message.decode(errors='replace')

def parts(sdk, p):
    count = N(); sdk.publication_parts(p, c.byref(count)); return count.value

def text(sdk, d):
    size = N(); ptr = sdk.document_text(d, c.byref(size)); return c.string_at(ptr, size.value).decode('utf-8')

def open_bytes(sdk, data, fmt=7, expected=0):
    p = P(1); message = call(sdk, 'publication_open_memory', fmt, data, len(data), c.byref(p), expected=expected)
    assert bool(p) == (not expected)
    return p, message

def load(sdk, p, part, expected=0):
    d = P(1); message = call(sdk, 'publication_load', p, part, c.byref(d), expected=expected)
    assert bool(d) == (not expected)
    return d, message

def navigation(sdk, p):
    nav = c.POINTER(Navigation)(); n = N()
    call(sdk, 'publication_navigation', p, c.byref(nav), c.byref(n))
    return [dict(parent=v.parent, part=v.part, label=v.label.decode(), href=v.href.decode()) for v in nav[:n.value]]

def records(data):
    n = struct.unpack_from('>H', data, 76)[0]
    offsets = [struct.unpack_from('>I', data, 78 + 8*i)[0] for i in range(n)] + [len(data)]
    return [bytearray(data[a:b]) for a, b in zip(offsets, offsets[1:])]

def pack(rs):
    head = bytearray(78); head[60:68] = b'BOOKMOBI'
    struct.pack_into('>H', head, 76, len(rs))
    pos = 78 + 8*len(rs); directory = bytearray()
    for i, r in enumerate(rs):
        directory += struct.pack('>II', pos, i); pos += len(r)
    return bytes(head + directory + b''.join(rs))

def mobi(html, images=(), encoding=65001):
    h = bytearray(244)
    struct.pack_into('>HHIHHHH', h, 0, 1, 0, len(html), 1, 4096, 0, 0)
    h[16:20] = b'MOBI'
    for offset, value in [(20,228),(28,encoding),(36,6),(104,6),(108,2)]:
        struct.pack_into('>I', h, offset, value)
    return pack([h, html, *images])

def png():
    return base64.b64decode(next(n.text for n in ET.parse(FIX/'rich.fb2').getroot().iter() if n.tag.endswith('binary')))

def render(sdk, d):
    font, pager, page = P(), P(), P(); bitmap = Bitmap()
    call(sdk, 'font_open', str(FIX/'fonts/fallback.ttf').encode(), c.byref(font))
    config = sdk.layout_config_defaults()
    call(sdk, 'pager_create', d, font, c.byref(config), c.byref(pager))
    call(sdk, 'pager_next', pager, c.byref(page)); assert page
    call(sdk, 'render_page_color', page, sdk.layout_font(page), 0, c.byref(bitmap))
    data = c.string_at(bitmap.pixels, bitmap.stride*bitmap.height)
    assert data != b'\xff'*len(data), 'blank first screen'
    sdk.bitmap_free(c.byref(bitmap)); sdk.layout_free(page); sdk.pager_free(pager); sdk.font_free(font)
    return hashlib.sha256(data).hexdigest()

def codec_group(sdk, probe, tmp):
    vectors = [(b'\0', b'\0'), (b'A\x80\x0f', b'A'*11), (b'\xc1', b' A')]
    vectors += [(bytes([n])+bytes(range(n)), bytes(range(n))) for n in range(1,9)]
    for encoded, expected in vectors:
        (tmp/'in').write_bytes(encoded)
        subprocess.run([probe, 'palmdoc', str(tmp/'in'), str(tmp/'out')], check=True)
        assert (tmp/'out').read_bytes() == expected
    for encoded in (b'\x80', b'\x80\0', b'\x03a', b'\x80\x08'):
        (tmp/'in').write_bytes(encoded)
        r = subprocess.run([probe, 'palmdoc', str(tmp/'in'), str(tmp/'out')], capture_output=True)
        assert r.returncode and r.stderr
    for name in ('mobi-huff-recursive.mobi', 'mobi-huff-long-code.mobi', 'mobi-huff-short-code.mobi'):
        r = subprocess.run([probe, 'decode', str(FIX/name), str(tmp/'out')], capture_output=True)
        assert r.returncode == 0, r.stderr

def mobi_group(sdk, probe, tmp):
    html = b'<h1>Caf\xe9</h1><img RECINDEX="1"/><MBP:PAGEBREAK/><h2 id="two">Two</h2><p>tail</p>'
    p, _ = open_bytes(sdk, mobi(html,[png()],1252))
    assert parts(sdk,p) == 2
    assert len(navigation(sdk,p)) == 2
    d, _ = load(sdk,p,0); assert text(sdk,d) == 'Café'
    render(sdk,d); sdk.document_free(d)
    d, _ = load(sdk,p,1); assert text(sdk,d) == 'Two\ntail'; sdk.document_free(d)
    sdk.publication_free(p)
    # A page break between two records must still produce two sections.
    data = records(mobi(b'<p>one</p><mbp:pagebreak/><p>two</p>'))
    raw = data[1]; data[1:2] = [raw[:17],raw[17:]]; struct.pack_into('>H',data[0],8,2)
    p,_ = open_bytes(sdk,pack(data)); assert parts(sdk,p)==2; sdk.publication_free(p)
    p,_ = open_bytes(sdk,mobi('<h1>中文</h1><p>é</p>'.encode()))
    d,_ = load(sdk,p,0); assert text(sdk,d)=='中文\né'; sdk.document_free(d); sdk.publication_free(p)

def progressive(huff=False):
    rs = records((FIX/'kf8-basic.azw3').read_bytes()); h=rs[0]; raw=bytes(rs[1])
    chunks=[raw[i:i+64] for i in range(0,len(raw),64)]; delta=len(chunks)-1
    struct.pack_into('>H',h,8,len(chunks)); struct.pack_into('>H',h,10,64)
    for offset in (192,244,248,252,260):
        v=struct.unpack_from('>I',h,offset)[0]
        if v!=0xffffffff:struct.pack_into('>I',h,offset,v+delta)
    rs=[h,*map(bytearray,chunks),*rs[2:]]
    if huff:
        dictionaries=records((FIX/'mobi-huff.mobi').read_bytes())[3:]
        struct.pack_into('>H',h,0,0x4448); struct.pack_into('>II',h,112,len(rs),len(dictionaries))
        rs+=dictionaries
    return rs, len(chunks)

def kf8_group(sdk, probe, tmp):
    for huff in (False,True):
        rs,last=progressive(huff); rs[last]=rs[last][:-2]
        p,_=open_bytes(sdk,pack(rs))
        d,_=load(sdk,p,0); assert 'Chapter one' in text(sdk,d); render(sdk,d); sdk.document_free(d)
        _,message=load(sdk,p,1,expected=5); assert 'KF8_RECORD_LENGTH' in message
        sdk.publication_free(p)
        rs,_=progressive(huff); p,_=open_bytes(sdk,pack(rs))
        for i in (1,0,1):
            d,_=load(sdk,p,i); assert ('Chapter two' if i else 'Chapter one') in text(sdk,d); sdk.document_free(d)
        sdk.publication_free(p)
    for name in ('kf8-navigation.azw3','kf8-positions.azw3','kf8-assets.azw3'):
        p,_=open_bytes(sdk,(FIX/name).read_bytes())
        for i in range(parts(sdk,p)):
            d,_=load(sdk,p,i); render(sdk,d); sdk.document_free(d)
        sdk.publication_free(p)
    p,_=open_bytes(sdk,(FIX/'kf8-svg.azw3').read_bytes())
    _,msg=load(sdk,p,0,expected=11); assert 'KF8_SVG_BITMAP' in msg; sdk.publication_free(p)
    # An SVG containing one full-frame bitmap must render the actual cover.
    hashes=[]
    for wrapped in (True,False):
        h=records((FIX/'kf8-unsplit.azw3').read_bytes())[0]
        src=b'kindle:flow:0001?mime=image/svg+xml' if wrapped else b'kindle:embed:0001?mime=image/png'
        html=b'<html xmlns="http://www.w3.org/1999/xhtml"><body><img src="'+src+b'"/></body></html>'
        svg=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><image width="8" height="8" href="kindle:embed:0001?mime=image/png"/></svg>'
        raw=html+svg; fdst=b'FDST'+struct.pack('>IIIIII',12,2,0,len(html),len(html),len(raw))
        for off,value in [(4,len(raw)),(108,3),(192,2),(196,2)]:struct.pack_into('>I',h,off,value)
        p,_=open_bytes(sdk,pack([h,raw,fdst,png()]));d,_=load(sdk,p,0);hashes.append(render(sdk,d))
        sdk.document_free(d);sdk.publication_free(p)
    assert hashes[0]==hashes[1], 'SVG bitmap cover became a placeholder'
    # A composed SVG bitmap must fail explicitly instead of rendering a gray box.
    complex_svg=svg.replace(b'<image ',b'<rect width="8" height="8"/><image ',1)
    raw=html.replace(src,b'kindle:flow:0001?mime=image/svg+xml')+complex_svg
    body_length=len(raw)-len(complex_svg)
    struct.pack_into('>I',h,4,len(raw))
    fdst=b'FDST'+struct.pack('>IIIIII',12,2,0,body_length,body_length,len(raw))
    p,_=open_bytes(sdk,pack([h,raw,fdst,png()]));_,msg=load(sdk,p,0,expected=11)
    assert 'KF8_SVG_BITMAP' in msg;sdk.publication_free(p)

def fb2_xml():
    return '''<?xml version="1.0" encoding="UTF-8"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
<description><title-info><book-title>Книга</book-title></title-info></description><body>
<section id="one"><title><p>Глава</p><p>Один</p></title><p>текст</p><image l:href="#img"/>
<section id="two"><title><p>Два</p></title><p><a l:href="#one">назад</a></p></section></section>
<section><title><p>Три</p></title><p>конец</p></section></body><binary id="img" content-type="image/png">%s</binary></FictionBook>''' % base64.b64encode(png()).decode()

def zip_fb2(data, duplicate=False):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('Book.FB2',data)
        if duplicate:z.writestr('second.fb2',data)
    return out.getvalue()

def fb2_group(sdk, probe, tmp):
    xml=fb2_xml(); utf=xml.encode(); cp=xml.replace('UTF-8','windows-1251').encode('cp1251')
    for data in (utf,cp,zip_fb2(utf),zip_fb2(cp)):
        p,_=open_bytes(sdk,data,3); assert parts(sdk,p)==3
        nav=navigation(sdk,p); assert [n['label'] for n in nav]==['Глава\nОдин','Два','Три'],nav
        assert [n['parent'] for n in nav]==[MAX,0,MAX],nav
        d,_=load(sdk,p,0); assert 'текст' in text(sdk,d)
        n=N(); resources=sdk.document_resources(d,c.byref(n)); images=0
        for i,r in enumerate(resources[:n.value]):
            if r.media_type==b'image/png':
                payload=P();size=N();bitmap=Bitmap()
                call(sdk,'document_resource',d,i,c.byref(payload),c.byref(size))
                call(sdk,'image_decode',payload,size,c.byref(bitmap));assert bitmap.width and bitmap.height
                sdk.bitmap_free(c.byref(bitmap));sdk.free(payload);images+=1
        assert images==1; render(sdk,d);sdk.document_free(d);sdk.publication_free(p)

def errors_group(sdk, probe, tmp):
    for name in ('mobi-huff-cycle.mobi','mobi-huff-bad-offset.mobi','mobi-palmdoc-truncated.mobi',
                 'kf8-bad-pointer.azw3','kf8-bad-fdst.azw3','kf8-bad-nav-target.azw3'):
        open_bytes(sdk,(FIX/name).read_bytes(),expected=5)
    data=records(mobi(b'<p>x</p>'));struct.pack_into('>H',data[0],12,2)
    _,msg=open_bytes(sdk,pack(data),expected=11);assert 'MOBI_DRM' in msg
    for name,code in [('mobi-huff-depth-65.mobi',6),('mobi-huff-expansion.mobi',6)]:
        open_bytes(sdk,(FIX/name).read_bytes(),expected=code)
    p,_=open_bytes(sdk,(FIX/'kf8-bad-xml.azw3').read_bytes())
    load(sdk,p,0,expected=5);sdk.publication_free(p)
    p,_=open_bytes(sdk,(FIX/'kf8-zero-fragments.azw3').read_bytes())
    _,msg=load(sdk,p,0,expected=5);assert 'KF8_EMPTY_SECTION' in msg;sdk.publication_free(p)
    open_bytes(sdk,zip_fb2(fb2_xml().encode(),True),3,expected=5)
    open_bytes(sdk,fb2_xml().replace('l:href="#img"','l:href="#missing"').encode(),3,expected=5)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--library',required=True);parser.add_argument('--probe',required=True)
    parser.add_argument('--group',choices=['codec','mobi','kf8','fb2','errors'],required=True);args=parser.parse_args()
    sdk=bind(SDK(Path(args.library).resolve()))
    with tempfile.TemporaryDirectory(prefix='exr-book-') as folder:
        globals()[args.group+'_group'](sdk,str(Path(args.probe).resolve()),Path(folder))
    print(args.group+': passed')
