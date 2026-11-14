#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fault injection for the M6 oracle; no native library or host font required."""
from io import BytesIO
from unittest.mock import patch

from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt

import pptx_real_matrix as matrix


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

    deck = Presentation()
    deck.slide_width, deck.slide_height = Pt(360), Pt(240)
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    rectangle = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE,
                                       Pt(40), Pt(40), Pt(280), Pt(160))
    rectangle.fill.solid()
    rectangle.fill.fore_color.rgb = RGBColor(224, 32, 32)
    rectangle.line.fill.background()
    text = slide.shapes.add_textbox(Pt(60), Pt(60), Pt(220), Pt(80))
    text.text = 'Glyph presence'
    text.text_frame.paragraphs[0].runs[0].font.size = Pt(18)

    # Expected pixels come solely from the PPTX; the ABI cannot be consulted.
    with patch.object(matrix, 'Engine', side_effect=AssertionError('oracle used engine')), \
         patch.object(matrix, 'render', side_effect=AssertionError('oracle used renderer')):
        reference = matrix.Reference(deck, slide)
        samples = reference.samples()
        assert reference.expected(45, 45) == (224, 32, 32)
        assert reference.expected(20, 20) == matrix.WHITE
        assert len(samples) == len({(x, y) for x, y, _ in samples}) == 12
        assert sum(rgb == (224, 32, 32) for _, _, rgb in samples) >= 3

    base = Image.new('RGB', (360, 240), 'white')
    ImageDraw.Draw(base).rectangle((40, 40, 319, 199), fill=(224, 32, 32))
    correct = base.copy()
    ImageDraw.Draw(correct).rectangle((72, 74, 83, 91), fill='black')
    result = matrix.metrics(reference, correct, base)
    assert result['ok'] and result['colors'] == 12 and result['glyph_pixels'] > 0, result
    print('control: coverage=ok color=12/12 text=ok')

    blank = Image.new('RGB', correct.size, 'white')
    result = matrix.metrics(reference, blank, blank)
    assert not result['ok'] and not result['coverage'] and not result['text'], result
    print('all-white injection: FAIL detected')

    shifted, shifted_base = blank.copy(), blank.copy()
    shifted.paste(correct, (16, 0))
    shifted_base.paste(base, (16, 0))
    result = matrix.metrics(reference, shifted, shifted_base)
    assert not result['ok'] and not result['coverage'], result
    print('16px translation injection: coverage failure detected')

    blue_base = blank.copy()
    ImageDraw.Draw(blue_base).rectangle((40, 40, 319, 199), fill=(32, 32, 224))
    blue = blue_base.copy()
    ImageDraw.Draw(blue).rectangle((72, 74, 83, 91), fill='black')
    result = matrix.metrics(reference, blue, blue_base)
    assert not result['ok'] and result['coverage'] and result['colors'] < 10, result
    failures = [sample for sample in result['samples'] if not sample['ok']]
    assert failures and all({'x', 'y', 'actual', 'expected', 'delta'} <= sample.keys()
                            for sample in failures), failures
    print(f'wrong-color injection: color={result["colors"]}/12; coordinates/RGB retained')

    result = matrix.metrics(reference, base, base)
    assert not result['ok'] and result['coverage'] and result['colors'] == 12, result
    assert not result['text'] and result['glyph_pixels'] == 0, result
    assert reference.samples() == samples, 'reference samples changed with actual pixels'
    print('lost-text injection: text failure detected despite intact colored rectangle')

    stream = BytesIO()
    deck.save(stream)
    emptied = Presentation(BytesIO(matrix.without_text(stream.getvalue())))
    empty_reference = matrix.Reference(emptied, emptied.slides[0])
    assert not empty_reference.text_boxes
    assert empty_reference.frames == reference.frames
    assert empty_reference.samples() == samples
    assert empty_reference.expected(45, 45) == reference.expected(45, 45)
    print('textless package: geometry/fills preserved; reference samples independent')

    text_deck = Presentation()
    text_deck.slide_width, text_deck.slide_height = Pt(360), Pt(240)
    text_page = text_deck.slides.add_slide(text_deck.slide_layouts[6])
    text_page.shapes.add_textbox(Pt(40), Pt(40), Pt(120), Pt(60)).text = 'Only text'
    text_reference = matrix.Reference(text_deck, text_page)
    ink = blank.copy()
    ImageDraw.Draw(ink).rectangle((48, 48, 89, 69), fill='black')
    result = matrix.metrics(text_reference, ink, blank)
    assert not result['ok'] and not result['coverage'] and result['text'], result
    print('transparent textbox: inset glyph ink does not falsely cover the full shape frame')

    alpha = OxmlElement('a:alpha')
    alpha.set('val', '50000')
    rectangle._element.spPr.solidFill[0].append(alpha)
    alpha_reference = matrix.Reference(deck, slide)
    assert alpha_reference.expected(45, 45) == (240, 144, 144)
    assert alpha_reference.expected(20, 20) == matrix.WHITE

    image_deck = Presentation()
    image_page = image_deck.slides.add_slide(image_deck.slide_layouts[6])
    source = Image.new('RGB', (4, 2), 'red')
    ImageDraw.Draw(source).rectangle((2, 0, 3, 1), fill='blue')
    encoded = BytesIO()
    source.save(encoded, format='PNG')
    picture = image_page.shapes.add_picture(BytesIO(encoded.getvalue()),
                                           Pt(40), Pt(40), Pt(80), Pt(40))
    image_reference = matrix.Reference(image_deck, image_page)
    assert image_reference.expected(45, 45) == (255, 0, 0)
    assert image_reference.expected(115, 45) == (0, 0, 255)
    picture.crop_left = .5
    cropped_reference = matrix.Reference(image_deck, image_page)
    assert cropped_reference.expected(45, 45) == (0, 0, 255)
    print('independent paint oracle: half-alpha compositing and cropped image colors verified')


if __name__ == '__main__':
    run()
