"""Independently validate the C renderer's PNG structure, CRCs and scanlines."""
import struct
import sys
import zlib
from pathlib import Path
payload=Path(sys.argv[1]).read_bytes()
assert payload[:8]==b"\x89PNG\r\n\x1a\n"
pos=8
compressed=bytearray()
width=height=0
while pos<len(payload):
    size=struct.unpack_from(">I",payload,pos)[0]
    kind=payload[pos+4:pos+8]
    data=payload[pos+8:pos+8+size]
    crc=struct.unpack_from(">I",payload,pos+8+size)[0]
    assert zlib.crc32(kind+data)==crc,kind
    if kind==b"IHDR":
        width,height,depth,color,*_=struct.unpack(">IIBBBBB",data)
        assert depth==8 and color==0
    elif kind==b"IDAT": compressed.extend(data)
    pos+=12+size
    if kind==b"IEND": break
assert pos==len(payload) and width and height
pixels=zlib.decompress(compressed)
assert len(pixels)==(width+1)*height
assert all(pixels[y*(width+1)]==0 for y in range(height))
assert sum(v<200 for y in range(height) for v in pixels[y*(width+1)+1:(y+1)*(width+1)])>1000
print(f"PNG verified: {width} x {height}, native rasterized text present")
