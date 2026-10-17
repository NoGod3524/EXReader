#!/usr/bin/env python3
"""Original color quadrants/gray JPEG fixtures; Pillow is development-only."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]/'tests/fixtures/pdf-images'
ROOT.mkdir(parents=True, exist_ok=True)
image = Image.new('RGB', (16,16))
colors = [(255,0,0), (0,255,0), (0,0,255), (255,255,255)]
image.putdata([colors[(y//8)*2+x//8] for y in range(16) for x in range(16)])
for progressive in (False, True):
    image.save(ROOT/('progressive.jpg' if progressive else 'baseline.jpg'), quality=100, subsampling=0, progressive=progressive)
Image.new('L', (8,8), 64).save(ROOT/'gray.jpg', quality=100)
print('Generated three original JPEG fixtures')
