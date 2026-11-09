#!/usr/bin/env python3
"""Reproducible full-result index acceptance against the public linear API."""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import time


class Error(c.Structure):
    _fields_ = [('code', c.c_int), ('message', c.c_char * 256)]


class Position(c.Structure):
    _fields_ = [('part', c.c_size_t), ('offset', c.c_size_t)]


class Cursor(c.Structure):
    _fields_ = [('next', Position), ('done', c.c_int)]


class Hit(c.Structure):
    _fields_ = [('found', c.c_int), ('part', c.c_size_t), ('offset', c.c_size_t), ('length', c.c_size_t)]


class Stats(c.Structure):
    _fields_ = [(k, c.c_size_t) for k in ('text_bytes', 'memory_bytes', 'peak_memory_bytes', 'disk_bytes',
                                       'indexed_parts', 'total_parts')] + [('complete', c.c_int)]


Callback = c.CFUNCTYPE(c.c_int, c.c_void_p, c.POINTER(Hit))


class SDK:
    def __init__(self, dll):
        self.directory = os.add_dll_directory(str(dll.parent)) if os.name == 'nt' else None
        self.lib = c.CDLL(str(dll))
        p, s, err = c.c_void_p, c.c_size_t, c.POINTER(Error)
        signatures = {
            'open': [c.c_char_p, c.POINTER(p), err],
            'index_build': [p, s, s, p, c.POINTER(Stats), err],
            'index_info': [p, c.POINTER(Stats), err],
            'index_search': [p, c.c_char_p, c.c_uint, c.POINTER(Cursor), s, Callback, p, p, c.POINTER(s), err],
            'search_all': [p, c.c_char_p, c.c_uint, Callback, p, p, c.POINTER(s), err],
            'index_save': [p, c.c_char_p, c.c_char_p, p, err],
            'index_load': [p, c.c_char_p, c.c_char_p, s, p, c.POINTER(Stats), err],
        }
        for name, args in signatures.items():
            fn = getattr(self.lib, 'exr_publication_' + name)
            fn.argtypes, fn.restype = args, c.c_int
            setattr(self, name, fn)
        self.free = self.lib.exr_publication_free
        self.free.argtypes, self.free.restype = [p], None

    def check(self, name, *args):
        error = Error()
        status = getattr(self, name)(*args, c.byref(error))
        if status:
            raise RuntimeError(f'{name}: {status}: {error.message.decode()}')

    def publication(self, path):
        p = c.c_void_p()
        self.check('open', str(path).encode(), c.byref(p))
        return p

    def query(self, p, query, indexed=True, flags=0, batch=64):
        hits, first_ms = [], None
        begin = time.perf_counter()

        @Callback
        def collect(_ctx, hit):
            nonlocal first_ms
            v = hit.contents
            hits.append((v.part, v.offset, v.length))
            if len(hits) == batch:
                first_ms = (time.perf_counter() - begin) * 1000
            return 1

        count = c.c_size_t()
        if indexed:
            cursor = Cursor()
            self.check('index_search', p, query.encode(), flags, c.byref(cursor), 0, collect, None, None, c.byref(count))
            assert cursor.done
        else:
            self.check('search_all', p, query.encode(), flags, collect, None, None, c.byref(count))
        elapsed = (time.perf_counter() - begin) * 1000
        assert count.value == len(hits)
        return hits, {'total_ms': elapsed, 'first_64_ms': first_ms if first_ms is not None else elapsed,
                      'count': len(hits), 'sha256': hashlib.sha256(json.dumps(hits).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dll', type=Path, required=True)
    parser.add_argument('--book', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    sdk = SDK(args.dll.resolve())
    revision = hashlib.sha256(args.book.read_bytes()).hexdigest().encode()
    result = {'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(), 'book_sha256': revision.decode(),
              'clock': 'perf_counter; API wall time; first batch = 64 hits; all hits retained and compared',
              'queries': {}, 'build_load': [], 'comparisons': []}
    for query in ('宝玉', '寶玉', '的'):
        runs = []
        for _ in range(3):
            p = sdk.publication(args.book)
            cold_hits, cold = sdk.query(p, query)
            warm_hits, warm = sdk.query(p, query)
            assert cold_hits == warm_hits
            stats = Stats()
            sdk.check('index_info', p, c.byref(stats))
            runs.append({'cold_build_search': cold, 'reuse_search': warm})
            result['memory'] = {name: getattr(stats, name) for name, _ in Stats._fields_}
            sdk.free(p)
        result['queries'][query] = runs
    for _ in range(3):
        stats = Stats()
        p = sdk.publication(args.book)
        begin = time.perf_counter()
        sdk.check('index_build', p, 0, 0, None, c.byref(stats))
        build_ms = (time.perf_counter() - begin) * 1000
        sdk.check('index_save', p, str(args.cache).encode(), revision, None)
        sdk.free(p)
        p = sdk.publication(args.book)
        begin = time.perf_counter()
        sdk.check('index_load', p, str(args.cache).encode(), revision, 0, None, c.byref(stats))
        load_ms = (time.perf_counter() - begin) * 1000
        _, loaded = sdk.query(p, '的')
        result['build_load'].append({'build_ms': build_ms, 'load_ms': load_ms, 'loaded_search': loaded})
        sdk.free(p)
    p = sdk.publication(args.book)
    sdk.check('index_load', p, str(args.cache).encode(), revision, 0, None, c.byref(stats))
    queries = ('的', '寶玉', '宝玉', '賈寶玉', '黛玉', '寶釵', '賈母', '鳳姐', '王夫人', '丫頭',
               '姑娘', '知道', '說道', '什麼', '一個', '不知', 'Gutenberg', '24264', '2021', '紅樓夢')
    for query in queries:
        lhs, a = sdk.query(p, query, False)
        rhs, b = sdk.query(p, query)
        assert lhs == rhs, query
        result['comparisons'].append({'query': query, 'equal': True, 'linear': a, 'indexed': b})
    # Resume many small batches: complete equality including every occurrence.
    expected, _ = sdk.query(p, '的', False)
    actual, cursor = [], Cursor()

    @Callback
    def collect(_ctx, hit):
        v = hit.contents
        actual.append((v.part, v.offset, v.length))
        return 1

    while not cursor.done:
        n = c.c_size_t()
        sdk.check('index_search', p, '的'.encode(), 0, c.byref(cursor), 64, collect, None, None, c.byref(n))
    assert actual == expected
    result['resumed_64_hit_batches_equal'] = True
    sdk.free(p)
    memory = result['memory']
    memory['ratio'] = memory['memory_bytes'] / memory['text_bytes']
    memory['peak_ratio'] = memory['peak_memory_bytes'] / memory['text_bytes']
    result['passed'] = (len(result['comparisons']) == 20 and memory['peak_ratio'] <= .30 and
                        all(run[mode]['first_64_ms'] <= 50 for query in ('寶玉', '的') for run in result['queries'][query]
                            for mode in ('cold_build_search', 'reuse_search')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'memory': memory, 'timings': result['queries'],
                      'build_load': result['build_load'], 'equal': len(result['comparisons'])}, ensure_ascii=True, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
