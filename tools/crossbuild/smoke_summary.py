"""Compare the same platform probe's logs and tightly packed RGBA bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(directory):
    log = (directory / 'create.log').read_text()
    pages = int(re.search(r'^PASS open pages=(\d+)$', log, re.M)[1])
    hits = int(re.search(r'^PASS search_all needle=deliveryneedle hits=(\d+)$', log, re.M)[1])
    width, height, ink = map(int, re.search(r'^PASS render width=(\d+) height=(\d+) ink_pixels=(\d+)', log, re.M).groups())
    pixels = directory / 'page.rgba'
    if pixels.stat().st_size != width * height * 4 or not 0 < ink < width * height:
        raise ValueError('Missing or invalid RGBA pixel evidence: ' + str(directory))
    if pages <= 0 or hits != 1000:
        raise ValueError('Incorrect fixture pagination/search: ' + str(directory))
    return {'pages': pages, 'search_hits': hits, 'pixel_sha256': sha256(pixels),
            'png_sha256': sha256(directory / 'page.png'), 'width': width,
            'height': height, 'ink_pixels': ink, 'pixel_bytes': pixels.stat().st_size,
            'raw_log_sha256': sha256(directory / 'create.log')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True, type=Path,
                        help='JSON: platform -> {directory, library, book, font, source_commit, environment}')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    inputs = json.loads(args.inputs.read_text())
    if set(inputs) != {'windows', 'linux', 'android'}:
        raise ValueError('Require Windows, Linux and Android evidence')
    rows = {}
    for platform, entry in inputs.items():
        rows[platform] = summarize(Path(entry['directory']))
        rows[platform].update({name + '_sha256': sha256(Path(entry[name])) for name in ('book', 'font', 'library')})
        rows[platform].update({name: entry[name] for name in ('source_commit', 'environment')})
    same = {name: len({row[name] for row in rows.values()}) == 1 for name in
            ('source_commit', 'book_sha256', 'font_sha256', 'pages', 'search_hits', 'pixel_sha256')}
    result = {'schema_version': 1,
              'probe_source_sha256': sha256(Path(__file__).resolve().parents[1] / 'platforms/probe.c'),
              'layout': {'width': 360, 'height': 480, 'margin': 24, 'font_size': 18,
                         'line_height': 1.5, 'paragraph_spacing': 8, 'font_dpi': 72},
              'search': {'needle': 'deliveryneedle', 'case_sensitive': True, 'expected_hits': 1000},
              'pixels': 'SHA-256 over row-major RGBA bytes, excluding stride padding and PNG metadata',
              'platforms': rows, 'equal': same}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(same, indent=2))
    if not all(same[key] for key in same if key != 'pixel_sha256'):
        raise SystemExit('Source, fixture, pagination or search mismatch')


if __name__ == '__main__':
    main()
