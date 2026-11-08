#!/usr/bin/env python3
"""On a macOS CI runner, merge installed engine components/vendors into one .a."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from check_exports import DEFAULT_CONTRACT, inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('requires macOS CI and xcrun libtool; no Windows archive substitution')
    layers = 'base graphics text doc formats layout render pdf pdf_edit audio library textindex'.split()
    components = [args.sdk/'lib'/('libexr_'+name+'.a') for name in layers]
    for path in components:
        if not path.is_file():
            parser.error('missing full SDK component: ' + str(path))
    vendors = sorted((args.sdk/'lib/exreader').glob('*.a'))
    if not vendors:
        parser.error('installed vendor archives absent')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['xcrun', 'libtool', '-static', '-o', str(args.output),
                    *(str(p) for p in components+vendors)], check=True)
    expected = set(json.loads(DEFAULT_CONTRACT.read_text())['symbols'])
    report = inspect(args.output, expected)
    if any(p['missing'] for p in report['slices']):
        raise ValueError('merged archive is missing ABI symbols')
    print(f'{args.output}: {report["size_bytes"]} bytes; SHA256={report["sha256"]}')
    print('Static definitions include vendors; use --allow-extra, then link/run the acceptance app.')


if __name__ == '__main__':
    main()
