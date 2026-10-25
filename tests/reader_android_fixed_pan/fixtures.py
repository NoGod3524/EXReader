"""Actions-only independent quadrant originals and predeclared viewport plan."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zipfile
import zlib
assert os.environ.get('GITHUB_ACTIONS') == 'true'
folder=Path(sys.argv[1])
root=Path(__file__).resolve().parents[2]
subprocess.check_call([sys.executable,str(root/'tests/reader_android_reading/fixtures.py'),str(folder)])
colors=[[200,40,40],[40,180,60],[40,70,200],[210,180,30]]
def png():
    rows=[]
    for y in range(800):
        rows.append(b'\x00'+b''.join(bytes(colors[(2 if y>=400 else 0)+(1 if x>=300 else 0)]) for x in range(600)))
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',600,800,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows),6))+chunk(b'IEND',b'')
image=png()
with zipfile.ZipFile(folder/'search.cbz','w') as book:
    for index in range(3):
        entry=zipfile.ZipInfo(f'{index+1:03}.png',(2020,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
        book.writestr(entry,image)
objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Count 4 /Kids [3 0 R 4 0 R 5 0 R 6 0 R] >>']
for index in range(4):
    objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 11 0 R >> >> /Contents {7+index} 0 R >>'.encode())
for index in range(4):
    commands=[]
    for (x,y),rgb in zip([(0,400),(300,400),(0,0),(300,0)],colors):
        commands.append(' '.join(f'{value/255:.9f}' for value in rgb)+f' rg {x} {y} 300 400 re f')
    commands.extend([f'0 0 0 rg BT /F1 12 Tf 40 750 Td (PAGE{index+1}TOPLEFT) Tj ET','0 0 0 rg BT /F1 12 Tf 450 50 Td (BOTTOMRIGHT) Tj ET'])
    content=('\n'.join(commands)+'\n').encode()
    objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'endstream')
objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
data=bytearray(b'%PDF-1.7\n');offsets=[0]
for index,body in enumerate(objects,1):
    offsets.append(len(data));data+=f'{index} 0 obj\n'.encode()+body+b'\nendobj\n'
xref=len(data);data+=f'xref\n0 {len(offsets)}\n'.encode()+b'0000000000 65535 f \n'
for offset in offsets[1:]:data+=f'{offset:010d} 00000 n \n'.encode()
data+=f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
(folder/'search.pdf').write_bytes(data)
path=folder/'manifest.json';manifest=json.loads(path.read_text());manifest.pop('expected',None)
for row in manifest['books']:
    payload=(folder/row['file']).read_bytes();row['bytes']=len(payload);row['sha256']=hashlib.sha256(payload).hexdigest()
manifest['pan_expected']={'width':600,'height':800,'rgb':colors,'points':[[30,30],[570,30],[30,770],[570,770]],'pdf_marker':'BOTTOMRIGHT','plan_precedes_sdk_read':True}
path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
