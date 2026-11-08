#!/usr/bin/env python3
"""Create a one-chapter EPUB with enough text for twenty page turns."""
import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from host_font import fetch


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--font', type=Path, help='optional existing font; default downloads the pinned OFL reference font')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    paragraph = 'deliveryneedle A reader opens a book, turns pages, searches a word and keeps a highlight. '
    with zipfile.ZipFile(args.output/'smoke.epub', 'w') as book:
        def write(name, text):
            info = zipfile.ZipInfo(name, (2026, 11, 8, 0, 0, 0))
            info.create_system = 3
            book.writestr(info, text.encode('utf-8'))
        write('mimetype', 'application/epub+zip')
        write('META-INF/container.xml', '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        write('book.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">exreader-platform-smoke</dc:identifier><dc:title>Platform delivery smoke</dc:title><dc:language>en</dc:language><meta property="dcterms:modified">2026-11-08T00:00:00Z</meta></metadata><manifest><item id="body" href="body.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine><itemref idref="body"/></spine></package>')
        write('body.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Smoke</title></head><body>'+''.join('<p>'+paragraph+'</p>' for _ in range(1000))+'</body></html>')
        write('nav.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><ol><li><a href="body.xhtml">Smoke</a></li></ol></nav></body></html>')
    font = args.font or fetch(args.output/'font-assets')/'Reader.otf'
    shutil.copyfile(font, args.output/'font.otf')
    print(args.output.resolve())


if __name__ == '__main__':
    main()
