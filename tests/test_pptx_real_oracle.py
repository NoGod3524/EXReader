#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fault injection for the M6 oracle; no native library or host font required."""
from io import BytesIO
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_STORED

import pptx_real_matrix as matrix

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'


def transform(box):
    x, y, w, h = (round(value * 12700) for value in box)
    return (f'<a:xfrm><a:off x="{x}" y="{y}"/>'
            f'<a:ext cx="{w}" cy="{h}"/></a:xfrm>')


def shape(box, color=None, text='', outline=False, alpha=None, number=1):
    fill = ('<a:solidFill><a:srgbClr val="' + color + '">' +
            (f'<a:alpha val="{alpha}"/>' if alpha is not None else '') +
            '</a:srgbClr></a:solidFill>') if color else '<a:noFill/>'
    line = ('<a:ln w="12700"><a:solidFill><a:srgbClr val="000000"/>'
            '</a:solidFill></a:ln>') if outline else '<a:ln><a:noFill/></a:ln>'
    body = (f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r>'
            f'<a:rPr sz="1800"/><a:t>{escape(text)}</a:t>'
            '</a:r></a:p></p:txBody>') if text else ''
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{number}" name="Shape {number}"/>'
            '<p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr>' + transform(box) +
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>' + fill + line +
            '</p:spPr>' + body + '</p:sp>')


def picture(crop=0):
    return ('<p:pic><p:nvPicPr><p:cNvPr id="1" name="Picture"/>'
            '<p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill>'
            f'<a:blip r:embed="image"/><a:srcRect l="{crop}"/>'
            '<a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr>' +
            transform((40, 40, 80, 40)) +
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')


def package(shapes, background='FFFFFF', image=None):
    """Small complete OPC package, authored independently of the reader."""
    types = {
        '/ppt/presentation.xml': 'presentationml.presentation.main',
        '/ppt/slides/slide1.xml': 'presentationml.slide',
        '/ppt/slideLayouts/slideLayout1.xml': 'presentationml.slideLayout',
        '/ppt/slideMasters/slideMaster1.xml': 'presentationml.slideMaster',
        '/ppt/theme/theme1.xml': 'theme',
    }
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>' + ''.join(
                f'<Override PartName="{name}" ContentType="application/vnd.openxmlformats-officedocument.{kind}+xml"/>'
                for name, kind in types.items()) + '</Types>',
        '_rels/.rels': f'<Relationships xmlns="{REL}"><Relationship Id="office" Type="{R}/officeDocument" Target="ppt/presentation.xml"/></Relationships>',
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="256" r:id="slide"/></p:sldIdLst><p:sldSz cx="4572000" cy="3048000"/></p:presentation>',
        'ppt/_rels/presentation.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="slide" Type="{R}/slide" Target="slides/slide1.xml"/></Relationships>',
        'ppt/slides/slide1.xml': f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="{background}"/></a:solidFill></p:bgPr></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id="0" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>{shapes}</p:spTree></p:cSld></p:sld>',
        'ppt/slides/_rels/slide1.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="layout" Type="{R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="image" Type="{R}/image" Target="../media/image1.png"/></Relationships>',
        'ppt/slideLayouts/slideLayout1.xml': f'<p:sldLayout xmlns:p="{P}"><p:cSld><p:spTree/></p:cSld></p:sldLayout>',
        'ppt/slideLayouts/_rels/slideLayout1.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="master" Type="{R}/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>',
        'ppt/slideMasters/slideMaster1.xml': f'<p:sldMaster xmlns:p="{P}"><p:cSld><p:spTree/></p:cSld><p:clrMap accent1="accent1" bg1="lt1" tx1="dk1"/></p:sldMaster>',
        'ppt/slideMasters/_rels/slideMaster1.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="theme" Type="{R}/theme" Target="../theme/theme1.xml"/></Relationships>',
        'ppt/theme/theme1.xml': f'<a:theme xmlns:a="{A}" name="Oracle"><a:themeElements><a:clrScheme name="Oracle"><a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1></a:clrScheme></a:themeElements></a:theme>',
    }
    if image is not None:
        parts['ppt/media/image1.png'] = image
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_STORED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return stream.getvalue()


