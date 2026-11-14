#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Independent fault injections for the PPT COM manifest/pixel oracle."""
from contextlib import redirect_stdout
from io import StringIO
import struct
from unittest.mock import patch

from check_ppt import compound, record
import ppt_real_matrix as matrix


def oracle(regions, background=(255, 255, 255)):
    samples = [[x, y, *color] for x, y, color in (
        (45, 45, (224, 32, 32)), (310, 45, (224, 32, 32)),
        (45, 190, (224, 32, 32)), (310, 190, (224, 32, 32)),
        (150, 180, (224, 32, 32)), (250, 180, (224, 32, 32)),
        (10, 10, background), (340, 10, background), (10, 220, background),
        (340, 220, background), (180, 10, background), (180, 220, background))]
    return dict(width=360, height=240, background=list(background),
                slides=[dict(regions=regions, samples=samples)])


def region(name, bounds, fill=None, text=False):
    return dict(name=name, bounds=bounds, geometry='rect', fill=fill, text=text, stroke=1)


def only_white_samples(data):
    for sample in data['slides'][0]['samples']:
        sample[2:] = data['background']
    return data


def run():
    for warning in ('', 'PPT warning: font fallback=Arial; ',
                    'PPT warning: glyph Arial U+4E00 fallback; glyph Arial U+4E8C missing; ',
                    'PPT warning: font fallback=Arial; glyph Arial U+4E00 missing; '):
        assert matrix.font_warnings_only(warning), warning
    for warning in ('PPT warning: font fallback=Arial; missing-anchor=1 ',
                    'PPT warning: missing-anchor=1 font fallback=Arial; ',
                    'PPT warning: glyph Arial U+4E00 missing; unsupported=1 ',
                    'PPT warning: font fallback=Arial; table-merge=1 ',
                    'PPT warning: gradient-horizontal=1 ', 'unrecognized warning'):
        assert not matrix.font_warnings_only(warning), warning
    print('warning gate: font-only accepted; mixed/nonfont warnings rejected')

    rectangle = region('rectangle', (40, 40, 320, 200), [224, 32, 32])
    textbox = region('text', (60, 60, 280, 140), text=True)
    data = oracle([rectangle, textbox])
    # COM metadata is the sole reference; constructing it cannot touch the ABI.
    with patch.object(matrix, 'Engine', side_effect=AssertionError('oracle used engine')), \
         patch.object(matrix, 'render', side_effect=AssertionError('oracle used renderer')):
        reference = matrix.Reference(data)
        samples = reference.samples()
        assert len(samples) == len({(x, y) for x, y, _ in samples}) == 12
        assert sum(rgb == (224, 32, 32) for _, _, rgb in samples) == 6

    blank = matrix.Raster.new((360, 240), (255, 255, 255))
    base = blank.copy()
    base.rectangle((40, 40, 319, 199), fill=(224, 32, 32))
    correct = base.copy()
    correct.rectangle((72, 74, 83, 91), fill=(0, 0, 0))
    result = matrix.metrics(reference, correct, base)
    assert result['ok'] and result['colors'] == 12 and result['glyph_pixels'] > 0, result
    print('control: coverage=ok color=12/12 text=ok')

    result = matrix.metrics(reference, blank, blank)
    assert not result['ok'] and not result['coverage'] and not result['text'], result
    print('all-white injection: coverage/text failures detected')

    shifted, shifted_base = blank.copy(), blank.copy()
    shifted.paste(correct, (16, 0))
    shifted_base.paste(base, (16, 0))
    result = matrix.metrics(reference, shifted, shifted_base)
    assert not result['ok'] and not result['coverage'], result
    print('16px translation injection: coverage failure detected')

    blue_base = blank.copy()
    blue_base.rectangle((40, 40, 319, 199), fill=(32, 32, 224))
    blue = blue_base.copy()
    blue.rectangle((72, 74, 83, 91), fill=(0, 0, 0))
    result = matrix.metrics(reference, blue, blue_base)
    assert result['coverage'] and result['colors'] == 6 and not result['ok'], result
    assert all({'x', 'y', 'actual', 'expected', 'delta'} <= sample.keys() for sample in result['samples'])
    print('wrong-color injection: color=6/12; coordinates/RGB retained')

    result = matrix.metrics(reference, base, base)
    assert not result['coverage'] and result['colors'] == 12 and not result['text'], result
    assert result['glyph_pixels'] == 0 and reference.samples() == samples, result
    print('lost-text injection: text failure detected despite intact colored fill')

    text_reference = matrix.Reference(only_white_samples(oracle([region('text', (40, 40, 160, 100), text=True)])))
    ink = blank.copy()
    ink.rectangle((48, 48, 89, 69), fill=(0, 0, 0))
    result = matrix.metrics(text_reference, ink, blank)
    # Remove samples beneath the deliberately injected glyphs; unlike sample
    # selection from pixels, this predetermined background pool is independent.
    assert result['coverage'] and result['text'] and result['coverage_shapes'][0]['kind'] == 'text', result
    print('transparent textbox: inset glyph ink passes without filling the frame')

    overflow = blank.copy()
    overflow.rectangle((48, 48, 175, 69), fill=(0, 0, 0))
    result = matrix.metrics(text_reference, overflow, blank)
    assert not result['coverage'] and result['text'], result
    assert result['coverage_shapes'][0]['actual_bbox'] == (48, 48, 176, 70), result
    print('text overflow injection: glyphs outside the frame rejected')

    two = only_white_samples(oracle([region('first', (40, 40, 160, 100), text=True),
                                    region('second', (190, 40, 310, 100), text=True)]))
    result = matrix.metrics(matrix.Reference(two), ink, blank)
    assert not result['coverage'] and not result['text'], result
    assert result['coverage_shapes'][0]['ok'] and not result['coverage_shapes'][1]['ok'], result
    print('one-of-two textboxes lost: per-shape presence failure detected')

    border_ref = matrix.Reference(only_white_samples(oracle([region('border', (40, 40, 160, 100))])))
    border = blank.copy()
    border.rectangle((40, 40, 159, 99), outline=(0, 0, 0))
    result = matrix.metrics(border_ref, border, border)
    assert result['coverage'] and result['coverage_shapes'][0]['kind'] == 'outline', result
    assert not matrix.metrics(border_ref, blank, blank)['coverage']
    print('unfilled outline: border ink required; missing border rejected')

    colored = only_white_samples(oracle([region('border', (40, 40, 160, 100))], (32, 64, 96)))
    colored_blank = matrix.Raster.new(blank.size, (32, 64, 96))
    result = matrix.metrics(matrix.Reference(colored), colored_blank, colored_blank)
    assert not result['coverage'] and result['colors'] == 12, result
    print('colored backdrop: background cannot impersonate missing foreground ink')

    text_records = record(0xfa0, '中文\rText'.encode('utf-16le')) + record(0xfa8, b'Table')
    fake = record(0xfa0, b'not a nested record')
    # Both incremental snapshots are visited; an atom containing similar bytes
    # must remain unchanged. Textbox records nested in drawing containers count.
    snapshot = record(0x3e8, record(0xff0, text_records, 15) +
                      record(0x40c, record(0xf00d, text_records, 15), 15), 15)
    stream = snapshot + record(0x4000, fake) + snapshot
    for sector in (512, 4096):
        for padding in (0, 5000):
            source_stream = stream + record(0x4000, b'x'*padding)
            source = compound(source_stream, sector_size=sector)
            changed = matrix.without_text(source)
            before, after = matrix.Compound(source), matrix.Compound(changed)
            mapping = before.stream_map('PowerPoint Document')
            old = before.read(mapping)
            new = after.read(after.stream_map('PowerPoint Document'))
            offsets = list(matrix.text_atom_offsets(old))
            assert len(offsets) == 8
            assert not list(matrix.text_atom_offsets(new))
            allowed = {mapping[at+i] for at in offsets for i in range(2)}
            assert len(changed) == len(source)
            assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, changed)))
            assert fake in new, 'atom payload was incorrectly traversed'
            assert all(struct.unpack_from('<H', new, at)[0] == 0x7ffe for at in offsets)
    print('textless CFB mutation: mini/regular streams, 512/4096 sectors, nested text and both persist snapshots preserved')

    # Empty mini/root streams are represented with either sentinel by CFB
    # writers. They are never followed when their declared length/count is zero.
    empty_mini = bytearray(compound(record(0x4000, b'x'*5000)))
    parsed = matrix.Compound(empty_mini)
    directory_map = parsed.chain(parsed.u32(48), parsed.fat, parsed.sector)
    for marker in (matrix.END, matrix.FREE):
        candidate = empty_mini.copy()
        struct.pack_into('<I', candidate, 60, marker)
        for i, value in enumerate(struct.pack('<I', marker)):
            candidate[directory_map[116+i]] = value
        assert matrix.Compound(candidate).read(matrix.Compound(candidate).stream_map('PowerPoint Document'))
    print('CFB empty mini/root streams: END/FREE sentinels accepted without following a chain')

    try:
        list(matrix.text_atom_offsets(record(0x3e8, b'broken', 15)))
    except ValueError:
        pass
    else:
        raise AssertionError('truncated record accepted')
    print('textless mutation: truncated records rejected')

    single_entry = dict(slides=1, oracle=data)
    many_oracle = dict(data, slides=data['slides']*20)
    many_entry = dict(slides=20, oracle=many_oracle, benchmark=True, benchmark_baseline='single')
    single_result = dict(file='single.ppt', pages=[dict(render_ms=1000, render_samples_ms=[1000])])
    many_result = dict(file='many.ppt', pages=[dict(render_ms=2000, render_samples_ms=[2000]) for _ in range(20)])
    with redirect_stdout(StringIO()):
        perf = matrix.performance([(None, single_entry), (None, many_entry)], [single_result, many_result])[0]
        assert perf['ok'] and perf['ratio'] == 2 and not perf['max_under_200ms'], perf
        for page in many_result['pages']:
            page.update(render_ms=4000, render_samples_ms=[4000])
        perf = matrix.performance([(None, single_entry), (None, many_entry)], [single_result, many_result])[0]
        assert not perf['ok'] and perf['ratio'] == 4, perf
    print('performance gate: same-machine ratios enforced; absolute milliseconds remain observations')


if __name__ == '__main__':
    run()
