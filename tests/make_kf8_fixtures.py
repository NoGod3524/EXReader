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


# Resource fixtures reuse only the project's original geometric font and tiny images.
import zlib, zipfile, base64, xml.etree.ElementTree as ET
png=base64.b64decode(next(n.text for n in ET.parse(root/'rich.fb2').getroot().iter() if n.tag.endswith('binary')))
with zipfile.ZipFile(root/'layout.epub') as z:
    jpg=z.read(next(n for n in z.namelist() if n.endswith('sample.jpg')))
font=(root/'fonts/fallback.ttf').read_bytes()
def font_record(flags=3):
    content=zlib.compress(font) if flags&1 else font
    key=b'EXReader-key'
    if flags&2: content=bytes(c^(key[i%len(key)] if i<1040 else 0) for i,c in enumerate(content))
    return b'FONT'+u32(len(font))+u32(flags)+u32(24+len(key))+u32(len(key))+u32(24)+key+content
xhtml=(b'<html xmlns="http://www.w3.org/1999/xhtml"><head><link rel="stylesheet" href="kindle:flow:0001?mime=text/css"/>'
       b'<style>p { margin: 0; background-image:url( kindLeLiteral ); } /* kindle:embed:FFFF */</style></head><body>'
       b'<p class="book">'+chr(0x7532).encode()+b'</p><p style="color:#654321; background-image: URL(\'kindle:embed:0001?mime=image/png\')">Image</p>'
       b'<img src="kindle:embed:0001?mime=image/png" width="8" height="8"/>'
       b'<img src="kindle:embed:0002?mime=image/jpeg" width="8" height="8"/>'
       b'<img src="kindle:embed:0001?mime=image/png" width="8" height="8"/>'
       b'<p>Literal kindle:embed:ZZZZ</p></body></html>')
css1=(b'@font-face {font-family:Book;src:URL("kindle:embed:0003")} .book {font-family:Book;color:#123456}'
      b' p { background:url(kindle:flow:0002?mime=text/css); content:"kindle:embed:FFFF"; }'
      b' /* url(kindle:embed:ZZZZ) */')
css2=b'p { background-image:url(kindle:embed:0001?mime=image/png); background:url(kindle:flow:0001?mime=text/css) }'
def asset_fixture(name='kf8-assets.azw3',fontdata=None,xml=None,css=None,mutate=None):
    chunks=[xhtml if xml is None else xml,css1 if css is None else css,css2]
    table=b'FDST'+u32(12)+u32(3); pos=0
    for chunk in chunks: table+=u32(pos)+u32(pos+len(chunk)); pos+=len(chunk)
    def change(r):
        r[0][108:112]=u32(3)
        if mutate: mutate(r)
    container(name,b''.join(chunks),[table,png,jpg,font_record() if fontdata is None else fontdata],
              skel=0xffffffff,frag=0xffffffff,flows=3,fdst=2,mutate=change)
asset_fixture()
for flags in (0,1,2): asset_fixture('kf8-assets-font'+str(flags)+'.azw3',fontdata=font_record(flags))
for name,uri in [('embed-zero','kindle:embed:0'),('embed-range','kindle:embed:FFFF'),
                 ('embed-overflow','kindle:embed:VVVVVVVVVVV'),('embed-bad-number','kindle:embed:WW'),
                 ('flow-zero','kindle:flow:0?mime=text/css'),('flow-range','kindle:flow:3?mime=text/css'),
                 ('flow-mime','kindle:flow:1?mime=image/png'),('flow-conflict','kindle:flow:1?mime=image/svg+xml')]:
    asset_fixture('kf8-bad-'+name+'.azw3',xml=xhtml.replace(b'kindle:embed:0001?mime=image/png',uri.encode()))
asset_fixture('kf8-bad-asset-signature.azw3',mutate=lambda r:r[3].__setitem__(slice(0,8),b'notimage'))
asset_fixture('kf8-bad-asset-pointer.azw3',mutate=lambda r:r[0].__setitem__(slice(108,112),u32(1)))
for name,offset,value in [('font-flags',8,4),('font-offset',12,1),('font-key',16,0),('font-size',4,len(font)+1),('font-key-start',20,99999)]:
    f=bytearray(font_record()); f[offset:offset+4]=u32(value)
    asset_fixture('kf8-bad-'+name+'.azw3',fontdata=f)
