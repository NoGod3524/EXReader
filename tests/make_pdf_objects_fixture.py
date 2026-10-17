#!/usr/bin/env python3
"""Original PDF object/xref/stream fixtures; no external PDF inputs."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import zlib
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
def incremental(name,previous=None,rootref=True,deleted=True):
    data=bytearray(base); offsets={}
    for i,value in [(1,b'<< /Type /Catalog /Pages 2 0 R /Revision (Updated) /Deleted 9 0 R /Extra 11 0 R >>'),(11,b'(Extra object)')]:
        offsets[i]=len(data);data+=str(i).encode()+b' 0 obj\n'+value+b'\nendobj\n'
    xref=len(data);data+=b'xref\n1 1\n'+f'{offsets[1]:010d} 00000 n \n'.encode()
    if deleted: data+=b'9 1\n0000000000 00001 f \n'
    data+=b'11 1\n'+f'{offsets[11]:010d} 00000 n \n'.encode()
    prev=xref if previous=='self' else base_xref if previous is None else previous
    data+=b'trailer\n<< /Size 12'+(b' /Root 1 0 R' if rootref else b'')+b' /Prev '+str(prev).encode()+b' >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n'
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
