#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Developer reference check: fixed 3px erosion includes an empty exterior."""
import importlib.util
from pathlib import Path
from PIL import Image

spec = importlib.util.spec_from_file_location('color_reference', Path(__file__).resolve().parents[1] / 'tools/check_color_font_reference.py')
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)

def main():
    for width,height in ((13,11),(6,6),(3,9)):
        result = reference.interior_mask(Image.new('L',(width,height),255))
        actual = {(x,y) for y in range(height) for x in range(width) if result.getpixel((x,y))}
        expected = {(x,y) for y in range(3,height-3) for x in range(3,width-3)}
        assert actual == expected
    covered = Image.new('L',(17,17),255)
    covered.putpixel((8,8),0)
    result = reference.interior_mask(covered)
    assert result.getpixel((4,8)) == 255
    assert result.getpixel((5,8)) == result.getpixel((11,8)) == 0
    assert result.getpixel((12,8)) == 255
    print('4 reference erosion cases passed; thresholds unchanged')

if __name__ == '__main__':
    main()