asset_fixture('kf8-bad-font-trailing.azw3',fontdata=font_record(1)+b'junk')
f=bytearray(font_record(1)); f[-1]^=255
asset_fixture('kf8-bad-font-compressed.azw3',fontdata=f)
f=bytearray(font_record()); f[4:8]=u32(32*1024*1024+1)
asset_fixture('kf8-limit-font.azw3',fontdata=f)


def b32(n):
    alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUV'; result=''
    while n: result=alphabet[n%32]+result; n//=32
    return result or '0'
def positional(name='kf8-positions.azw3',replacement=None,target=None):
    targetbody=(b'<p>Top.</p><p id="target % # '+chr(0x7532).encode()+b'">Second.</p>'
                b'<a name="legacy"></a><p>Legacy target.</p><p xml:id="xml-target">XML target.</p>'
                b'<p id="shared">Shared second.</p>') if target is None else target
    locations=[('top',0),('forward',targetbody.index(b'<p id=')),
               ('inside',targetbody.index(b'<p id=')+7),('legacy',targetbody.index(b'<a name=')),
               ('xml',targetbody.index(b'<p xml:id=')),('shared',targetbody.index(b'<p id="shared"'))]
    body=b'<p id="shared">First.</p>'
    for key,offset in locations:
        uri='kindle:pos:fid:1:off:'+b32(offset)
        if replacement is not None and key=='forward': uri=replacement
        body+=b'<a data-test="'+key.encode()+b'" href="'+uri.encode()+b'">'+key.encode()+b'</a>'
    body+=b'<a data-test="back" href="kindle:pos:fid:0:off:0">Back.</a>'
    html=skel.replace(b'<body>',b'<body id="body-top">')
    where=html.index(b'</body>'); second=len(html)+len(body)
    skeleton=[('0',[1,0,len(html)]),('1',[1,second,len(html)])]
    fragment=[(where,[0,0,0,len(body)]),(second+where,[1,1,0,len(targetbody)])]
    container(name,html+body+html+targetbody,indx(skeleton)+indx(fragment,True))
positional()
for key,uri in [('fid','kindle:pos:fid:9:off:0'),('off','kindle:pos:fid:1:off:FFFF'),
                ('overflow','kindle:pos:fid:1:off:VVVVVVVVVV'),('separator','kindle:pos:fid:1:off0'),
                ('trailing','kindle:pos:fid:1:off:0?x=1'),('empty','kindle:pos:fid::off:0'),
                ('prefix','kindle:pos:foo'),('length','kindle:pos:fid:1:off:'+b32(9999))]:
    positional('kf8-bad-pos-'+key+'.azw3',replacement=uri)
# Duplicate anchors within a chapter cannot produce an unambiguous translated link.
positional('kf8-bad-pos-duplicate.azw3',target=(b'<p>Top.</p><p id="shared">Second.</p>'
           b'<a name="legacy"></a><p xml:id="xml-target">XML.</p><p id="shared">Duplicate.</p>'))
positional('kf8-bad-pos-body-duplicate.azw3',target=(b'<p>Top.</p><p id="body-top">Second.</p>'
           b'<a name="legacy"></a><p xml:id="xml-target">XML.</p><p id="shared">Shared.</p>'))


# Authored KF8 NCX hierarchy, including a second CNCX record (offset +65536).
def ncx_index(rows,ctoc=2,parents=True,children=True):
    tags=[(3,1,1,0),(4,1,2,0),(6,2,12,0),(21,1,16,0),(22,1,32,0),(23,1,64,0)]
    master=bytearray(192); master[:4]=b'INDX'; master[4:8]=u32(192)
    master[24:28]=u32(1); master[28:32]=u32(65001); master[36:40]=u32(len(rows)); master[52:56]=u32(ctoc)
    master+=b'TAGX'+u32(12+4*len(tags))+u32(1)+b''.join(bytes(t) for t in tags)
    data=bytearray(192); data[:4]=b'INDX'; data[4:8]=u32(192); data[24:28]=u32(len(rows)); offsets=[]
    for i,(title,level,fid,off,parent,first,last) in enumerate(rows):
        offsets.append(len(data)); label=str(i).encode()
        control=7|(16 if parents else 0)|(96 if children else 0)
        values=[title,level,fid,off]+([parent] if parents else [])+([first,last] if children else [])
        data+=bytes([len(label)])+label+bytes([control])+b''.join(vwi(n) for n in values)
    data+=bytes(2); data[20:24]=u32(len(data)); data+=b'IDXT'+b''.join(map(u16,offsets))
    return [master,data]