def reference(data):
    deck = matrix.Presentation(BytesIO(data))
    return deck, matrix.Reference(deck, deck.slides[0])


def run():
    for warning in ('', 'PPTX warning: font fallback=Arial; ',
                    'PPTX warning: missing glyph: Arial U+4E00 fallback; Arial U+4E8C missing; ',
                    'PPTX warning: font fallback=Arial; missing glyph: Arial U+4E00 missing; '):
        assert matrix.font_warnings_only(warning), warning
    for warning in ('PPTX warning: font fallback=Arial; missing off/ext=1; ',
                    'PPTX warning: missing off/ext=1; font fallback=Arial; ',
                    'PPTX warning: missing glyph: Arial U+4E00 missing; rect fallback=star; ',
                    'PPTX warning: invalid color=1; ', 'unrecognized warning'):
        assert not matrix.font_warnings_only(warning), warning
    print('warning gate: font-only accepted; mixed/nonfont warnings rejected')

    rectangle = shape((40, 40, 280, 160), 'E02020')
    textbox = shape((60, 60, 220, 80), text='Glyph presence', number=2)
    data = package(rectangle + textbox)
    # Expected pixels come solely from the PPTX; the ABI cannot be consulted.
    with patch.object(matrix, 'Engine', side_effect=AssertionError('oracle used engine')), \
         patch.object(matrix, 'render', side_effect=AssertionError('oracle used renderer')):
        deck, original = reference(data)
        samples = original.samples()
        assert original.expected(45, 45) == (224, 32, 32)
        assert original.expected(20, 20) == matrix.WHITE
        assert len(samples) == len({(x, y) for x, y, _ in samples}) == 12
        assert sum(rgb == (224, 32, 32) for _, _, rgb in samples) >= 3

    base = matrix.Raster.new((360, 240), matrix.WHITE)
    base.rectangle((40, 40, 319, 199), fill=(224, 32, 32))
    correct = base.copy()
    correct.rectangle((72, 74, 83, 91), fill=(0, 0, 0))
    result = matrix.metrics(original, correct, base)
    assert result['ok'] and result['colors'] == 12 and result['glyph_pixels'] > 0, result
    print('control: coverage=ok color=12/12 text=ok')

    blank = matrix.Raster.new(correct.size, matrix.WHITE)
    result = matrix.metrics(original, blank, blank)
    assert not result['ok'] and not result['coverage'] and not result['text'], result
    print('all-white injection: FAIL detected')

    shifted, shifted_base = blank.copy(), blank.copy()
    shifted.paste(correct, (16, 0))
    shifted_base.paste(base, (16, 0))
    result = matrix.metrics(original, shifted, shifted_base)
    assert not result['ok'] and not result['coverage'], result
    print('16px translation injection: coverage failure detected')

    blue_base = blank.copy()
    blue_base.rectangle((40, 40, 319, 199), fill=(32, 32, 224))
    blue = blue_base.copy()
    blue.rectangle((72, 74, 83, 91), fill=(0, 0, 0))
    result = matrix.metrics(original, blue, blue_base)
    assert not result['ok'] and result['coverage'] and result['colors'] < 10, result
    failures = [sample for sample in result['samples'] if not sample['ok']]
    assert failures and all({'x', 'y', 'actual', 'expected', 'delta'} <= sample.keys()
                            for sample in failures), failures
    print(f'wrong-color injection: color={result["colors"]}/12; coordinates/RGB retained')

    result = matrix.metrics(original, base, base)
    assert not result['ok'] and not result['coverage'] and result['colors'] == 12, result
    assert not result['text'] and result['glyph_pixels'] == 0, result
    assert original.samples() == samples, 'reference samples changed with actual pixels'
    print('lost-text injection: text failure detected despite intact colored rectangle')

    _, empty_reference = reference(matrix.without_text(data))
    assert not empty_reference.text_boxes
    assert empty_reference.frames == original.frames
    assert empty_reference.samples() == samples
    assert empty_reference.expected(45, 45) == original.expected(45, 45)
    print('textless package: geometry/fills preserved; reference samples independent')

    bare, bare_reference = reference(matrix.without_shapes(data))
    assert len(bare.slides) == len(deck.slides) and not bare_reference.regions
    assert bare_reference.background == original.background
    print('background-only package: slide count/background preserved; foreground removed')

    first_text = shape((40, 40, 120, 60), text='Only text')
    _, text_reference = reference(package(first_text))
    ink = blank.copy()
    ink.rectangle((48, 48, 89, 69), fill=(0, 0, 0))
    result = matrix.metrics(text_reference, ink, blank)
    assert result['ok'] and result['coverage'] and result['text'], result
    assert result['coverage_shapes'][0]['kind'] == 'text', result
    print('transparent textbox: inset glyph ink passes without covering the full frame')

    overflow = blank.copy()
    overflow.rectangle((48, 48, 175, 69), fill=(0, 0, 0))
    result = matrix.metrics(text_reference, overflow, blank)
    assert not result['coverage'] and result['text'], result
    assert result['coverage_shapes'][0]['actual_bbox'] == (48, 48, 176, 70), result
    print('text overflow injection: glyphs outside the frame are retained and rejected')

    # Per-frame presence must reject one lost textbox even while another has ink.
    second_text = shape((190, 40, 120, 60), text='Second text', number=2)
    _, two_text_reference = reference(package(first_text + second_text))
    result = matrix.metrics(two_text_reference, ink, blank)
    assert not result['coverage'] and not result['text'], result
    assert result['coverage_shapes'][0]['ok'] and not result['coverage_shapes'][1]['ok'], result
    print('one-of-two textboxes lost: per-shape presence failure detected')

    border = shape((40, 40, 120, 60), outline=True)
    _, outline_reference = reference(package(border))
    border_image = blank.copy()
    border_image.rectangle((40, 40, 159, 99), outline=(0, 0, 0))
    result = matrix.metrics(outline_reference, border_image, border_image)
    assert result['coverage'] and result['coverage_shapes'][0]['kind'] == 'outline', result
    result = matrix.metrics(outline_reference, blank, blank)
    assert not result['coverage'], result
    print('unfilled outline: local non-background ink required; missing border rejected')

    _, colored_reference = reference(package(border, background='204060'))
    colored_blank = matrix.Raster.new(blank.size, (32, 64, 96))
    result = matrix.metrics(colored_reference, colored_blank, colored_blank)
    assert not result['coverage'] and result['colors'] == 12, result
    result = matrix.metrics(colored_reference, blank, blank, blank)
    assert not result['coverage'], result
    print('colored backdrop: background cannot impersonate missing shape ink')

    _, alpha_reference = reference(package(shape((40, 40, 280, 160), 'E02020', alpha=50000) + textbox))
    assert alpha_reference.expected(45, 45) == (240, 144, 144)
    assert alpha_reference.expected(20, 20) == matrix.WHITE

    source = matrix.Raster.new((4, 2), (255, 0, 0))
    source.rectangle((2, 0, 3, 1), fill=(0, 0, 255))
    encoded = BytesIO()
    source.save(encoded)
    _, image_reference = reference(package(picture(), image=encoded.getvalue()))
    assert image_reference.expected(45, 45) == (255, 0, 0)
    assert image_reference.expected(115, 45) == (0, 0, 255)
    _, cropped_reference = reference(package(picture(crop=50000), image=encoded.getvalue()))
    assert cropped_reference.expected(45, 45) == (0, 0, 255)
    print('independent paint oracle: half-alpha compositing and cropped image colors verified')


if __name__ == '__main__':
    run()
