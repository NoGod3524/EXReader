#!/usr/bin/env python3
"""Differential raw-codec check against Python's independent liblzma encoder.

Pass a test-only shared library built from src/lzma.c and src/common.c; this
does not link liblzma into the engine. Optionally emit libFuzzer seeds.
"""
import argparse
import ctypes as c
import lzma
from pathlib import Path
import random


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--seeds', type=Path)
    args = parser.parse_args()
    sdk = c.CDLL(str(args.dll.resolve()))
    decode = sdk.exr_lzma_decode
    decode.argtypes = [c.c_int, c.c_void_p, c.c_size_t, c.c_void_p, c.c_size_t,
                       c.c_void_p, c.c_size_t, c.c_void_p, c.c_void_p]
    rng = random.Random(47)
    values = [b'', b'A', b'A' * 300000, bytes(range(256)) * 5000,
              rng.randbytes(400000), b'hello reader 1234\n' * 300000]
    checks = negatives = 0
    if args.seeds:
        args.seeds.mkdir(parents=True, exist_ok=True)
    for two in (0, 1):
        for lc, lp, pb in ((3, 0, 2), (0, 0, 0), (2, 1, 1), (4, 0, 4)):
            filters = [dict(id=lzma.FILTER_LZMA2 if two else lzma.FILTER_LZMA1,
                            dict_size=1 << 20, lc=lc, lp=lp, pb=pb)]
            props = bytes([16]) if two else bytes([(pb * 5 + lp) * 9 + lc]) + (1 << 20).to_bytes(4, 'little')
            for data in values:
                packed = lzma.compress(data, format=lzma.FORMAT_RAW, filters=filters)
                output, error = c.create_string_buffer(len(data)), c.create_string_buffer(260)
                status = decode(two, props, len(props), packed, len(packed), output, len(data), None, error)
                assert not status and output.raw == data, (two, lc, lp, pb, len(data), status, error.raw[4:])
                checks += 1
                if args.seeds:
                    seed = bytes([two]) + props + min(len(data), 65535).to_bytes(2, 'little') + packed
                    (args.seeds / f'raw-{checks}').write_bytes(seed)
                for length in sorted({0, min(4, len(packed)), len(packed) // 2, len(packed) - 1}):
                    if length == len(packed):
                        continue
                    status = decode(two, props, len(props), packed, length, output, len(data), None, error)
                    assert status != 0, (two, len(data), length)
                    negatives += 1
    print(f'{checks} independent codec round trips; {negatives} truncated streams rejected')


if __name__ == '__main__':
    main()
