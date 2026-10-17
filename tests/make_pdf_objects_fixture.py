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
