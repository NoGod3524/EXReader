#!/usr/bin/env python3
"""Original bitmap-only CBDT/CBLC fixture; no external font/image assets."""
# SPDX-License-Identifier: MIT
from pathlib import Path
import struct
import hashlib
import zipfile
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from generate_bitmap_test_font import png

ROOT = Path(__file__).resolve().parents[1]/'tests/fixtures/fonts'


def main():
    font = TTFont(ROOT/'color.ttf', recalcTimestamp=False, recalcBBoxes=False)
    for tag in ['glyf','loca','COLR','CPAL']:
        del font[tag]
    font['maxp'].tableVersion = 0x00005000
    data = bytearray(struct.pack('>I',0x00030000))
    locations = bytearray(struct.pack('>II',0x00030000,2)+bytes(96))
    for strike, ppem in enumerate((10,20)):
        size = ppem*4//5
        colors = [(255,0,0,255),(255,255,0,128)] if ppem==10 else [(0,255,0,255),(0,0,255,128)]
        image = png(size,colors)
        small = struct.pack('>BBbbB',size,size,ppem//10,ppem*3//5,ppem*9//10)
        big = small+struct.pack('>bbB',-size//2,ppem//10,ppem)
        encoded = struct.pack('>I',len(image))+image
        subtables=[]
        start=len(data);data+=big+encoded
        subtables.append((0,1,struct.pack('>HHIIHHHH',4,18,start,1,0,0,1,len(big+encoded))))
        start=len(data);offsets=[]
        fmt=17 if ppem==10 else 18
        for glyph in range(2,5):
            offsets.append(len(data)-start)
            if glyph==2 or glyph==(3 if ppem==10 else 4):
                data+=(small if fmt==17 else big)+encoded
        offsets.append(len(data)-start)
        index=1 if ppem==10 else 3
        subtables.append((2,4,struct.pack('>HHI',index,fmt,start)+struct.pack('>'+('I' if index==1 else 'H')*len(offsets),*offsets)))
        start=len(data);data+=encoded*2
        subtables.append((5,6,struct.pack('>HHII',2,19,start,len(encoded))+big))
        start=len(data);data+=encoded*2
        subtables.append((7,10,struct.pack('>HHII',5,19,start,len(encoded))+big+struct.pack('>IHH',2,7,10)))
        array = len(locations)
        rows=bytearray();bodies=bytearray()
        for first,last,body in subtables:
            rows+=struct.pack('>HHI',first,last,len(subtables)*8+len(bodies));bodies+=body
        locations+=rows+bodies
        line = struct.pack('>bbB',ppem*4//5,-ppem//5,ppem*9//10)+bytes(9)
        record = struct.pack('>IIII',array,len(locations)-array,len(subtables),0)+line+line
        record += struct.pack('>HHBBBB',0,len(font.getGlyphOrder())-1,ppem,ppem,32,1)
        locations[8+strike*48:8+(strike+1)*48] = record
    for tag, binary in [('CBLC',locations),('CBDT',data)]:
        table=DefaultTable(tag); table.data=bytes(binary); font[tag]=table
    path=ROOT/'cbdt.ttf'; font.save(path)
    print(path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())
    book=ROOT.parent/'cbdt-fonts.epub'
    with zipfile.ZipFile(ROOT.parent/'color-fonts.epub') as source, zipfile.ZipFile(book,'w') as target:
        for info in source.infolist():
            target.writestr(info,path.read_bytes() if info.filename=='OPS/fonts/bitmap.ttf' else source.read(info.filename))
    print(book.name,book.stat().st_size,hashlib.sha256(book.read_bytes()).hexdigest())


if __name__=='__main__':
    main()
