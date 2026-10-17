#!/usr/bin/env python3
"""Development oracle: fontTools/Pillow CBDT pixels and HarfBuzz emoji shaping.

Usage: python check_bitmap_reference.py shared_library cbdt_font [emoji-test.txt]
Dependencies are for this check only, never part of the SDK.
"""
# SPDX-License-Identifier: GPL-3.0-only
import ctypes as c
import hashlib
import io
from pathlib import Path
import sys
from fontTools.ttLib import TTFont
from PIL import Image

P,Z,U,F=c.c_void_p,c.c_size_t,c.c_uint32,c.c_float
class Error(c.Structure):
    _fields_=[('code',c.c_int),('message',c.c_char*256)]
class Bitmap(c.Structure):
    _fields_=[('width',U),('height',U),('stride',U),('pixels',P),('channels',U)]
class GlyphImage(c.Structure):
    _fields_=[('bitmap',Bitmap),('left',F),('top',F),('scale',F),('flags',U)]
class Control(c.Structure):
    _fields_=[('cancelled',P),('progress',P),('context',P)]
class Options(c.Structure):
    _fields_=[('font_size',F),('style_flags',U),('direction',c.c_int),('script',U),('language',U),
              ('features',P),('feature_count',Z),('context_before',U),('context_after',U),('control',Control)]
class Glyph(c.Structure):
    _fields_=[('start',Z),('end',Z),('glyph',U),('advance_x',F),('advance_y',F),('offset_x',F),('offset_y',F),('flags',U)]

def main():
    if len(sys.argv) not in (3,4):
        raise SystemExit(__doc__)
    dll=c.CDLL(str(Path(sys.argv[1]).resolve()))
    dll.exr_font_open.argtypes=[c.c_char_p,c.POINTER(P),c.POINTER(Error)]
    dll.exr_font_glyph_image.argtypes=[P,Z,U,F,c.POINTER(GlyphImage),P,c.POINTER(Error)]
    dll.exr_bitmap_free.argtypes=[c.POINTER(Bitmap)]
    dll.exr_font_free.argtypes=[P];dll.exr_free.argtypes=[P]
    dll.exr_shape_defaults.restype=Options
    dll.exr_shape.argtypes=[P,Z,c.c_char_p,Z,c.POINTER(Options),c.POINTER(c.POINTER(Glyph)),c.POINTER(Z),c.POINTER(Error)]
    path=Path(sys.argv[2]);font=P();error=Error();data=path.read_bytes()
    assert dll.exr_font_open(str(path).encode('utf-8'),c.byref(font),c.byref(error))==0,error.message
    try:
        source=TTFont(path);strikes=source['CBLC'].strikes
        # One strike avoids reference ambiguity when glyph coverage differs.
        assert len(strikes)==1,'Reference font must have one strike'
        ppem=strikes[0].bitmapSizeTable.ppemY;records=source['CBDT'].strikeData[0];count=0
        for gid,name in enumerate(source.getGlyphOrder()):
            frame=GlyphImage()
            assert dll.exr_font_glyph_image(font,0,gid,ppem,c.byref(frame),None,c.byref(error))==0,(gid,error.message)
            try:
                if name in records:
                    record=records[name];record.ensureDecompiled();image=Image.open(io.BytesIO(record.imageData)).convert('RGBA')
                    assert (frame.bitmap.width,frame.bitmap.height)==image.size,(gid,'size')
                    assert c.string_at(frame.bitmap.pixels,frame.bitmap.stride*frame.bitmap.height)==image.tobytes(),(gid,'pixels')
                    assert (frame.left,frame.top,frame.scale)==(record.metrics.BearingX,-record.metrics.BearingY,1),(gid,'bearing')
                    count+=1
                else:
                    assert not frame.bitmap.pixels,(gid,'absent')
            finally:
                dll.exr_bitmap_free(c.byref(frame.bitmap))
        print('Pixel-exact CBDT images:',count,'of',source['maxp'].numGlyphs,'glyphs; SHA-256',hashlib.sha256(data).hexdigest())
        if len(sys.argv)==4:
            import uharfbuzz as hb
            oracle=hb.Font(hb.Face(data));oracle.scale=(6400,6400);count=0
            for line in Path(sys.argv[3]).read_text(encoding='utf-8').splitlines():
                if '; fully-qualified' not in line:
                    continue
                text=''.join(chr(int(cp,16)) for cp in line.split(';')[0].split()).encode('utf-8')
                options=dll.exr_shape_defaults();options.font_size=100;out=c.POINTER(Glyph)();n=Z()
                assert dll.exr_shape(font,0,text,len(text),c.byref(options),c.byref(out),c.byref(n),c.byref(error))==0,error.message
                try:
                    buffer=hb.Buffer();buffer.add_utf8(text);buffer.guess_segment_properties();hb.shape(oracle,buffer)
                    actual=[(out[i].glyph,out[i].advance_x,out[i].advance_y,out[i].offset_x,out[i].offset_y) for i in range(n.value) if not (out[i].flags&4)]
                    expected=[(g.codepoint,p.x_advance/64,p.y_advance/64,p.x_offset/64,p.y_offset/64) for g,p in zip(buffer.glyph_infos,buffer.glyph_positions)]
                    assert len(actual)==len(expected) and all(a[0]==b[0] and all(abs(x-y)<.02 for x,y in zip(a[1:],b[1:])) for a,b in zip(actual,expected)),(text,actual,expected)
                    count+=1
                finally:
                    dll.exr_free(out)
            print('HarfBuzz-matched fully qualified emoji:',count)
    finally:
        dll.exr_font_free(font)

if __name__=='__main__':
    main()
