#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Footnote recognition counts through the public SDK (exr_publication_footnotes).
Usage: count_footnotes.py SDK_DLL OUTPUT.json EPUB...  (or --corpus tools/regress/corpus.json)
"""
import ctypes as C
import json
import sys
from pathlib import Path


class Error(C.Structure):
    _fields_ = [('code', C.c_int), ('message', C.c_char * 256)]


class Footnote(C.Structure):
    _fields_ = [('id', C.c_char_p), ('label', C.c_char_p), ('target_part', C.c_size_t),
                ('target_offset', C.c_size_t), ('text', C.c_char_p)]


class Reference(C.Structure):
    _fields_ = [('part', C.c_size_t), ('start', C.c_size_t), ('end', C.c_size_t), ('footnote', C.c_size_t)]


def main():
    dll, output, *books = sys.argv[1:]
    if books[:1] == ['--corpus']:
        books = [b['path'] for b in json.loads(Path(books[1]).read_text(encoding='utf-8'))['books']]
    sdk = C.CDLL(str(Path(dll).resolve()))
    sdk.exr_publication_open.argtypes = [C.c_char_p, C.POINTER(C.c_void_p), C.POINTER(Error)]
    sdk.exr_publication_footnotes.argtypes = [C.c_void_p, C.POINTER(C.POINTER(Footnote)), C.POINTER(C.c_size_t),
                                              C.POINTER(C.POINTER(Reference)), C.POINTER(C.c_size_t), C.POINTER(Error)]
    sdk.exr_publication_free.argtypes = [C.c_void_p]
    result = []
    for path in books:
        p, e = C.c_void_p(), Error()
        notes, n, refs, r = C.POINTER(Footnote)(), C.c_size_t(), C.POINTER(Reference)(), C.c_size_t()
        if sdk.exr_publication_open(str(path).encode('utf-8'), C.byref(p), C.byref(e)) != 0:
            result.append(dict(book=Path(path).name, error=e.message.decode('utf-8', 'replace'))); continue
        status = sdk.exr_publication_footnotes(p, C.byref(notes), C.byref(n), C.byref(refs), C.byref(r), C.byref(e))
        item = dict(book=Path(path).name, status=status, footnotes=n.value, references=r.value)
        if status == 0 and n.value:
            item['first'] = dict(id=notes[0].id.decode(), label=notes[0].label.decode(),
                                 text=notes[0].text.decode('utf-8', 'replace')[:120])
        result.append(item); sdk.exr_publication_free(p)
        print(json.dumps({k: v for k, v in item.items() if k != 'first'}, ensure_ascii=False), flush=True)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
