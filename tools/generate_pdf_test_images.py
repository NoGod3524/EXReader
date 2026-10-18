#!/usr/bin/env python3
"""Original color quadrants/gray JPEG fixtures; Pillow is development-only."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import io
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]/'tests/fixtures/pdf-images'
ROOT.mkdir(parents=True, exist_ok=True)
image = Image.new('RGB', (16,16))
colors = [(255,0,0), (0,255,0), (0,0,255), (255,255,255)]
image.putdata([colors[(y//8)*2+x//8] for y in range(16) for x in range(16)])
for progressive in (False, True):
    image.save(ROOT/('progressive.jpg' if progressive else 'baseline.jpg'), quality=100, subsampling=0, progressive=progressive)
Image.new('L', (8,8), 64).save(ROOT/'gray.jpg', quality=100)
# Four independent ink channels. Pillow's Adobe CMYK JPEG stores inverted
# samples; the PDF fixtures explicitly supply Decode [1 0 ...].
ink = (40, 80, 120, 32)
for progressive in (False, True):
    Image.new('CMYK', (17,9), ink).save(
        ROOT/('cmyk-progressive.jpg' if progressive else 'cmyk.jpg'),
        quality=100, subsampling=0, progressive=progressive)
# Author Y/Cb/Cr/K planes directly, then mark the JPEG as Adobe YCCK.
# This is an original synthetic input, independent of the runtime decoder.
ycc = Image.new('RGB', (1,1), ink[:3]).convert('YCbCr').getpixel((0,0))
ycck = Image.new('CMYK', (17,9), tuple(255-v for v in ycc)+(ink[3],))
for progressive in (False, True):
    encoded = io.BytesIO()
    ycck.save(encoded, 'JPEG', quality=100, subsampling=2, progressive=progressive)
    data = bytearray(encoded.getvalue())
    marker = data.index(b'Adobe')
    data[marker+11] = 2
    (ROOT/('ycck-progressive.jpg' if progressive else 'ycck.jpg')).write_bytes(data)
quad = Image.new('CMYK', (32,32))
inks = [(0,255,255,0), (255,0,255,0), (255,255,0,0), (0,0,0,128)]
quad.putdata([inks[(y//16)*2+x//16] for y in range(32) for x in range(32)])
quad.save(ROOT/'cmyk-quadrants.jpg', quality=100, subsampling=2)
components = [quad.getpixel((x,y)) for y in range(32) for x in range(32)]
ycc = Image.new('RGB', quad.size)
ycc.putdata([p[:3] for p in components])
ycc = ycc.convert('YCbCr')
converted = [ycc.getpixel((x,y)) for y in range(32) for x in range(32)]
quad.putdata([tuple(255-v for v in p)+(ink[3],) for p,ink in zip(converted,components)])
encoded = io.BytesIO()
quad.save(encoded, 'JPEG', quality=100, subsampling=2, progressive=True)
data = bytearray(encoded.getvalue())
data[data.index(b'Adobe')+11] = 2
(ROOT/'ycck-quadrants.jpg').write_bytes(data)
print('Generated nine original JPEG fixtures')
