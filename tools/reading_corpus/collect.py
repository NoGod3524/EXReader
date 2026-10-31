#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Collect published inputs in Actions; discovery never runs the engine."""
import argparse
from datetime import timezone
from email.utils import parsedate_to_datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PolicyText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.words = []

    def handle_data(self, data):
        self.words.append(data)


def retry_delay(value, attempt):
    if value is not None:
        value = value.strip()
        try:
            if value.isascii() and value.isdigit():
                return float(value)
            date = parsedate_to_datetime(value)
            return max(0, date.replace(tzinfo=date.tzinfo or timezone.utc).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            pass
    return 2 ** (attempt + 1)


def fetch(url, limit):
    if not url.startswith('https://'):
        raise ValueError('HTTPS required')
    request = urllib.request.Request(url, headers={'User-Agent': 'EXReader-reading-corpus/1 (compatibility research)'})
    deadline = time.monotonic() + 180
    for attempt in range(4):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Download retry window exhausted')
        try:
            with urllib.request.urlopen(request, timeout=min(60, remaining)) as response:
                if not response.url.startswith('https://'):
                    raise ValueError('HTTPS redirect required')
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError('Declared download bound exceeded')
                return data, response.url
        except urllib.error.HTTPError as error:
            if not error.url.startswith('https://'):
                raise ValueError('HTTPS redirect required') from error
            if error.code != 429 or attempt == 3:
                raise
            delay = retry_delay(error.headers.get('Retry-After'), attempt)
            if delay >= deadline - time.monotonic():
                raise
            error.close()
            print(json.dumps({'collection_retry': {'url': url, 'status': 429, 'attempt': attempt + 1,
                                                   'delay_seconds': delay}}), flush=True)
            time.sleep(delay)


def structure(path, entry):
    # Independent source inspection only: no SDK outcomes influence selection.
    if entry['format'] == 'EPUB':
        with zipfile.ZipFile(path) as book:
            root = ET.fromstring(book.read('META-INF/container.xml'))
            opf = next(x.attrib['full-path'] for x in root.iter() if x.tag.endswith('rootfile'))
            package = ET.fromstring(book.read(opf))
            items = [x for x in package.iter() if x.tag.endswith('}item')]
            return {'spine_items': sum(x.tag.endswith('}itemref') for x in package.iter()),
                    'image_items': sum(x.attrib.get('media-type', '').startswith('image/') for x in items),
                    'largest_archive_member_bytes': max(x.file_size for x in book.infolist()),
                    'rights': [x.text for x in package.iter() if x.tag.endswith('}rights')]}
    proc = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise ValueError('Independent pdfinfo failed')
    return {'pdfinfo': proc.stdout}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['discover', 'collect'])
    p.add_argument('manifest', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    if a.output.exists():
        p.error('Choose a new output; previous failures are retained')
    a.output.mkdir(parents=True)
    manifest_bytes = a.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    records, failures, hashes = [], [], set()
    for original in manifest['files']:
        entry = dict(original)
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe manifest path')
        folder = a.output / 'assets'
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            time.sleep(0.5)
            data, final_url = fetch(entry['source_url'], entry['limits']['download_bytes'])
            if a.mode == 'collect' and (sha(data) != entry['sha256'] or len(data) != entry['size']):
                raise ValueError('Frozen source identity changed')
            if sha(data) in hashes:
                raise ValueError('Duplicate document content')
            hashes.add(sha(data))
            target.write_bytes(data)
            time.sleep(0.5)
            rights, rights_url = fetch(entry['license_url'], 4 * 1024 * 1024)
            evidence = a.output / 'licenses' / (entry['id'] + '.txt')
            evidence.parent.mkdir(exist_ok=True)
            evidence.write_bytes(rights)
            policy = PolicyText()
            policy.feed(rights.decode('utf-8'))
            policy_text = ' '.join(' '.join(policy.words).split())
            if a.mode == 'collect' and not all(term in policy_text for term in entry['license_required_terms']):
                raise ValueError('Required license terms absent from current publisher policy')
            entry.update(sha256=sha(data), size=len(data), bytes=len(data),
                         retrieved_url=final_url, retrieved_license_url=rights_url,
                         source_structure=structure(target, entry))
            entry['observed_license_sha256'] = sha(rights)
            if a.mode == 'discover':
                entry['license_sha256'] = sha(rights)
            records.append(entry)
            print(json.dumps({'asset': entry}, ensure_ascii=False), flush=True)
        except Exception as error:
            failure = {'id': entry['id'], 'error_type': type(error).__name__, 'error': str(error)}
            failures.append(failure)
            print(json.dumps({'collection_failure': failure}), flush=True)
    result = dict(manifest, files=records, complete=not failures,
                  target=len(manifest['files']), collection_failures=failures,
                  original_manifest_sha256=sha(manifest_bytes), engine_executed=False)
    (a.output / 'manifest.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'collection_complete': not failures, 'collected': len(records),
                      'required': len(manifest['files']), 'engine_executed': False}), flush=True)
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
