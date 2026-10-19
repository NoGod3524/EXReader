#!/usr/bin/env python3
"""Original tiny MOBI/HUFF fixtures with deterministic PalmDB records."""
# SPDX-License-Identifier: MIT
from pathlib import Path
import struct
root=Path(__file__).resolve().parent/'fixtures'
u16=lambda n:struct.pack('>H',n)
u32=lambda n:struct.pack('>I',n)

def seed(long_code=False,invalid_prefix=False):
    data=bytearray(b'HUFF'+u32(24)+u32(24)+u32(1048)+bytes(8))
    table=[(255<<8)|0x80|8]*256
    if long_code: table[0]=9
    data+=b''.join(map(u32,table))
    limits=[0]*64
    if long_code: limits[16]=1
    if invalid_prefix:
        for i in range(8,32): limits[i*2]=0xffffffff
    data+=b''.join(map(u32,limits))
    return bytes(data)

def dictionaries(phrases,bits=8):
    records=[]
    for start in range(0,len(phrases),1<<bits):
        group=phrases[start:start+(1<<bits)]; payload=bytearray(); offsets=[]
        for content,literal in group:
            offsets.append(2*len(group)+len(payload))
            payload+=u16(len(content)|(0x8000 if literal else 0))+content
        records.append(b'CDIC'+u32(16)+u32(len(phrases))+u32(bits)+b''.join(map(u16,offsets))+payload)
    return records

def mobi(name,text_records,text_size,compression=0x4448,dict_records=None,encoding=65001,flags=0,mutate=None):
    header=bytearray(244)
    struct.pack_into('>HHIHHHH',header,0,compression,0,text_size,len(text_records),4096,0,0)
    header[16:20]=b'MOBI'; header[20:24]=u32(228); header[28:32]=u32(encoding)
    header[36:40]=u32(6); header[104:108]=u32(6); header[242:244]=u16(flags)
    extras=dict_records or []
    if compression==0x4448:
        header[112:116]=u32(1+len(text_records)); header[116:120]=u32(len(extras))
    trailer=(b'\x00' if flags&1 else b'')+b''.join(b'XY\x83' for bit in range(1,16) if flags&(1<<bit))
    records=[bytes(header)]+[r+trailer for r in text_records]+extras
    pdb=bytearray(78); pdb[:11]=b'EXR fixture'; pdb[60:68]=b'BOOKMOBI'; pdb[76:78]=u16(len(records))
    directory=bytearray(); offset=78+len(records)*8
    for i,record in enumerate(records):
        directory+=u32(offset)+u32(i); offset+=len(record)
    output=pdb+directory+b''.join(records)
    if mutate: mutate(output)
    (root/name).write_bytes(output)

phrases=[(bytes([255-i]),True) for i in range(256)]
html=b'<html><body><p>HUFF native reading.</p></body></html>'
normal=[seed()]+dictionaries(phrases)
mobi('mobi-huff.mobi',[html[:23],html[23:]],len(html),dict_records=normal)
mobi('mobi-huff-trailers.mobi',[html[:23],html[23:]],len(html),dict_records=normal,flags=3)
mobi('mobi-huff-split.mobi',[html],len(html),dict_records=[seed()]+dictionaries(phrases,5))
cp=b'<p>Caf\xe9</p>'
mobi('mobi-huff-many-trailers.mobi',[html[:23],html[23:]],len(html),dict_records=normal,flags=7)
short=bytearray(seed())
for i in range(256): short[24+i*4:28+i*4]=u32(((i>>1)<<8)|0x80|7)
mobi('mobi-huff-short-code.mobi',[bytes(1)],1,dict_records=[bytes(short)]+dictionaries([(b'X',True)],0))
mobi('mobi-huff-cp1252.mobi',[cp],len(cp),dict_records=normal,encoding=1252)
recursive=phrases.copy(); recursive[0]=(b'\xfe',False); recursive[1]=(b'<p>Recursive</p>',True)
mobi('mobi-huff-recursive.mobi',[b'\xff'],len(b'<p>Recursive</p>'),dict_records=[seed()]+dictionaries(recursive))
mobi('mobi-huff-long-code.mobi',[bytes(2)],1,dict_records=[seed(True)]+dictionaries([(b'X',True)],0))
for depth in (64,65):
    entries=phrases.copy()
    for i in range(depth): entries[i]=(bytes([254-i]),False)
    entries[depth]=(b'X',True)
    mobi(f'mobi-huff-depth-{depth}.mobi',[b'\xff'],1,dict_records=[seed()]+dictionaries(entries))
cycle=phrases.copy(); cycle[0]=(b'\xff',False)
mobi('mobi-huff-cycle.mobi',[b'\xff'],1,dict_records=[seed()]+dictionaries(cycle))
bomb=phrases.copy()
for i in range(26): bomb[i]=(bytes([254-i])*2,False)
bomb[26]=(b'X',True)
mobi('mobi-huff-expansion.mobi',[b'\xff'],1,dict_records=[seed()]+dictionaries(bomb))
bad=bytearray(seed()); bad[24:28]=u32(0)
mobi('mobi-huff-zero-length.mobi',[html],len(html),dict_records=[bytes(bad)]+dictionaries(phrases))
bad=bytearray(dictionaries(phrases)[0]); bad[16:18]=u16(0)
mobi('mobi-huff-bad-offset.mobi',[html],len(html),dict_records=[seed(),bytes(bad)])
bad=bytearray(dictionaries(phrases)[0]); bad[528:530]=u16(0xffff)
mobi('mobi-huff-truncated-phrase.mobi',[html],len(html),dict_records=[seed(),bytes(bad)])
mobi('mobi-huff-missing-dict.mobi',[html],len(html),dict_records=[seed()])
mobi('mobi-huff-bad-code.mobi',[b'\x00'],1,dict_records=[seed()]+dictionaries([(b'X',True)],0))
mobi('mobi-huff-bad-prefix.mobi',[bytes(8)],1,dict_records=[seed(True,True)]+dictionaries([(b'X',True)],0))
mobi('mobi-raw-trailers.mobi',[html[:23],html[23:]],len(html),compression=1,flags=3)
mobi('mobi-palmdoc-trailers.mobi',[html[:23],html[23:]],len(html),compression=2,flags=3)
mobi('mobi-palmdoc-overlap.mobi',[b'A\x80\x0f'],11,compression=2)
mobi('mobi-palmdoc-cross-record.mobi',[b'A',b'\x80\x08'],4,compression=2)
mobi('mobi-palmdoc-truncated.mobi',[b'\x03a'],3,compression=2)
mobi('mobi-bad-directory.mobi',[html],len(html),compression=1,mutate=lambda b:b.__setitem__(slice(78,82),u32(0)))
mobi('mobi-bad-trailer.mobi',[html+b'\x00'],len(html),compression=1,flags=0,mutate=lambda b:b.__setitem__(slice(94+242,94+244),u16(2)))
