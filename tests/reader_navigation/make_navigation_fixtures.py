# SPDX-License-Identifier: MIT
"""Generate reader-navigation originals in Actions only; never run locally.

Standard library only. Stored ZIP entries keep Windows and Linux originals
byte-identical; the manifest records each original's size and SHA-256. Each EPUB
with navigation also gets a tab-separated expectation list written by hand here,
independent of the module under test:

  index  parent(-1 = root)  role  label  href  part_path(- = none)  outcome

outcome is what a correct resolver must report for that row against the book:
ok, part_only, needs_host, unresolved, range or ambiguous.
"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

STAMP = (2026, 1, 1, 0, 0, 0)
A, B, C = 'OPS/Text/a.xhtml', 'OPS/Text/第二章.xhtml', 'OPS/Text/c.xhtml'
NAV_BASE, NCX_BASE = 'OPS/Nav/nav.xhtml', 'OPS/Nav/main.ncx'

NAV3 = '''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol>
<li><a href="../Text/a.xhtml#start">First &amp; chapter</a>
<ol><li><a href="../Text/%E7%AC%AC%E4%BA%8C%E7%AB%A0.xhtml#intro">子节 🙂</a></li></ol></li>
<li><span>Group</span><ol>
<li><a href="https://example.test/">Outside</a></li>
<li><a href="../Text/c.xhtml">Chapter</a></li></ol></li>
<li><a href="../Text/c.xhtml#nope">Chapter</a></li>
<li><a href="mailto:reader@example.test">Mail</a></li>
<li><a href="../Text/gone.xhtml">Missing</a></li>
<li><a href="../../../outside.xhtml">Escape</a></li>
<li><a href="../Text/a.xhtml#again">&lt;script&gt;alert(1)&lt;/script&gt; label</a></li>
<li><a href="//example.test/x.xhtml">Network</a></li>
</ol></nav>
<nav epub:type="landmarks"><ol><li><a href="../Text/a.xhtml">Begin</a></li></ol></nav>
<nav epub:type="page-list"><ol><li><a href="../Text/a.xhtml#deep">7</a></li></ol></nav>
</body></html>'''
NAV3_ROWS = [
    (0, -1, 'toc', 'First & chapter', '../Text/a.xhtml#start', A, 'ok'),
    (1, 0, 'toc', '子节 🙂', '../Text/%E7%AC%AC%E4%BA%8C%E7%AB%A0.xhtml#intro', B, 'ok'),
    (2, -1, 'toc', 'Group', '', '-', 'unresolved'),
    (3, 2, 'toc', 'Outside', 'https://example.test/', '-', 'needs_host'),
    (4, 2, 'toc', 'Chapter', '../Text/c.xhtml', C, 'ok'),
    (5, -1, 'toc', 'Chapter', '../Text/c.xhtml#nope', C, 'part_only'),
    (6, -1, 'toc', 'Mail', 'mailto:reader@example.test', '-', 'needs_host'),
    (7, -1, 'toc', 'Missing', '../Text/gone.xhtml', '-', 'unresolved'),
    (8, -1, 'toc', 'Escape', '../../../outside.xhtml', '-', 'range'),
    (9, -1, 'toc', '<script>alert(1)</script> label', '../Text/a.xhtml#again', A, 'ok'),
    (10, -1, 'toc', 'Network', '//example.test/x.xhtml', '-', 'needs_host'),
    (11, -1, 'landmarks', 'Begin', '../Text/a.xhtml', A, 'ok'),
    (12, -1, 'page-list', '7', '../Text/a.xhtml#deep', A, 'ok'),
]

NCX2 = '''<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><navMap>
<navPoint id="n1"><navLabel><text>First &amp; chapter</text></navLabel><content src="../Text/a.xhtml#start"/>
<navPoint id="n2"><navLabel><text>子节 🙂</text></navLabel><content src="../Text/%E7%AC%AC%E4%BA%8C%E7%AB%A0.xhtml#intro"/></navPoint></navPoint>
<navPoint id="n3"><navLabel><text>Group</text></navLabel>
<navPoint id="n4"><navLabel><text>Outside</text></navLabel><content src="https://example.test/"/></navPoint>
<navPoint id="n5"><navLabel><text>Chapter</text></navLabel><content src="../Text/c.xhtml"/></navPoint></navPoint>
<navPoint id="n6"><navLabel><text>Chapter</text></navLabel><content src="../Text/c.xhtml#nope"/></navPoint>
<navPoint id="n7"><navLabel><text>Missing</text></navLabel><content src="../Text/gone.xhtml"/></navPoint>
</navMap><pageList><pageTarget id="p1"><navLabel><text>7</text></navLabel><content src="../Text/a.xhtml#deep"/></pageTarget></pageList></ncx>'''
NCX2_ROWS = [
    (0, -1, 'toc', 'First & chapter', '../Text/a.xhtml#start', A, 'ok'),
    (1, 0, 'toc', '子节 🙂', '../Text/%E7%AC%AC%E4%BA%8C%E7%AB%A0.xhtml#intro', B, 'ok'),
    (2, -1, 'toc', 'Group', '', '-', 'unresolved'),
    (3, 2, 'toc', 'Outside', 'https://example.test/', '-', 'needs_host'),
    (4, 2, 'toc', 'Chapter', '../Text/c.xhtml', C, 'ok'),
    (5, -1, 'toc', 'Chapter', '../Text/c.xhtml#nope', C, 'part_only'),
    (6, -1, 'toc', 'Missing', '../Text/gone.xhtml', '-', 'unresolved'),
    (7, -1, 'page-list', '7', '../Text/a.xhtml#deep', A, 'ok'),
]

REPEATED_NAV = '''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol><li><a href="../Text/a.xhtml#start">First</a>
<ol><li><a href="../Text/%E7%AC%AC%E4%BA%8C%E7%AB%A0.xhtml#intro">子节</a></li></ol></li></ol></nav>
<nav epub:type="landmarks"><ol><li><a href="../Text/a.xhtml">Begin</a></li></ol></nav>
</body></html>'''
REPEATED_ROWS = [
    (0, -1, 'toc', 'First', '../Text/a.xhtml#start', A, 'ambiguous'),
    (1, 0, 'toc', '子节', '../Text/%E7%AC%AC%E4%BA%8C%E7%AB%A0.xhtml#intro', B, 'ok'),
    (2, -1, 'landmarks', 'Begin', '../Text/a.xhtml', A, 'ambiguous'),
]


def entry(archive, name, data):
    # Stored entries keep the originals byte-identical across runner zlib builds.
    info = zipfile.ZipInfo(name, date_time=STAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data.encode('utf-8') if isinstance(data, str) else data)


def epub(path, version=3, navigation=None, ncx=None, duplicate=False, toc=None):
    pages = {
        A: '<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="start">A start</p><p id="again">A again</p>'
           '<p id="deep">A deep</p></body></html>',
        B: '<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="intro">B intro</p><p id="fig">B fig</p></body></html>',
        C: '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>C plain</p></body></html>',
    }
    manifest = ('<item id="a" href="Text/a.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="b" href="Text/第二章.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="c" href="Text/c.xhtml" media-type="application/xhtml+xml"/>')
    entries = {'mimetype': 'application/epub+zip',
               'META-INF/container.xml': '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                                         '<rootfile full-path="OPS/book.opf"/></rootfiles></container>'}
    entries.update(pages)
    if navigation is not None:
        manifest += '<item id="nav" href="Nav/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        entries['OPS/Nav/nav.xhtml'] = navigation
    if ncx is not None:
        manifest += '<item id="ncx" href="Nav/main.ncx" media-type="application/x-dtbncx+xml"/>'
        entries['OPS/Nav/main.ncx'] = ncx
    spine = '<itemref idref="a"/>' + ('<itemref idref="a"/>' if duplicate else '') + '<itemref idref="b"/><itemref idref="c"/>'
    attr = f' toc="{toc}"' if toc else ''
    entries['OPS/book.opf'] = (f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}.0">'
                               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Navigation fixture</dc:title></metadata>'
                               f'<manifest>{manifest}</manifest><spine{attr}>{spine}</spine></package>')
    with zipfile.ZipFile(path, 'w') as book:
        for name, data in entries.items():
            entry(book, name, data)


def pdf(path):
    """Three pages and an authored /Outlines tree the module must never read."""
    count = 3
    font = 3 + count * 2
    outlines, item = font + 1, font + 2
    kids = ' '.join(f'{3 + i} 0 R' for i in range(count))
    objects = [f'<< /Type /Catalog /Pages 2 0 R /Outlines {outlines} 0 R >>'.encode(),
               f'<< /Type /Pages /Count {count} /Kids [{kids}] >>'.encode()]
    for i in range(count):
        objects.append((f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 {font} 0 R >> >> '
                        f'/Contents {3 + count + i} 0 R >>').encode())
    for i in range(count):
        stream = f'BT /F1 12 Tf 36 720 Td (Page {i + 1}) Tj ET'.encode('ascii')
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream')
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    objects.append(f'<< /Type /Outlines /First {item} 0 R /Last {item} 0 R /Count 1 >>'.encode())
    objects.append(f'<< /Title (Authored Outline Title) /Parent {outlines} 0 R /Dest [4 0 R /Fit] >>'.encode())
    data = bytearray(b'%PDF-1.7\n')
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{index} 0 obj\n'.encode() + body + b'\nendobj\n'
    xref = len(data)
    data += f'xref\n0 {len(offsets)}\n'.encode() + b'0000000000 65535 f \n'
    for offset in offsets[1:]:
        data += f'{offset:010d} 00000 n \n'.encode()
    data += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    path.write_bytes(bytes(data))


def rows(path, table, base):
    lines = []
    for index, parent, role, label, href, part, outcome in table:
        assert all('\t' not in str(v) and '\n' not in str(v) for v in (role, label, href, part, outcome))
        lines.append('\t'.join([str(index), str(parent), role, label, href, part, outcome, base]))
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')


def main(folder):
    folder.mkdir(parents=True, exist_ok=False)
    epub(folder / 'nav3.epub', 3, navigation=NAV3)
    epub(folder / 'ncx2.epub', 2, ncx=NCX2, toc='ncx')
    epub(folder / 'repeated.epub', 3, navigation=REPEATED_NAV, duplicate=True)
    epub(folder / 'empty.epub', 2)
    epub(folder / 'broken.epub', 3, navigation='<html><nav><ol><li>Unclosed')
    epub(folder / 'entity.epub', 3, navigation='<!DOCTYPE html [<!ENTITY x "blocked">]><html><nav><ol><li>'
                                               '<a href="../Text/a.xhtml">&x;</a></li></ol></nav></html>')
    epub(folder / 'missing-ncx.epub', 2, ncx=NCX2, toc='absent')
    pdf(folder / 'pages.pdf')
    rows(folder / 'nav3.tsv', NAV3_ROWS, NAV_BASE)
    rows(folder / 'ncx2.tsv', NCX2_ROWS, NCX_BASE)
    rows(folder / 'repeated.tsv', REPEATED_ROWS, NAV_BASE)
    manifest = {}
    for name in sorted(p.name for p in folder.iterdir()):
        data = (folder / name).read_bytes()
        manifest[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
