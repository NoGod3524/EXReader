"""Rebuild the local-only simplified corpus; retain original bytes and provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request
import zipfile
import html
import xml.etree.ElementTree as ET

from run_realbooks import file_hash, write_json


def convert_epub(source, target, converter):
    # Convert text nodes only: hrefs, IDs, styles, images and package paths survive.
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, 'w') as new:
        for name in old.namelist():
            data = old.read(name)
            if name.endswith(('.xhtml', '.html', '.opf', '.ncx')):
                tokens = re.split(r'(<[^>]*>)', data.decode('utf-8'))
                data = ''.join(t if i % 2 else converter.convert(t)
                               for i, t in enumerate(tokens)).encode('utf-8')
            item = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED
            new.writestr(item, data)


def package(target, title, chapters, resources):
    """Minimal deterministic EPUB2, keeping complete chapter content/resources."""
    files = {'META-INF/container.xml': b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'}
    items, refs = [], []
    for i, (name, data) in enumerate(chapters + resources):
        suffix = Path(name).suffix
        mime = {'.xhtml': 'application/xhtml+xml', '.css': 'text/css', '.png': 'image/png',
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml',
                '.gif': 'image/gif'}.get(suffix, 'application/octet-stream')
        files[name] = data
        items.append(f'<item id="i{i}" href="{html.escape(name)}" media-type="{mime}"/>')
        if i < len(chapters):
            refs.append(f'<itemref idref="i{i}"/>')
    files['content.opf'] = ('<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">exr-simplified-'+html.escape(title)+
        '</dc:identifier><dc:title>'+html.escape(title)+'</dc:title><dc:language>zh-Hans</dc:language></metadata>'
        '<manifest>'+''.join(items)+'</manifest><spine>'+''.join(refs)+'</spine></package>').encode()
    with zipfile.ZipFile(target, 'w') as z:
        for name, data in [('mimetype', b'application/epub+zip')] + list(files.items()):
            info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED
            z.writestr(info, data)


def howto_epub(source, target):
    with zipfile.ZipFile(source) as z:
        opf = ET.fromstring(z.read('content.opf'))
        ns = {'o': 'http://www.idpf.org/2007/opf'}
        paths = {e.attrib['id']: e.attrib['href'] for e in opf.find('o:manifest', ns)}
        names = [paths[e.attrib['idref']] for e in opf.find('o:spine', ns)]
        names = list(dict.fromkeys(n for n in names if n.startswith('howto/') or n in ('copyright.xhtml', 'license.xhtml')))
        chapters = [(n, z.read(n)) for n in names]
        resources = [(n, z.read(n)) for n in sorted(z.namelist())
                     if n.endswith(('.css', '.png', '.jpg', '.jpeg', '.svg', '.gif'))]
    package(target, 'Python 3.14 HOWTO 中文完整册', chapters, resources)


def byte_epub(source, target):
    import markdown
    import importlib.metadata
    if importlib.metadata.version('Markdown') != '3.10.2':
        raise ValueError('use Markdown==3.10.2')
    chapters = []
    with zipfile.ZipFile(source) as z:
        prefix = z.namelist()[0]
        summary = z.read(prefix+'SUMMARY.md').decode('utf-8')
        for name in re.findall(r'\]\(([^)]+\.md)\)', summary):
            text = z.read(prefix+name).decode('utf-8')
            # Old GitBook accepts #Title; CommonMark requires the space.
            text = re.sub(r'^(#{1,6})(?=\S)', r'\1 ', text, flags=re.M)
            body = markdown.markdown(text, extensions=['tables', 'fenced_code'])
            body = re.sub(r'(href=")([^"]+)\.md(?=["#])', r'\1\2.xhtml', body)
            data = ('<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-Hans"><head><title>简明 Python 教程</title></head><body>'+body+'</body></html>').encode()
            chapters.append((name[:-3]+'.xhtml', data))
        resources = [(n[len(prefix):], z.read(n)) for n in sorted(z.namelist())
                     if n.startswith(prefix+'img/') and not n.endswith('/')]
    package(target, '简明 Python 教程 4.08c', chapters, resources)


def prepare(manifest, root):
    from opencc import OpenCC
    import importlib.metadata
    if importlib.metadata.version('opencc-python-reimplemented') != '0.1.7':
        raise ValueError('use opencc-python-reimplemented==0.1.7')
    converter = OpenCC('t2s')
    root.mkdir(parents=True, exist_ok=True)
    result = []
    for entry in json.loads(manifest.read_text(encoding='utf-8'))['books']:
        source = root / entry['source_filename']
        if not source.exists():
            source.write_bytes(urllib.request.urlopen(entry['download_url'], timeout=60).read())
        if file_hash(source) != entry['source_sha256']:
            raise ValueError(f"source hash changed: {entry['id']}; retain/review new edition separately")
        target = root / entry['filename']
        if entry['conversion'] == 'OpenCC t2s 0.1.7':
            convert_epub(source, target, converter)
        elif entry['conversion'] == 'HOWTO complete spine; original XHTML/resources':
            howto_epub(source, target)
        elif entry['conversion'] == 'GitBook Markdown to XHTML; Markdown 3.10.2':
            byte_epub(source, target)
        elif source != target:
            target.write_bytes(source.read_bytes())
        if file_hash(target) != entry['sha256']:
            raise ValueError(f"derived hash differs: {entry['id']}")
        result.append({'id': entry['id'], 'sha256': file_hash(target)})
        print(entry['id'], 'verified', flush=True)
    write_json(root / 'prepared.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('simplified.json'))
    parser.add_argument('--root', type=Path, default=Path('tests/corpus/simplified'))
    args = parser.parse_args()
    prepare(args.manifest, args.root)
