#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only fixtures and independent full-XML oracle for the Large page-2 point."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))


def require(value, message):
    if not value:
        raise ValueError(message)


def utf16(text):
    return len(text.encode('utf-16-le')) // 2


def prepare(folder):
    from build_android_host import epub, write_fixtures
    from host_font import fetch
    write_fixtures(folder)
    # Complete-node replay must cover entities and XML whitespace, a supplementary
    # scalar, combining text, and a chapter extending beyond several 64-KiB windows.
    body = '<p>  A \t&amp;\n 😀 é  X </p>'
    body += ''.join('<p>Edge %04d: %s</p>' % (i, 'abcdefghij ' * 20) for i in range(1200))
    epub(folder / 'Boundary.epub', 'Resident CFI boundaries', [body])
    font = fetch(folder / 'font')
    print(json.dumps({'font': str(font / 'Reader.otf'),
                      'large_sha256': hashlib.sha256((folder / 'Large.epub').read_bytes()).hexdigest(),
                      'experimental_only': True}))


def check(epub, prefix, resolved):
    capture = json.loads(prefix.with_suffix('.json').read_text())
    actual = json.loads(resolved.read_text())
    require((actual['raw_node'], actual['raw_utf16']) ==
            (capture['raw_node'], capture['raw_utf16']), 'fresh-process point differs')
    with zipfile.ZipFile(epub) as book:
        xml = book.read('OEBPS/ch01.xhtml')
    root = ET.fromstring(xml)
    body = root.find('{http://www.w3.org/1999/xhtml}body')
    # This oracle parses the entire actual Large fixture independently. Its body
    # consists of one h1 and 3000 p nodes, each a complete ASCII text node.
    require(body is not None and len(body) == 3001, 'actual Large fixture shape differs')
    wanted = capture['normalized_offset']
    base = 0
    target = None
    for element in body:
        require(not list(element), 'Large reference expects un-nested raw text')
        raw = element.text or ''
        runs = list(re.finditer(r'[^ \t\r\n]+', raw))
        normalized = ' '.join(match.group() for match in runs)
        size = len(normalized.encode('utf-8'))
        if base <= wanted <= base + size:
            target = (raw, runs, base, wanted - base)
            break
        base += size + 1  # The SDK's documented block projection separator.
    require(target is not None, 'page-2 point outside full XML projection')
    raw, runs, base, local = target
    expected = None
    projected = 0
    for index, run in enumerate(runs):
        if index:
            projected += 1
        word = run.group()
        word_bytes = len(word.encode('utf-8'))
        if projected <= local <= projected + word_bytes:
            relative = local - projected
            prefix_bytes = word.encode('utf-8')[:relative]
            try:
                selected = prefix_bytes.decode('utf-8')
            except UnicodeDecodeError as error:
                raise ValueError('point is inside an independent-reference scalar') from error
            expected = utf16(raw[:run.start()] + selected)
            break
        projected += word_bytes
    require(expected is not None, 'point has no independent raw XML boundary')
    require(raw.encode('utf-8') == prefix.with_suffix('.raw').read_bytes(), 'full SDK CFI chose another raw text node')
    require(capture['full_node_start'] == base, 'full-document projection start differs from XML oracle')
    require(capture['raw_utf16'] == expected, 'raw UTF16 differs from independent full XML oracle')
    result = {'experimental_only': True, 'product_adopted': False,
              'frozen_sdk_accepted': False, 'budget_credit_seconds': 0,
              'source_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'large_sha256': hashlib.sha256(epub.read_bytes()).hexdigest(),
              'large_actual_page': 2, 'normalized_offset': wanted,
              'raw_utf16': expected, 'fresh_process_matches': True,
              'full_xml_reference_matches': True, 'full_document_reference_matches': True,
              'capture_cpu_ms': capture['capture_cpu_ms'],
              'resolve_cpu_ms': actual['resolve_cpu_ms']}
    prefix.with_suffix('.verified.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'run this experiment only in cloud CI')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'check'])
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.folder)
    else:
        check(args.folder / 'Large.epub', args.folder / 'large-page2', args.folder / 'resolved.json')


if __name__ == '__main__':
    main()