navbody=(b'<h1 id="chapter-a">Alpha.</h1><h2 id="child-a">Child.</h2>'
         b'<h3 id="deep-a">Deep.</h3><h2 id="child-b">Sibling.</h2>')
navbody2=b'<h1 id="chapter-b">Beta.</h1>'
navraw=skel+navbody+skel+navbody2; navstart=len(skel)+len(navbody)
navbase=indx([('0',[1,0,len(skel)]),('1',[1,navstart,len(skel)])])+indx([(insert,[0,0,0,len(navbody)]),(navstart+insert,[1,1,0,len(navbody2)])],True)
texts=[b'Alpha',b'Child',b'Deep',b'Sibling']; ctoc=bytearray(); keys=[]
for t in texts: keys.append(len(ctoc)); ctoc+=vwi(len(t))+t
ctoc+=bytes(4); label2=('Beta '+chr(0x4e8c)+' & "quotes"').encode(); ctoc2=vwi(len(label2))+label2+bytes(2)
navrows=[(keys[0],0,0,0,0xffffffff,1,3),
         (keys[1],1,0,navbody.index(b'<h2'),0,2,2),
         (keys[2],2,0,navbody.index(b'<h3'),1,0xffffffff,0xffffffff),
         (keys[3],1,0,navbody.index(b'<h2 id="child-b"'),0,0xffffffff,0xffffffff),
         (65536,0,1,0,0xffffffff,0xffffffff,0xffffffff)]
def nav_fixture(name='kf8-navigation.azw3',rows=None,mutate=None,parents=True,children=True):
    def change(r):
        r[0][244:248]=u32(6)
        if mutate: mutate(r)
    container(name,navraw,navbase+ncx_index(navrows if rows is None else rows,parents=parents,children=children)+[ctoc,ctoc2],mutate=change)
nav_fixture(); nav_fixture('kf8-navigation-derived.azw3',parents=False,children=False)
for name,row,col,value in [('nav-title',0,0,999),('nav-level',1,1,3),('nav-parent',2,4,0),
                           ('nav-child',0,5,2),('nav-last',0,6,4),('nav-leaf',4,5,0),('nav-target',4,2,9)]:
    rows=[list(r) for r in navrows]; rows[row][col]=value
    nav_fixture('kf8-bad-'+name+'.azw3',rows=rows)
nav_fixture('kf8-bad-cncx-truncated.azw3',mutate=lambda r:r.__setitem__(8,bytearray(b'\x7f')))
nav_fixture('kf8-bad-cncx-padding.azw3',mutate=lambda r:r[8].__setitem__(-1,1))
nav_fixture('kf8-bad-cncx-index.azw3',mutate=lambda r:r[6].__setitem__(slice(52,56),u32(99)))


# Hybrid containers retain resource records before the BOUNDARY marker.
def read_records(name):
    data=(root/name).read_bytes(); n=struct.unpack_from('>H',data,76)[0]
    starts=[struct.unpack_from('>I',data,78+i*8)[0] for i in range(n)]+[len(data)]
    return [bytearray(data[starts[i]:starts[i+1]]) for i in range(n)]
def write_records(name,records):
    pdb=bytearray(78); pdb[:11]=b'KF8 fixture'; pdb[60:68]=b'BOOKMOBI'; pdb[76:78]=u16(len(records))
    offset=78+8*len(records); directory=bytearray()
    for i,r in enumerate(records): directory+=u32(offset)+u32(i); offset+=len(r)
    (root/name).write_bytes(pdb+directory+b''.join(records))
legacy=b'<p>Legacy fallback.</p>'
def hybrid(name,source='kf8-basic.azw3',shared=0,huff=False,mutate=None):
    modern=read_records(source); resources=[]
    if shared:
        resources=modern[3:3+shared]; del modern[3:3+shared]
    if huff:
        dictionary=read_records('mobi-huff.mobi')[3:]
        modern[0][0:2]=u16(0x4448); modern[0][112:116]=u32(len(modern)); modern[0][116:120]=u32(len(dictionary)); modern+=dictionary
    start=3+len(resources)
    old=bytearray(244); struct.pack_into('>HHIHHHH',old,0,1,0,len(legacy),1,4096,0,0)
    old[16:20]=b'MOBI'; old[20:24]=u32(228); old[28:32]=u32(65001); old[36:40]=u32(6)
    old[104:108]=u32(6); old[108:112]=u32(2 if resources else 0xffffffff); old[128:132]=u32(64)
    old+=b'EXTH'+u32(24)+u32(1)+u32(121)+u32(12)+u32(start)
    records=[old,bytearray(legacy)]+resources+[bytearray(b'BOUNDARY')]+modern
    if mutate: mutate(records,start)
    write_records(name,records)
