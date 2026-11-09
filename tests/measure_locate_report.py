#!/usr/bin/env python3
"""Measure each TOC entry once through the public SDK, without rendering."""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path


class Error(c.Structure):
    _fields_ = [('code', c.c_int), ('message', c.c_char * 256)]


class Target(c.Structure):
    _fields_ = [('part', c.c_size_t), ('fragment', c.c_char_p), ('offset', c.c_size_t)]


class Entry(c.Structure):
    _fields_ = [('title', c.c_char_p), ('level', c.c_size_t), ('target', Target),
                ('source', c.c_int), ('play_order', c.c_size_t)]


class Location(c.Structure):
    _fields_ = [('part', c.c_size_t), ('offset', c.c_size_t), ('state', c.c_int)]


class Report(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in
                ('total_entries', 'resolved_exact', 'resolved_part_start', 'missing_part', 'missing_anchor')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dll', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    dll = args.dll.resolve()
    directory = os.add_dll_directory(str(dll.parent)) if os.name == 'nt' else None
    sdk = c.CDLL(str(dll))
    signatures = {
        'open': (c.c_int, [c.c_char_p, c.POINTER(c.c_void_p), c.POINTER(Error)]),
        'toc': (c.c_int, [c.c_void_p, c.POINTER(c.POINTER(Entry)), c.POINTER(c.c_size_t), c.POINTER(Error)]),
        'locate': (c.c_int, [c.c_void_p, c.POINTER(Target), c.POINTER(Location), c.POINTER(Error)]),
        'locate_report': (Report, [c.c_void_p]),
        'locate_report_reset': (None, [c.c_void_p]),
        'free': (None, [c.c_void_p]),
    }
    for name, (result, arguments) in signatures.items():
        function = getattr(sdk, 'exr_publication_' + name)
        function.restype, function.argtypes = result, arguments
    result = dict(dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(), books=[])
    books = json.loads(args.manifest.read_text(encoding='utf-8-sig'))['books']
    selected = ['hongloumeng-24264', 'xingshihengyan-24239', 'pachinko']
    for name in selected:
        book = next(b for b in books if b['id'] == name)
        path = Path(book['path'])
        if not path.is_absolute():
            path = args.manifest.parent / path
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == book['sha256']
        publication, count, entries, error = c.c_void_p(), c.c_size_t(), c.POINTER(Entry)(), Error()
        assert not sdk.exr_publication_open(str(path).encode('utf-8'), c.byref(publication), c.byref(error)), error.message
        try:
            assert not sdk.exr_publication_toc(publication, c.byref(entries), c.byref(count), c.byref(error)), error.message
            sdk.exr_publication_locate_report_reset(publication)
            observed = [0, 0, 0]
            missing_by_part = {}
            for i in range(count.value):
                location = Location()
                assert not sdk.exr_publication_locate(publication, c.byref(entries[i].target), c.byref(location), c.byref(error)), error.message
                observed[location.state] += 1
                if location.state == 1:
                    assert location.offset == 0
                    key = str(location.part)
                    missing_by_part[key] = missing_by_part.get(key, 0) + 1
            report = sdk.exr_publication_locate_report(publication)
            counters = {name: getattr(report, name) for name, _ in Report._fields_}
            assert report.total_entries == count.value
            assert [report.resolved_exact, report.missing_anchor, report.missing_part] == observed
            assert report.resolved_part_start == report.missing_anchor
            result['books'].append(dict(id=name, sha256=digest, **counters, missing_anchor_by_part=missing_by_part))
            print(json.dumps(result['books'][-1]), flush=True)
            sdk.exr_publication_locate_report_reset(publication)
            assert not sdk.exr_publication_locate_report(publication).total_entries
        finally:
            sdk.exr_publication_free(publication)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    if directory:
        directory.close()


if __name__ == '__main__':
    main()
