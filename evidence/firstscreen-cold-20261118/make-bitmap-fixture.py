#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Replace page 1 of real-mixed-120 with an opaque raster of deck page 1."""
import argparse
from pathlib import Path

import pymupdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with pymupdf.open(ROOT / 'tests/fixtures/pdf-ppt/deck.pdf') as deck:
        source = deck[0]
        width, height = source.rect.width, source.rect.height
        scale = 2400 / width
        pix = source.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)

    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    image = DecodedStreamObject()
    image.set_data(pix.samples)
    image.update({
        NameObject('/Type'): NameObject('/XObject'),
        NameObject('/Subtype'): NameObject('/Image'),
        NameObject('/Width'): NumberObject(pix.width),
        NameObject('/Height'): NumberObject(pix.height),
        NameObject('/ColorSpace'): NameObject('/DeviceRGB'),
        NameObject('/BitsPerComponent'): NumberObject(8),
        NameObject('/Interpolate'): BooleanObject(True),
    })
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/XObject'): DictionaryObject({NameObject('/Slide'): writer._add_object(image.flate_encode())}),
    })
    content = DecodedStreamObject()
    content.set_data(f'q {width:g} 0 0 {height:g} 0 0 cm /Slide Do Q\n'.encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(content)
    writer.append(PdfReader(ROOT / 'tests/fixtures/pdf-large/real-mixed-120.pdf'), pages=(1, 120), import_outline=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('wb') as output:
        writer.write(output)
    print(f'{len(writer.pages)} pages, page 1 RGB image {pix.width}x{pix.height}')


if __name__ == '__main__':
    main()
