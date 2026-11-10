#!/usr/bin/env python3
"""Merge public-domain EPUBs into one oversized EPUB3 for stress testing.

Each source volume keeps its original relative file names under OEBPS/vNN/, so
internal links, CSS and images stay valid without rewriting XHTML. Sources are
cycled in the given order until --volumes volumes are emitted; repeated
volumes are byte-identical copies under a new directory. The navigation
document links only each volume's Gutenberg licence heading, which reproduces
the single-book behaviour (the engine recovers the body TOC).
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET
import zipfile

OPF = '{http://www.idpf.org/2007/opf}'
DC = '{http://purl.org/dc/elements/1.1/}'
CONTAINER = '{urn:oasis:names:tc:opendocument:xmlns:container}'


def load(path):
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read('META-INF/container.xml'))
    opf_path = root.find(f'.//{CONTAINER}rootfile').get('full-path')
    base = PurePosixPath(opf_path).parent
    opf = ET.fromstring(z.read(opf_path))
    title = opf.find(f'.//{DC}title').text or path.stem
    manifest = {}
    for item in opf.find(f'{OPF}manifest'):
        manifest[item.get('id')] = item.attrib
    spine = [i.get('idref') for i in opf.find(f'{OPF}spine') if i.get('linear', 'yes') != 'no']
    nav = next((m for m in manifest.values() if 'nav' in (m.get('properties') or '')), None)
    licence = []
    if nav:
        text = z.read(str(base / nav['href'])).decode('utf-8')
        licence = re.findall(r'<a href="([^"]+)"[^>]*>([^<]*LICENSE[^<]*)</a>', text)
    return z, base, title, manifest, spine, nav, licence


def merge(sources, volumes, output):
    loaded = [load(Path(s)) for s in sources]
    files, items, spine, nav_points, record = {}, [], [], [], []
    for v in range(volumes):
        z, base, title, manifest, order, nav, licence = loaded[v % len(loaded)]
        prefix = f'v{v + 1:02d}'
        for key, item in manifest.items():
            if nav is not None and item is nav or item.get('media-type') == 'application/x-dtbncx+xml':
                continue
            href = f'{prefix}/{item["href"]}'
            files[f'OEBPS/{href}'] = z.read(str(base / item['href']))
            props = (item.get('properties') or '').replace('cover-image', '').strip()
            if v == 0 and 'cover-image' in (item.get('properties') or ''):
                props = (props + ' cover-image').strip()
            attrs = f' properties="{props}"' if props else ''
            items.append(f'<item id="{prefix}_{key}" href="{href}" media-type="{item["media-type"]}"{attrs}/>')
        spine += [f'<itemref idref="{prefix}_{idref}"/>' for idref in order]
        nav_points += [f'<li><a href="{prefix}/{h}">{label}</a></li>' for h, label in licence]
        record.append({'volume': prefix, 'source': Path(sources[v % len(loaded)]).name, 'title': title,
                       'repeat': v >= len(loaded), 'spine_items': len(order)})
    nav = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh"><head><title>目录</title></head><body>'
           '<nav epub:type="toc"><ol>' + ''.join(nav_points) + '</ol></nav></body></html>')
    files['OEBPS/nav.xhtml'] = nav.encode('utf-8')
    items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    ident = hashlib.sha256(json.dumps(record, ensure_ascii=False).encode()).hexdigest()[:16]
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           'unique-identifier="id" xml:lang="zh"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="id">urn:exr-large-book:{ident}</dc:identifier>'
           f'<dc:title>超大合订本 {volumes} 卷</dc:title><dc:language>zh</dc:language>'
           '<dc:rights>Public domain in the USA (Project Gutenberg sources).</dc:rights>'
           '<meta property="dcterms:modified">2026-11-09T00:00:00Z</meta></metadata><manifest>'
           + ''.join(items) + '</manifest><spine>' + ''.join(spine) + '</spine></package>')
    container = ('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w') as out:
        out.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip', zipfile.ZIP_STORED)
        out.writestr('META-INF/container.xml', container, zipfile.ZIP_DEFLATED)
        out.writestr('OEBPS/content.opf', opf, zipfile.ZIP_DEFLATED)
        for name, data in files.items():
            out.writestr(zipfile.ZipInfo(name, (2026, 11, 9, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
    text_chars = images = 0
    for name, data in files.items():
        if name.endswith(('.xhtml', '.html', '.htm')):
            text_chars += len(re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', data.decode('utf-8', 'replace'))))
        elif name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')):
            images += 1
    return {'output': str(output), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'volumes': record,
            'spine_items': len(spine), 'text_chars_non_space': text_chars, 'images': images}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--volumes', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('sources', nargs='+')
    a = p.parse_args()
    meta = merge(a.sources, a.volumes, a.output)
    a.output.with_suffix('.meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    print(meta['bytes'], meta['text_chars_non_space'], meta['images'], meta['spine_items'])


if __name__ == '__main__':
    main()
