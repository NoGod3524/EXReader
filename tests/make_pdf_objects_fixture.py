#!/usr/bin/env python3
"""Original PDF object/xref/stream fixtures; no external PDF inputs."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import zlib
import base64
root=Path(__file__).resolve().parent/'fixtures'
payload=b'BT /F1 12 Tf (Hello native PDF.) Tj ET\n'
raw=b'Raw\0\nendstream-not-a-token\n'
def objects(data=None,filter=b'/FlateDecode',parameters=b'',literal=None):
    encoded=zlib.compress(payload) if data is None else data
    stream=b'<< /Length 8 0 R'+(b' /Filter '+filter if filter else b'')+(b' /DecodeParms '+parameters if parameters else b'')+b' >>\nstream\n'+encoded+b'\nendstream'
    values=b'<< /Esc#61pedName /A#20B /Text (a\\(b\\)\\101\\nline\\\r\ncontinued\r\nend) /Nested (nested (inner)) /Hex <41 42 4> /UTF16 <FEFF4E8C> /Null null /Bool true /Values [-2 .5 1.25 0 5 0 R] /Duplicate 1 /Duplicate 2 /I64 9223372036854775807 /Min -9223372036854775808 >>'
    return {1:b'<< /Type /Catalog /Pages 2 0 R /Flate 4 0 R /Data 5 0 R /Cycle 6 0 R /WrongGeneration 9 1 R /Unknown 999 0 R /Raw 10 0 R >>',
            2:b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',3:b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] >>',
            4:stream,5:values if literal is None else literal,6:b'7 0 R',7:b'6 0 R',8:str(len(encoded)).encode(),
            9:b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',10:b'<< /Length '+str(len(raw)).encode()+b' >>\nstream\n'+raw+b'\nendstream'}
def pdf(name,values=None,trailer=b'',mutate=None):
    values=objects() if values is None else values; data=bytearray(b'%PDF-1.7\n%\x80\x81\x82\x83\n'); offsets={}
    for i,value in sorted(values.items()): offsets[i]=len(data); data+=str(i).encode()+b' 0 obj\n'+value+b'\nendobj\n'
    xref=len(data); size=max(values)+1;data+=b'xref\n0 '+str(size).encode()+b'\n0000000000 65535 f \n'
    for i in range(1,size): data+=f'{offsets[i]:010d} 00000 n \n'.encode() if i in offsets else b'0000000000 00000 f \n'
    data+=b'trailer\n<< /Size '+str(size).encode()+b' /Root 1 0 R '+trailer+b' >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n'
    if mutate: mutate(data,xref,offsets)
    (root/name).write_bytes(data); return data,xref
base,base_xref=pdf('pdf-objects.pdf')
def incremental(name,previous=None,rootref=True,deleted=True,size=12,extra=11):
    data=bytearray(base); offsets={}
    for i,value in [(1,b'<< /Type /Catalog /Pages 2 0 R /Revision (Updated) /Deleted 9 0 R /Extra '+str(extra).encode()+b' 0 R >>'),(extra,b'(Extra object)')]:
        offsets[i]=len(data);data+=str(i).encode()+b' 0 obj\n'+value+b'\nendobj\n'
    xref=len(data);data+=b'xref\n1 1\n'+f'{offsets[1]:010d} 00000 n \n'.encode()
    if deleted: data+=b'9 1\n0000000000 00001 f \n'
    data+=str(extra).encode()+b' 1\n'+f'{offsets[extra]:010d} 00000 n \n'.encode()
    prev=xref if previous=='self' else base_xref if previous is None else previous
    data+=b'trailer\n<< /Size '+str(size).encode()+(b' /Root 1 0 R' if rootref else b'')+b' /Prev '+str(prev).encode()+b' >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n'
    (root/name).write_bytes(data)
incremental('pdf-incremental.pdf');incremental('pdf-incremental-inherit.pdf',rootref=False)
incremental('pdf-bad-prev-cycle.pdf','self');incremental('pdf-bad-prev-offset.pdf',999999)
pdf('pdf-objects-predictor-one.pdf',values=objects(parameters=b'<< /Predictor 1 >>'))
pdf('pdf-bad-encrypted.pdf',trailer=b'/Encrypt 9 0 R')
pdf('pdf-bad-hybrid.pdf',trailer=b'/XRefStm 9')
pdf('pdf-bad-xref-offset.pdf',mutate=lambda d,x,o:d.__setitem__(slice(x+len(b'xref\n0 11\n')+20,x+len(b'xref\n0 11\n')+30),f'{o[1]+1:010d}'.encode()))
pdf('pdf-bad-header.pdf',mutate=lambda d,x,o:d.__setitem__(7,ord('9')))
pdf('pdf-bad-eof.pdf',mutate=lambda d,x,o:d.__setitem__(slice(-6,-1),b'BAD!!'))
pdf('pdf-bad-startxref.pdf',mutate=lambda d,x,o:d.__setitem__(slice(d.rfind(b'startxref')),b'startxref\n999999\n%%EOF\n'))
pdf('pdf-bad-root-type.pdf',values={**objects(),1:b'<< /Type /Page >>'})
pdf('pdf-bad-root-direct.pdf',trailer=b'/Root << /Type /Catalog >>')
pdf('pdf-bad-size.pdf',trailer=b'/Size 2')
pdf('pdf-bad-token.pdf',values={**objects(),1:b'<< /Type /Catalog /Unknown not-a-value >>'})
pdf('pdf-bad-root-reference.pdf',trailer=b'/Root 999 0 R')
pdf('pdf-bad-generation.pdf',trailer=b'/Root 1 1 R')
pdf('pdf-bad-string.pdf',values={**objects(),1:b'<< /Type /Catalog /Text (Unterminated >>'})
pdf('pdf-bad-key.pdf',values={**objects(),1:b'<< /Type /Catalog (not a name) 1 >>'})
pdf('pdf-bad-hex.pdf',values={**objects(),1:b'<< /Type /Catalog /Text <QQ> >>'})
pdf('pdf-bad-nesting.pdf',values={**objects(),1:b'<< /Type /Catalog /Deep '+b'['*130+b'0'+b']'*130+b' >>'})
pdf('pdf-bad-string-depth.pdf',values={**objects(),1:b'<< /Type /Catalog /Deep '+b'('*129+b'X'+b')'*129+b' >>'})
pdf('pdf-stream-invalid-length.pdf',values={**objects(),8:b'999999'})
pdf('pdf-stream-cycle-length.pdf',values={**objects(),8:b'4 0 R'})
compressed=bytearray(zlib.compress(payload));compressed[-1]^=255
pdf('pdf-stream-bad-flate.pdf',values=objects(data=compressed))
pdf('pdf-stream-unsupported-filter.pdf',values=objects(filter=b'/DCTDecode'))
pdf('pdf-stream-bad-parameters.pdf',values=objects(parameters=b'/Invalid'))
pdf('pdf-stream-unsupported-predictor.pdf',values=objects(parameters=b'<< /Predictor 12 >>'))
pdf('pdf-stream-trailing.pdf',values=objects(data=zlib.compress(payload)+b'junk'))
pdf('pdf-stream-whitespace.pdf',values=objects(data=zlib.compress(payload)+b'\n\r '))
pdf('pdf-stream-expansion.pdf',values=objects(data=zlib.compress(b'X'*(64*1024*1024+1),9)))

pdf('pdf-bad-integer.pdf',values={**objects(),1:b'<< /Type /Catalog /Number 9223372036854775808 >>'})


# Modern cross-reference streams and compressed objects. Reuse the scalar/stream
# checks above so both container encodings must produce the same object graph.
def modern(name, compressed=True, hybrid=False, widths=(1,4,2), index=None, damage=None, zipped=True, object_header=None, object_body=None, stream_extra=b'', append_to=None, predictor=False):
    values=objects(); members=[1,2,3,5,8,9] if compressed else []
    body=bytearray(); pairs=[]
    for number in members:
        pairs.append((number,len(body))); body+=values.pop(number)+b'\n'
    header=b''.join(f'{number} {offset} '.encode() for number,offset in pairs)
    if object_header is not None: header=object_header
    if object_body is not None: body=object_body
    if members:
        packed=zlib.compress(header+body)
        values[11]=b'<< /Type /ObjStm /N '+str(len(members)).encode()+b' /First '+str(len(header)).encode()+b' /Filter /FlateDecode /Length '+str(len(packed)).encode()+b' >>\nstream\n'+packed+b'\nendstream'
    data=bytearray(b'%PDF-1.7\n%\x80\x81\x82\x83\n' if append_to is None else append_to[0]); offsets={}
    for number,value in sorted(values.items()):
        offsets[number]=len(data);data+=f'{number} 0 obj\n'.encode()+value+b'\nendobj\n'
    xref=len(data);offsets[12]=xref
    entries={0:(0,0,65535)}
    for number in range(1,13):
        entries[number]=(2,11,members.index(number)) if number in members else (1,offsets[number],0) if number in offsets else (0,0,0)
    ranges=[0,13] if index is None else index
    if damage: damage(entries)
    stream=bytearray()
    for at in range(0,len(ranges)-1,2):
        for number in range(ranges[at],ranges[at]+ranges[at+1]):
            for field,width in zip(entries.get(number,(0,0,0)),widths):
                if width: stream+=field.to_bytes(width,'big')
    if predictor:
        stride=sum(widths); predicted=bytearray(); previous=bytes(stride)
        for offset in range(0,len(stream),stride):
            row=stream[offset:offset+stride]; predicted.append(2)
            predicted+=bytes((a-b)&255 for a,b in zip(row,previous)); previous=row
        stream=predicted
        stream_extra+=b'/DecodeParms << /Predictor 12 /Columns '+str(stride).encode()+b' >>'
    encoded=zlib.compress(stream) if zipped else stream
    dictionary=b'<< /Type /XRef /Size 13 /Root 1 0 R /W ['+b' '.join(str(w).encode() for w in widths)+b']'
    if index is not None: dictionary+=b' /Index ['+b' '.join(str(x).encode() for x in index)+b']'
    dictionary+=stream_extra
    if append_to is not None: dictionary+=b' /Prev '+str(append_to[1]).encode()
    dictionary+=(b' /Filter /FlateDecode' if zipped else b'')+b' /Length '+str(len(encoded)).encode()+b' >>'
    data+=b'12 0 obj\n'+dictionary+b'\nstream\n'+encoded+b'\nendstream\nendobj\n'
    if hybrid:
        table=len(data); data+=b'xref\n0 13\n0000000000 65535 f \n'
        for number in range(1,13): data+=f'{offsets[number]:010d} 00000 n \n'.encode() if number in offsets else b'0000000000 00000 f \n'
        data+=b'trailer\n<< /Size 13 /Root 1 0 R /XRefStm '+str(xref).encode()+b' >>\n'
        xref=table
    data+=b'startxref\n'+str(xref).encode()+b'\n%%EOF\n'
    (root/name).write_bytes(data)
    return data,xref
modern('pdf-xref-stream.pdf',compressed=False)
modern('pdf-object-stream.pdf')
modern('pdf-hybrid.pdf',hybrid=True)
modern('pdf-xref-index.pdf',index=[0,4,4,9])
modern('pdf-xref-wide.pdf',widths=(2,8,4),zipped=False)
modern('pdf-xref-default-type.pdf',compressed=False,widths=(0,4,0),index=[1,10,12,1],zipped=False)
modern('pdf-bad-xref-width.pdf',widths=(1,9,2))
modern('pdf-bad-xref-overlap.pdf',index=[0,4,3,10])
modern('pdf-bad-xref-odd-index.pdf',index=[0,4,4])
modern('pdf-bad-xref-generation.pdf',damage=lambda e:e.__setitem__(1,(1,9,65536)),widths=(1,4,4))
modern('pdf-bad-object-stream-number.pdf',damage=lambda e:e.__setitem__(1,(2,11,1)))
modern('pdf-bad-object-stream-index.pdf',damage=lambda e:e.__setitem__(1,(2,11,99)))
modern('pdf-bad-object-stream-self.pdf',damage=lambda e:e.__setitem__(11,(2,11,0)))
modern('pdf-bad-object-stream-missing.pdf',damage=lambda e:e.__setitem__(1,(2,10,0)))

modern('pdf-bad-object-header-duplicate.pdf',object_header=b'1 0 1 500 3 600 5 700 8 800 9 900 ')
modern('pdf-bad-object-header-offset.pdf',object_header=b'1 999999 2 0 3 1 5 2 8 3 9 4 ')
modern('pdf-bad-object-header-order.pdf',object_header=b'1 0 2 0 3 1 5 2 8 3 9 4 ')
modern('pdf-bad-object-header-tail.pdf',object_header=b'1 0 2 1 3 2 5 3 8 4 9 5 junk')
modern('pdf-bad-object-body.pdf',object_body=b'not-a-value')
modern('pdf-bad-xref-indirect.pdf',stream_extra=b'/DecodeParms 9 0 R')
modern('pdf-bad-xref-empty-index.pdf',index=[])
modern('pdf-bad-xref-size.pdf',stream_extra=b'/Size 2')
modern('pdf-bad-xref-nested-hybrid.pdf',stream_extra=b'/XRefStm 9')
modern('pdf-stream-after-classic.pdf',append_to=(base,base_xref))
saved_base,saved_xref=base,base_xref
base,base_xref=modern('pdf-compressed-incremental-base.pdf')
incremental('pdf-classic-after-stream.pdf',size=14,extra=13)
base,base_xref=saved_base,saved_xref


# Filter pipelines, PNG byte filters and packed TIFF horizontal prediction.
def encoded_stream(name,data,filter,parameters=b''):
    pdf('pdf-filter-'+name+'.pdf',values=objects(data=data,filter=filter,parameters=parameters))
def png_encode(rows):
    encoded=bytearray(); previous=bytes(len(rows[0]))
    for kind,row in enumerate(rows):
        encoded.append(kind)
        for x,value in enumerate(row):
            left=row[x-1] if x else 0; up=previous[x]; upper_left=previous[x-1] if x else 0
            p=left+up-upper_left; a,b,c=abs(p-left),abs(p-up),abs(p-upper_left)
            paeth=left if a<=b and a<=c else up if b<=c else upper_left
            add=[0,left,up,(left+up)//2,paeth][kind]
            encoded.append((value-add)&255)
        previous=row
    return bytes(encoded)
encoded_stream('hex',payload.hex().encode()+b'>',b'/ASCIIHexDecode')
encoded_stream('hex-odd',b'4 1 4>',b'/AHx')
encoded_stream('a85',base64.a85encode(payload)+b'~>',b'/ASCII85Decode')
for count in range(1,5): encoded_stream('a85-tail'+str(count),base64.a85encode(bytes(count))+b'~>',b'/A85')
encoded_stream('runlength',bytes([len(payload)-1])+payload+b'\x80',b'/RunLengthDecode')
encoded_stream('repeat',b'\x81X\x80',b'/RL')
encoded_stream('chain',base64.a85encode(zlib.compress(payload))+b'~>',b'[/A85 /Fl]',b'[null null]')
encoded_stream('chain-hex',base64.a85encode(payload.hex().encode()+b'>')+b'~>',b'[/A85 /AHx]')
encoded_stream('empty-array',payload,b'[]',b'[]')
encoded_stream('empty-hex',b'>',b'/AHx')
encoded_stream('png',zlib.compress(png_encode([payload]*5)),b'/Fl',b'<< /Predictor 15 /Columns '+str(len(payload)).encode()+b' >>')
encoded_stream('png-chain',base64.a85encode(zlib.compress(png_encode([payload]*5)))+b'~>',b'[/A85 /Fl]',b'[null << /Predictor 12 /Columns '+str(len(payload)).encode()+b' >>]')
encoded_stream('tiff8',zlib.compress(bytes((v-(payload[i-1] if i else 0))&255 for i,v in enumerate(payload))),b'/Fl',b'<< /Predictor 2 /Columns '+str(len(payload)).encode()+b' >>')
def pack(samples,bits):
    value=0
    for sample in samples: value=(value<<bits)|sample
    padding=(-len(samples)*bits)%8
    return (value<<padding).to_bytes((len(samples)*bits+7)//8,'big')
for bits in [1,2,4,16]:
    samples=[1,0,(1<<bits)-1,1,0,1]; colors=2
    predicted=[(v-(samples[i-colors] if i>=colors else 0))% (1<<bits) for i,v in enumerate(samples)]
    encoded_stream('tiff'+str(bits),zlib.compress(pack(predicted,bits)),b'/Fl',f'<< /Predictor 2 /Colors 2 /Columns 3 /BitsPerComponent {bits} >>'.encode())
encoded_stream('png-short',zlib.compress(b'\0AB'),b'/Fl',b'<< /Predictor 15 /Columns 3 >>')
encoded_stream('png-bad-tag',zlib.compress(b'\5ABC'),b'/Fl',b'<< /Predictor 15 /Columns 3 >>')
encoded_stream('tiff-short',zlib.compress(b'AB'),b'/Fl',b'<< /Predictor 2 /Columns 3 >>')
for name,parameters in [('bits',b'<< /Predictor 2 /BitsPerComponent 3 >>'),('colors',b'<< /Predictor 2 /Colors 0 >>'),('columns',b'<< /Predictor 2 /Columns 0 >>'),('predictor',b'<< /Predictor 3 >>')]:
    encoded_stream('bad-'+name,zlib.compress(payload),b'/Fl',parameters)
for name,data,filter,params in [('bad-hex',b'GG>',b'/AHx',b''),('hex-tail',b'41>junk',b'/AHx',b''),('hex-end',b'41',b'/AHx',b''),('a85-overflow',b'uuuuu~>',b'/A85',b''),('a85-z',b'!z~>',b'/A85',b''),('a85-one',b'!~>',b'/A85',b''),('a85-tail',b'z~>junk',b'/A85',b''),('a85-end',b'!!',b'/A85',b''),('rl-short',b'\x02AB',b'/RL',b''),('rl-repeat',b'\xff',b'/RL',b''),('rl-end',b'\0A',b'/RL',b''),('rl-tail',b'\x80junk',b'/RL',b''),('params-short',b'',b'[/A85 /Fl]',b'[null]'),('params-shape',b'',b'[/A85 /Fl]',b'<< >>'),('filter-value',b'',b'[42]',b''),('filter-depth',b'',b'['+b'/Fl '*17+b']',b'')]:
    encoded_stream(name,data,filter,params)

modern('pdf-xref-predictor.pdf',predictor=True)
modern('pdf-hybrid-predictor.pdf',hybrid=True,predictor=True)


# Original LZW encoder; bit widths follow the emitted-data-code count, separately
# from the reader's prefix/suffix dictionary growth.
def lzw_codes(codes,early=1):
    buffer=0; bitcount=0; output=bytearray(); emitted=0
    for code in codes:
        width=next((w for w in range(9,12) if emitted<(1<<w)-257-early),12)
        buffer=(buffer<<width)|code;bitcount+=width
        while bitcount>=8:
            bitcount-=8;output.append((buffer>>bitcount)&255)
        if code==256: emitted=0
        elif code!=257: emitted+=1
    if bitcount: output.append((buffer<<(8-bitcount))&255)
    return bytes(output)
def lzw_encode(data,early=1):
    table={bytes([i]):i for i in range(256)};codes=[256];word=b''
    for byte in data:
        candidate=word+bytes([byte])
        if candidate in table: word=candidate
        else:
            codes.append(table[word])
            if len(table)<4094: table[candidate]=len(table)+2
            word=bytes([byte])
    if word:codes.append(table[word])
    return lzw_codes(codes+[257],early)
encoded_stream('lzw',lzw_encode(payload),b'/LZWDecode')
encoded_stream('lzw-special',lzw_encode(b'A'*1000),b'/LZW')
for early in [0,1]:
    params=f'<< /EarlyChange {early} >>'.encode()
    encoded_stream('lzw-wide'+str(early),lzw_codes([256]+[i%256 for i in range(10000)]+[257],early),b'/LZW',params)
    encoded_stream('lzw-dictionary'+str(early),lzw_encode(bytes(i%251 for i in range(20000)),early),b'/LZW',params)
    encoded_stream('lzw-reset'+str(early),lzw_codes([256]+[i%256 for i in range(1000)]+[256]+[i%256 for i in range(1000)]+[257],early),b'/LZW',params)
encoded_stream('lzw-png',lzw_encode(png_encode([payload]*5)),b'/LZW',b'<< /Predictor 15 /Columns '+str(len(payload)).encode()+b' >>')
encoded_stream('lzw-empty',lzw_codes([256,257]),b'/LZW')
encoded_stream('lzw-bad-code',lzw_codes([256,65,300,257]),b'/LZW')
encoded_stream('lzw-first-reference',lzw_codes([256,258,257]),b'/LZW')
encoded_stream('lzw-no-clear',lzw_codes([65,257]),b'/LZW')
encoded_stream('lzw-no-end',lzw_codes([256,65]),b'/LZW')
encoded_stream('lzw-tail',lzw_encode(payload)+b'junk',b'/LZW')
encoded_stream('lzw-bad-early',lzw_encode(payload),b'/LZW',b'<< /EarlyChange 2 >>')


# Ordered page trees, inherited attributes and lazy content concatenation.
page_objects={
 1:b'<< /Type /Catalog /Pages 2 0 R >>',
 2:b'<< /Type /Pages /Count 3 /Kids [3 0 R 4 0 R] /MediaBox [-10 -20 200 300] /Resources 10 0 R /Rotate -90 >>',
 3:b'<< /Type /Page /Parent 2 0 R /Contents [8 0 R 9 0 R] /Annots [] >>',
 4:b'<< /Type /Pages /Parent 2 0 R /Count 2 /Kids [5 0 R 6 0 R] /MediaBox [400 500 0 0] /CropBox [10 20 300 450] /Resources << /Local true >> /Rotate 450 >>',
 5:b'<< /Type /Page /Parent 4 0 R /Resources null /Contents 8 0 R /UserUnit 2.5 >>',
 6:b'<< /Type /Page /Parent 4 0 R /MediaBox [0 0 100 150] /CropBox null /Rotate 0 /Contents null >>',
 8:b'<< /Length 4 >>\nstream\n(hel\nendstream',
 9:b'<< /Length 10 /Filter /Fl >>\nstream\n'+zlib.compress(b'lo) Tj')+b'\nendstream',
 10:b'<< /Inherited true >>'
}
# compressed content length is authoritative even if it contains token-like bytes
page_objects[9]=page_objects[9].replace(b'/Length 10',b'/Length '+str(len(zlib.compress(b'lo) Tj'))).encode())
pdf('pdf-pages.pdf',values=page_objects)
pdf('pdf-pages-empty.pdf',values={1:page_objects[1],2:b'<< /Type /Pages /Count 0 /Kids [] >>'})
for name,number,value in [
 ('count',2,page_objects[2].replace(b'/Count 3',b'/Count 2')),
 ('cycle',4,page_objects[4].replace(b'[5 0 R 6 0 R]',b'[5 0 R 4 0 R]')),
 ('repeated',4,page_objects[4].replace(b'[5 0 R 6 0 R]',b'[5 0 R 5 0 R]')),
 ('parent',5,page_objects[5].replace(b'/Parent 4',b'/Parent 2')),
 ('root-parent',2,page_objects[2].replace(b'/Type /Pages',b'/Type /Pages /Parent 2 0 R')),
 ('root-type',2,page_objects[2].replace(b'/Type /Pages',b'/Type /Page')),
 ('missing-media',2,page_objects[2].replace(b'/MediaBox [-10 -20 200 300]',b'')),
 ('media-size',2,page_objects[2].replace(b'[-10 -20 200 300]',b'[0 0 0 300]')),
 ('media-arity',2,page_objects[2].replace(b'[-10 -20 200 300]',b'[0 0 300]')),
 ('media-number',2,page_objects[2].replace(b'[-10 -20 200 300]',b'[0 0 /Name 300]')),
 ('media-range',2,page_objects[2].replace(b'[-10 -20 200 300]',b'[0 0 10000001 300]')),
 ('rotate',4,page_objects[4].replace(b'/Rotate 450',b'/Rotate 45')),
 ('rotate-real',4,page_objects[4].replace(b'/Rotate 450',b'/Rotate 90.0')),
 ('resources',4,page_objects[4].replace(b'/Resources << /Local true >>',b'/Resources []')),
 ('kids',4,page_objects[4].replace(b'[5 0 R 6 0 R]',b'[<< /Type /Page >>]')),
 ('unit',5,page_objects[5].replace(b'/UserUnit 2.5',b'/UserUnit 0')),
 ('unit-limit',5,page_objects[5].replace(b'/UserUnit 2.5',b'/UserUnit 75001')),
 ('content-type',3,page_objects[3].replace(b'[8 0 R 9 0 R]',b'[8 0 R 42]')),
 ('content-stream',9,page_objects[9].replace(zlib.compress(b'lo) Tj'),b'X'*len(zlib.compress(b'lo) Tj')))),
]: pdf('pdf-pages-bad-'+name+'.pdf',values={**page_objects,number:value})
deep={1:b'<< /Type /Catalog /Pages 2 0 R >>'}
for number in range(2,132):
    deep[number]=b'<< /Type /Pages /Count 1 /Kids ['+str(number+1).encode()+b' 0 R]'+(b' /Parent '+str(number-1).encode()+b' 0 R' if number>2 else b'')+b' >>'
deep[132]=b'<< /Type /Page /Parent 131 0 R /MediaBox [0 0 1 1] >>'
pdf('pdf-pages-bad-depth.pdf',values=deep)


# PDF font dictionaries, owned text maps and declared glyph metrics.
def compressed_stream(data,extra=b''):
    encoded=zlib.compress(data)
    return b'<< /Length '+str(len(encoded)).encode()+b' /Filter /Fl '+extra+b' >>\nstream\n'+encoded+b'\nendstream'
cmap_prefix=b'begincmap /CMapType 2 def 1 begincodespacerange '
simple_map=cmap_prefix+b'<00> <ff> endcodespacerange 3 beginbfchar <41> <0041> <42> <00660069> <43> <4E00> endbfchar endcmap'
cid_map=cmap_prefix+b'<0000> <ffff> endcodespacerange 2 beginbfchar <0001> <0041> <0002> <D83DDE00> endbfchar 1 beginbfrange <000a> <000c> <0061> endbfrange endcmap'
font_objects={
 1:b'<< /Type /Catalog /Fonts << /Simple 2 0 R /Composite 3 0 R /Vertical 10 0 R /CFF 11 0 R >> >>',
 2:b'<< /Type /Font /Subtype /TrueType /BaseFont /ABCDEF+Primary /FirstChar 65 /LastChar 67 /Widths [500 600 700] /FontDescriptor 5 0 R /Encoding << /BaseEncoding /WinAnsiEncoding /Differences [65 /A /B 67 /uni0043] >> /ToUnicode 7 0 R >>',
 3:b'<< /Type /Font /Subtype /Type0 /BaseFont /ABCDEF+Primary /Encoding /Identity-H /DescendantFonts [4 0 R] /ToUnicode 6 0 R >>',
 4:b'<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Primary /FontDescriptor 5 0 R /DW 900 /DW2 [870 -990] /W [10 12 700 1 [510 520]] /W2 [1 [-1001 250 860 -1002 260 861] 10 12 -900 350 850] /CIDToGIDMap 9 0 R >>',
 5:b'<< /Type /FontDescriptor /FontName /Primary /MissingWidth 250 /FontFile2 8 0 R >>',
 6:compressed_stream(cid_map),7:compressed_stream(simple_map),8:compressed_stream((root/'fonts'/'primary.ttf').read_bytes()),
 9:compressed_stream(b'\0\0\0\3\0\7'),
 10:b'<< /Type /Font /Subtype /Type0 /BaseFont /Primary /Encoding /Identity-V /DescendantFonts [4 0 R] /ToUnicode 6 0 R >>',
 11:b'<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [12 0 R] >>',
 12:b'<< /Type /Font /Subtype /CIDFontType0 /DW 1000 >>'
}
font_objects[1]=font_objects[1][:-2]+b'/Resources << /Font << /Simple 2 0 R /Composite 3 0 R /Vertical 10 0 R >> /ExtGState << /G << /Font [3 0 R 20] >> >> /XObject << /Image 13 0 R /Form 14 0 R >> >> >>'
font_objects[13]=compressed_stream(b'\0',b'/Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8')
font_objects[14]=compressed_stream(b'',b'/Type /XObject /Subtype /Form /BBox [0 0 10 10]')
pdf('pdf-fonts.pdf',values=font_objects)
font_bad=[('width-short',2,font_objects[2].replace(b'[500 600 700]',b'[500 600]')),('width-extra',2,font_objects[2].replace(b'[500 600 700]',b'[500 600 700 800]')),
 ('first-char',2,font_objects[2].replace(b'/FirstChar 65',b'/FirstChar -1')),('differences',2,font_objects[2].replace(b'[65 /A /B 67 /uni0043]',b'[/A]')),
 ('encoding',3,font_objects[3].replace(b'/Identity-H',b'/Other-Encoding')),('descendants',3,font_objects[3].replace(b'[4 0 R]',b'[4 0 R 4 0 R]')),
 ('w-overlap',4,font_objects[4].replace(b'[10 12 700 1 [510 520]]',b'[1 3 700 2 [510 520]]')),
 ('w-truncated',4,font_objects[4].replace(b'[10 12 700 1 [510 520]]',b'[1 3]')),
 ('w-range',4,font_objects[4].replace(b'[10 12 700 1 [510 520]]',b'[65535 [1 2]]')),
 ('w-type',4,font_objects[4].replace(b'[10 12 700 1 [510 520]]',b'[1 [/bad]]')),
 ('w2-truncated',4,font_objects[4].replace(b'[1 [-1001 250 860 -1002 260 861] 10 12 -900 350 850]',b'[1 [1 2]]')),
 ('dw2',4,font_objects[4].replace(b'[870 -990]',b'[870]')),
 ('cid-map',9,compressed_stream(b'odd')),
 ('program-type',5,font_objects[5].replace(b'/FontFile2',b'/FontFile')),
 ('program-duplicate',5,font_objects[5].replace(b'/FontFile2 8 0 R',b'/FontFile2 8 0 R /FontFile3 8 0 R')),
 ('subtype',2,font_objects[2].replace(b'/TrueType',b'/Type3')),
 ('width-missing',2,font_objects[2].replace(b'/Widths [500 600 700]',b''))]
for name,number,value in font_bad: pdf('pdf-font-bad-'+name+'.pdf',values={**font_objects,number:value})


font_budget={**font_objects}
font_budget[1]=b'<< /Type /Catalog /Resources << /Font << '+b' '.join(f'/F{i} {20+i} 0 R'.encode() for i in range(129))+b' >> >> >>'
for i in range(129): font_budget[20+i]=font_objects[2]
pdf('pdf-text-font-budget.pdf',values=font_budget)


forms={**font_objects}
forms[1]=forms[1].replace(b'/Image 13 0 R /Form 14 0 R',b'/Image 13 0 R /Form 14 0 R /Outer 20 0 R /Inner 21 0 R /Inherit 22 0 R /Local 23 0 R')
form_extra=b'/Subtype /Form /BBox [0 0 100 100] '
forms[20]=compressed_stream(b'/Inner Do',form_extra+b'/Matrix [1 0 0 1 10 20] /Resources << /XObject << /Inner 21 0 R >> >>')
forms[21]=compressed_stream(b'q BT /Simple 10 Tf (A) Tj ET Q',form_extra+b'/Matrix [2 0 0 3 5 7] /Resources << /Font << /Simple 2 0 R >> >>')
forms[22]=compressed_stream(b'BT /Simple 10 Tf (B) Tj ET',form_extra)
forms[23]=compressed_stream(b'BT /C 10 Tf <0001> Tj ET',form_extra+b'/Matrix [0 1 -1 0 0 0] /Resources << /Font << /C 3 0 R >> >>')
pdf('pdf-text-forms.pdf',values=forms)
for name,body,extra in [
 ('cycle',b'/Outer Do',b'/Resources << /XObject << /Outer 20 0 R >> >>'),
 ('pop',b'Q',b''),('open',b'BT',b''),('save',b'q',b''),('matrix',b'',b'/Matrix [1 0 0 1 2]'),('box',b'',b'/BBox [0 1 2]'),('type',b'',b'/FormType 2'),('resources',b'',b'/Resources []')]:
    pdf('pdf-form-bad-'+name+'.pdf',values={**forms,20:compressed_stream(body,form_extra+extra)})
deep_forms={**forms}
for i in range(20,53):
    deep_forms[i]=compressed_stream(b'/Next Do' if i<52 else b'',form_extra+b'/Resources << /XObject << /Next '+str(i+1).encode()+b' 0 R >> >>')
pdf('pdf-form-bad-depth.pdf',values=deep_forms)
