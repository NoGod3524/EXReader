#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare two evidence trees screenshot by screenshot; any differing pixel fails.

Usage: compare_shots.py <evidence-a> <evidence-b>
Each tree holds the phase directories A, B and C written by --drive --evidence.
"""
import sys
from pathlib import Path
from PIL import Image, ImageChops

a, b = Path(sys.argv[1]), Path(sys.argv[2])
names = sorted(p.relative_to(a) for p in a.glob('[ABC]/*.png'))
failed = 0
for name in names:
    left, right = Image.open(a / name).convert('RGBA'), b / name
    if not right.exists():
        print(name.as_posix(), 'missing'); failed += 1; continue
    right = Image.open(right).convert('RGBA')
    if left.size != right.size:
        print(name.as_posix(), 'size', left.size, right.size); failed += 1; continue
    diff = ImageChops.difference(left, right)
    pixels = sum(1 for v in diff.getdata() if v != (0, 0, 0, 0)) if diff.getbbox() else 0
    failed += pixels > 0
    print(name.as_posix(), '%dx%d' % left.size, 'diffpx', pixels)
print('images=%d nonzero=%d' % (len(names), failed))
sys.exit(1 if failed or len(names) != 8 else 0)