hybrid('kf8-hybrid.azw3')
hybrid('kf8-hybrid-navigation.azw3','kf8-navigation.azw3')
hybrid('kf8-hybrid-assets.azw3','kf8-assets.azw3',shared=2)
hybrid('kf8-hybrid-all-shared.azw3','kf8-assets.azw3',shared=3)
hybrid('kf8-hybrid-local-assets.azw3','kf8-assets.azw3')
hybrid('kf8-hybrid-huff.azw3','kf8-assets.azw3',shared=2,huff=True)
for name,mutate in [
    ('boundary-pointer',lambda r,k:r[0].__setitem__(slice(-4,None),u32(9999))),
    ('boundary-text',lambda r,k:r[0].__setitem__(slice(-4,None),u32(1))),
    ('boundary-marker',lambda r,k:r[k-1].__setitem__(slice(0,8),b'INVALID!')),
    ('boundary-version',lambda r,k:r[k].__setitem__(slice(36,40),u32(6))),
    ('boundary-encrypted',lambda r,k:r[k].__setitem__(slice(12,14),u16(1))),
    ('boundary-resource',lambda r,k:r[0].__setitem__(slice(108,112),u32(1))),
    ('exth-signature',lambda r,k:r[0].__setitem__(slice(244,248),b'NOPE')),
    ('exth-length',lambda r,k:r[0].__setitem__(slice(248,252),u32(9999))),
    ('exth-count',lambda r,k:r[0].__setitem__(slice(252,256),u32(99))),
    ('exth-entry',lambda r,k:r[0].__setitem__(slice(260,264),u32(7))),
    ('exth-entry-size',lambda r,k:r[0].__setitem__(slice(260,264),u32(11)))]:
    hybrid('kf8-bad-'+name+'.azw3',mutate=mutate)
def duplicate_exth(records,start):
    records[0][248:252]=u32(36); records[0][252:256]=u32(2)
    records[0]+=u32(121)+u32(12)+u32(start)
hybrid('kf8-bad-exth-duplicate.azw3',mutate=duplicate_exth)
# Explicit absent boundary keeps the ordinary MOBI decoder.
hybrid('kf8-legacy-exth.azw3',mutate=lambda r,k:r[0].__setitem__(slice(-4,None),u32(0xffffffff)))

hybrid('kf8-bad-exth-fallback-encoding.azw3',mutate=lambda r,k:(r[0].__setitem__(slice(-4,None),u32(0xffffffff)),r[0].__setitem__(slice(28,32),u32(65002))))
hybrid('kf8-bad-exth-fallback-compression.azw3',mutate=lambda r,k:(r[0].__setitem__(slice(-4,None),u32(0xffffffff)),r[0].__setitem__(slice(0,2),u16(999))))


def guide_index(rows,extended=False):
    tags=[(1,1,1,0),(6 if extended else 3,2 if extended else 1,2,0)]
    master=bytearray(192); master[:4]=b'INDX'; master[4:8]=u32(192)
    master[24:28]=u32(1); master[28:32]=u32(65001); master[36:40]=u32(len(rows)); master[52:56]=u32(1)
    master+=b'TAGX'+u32(12+4*len(tags))+u32(1)+b''.join(bytes(t) for t in tags)
    data=bytearray(192); data[:4]=b'INDX'; data[4:8]=u32(192); data[24:28]=u32(len(rows)); offsets=[]
    for kind,title,fid,off in rows:
        offsets.append(len(data)); label=kind.encode()
        data+=bytes([len(label)])+label+b'\x03'+vwi(title)+vwi(fid)+(vwi(off) if extended else b'')
    data+=bytes(2); data[20:24]=u32(len(data)); data+=b'IDXT'+b''.join(map(u16,offsets))
    return [master,data]
guide_text=bytearray(); guide_keys=[]
for t in [b'Cover',b'Read from here',b'Other & custom',b'Thumbnail']:
    guide_keys.append(len(guide_text)); guide_text+=vwi(len(t))+t
