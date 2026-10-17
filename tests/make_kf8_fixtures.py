#!/usr/bin/env python3
"""Original KF8 skeleton/fragment/TAGX fixtures. No external ebook inputs."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import struct
root=Path(__file__).resolve().parent/'fixtures'
u16=lambda v:struct.pack('>H',v)
u32=lambda v:struct.pack('>I',v)
def vwi(n):
    groups=[n&127]; n>>=7
    while n: groups.append(n&127); n>>=7
    groups.reverse(); groups[-1]|=128
    return bytes(groups)
def indx(entries,fragment=False,multiple=False):
    tags=[(3,1,1,0),(4,1,2,0),(6,2,12,0)] if fragment else [(1,1,1,0),(6,2,6,0)]
    if multiple: tags=[(3,1,1,0),(0,0,0,1),(4,1,1,0),(6,2,6,0)]
    master=bytearray(192); master[:4]=b'INDX'; master[4:8]=u32(192)
    master[24:28]=u32(1); master[28:32]=u32(65001); master[36:40]=u32(len(entries))
    master+=b'TAGX'+u32(12+4*len(tags))+u32(2 if multiple else 1)+b''.join(bytes(t) for t in tags)
    data=bytearray(192); data[:4]=b'INDX'; data[4:8]=u32(192); data[24:28]=u32(len(entries)); offsets=[]
    for label,values in entries:
        offsets.append(len(data)); label=str(label).encode()
        if fragment:
            # Tag6 uses the byte-length mode of a multibit mask.
            payload=b''.join(vwi(x) for x in values[2:])
            control=bytes([1,7]) if multiple else bytes([15])
            row=control+vwi(len(payload))+vwi(values[0])+vwi(values[1])+payload
        else: row=bytes([3])+b''.join(vwi(x) for x in values)
        data+=bytes([len(label)])+label+row
    data+=bytes(2); data[20:24]=u32(len(data)); data+=b'IDXT'+b''.join(map(u16,offsets))
    return [master,data]
def container(name,raw,extras,skel=2,frag=4,flows=1,fdst=0xffffffff,mutate=None,version=8):
    header=bytearray(280); struct.pack_into('>HHIHHHH',header,0,1,0,len(raw),1,4096,0,0)
    header[16:20]=b'MOBI'; header[20:24]=u32(264); header[28:32]=u32(65001)
    header[36:40]=u32(version); header[104:108]=u32(8); header[108:112]=u32(0xffffffff)
    header[192:196]=u32(fdst); header[196:200]=u32(flows); header[244:248]=u32(0xffffffff)
    header[248:252]=u32(frag); header[252:256]=u32(skel); header[260:264]=u32(0xffffffff)
    records=[header,bytearray(raw)]+[bytearray(v) for v in extras]
    if mutate: mutate(records)
    pdb=bytearray(78); pdb[:11]=b'KF8 fixture'; pdb[60:68]=b'BOOKMOBI'; pdb[76:78]=u16(len(records))
    offsets=[]; start=78+8*len(records)
    for r in records: offsets.append(start); start+=len(r)
    (root/name).write_bytes(pdb+b''.join(u32(v)+u32(i) for i,v in enumerate(offsets))+b''.join(records))
skel=b'<html xmlns="http://www.w3.org/1999/xhtml"><head></head><body></body></html>'
body1=b'<h1>Chapter one</h1><p>A <b>bold</b> passage.</p>'
body2=b'<h1>Chapter two</h1><p>Second passage.</p>'
raw=skel+body1+skel+body2
start2=len(skel)+len(body1); insert=skel.index(b'</body>')
sk=[('0',[1,0,len(skel)]),('1',[1,start2,len(skel)])]
fr=[(insert,[0,0,0,len(body1)]),(start2+insert,[1,1,0,len(body2)])]
extras=indx(sk)+indx(fr,True)
container('kf8-basic.azw3',raw,extras)
container('kf8-multicontrol.azw3',raw,indx(sk)+indx(fr,True,True))
container('kf8-unsplit.azw3',skel.replace(b'</body>',body1+b'</body>'),[],0xffffffff,0xffffffff)
css=b'p { color: #123456; }'
fdst=b'FDST'+u32(12)+u32(2)+u32(0)+u32(len(raw))+u32(len(raw))+u32(len(raw)+len(css))
container('kf8-flows.azw3',raw+css,extras+[fdst],flows=2,fdst=6)
# Two insertions in the same skeleton, with positions in the growing output.
first=b'<p>One.</p>'; second=b'<p>Two.</p>'
container('kf8-two-inserts.azw3',skel+first+second,indx([('0',[2,0,len(skel)])])+indx([(insert,[0,0,0,len(first)]),(insert+len(first),[0,1,len(first),len(second)])],True))
container('kf8-zero-fragments.azw3',skel,indx([('0',[0,0,len(skel)])]),frag=0xffffffff)
def bad(name,mutate): container('kf8-bad-'+name+'.azw3',raw,extras,mutate=mutate)
bad('indx',lambda r:r[2].__setitem__(slice(0,4),b'NOPE'))
bad('pointer',lambda r:r[0].__setitem__(slice(252,256),u32(100)))
bad('idxt',lambda r:r[3].__setitem__(slice(-4,-2),u16(1)))
bad('total',lambda r:r[2].__setitem__(slice(36,40),u32(100)))
bad('tagx',lambda r:r[2].__setitem__(slice(192,196),b'NOPE'))
bad('controls',lambda r:r[2].__setitem__(slice(200,204),u32(0)))
bad('mask',lambda r:r[2].__setitem__(210,5))
bad('ordt',lambda r:r[2].__setitem__(slice(164,168),u32(1)))
bad('version',lambda r:r[0].__setitem__(slice(36,40),u32(9)))
for name,skdata,frdata in [
    ('insert-before',sk,[(0,[0,0,0,len(body1)]),fr[1]]),
    ('insert-after',sk,[(9999,[0,0,0,len(body1)]),fr[1]]),
    ('length',sk,[(insert,[0,0,0,9999]),fr[1]]),
    ('file',sk,[(insert,[4,0,0,len(body1)]),fr[1]]),
    ('missing-fragment',[('0',[3,0,len(skel)])],fr),
    ('extra-fragment',[('0',[0,0,len(skel)])],fr),
    ('overlap',[sk[0],('1',[1,0,len(skel)])],fr),
    ('label',sk,[('NaN',[0,0,0,len(body1)]),fr[1]])]:
    if name=='insert-before':
        # First skeleton starts at zero, so test before the second one.
        frdata=[fr[0],(0,[1,1,0,len(body2)])]
    container('kf8-bad-'+name+'.azw3',raw,indx(skdata)+indx(frdata,True))
container('kf8-bad-fdst.azw3',raw+css,extras+[fdst[:-1]],flows=2,fdst=6)

# Split the skeleton index into two data records.
a=indx(sk[:1]); b=indx(sk[1:]); a[0][24:28]=u32(2); a[0][36:40]=u32(2)
container('kf8-multirecord.azw3',raw,a+[b[1]]+indx(fr,True),frag=5)
container('kf8-bad-xml.azw3',b'<html><body>',[],0xffffffff,0xffffffff)
container('kf8-bad-orphan.azw3',raw,extras,skel=0xffffffff)
container('kf8-bad-fdst-gap.azw3',raw+css,extras+[fdst],flows=2,fdst=6,mutate=lambda r:r[6].__setitem__(slice(20,24),u32(len(raw)+1)))
bad('vwi',lambda r:r[5].__setitem__(slice(198,202),bytes(4)))
bad('short-header',lambda r:r[0].__setitem__(slice(20,24),u32(116)))
bad('decreasing-idxt',lambda r:r[3].__setitem__(slice(-2,None),u16(192)))
