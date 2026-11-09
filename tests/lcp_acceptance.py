#!/usr/bin/env python3
"""Reproduce A2 with public EDRLab input, a native comparison probe and SDK errors.

Downloads remain under --samples; no decrypted EPUB or resource is written.
The native probe compares every manifest resource in memory and counts pages.
"""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

BASE = 'https://raw.githubusercontent.com/edrlab/r2-shared-js/develop/misc/epubs/'
SAMPLES = {
    'wasteland.epub': ('wasteland-otf-obf_LCP_dan.lcpl.epub', '490bdc43b358dae88227865bb8ae9b2c4188c59d7d418a86219ef082aba6e093'),
    'wasteland-clear.epub': ('wasteland-otf-obf.epub', '6805fe8c45134a141dbc0dc5b0357774112adb977095b19427baa4c260372cbd'),
}


class Error(c.Structure):
    _fields_ = [('code', c.c_int), ('message', c.c_char * 256)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--samples', type=Path, required=True)
    ap.add_argument('--library', type=Path, required=True)
    ap.add_argument('--probe', type=Path, required=True)
    ap.add_argument('--font', type=Path, default=Path('tests/fixtures/fonts/primary.ttf'))
    ap.add_argument('--fixtures', type=Path, default=Path('tests/fixtures/lcp'))
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.samples.mkdir(parents=True, exist_ok=True)
    provenance = []
    for local, (remote, expected) in SAMPLES.items():
        file = args.samples / local
        if not file.exists():
            with urllib.request.urlopen(BASE + remote, timeout=60) as response:
                file.write_bytes(response.read())
        assert digest(file) == expected, f'Public sample changed: {local}'
        provenance.append(dict(filename=local, url=BASE + remote, sha256=expected, size=file.stat().st_size))
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    result = subprocess.run([str(args.probe.resolve()), 'sample',
                             str(args.samples / 'wasteland.epub'), str(args.samples / 'wasteland-clear.epub'),
                             'dan', str(args.font)], check=True, capture_output=True, text=True,
                            creationflags=flags)
    sample = json.loads(result.stdout)
    assert sample['pages'] > 0 and sample['resources_equal'] == 10
    directory = os.add_dll_directory(str(args.library.resolve().parent)) if os.name == 'nt' else None
    lib = c.CDLL(str(args.library.resolve()))
    lib.exr_publication_open_ex.argtypes = [c.c_char_p, c.c_char_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    lib.exr_publication_open_ex.restype = c.c_int
    lib.exr_publication_free.argtypes = [c.c_void_p]
    errors = []
    for scenario, file, password, expected in [
        ('missing_passphrase', args.samples / 'wasteland.epub', None, 14),
        ('wrong_passphrase', args.samples / 'wasteland.epub', b'wrong', 15),
        ('expired', args.fixtures / 'expired.epub', 'LCP café 口令'.encode(), 16),
        ('unsupported_profile', args.fixtures / 'profile.epub', b'any', 17),
        ('adobe_adept_marker', args.fixtures / 'adept-marker.epub', b'any', 17),
    ]:
        publication, error = c.c_void_p(), Error()
        status = lib.exr_publication_open_ex(str(file).encode(), password, c.byref(publication), c.byref(error))
        if publication.value:
            lib.exr_publication_free(publication)
        assert status == expected and error.code == expected and not publication.value, (scenario, status, error.message)
        errors.append(dict(scenario=scenario, status=status, reason=error.message.decode()))
    for local, (_, expected) in SAMPLES.items():
        assert digest(args.samples / local) == expected
    data = dict(sample=sample, samples=provenance, passphrase='dan (public test credential)',
                errors=errors, original_archives_unchanged=True,
                library_sha256=digest(args.library), probe_sha256=digest(args.probe),
                font_sha256=digest(args.font),
                scope='LCP Basic Profile resource decoder; no production profiles or signature/PKI validation')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(sample=sample, errors=errors), ensure_ascii=True))
    if directory:
        directory.close()


if __name__ == '__main__':
    main()