rows=[('cover',guide_keys[0],0,0),('start',guide_keys[1],1,0),('other:preface',guide_keys[2],0,0),('thumbimagestandard',guide_keys[3],0xffffffff,0)]
def guide_fixture(name='kf8-guide.azw3',with_ncx=True,extended=False,values=None):
    records=read_records('kf8-navigation.azw3' if with_ncx else 'kf8-basic.azw3')
    records[0][260:264]=u32(len(records))
    records+=guide_index(rows if values is None else values,extended)+[guide_text]
    write_records(name,records)
guide_fixture(); guide_fixture('kf8-guide-only.azw3',with_ncx=False)
extra=[list(r) for r in rows]; extra[2][3]=navbody.index(b'<h3')
guide_fixture('kf8-guide-offset.azw3',extended=True,values=extra)
hybrid('kf8-hybrid-guide.azw3','kf8-guide.azw3')
for name,column,value in [('guide-label',1,9999),('guide-target',2,9),('guide-kind',0,'')]:
    badrows=[list(r) for r in rows]; badrows[0][column]=value
    guide_fixture('kf8-bad-'+name+'.azw3',values=badrows)
badrows=[list(r) for r in rows]; badrows[0][0]='bad'+chr(1)
guide_fixture('kf8-encoding-guide.azw3',values=badrows)

guide_fixture('kf8-guide-budget.azw3',with_ncx=False,values=[('x',0,0,0)]*9998)
guide_fixture('kf8-limit-guide.azw3',with_ncx=False,values=[('x',0,0,0)]*10000)


svg_xml=(b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:other="urn:exreader:extension" width="2" height="2">'
         b'<style><![CDATA[image {background:url(kindle:embed:0002?mime=image/jpeg)}]]></style>'
         b'<other:style>url(kindle:embed:FFFF)</other:style><local xmlns="">Unnamespaced</local>'
         b'<image xlink:href="kindle:embed:0001?mime=image/png" width="2" height="2" style="fill:url(\'kindle:embed:0001?mime=image/png\')"/>'
         b'<use href="kindle:flow:3?mime=image/svg+xml#symbol%20%25"/>'
         b'<metadata>Literal kindle:embed:ZZZZ</metadata></svg>')
svg_cycle=b'<svg xmlns="http://www.w3.org/2000/svg"><use href="kindle:flow:2?mime=image/svg+xml"/></svg>'
svg_main=(b'<html xmlns="http://www.w3.org/1999/xhtml"><head><link rel="stylesheet" href="kindle:flow:1?mime=text/css"/></head>'
          b'<body><p class="book">'+chr(0x7532).encode()+b'</p><img src="kindle:flow:2?mime=image/svg+xml" width="12" height="12"/></body></html>')
svg_css=b'@font-face {font-family:Book;src:url(kindle:embed:3)} .book{font-family:Book;color:#123456}'
def svg_fixture(name='kf8-svg.azw3',svg=None):
    chunks=[svg_main,svg_css,svg_xml if svg is None else svg,svg_cycle]; table=b'FDST'+u32(12)+u32(4); pos=0
    for chunk in chunks: table+=u32(pos)+u32(pos+len(chunk)); pos+=len(chunk)
    container(name,b''.join(chunks),[table,png,jpg,font_record()],skel=0xffffffff,frag=0xffffffff,flows=4,fdst=2,
              mutate=lambda r:r[0].__setitem__(slice(108,112),u32(3)))
svg_fixture(); hybrid('kf8-hybrid-svg.azw3','kf8-svg.azw3',shared=2)
svg_fixture('kf8-bad-svg-xml.azw3',svg=b'<svg><image>')
svg_fixture('kf8-bad-svg-root.azw3',svg=b'<html/>')
svg_fixture('kf8-bad-svg-entity.azw3',svg=b'<!DOCTYPE svg [<!ENTITY x "forbidden">]><svg>&x;</svg>')
svg_fixture('kf8-bad-svg-reference.azw3',svg=svg_xml.replace(b'kindle:embed:0001',b'kindle:embed:FFFF'))

svg_fixture('kf8-bad-svg-namespace.azw3',svg=b'<svg xmlns="urn:wrong"/>')
svg_fixture('kf8-bad-svg-fragment.azw3',svg=svg_xml.replace(b'#symbol%20%25',b'#symbol%XX'))
