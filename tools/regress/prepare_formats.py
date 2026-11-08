"""Acquire published samples and derive encoding/container variants outside the repo.

Requires PyMuPDF only for the two explicitly labelled encrypted PDF derivatives.
No downloaded publication, extracted text, or image is written to the repository.
"""
import argparse
from pathlib import Path
import hashlib
import json
import shutil
import urllib.request
import zipfile

from run_realbooks import file_hash, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--text-pdf', type=Path, required=True)
    parser.add_argument('--second-text-pdf', type=Path, required=True)
    parser.add_argument('--scan-pdf', type=Path, required=True)
    parser.add_argument('--second-scan-pdf', type=Path, required=True)
    parser.add_argument('--additional-text-pdf', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    root = args.samples.resolve()
    if root.is_relative_to(repo):
        parser.error('--samples must be outside the repository')
    root.mkdir(parents=True, exist_ok=True)
    books = []

    def add(id, path, category, source, policy='hash', **metadata):
        path = path.resolve(strict=True)
        books.append(dict(id=id, filename=path.name, path=str(path), category=category,
                          sha256=file_hash(path), source=source, regression=policy, **metadata))

    def download(name, url):
        path = root / name
        if not path.exists():
            urllib.request.urlretrieve(url, path)
        return path

    releases = 'https://github.com/IDPF/epub3-samples/releases/download/20230704/'
    for name, category, policy in [
        ('page-blanche', 'EPUB-fixed', 'count'),
        ('haruko-html-jpeg', 'EPUB-fixed', 'count'),
        ('moby-dick-mo', 'EPUB-audio', 'count'),
        ('cc-shared-culture', 'EPUB-audio-video', 'count'),
    ]:
        url = releases + name + '.epub'
        add(name, download(name + '.epub', url), category, url, policy)
    for book in read_json(Path(__file__).with_name('corpus.json'))['books']:
        if book['id'] in ('between-the-world-and-me', 'the-house-on-mango-street'):
            add(book['id'], Path(book['path']), 'EPUB-reflow', 'existing 19-book corpus')
    for id, source in [('pdf-text-malcolm', args.text_pdf),
                       ('pdf-text-statistics', args.second_text_pdf),
                       ('pdf-scan-malcolm', args.scan_pdf),
                       ('pdf-scan-upstream', args.second_scan_pdf)]:
        add(id, source, 'PDF-scan' if 'scan' in id else 'PDF-text', 'existing local real-document corpus',
            'count' if id in ('pdf-text-statistics', 'pdf-scan-upstream') else 'hash')
    for name in ('Sample-Text.pdf', 'Sample.pdf'):
        add(name[:-4].lower(), args.payload / name, 'PDF-stress', 'existing Windows delivery payload', 'count', max_render_pages=1)
    for index, path in enumerate(args.additional_text_pdf):
        add('pdf-text-extra-' + str(index + 1), path, 'PDF-text', 'existing local real-document corpus', 'count')

    import pymupdf
    for id, source, encryption in [('pdf-encrypted-r4', args.second_text_pdf, pymupdf.PDF_ENCRYPT_AES_128),
                                    ('pdf-encrypted-r6', args.text_pdf, pymupdf.PDF_ENCRYPT_AES_256)]:
        path = root / (id + '.pdf')
        if not path.exists():
            with pymupdf.open(source) as doc:
                doc.save(path, encryption=encryption, user_pw='format-test', owner_pw='format-owner')
        add(id, path, 'PDF-encrypted', 'local encryption derivative', 'count', password_env='EXR_FORMAT_PDF_PASSWORD',
            derived_from_sha256=file_hash(source), transform='PyMuPDF ' + pymupdf.VersionBind + '; AES; no content edits')

    for name in ('page-blanche', 'haruko-html-jpeg'):
        source = root / (name + '.epub')
        path = root / (name + '.cbz')
        if not path.exists():
            with zipfile.ZipFile(source) as src, zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as dst:
                for n in sorted(src.namelist()):
                    if n.lower().endswith(('.jpg', '.jpeg', '.png')):
                        dst.writestr(Path(n).name, src.read(n))
        add(name + '-cbz', path, 'CBZ', 'real illustrated publication, image-only repack',
            derived_from_sha256=file_hash(source), transform='ZIP all PNG/JPEG members sorted by original path; unchanged image bytes')
    add('comic-fixture', repo / 'tests/fixtures/comic.cbz', 'CBZ-fixture', 'existing synthetic fixture (additional control)')

    for name in ('the-waste-land', 'accessible-epub-3'):
        license_url = f'https://www.edrlab.org/public/feed/{name}/{name}.lcpl'
        license_path = download(name + '.lcpl', license_url)
        license_bytes = license_path.read_bytes()
        license_data = json.loads(license_bytes)
        url = next(link['href'] for link in license_data['links'] if link['rel'] == 'publication')
        original = download('edrlab-' + name + '.epub', url)
        path = root / ('edrlab-' + name + '-licensed.epub')
        if not path.exists():
            shutil.copyfile(original, path)
            with zipfile.ZipFile(path, 'a') as archive:
                archive.writestr('META-INF/license.lcpl', license_bytes)
        add('drm-' + name, path, 'EPUB-DRM',
            'https://www.edrlab.org/readium-lcp/testing-readium-lcp-compliant-devices/', 'count',
            publication_url=url, license_url=license_url, license_sha256=file_hash(license_path),
            derived_from_sha256=file_hash(original),
            transform='append official public test license as META-INF/license.lcpl; encrypted resources unchanged')

    for id in (52323, 24239):
        url = f'https://www.gutenberg.org/ebooks/{id}.txt.utf-8'
        original = download(f'pg{id}.txt', url)
        # Genuine Chinese prose excerpts; choose a common representable prefix, no replacements.
        original_text = original.read_text(encoding='utf-8-sig')
        # Keep a contiguous real passage, avoiding unrepresentable header symbols.
        passages, start = [], 0
        for offset, char in enumerate(original_text):
            try:
                char.encode('gbk')
            except UnicodeEncodeError:
                passages.append((start, offset))
                start = offset + 1
        passages.append((start, len(original_text)))
        start, end = max(passages, key=lambda pair: pair[1] - pair[0])
        text = original_text[start:min(end, start + 12000)]
        assert len(text) >= 2000, 'need a substantial real Chinese passage'
        text.encode('gbk', errors='strict')
        canonical = hashlib.sha256(' '.join(text.split()).encode('utf-8')).hexdigest()
        for label, encoding in [('utf8', 'utf-8'), ('gbk', 'gbk'), ('utf8-bom', 'utf-8-sig'), ('utf16-bom', 'utf-16')]:
            path = root / f'pg{id}-{label}.txt'
            path.write_bytes(text.encode(encoding))
            add(f'pg{id}-{label}', path, 'TXT-' + label, url, 'count' if label == 'gbk' else 'hash',
                expected_text_sha256=canonical, encoding=encoding, derived_from_sha256=file_hash(original),
                transform=f'contiguous Unicode excerpt [{start}:{start + len(text)}]; strict encoding; no replacement')
    write_json(args.output, {'schema': 1, 'books': books})
    print(f'{len(books)} samples; publications retained outside repository: {root}')


if __name__ == '__main__':
    main()
