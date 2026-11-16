#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Red/green assertions, kept identical when running old and repaired DLLs."""
import argparse
import ctypes as c
import json
from pathlib import Path
import sys

import run_matrix as rt


def check(api, name):
    if name == 'text-command':
        assert api.set_text, 'missing public exr_edit_set_run_text; no supported body-text replacement command'
        return
    case = {'paragraph-markers': '14-style-inheritance', 'section-tail': '17-section-margins'}.get(name, '09-field-ref')
    item = next(v for v in json.loads((rt.HERE / 'manifest.json').read_text(encoding='utf-8'))['documents'] if v['id'] == case)
    source = rt.validate_fixture(item)
    doc = api.read(source)
    try:
        if name.startswith('text-'):
            assert api.set_text, 'missing public text command'
            block, index = api.target(doc)
            ids = block.id, block.runs[index].id
            props = bytes(block.props), bytes(block.runs[index].props)
            old = rt.unzip(api.write(doc))
            if name == 'text-history':
                doc, _ = api.change(doc)
                after = rt.unzip(api.write(doc))
                assert after == rt.expected_parts(source, True)
                assert api.undo(doc) == 0 and rt.unzip(api.write(doc)) == old
                assert api.redo(doc) == 0 and rt.unzip(api.write(doc)) == after
            elif name == 'text-alias':
                original_text = c.string_at(block.runs[index].text, block.runs[index].length)
                assert api.set_text(doc, block.id, index, block.runs[index].text + 6, len(original_text)-6) == 0
                changed = next(p for p in api.paragraphs(doc) if p.id == ids[0])
                assert c.string_at(changed.runs[index].text, changed.runs[index].length) == original_text[6:]
                assert api.set_text(doc, block.id, index, None, 0) == 0
                changed = next(p for p in api.paragraphs(doc) if p.id == ids[0])
                assert changed.runs[index].length == 0
            elif name == 'text-validation':
                for data in (b'\0', b'\x01', b'\xc0\x80', b'\xed\xa0\x80', b'\xf4\x90\x80\x80', b'\xef\xbf\xbe'):
                    storage = c.create_string_buffer(data)
                    assert api.set_text(doc, block.id, index, storage, len(data)) != 0
                    assert rt.unzip(api.write(doc)) == old
                assert api.set_text(doc, block.id, block.count, b'x', 1) != 0
                assert api.set_text(doc, 0, index, b'x', 1) != 0
                assert api.set_text(doc, block.id, index, None, 1) != 0
                assert api.set_text(doc, block.id, index, None, c.c_size_t(-1).value) != 0
                opaque = next(i for i in range(block.count) if block.runs[i].kind == 1)
                assert api.set_text(doc, block.id, opaque, b'x', 1) == 11  # EXR_UNSUPPORTED
                assert rt.unzip(api.write(doc)) == old
            elif name == 'text-transaction':
                tx = api.begin(doc)
                assert tx
                assert api.set_text(doc, block.id, index, b'changed', 7) == 0
                assert api.set_text(doc, block.id, index, b'\x01', 1) != 0
                assert api.set_text(doc, block.id, index, b'latched', 7) != 0
                assert api.commit(tx) != 0
                assert rt.unzip(api.write(doc)) == old
                assert api.undo(doc) != 0
            else:
                raise AssertionError(name)
            changed = next(p for p in api.paragraphs(doc) if p.id == ids[0])
            assert (changed.id, changed.runs[index].id) == ids
            assert (bytes(changed.props), bytes(changed.runs[index].props)) == props
            return
        actual = rt.unzip(api.write(doc))['word/document.xml']
        expected = rt.unzip(source)['word/document.xml']
        if name == 'paragraph-markers':
            assert b'<!-- paragraph property boundary --><?audit properties?><w:pPr>' in actual, 'paragraph property markers moved across pPr'
        else:
            assert b'</w:sectPr><!-- end-of-body audit marker --><?audit tail?></w:body>' in actual, 'body trailer moved before final sectPr'
        assert rt.tree(rt.parse(expected)) == rt.tree(rt.parse(actual)), 'unchanged document structure differs'
        assert expected == actual, 'unchanged main-part bytes differ'
    finally:
        api.doc_free(doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('name', choices=('text-command', 'paragraph-markers', 'section-tail',
        'text-history', 'text-alias', 'text-validation', 'text-transaction'))
    args = parser.parse_args()
    check(rt.RealBridge(args.library.resolve()), args.name)
    print(args.name, 'PASS')


if __name__ == '__main__':
    main()
