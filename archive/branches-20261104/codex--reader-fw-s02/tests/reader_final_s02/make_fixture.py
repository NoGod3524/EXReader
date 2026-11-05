#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CI-only original book used for the S02 read-back.

The fixture is generated inside the workflow job, never committed, and carries a
per-run marker so the rendered page can only match this job's own input.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import common

PARAGRAPH = ('%s 中文原件回读。The relocated package must render this text from the '
             'original file without changing it.\n\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--marker', default='')
    args = parser.parse_args()
    common.need(os.environ.get('GITHUB_ACTIONS') == 'true',
                'S02 fixtures are generated in GitHub Actions only')
    output = args.output.resolve()
    common.need(not output.exists(), 'fixture output already exists: %s' % output)
    output.mkdir(parents=True)
    marker = args.marker or 'S02 RELOCATED READBACK %s %s' % (
        os.environ.get('GITHUB_RUN_ID', 'local'), os.environ.get('GITHUB_RUN_ATTEMPT', '1'))
    text = PARAGRAPH % marker * 60
    book = output / 'S02 readback.txt'
    book.write_text(text, encoding='utf-8')
    manifest = {'path': book.name, 'bytes': book.stat().st_size,
                'sha256': common.sha256_file(book), 'marker': marker,
                'paragraphs': 60, 'format': 'txt',
                'generated_by': 'tests/reader_final_s02/make_fixture.py',
                'run': os.environ.get('GITHUB_RUN_ID', ''),
                'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', '')}
    common.write_json(output / 'manifest.json', manifest)
    print(json.dumps({'fixture': manifest['path'], 'bytes': manifest['bytes'],
                      'sha256': manifest['sha256']}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
