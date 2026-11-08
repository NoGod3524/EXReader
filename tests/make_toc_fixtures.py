#!/usr/bin/env python3
"""Deterministic original EPUBs for the engine TOC/link contract."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent / 'fixtures'
BODY = '''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Metadata</title></head><body>
<p>Before</p><h1 id="Start">第一章 Heading</h1><p>Text <a name="Legacy"/>after.</p>
<h2 id="子章">第二章 Child</h2><p id="Case">One</p><p id="case">Two</p>
<p><a id="empty"/></p><p>End</p><p id="Étage">Accent</p>
<p id="duplicate">First duplicate</p><p id="duplicate">Second duplicate</p>
<script id="unprojected">ignored</script><p>Following</p></body></html>'''
NAV = '''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol><li><a href="../Text/A%20B.xhtml#start">First <em>&amp; title</em></a>
<ol><li><a href="../Text/a%20b.XHTML#%E5%AD%90%E7%AB%A0">Child</a></li></ol></li>
<li><span>Group</span><ol><li><a href="../Text/A%20B.xhtml#missing">Missing</a></li></ol></li></ol></nav>
<nav epub:type="page-list"><ol><li><a href="../Text/A%20B.xhtml">1</a></li></ol></nav></body></html>'''
NCX = '''<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>
<navPoint playOrder="8"><navLabel><text>NCX first</text></navLabel><content src="../Text/A%20B.xhtml#Start"/>
<navPoint playOrder="2"><navLabel><text>NCX child</text></navLabel><content src="../Text/A%20B.xhtml#子章"/></navPoint></navPoint>
<navPoint playOrder="0"><navLabel><text>NCX missing</text></navLabel><content src="../Text/A%20B.xhtml#missing"/></navPoint>
<navPoint playOrder="999999999999999999999999999"><navLabel><text>Bad order</text></navLabel><content src="../Text/A%20B.xhtml#Legacy"/></navPoint>
</navMap></ncx>'''
RECOVERY = '''<html xmlns="http://www.w3.org/1999/xhtml"><body>
<h1>The Project Gutenberg eBook of Test</h1><nav><a>第九回 Fake link</a></nav>
<p>第一回中这是正文引用。\n第一回　Recovered heading\nBody prose.\n第二回\nBody two.</p>
<p>第四回中这是一句话。</p><p hidden="hidden">第五回 Hidden</p>
<p>第三回 Another heading</p></body></html>'''


def make(name, nav=None, ncx=NCX, body=BODY, continuation=None, path='A B.xhtml'):
    entries = {
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': '<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
        'OPS/Text/' + path: body,
    }
    manifest = f'<item id="a" href="Text/{path.replace(" ", "%20")}" media-type="application/xhtml+xml"/>'
    if nav is not None:
        manifest += '<item id="nav" href="Nav/nav.xhtml" media-type="application/xhtml+xml" properties="cover-image nav"/>'
        entries['OPS/Nav/nav.xhtml'] = nav
    if ncx is not None:
        manifest += '<item id="ncx" href="Nav/toc.ncx" media-type="application/x-dtbncx+xml"/>'
        entries['OPS/Nav/toc.ncx'] = ncx
    toc = ' toc="ncx"' if ncx else ''
    spine = '<itemref idref="a"/>'
    if continuation:
        manifest += '<item id="b" href="Text/continuation.xhtml" media-type="application/xhtml+xml"/>'
        entries['OPS/Text/continuation.xhtml'] = continuation
        spine += '<itemref idref="b"/>'
    entries['OPS/book.opf'] = f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/><manifest>{manifest}</manifest><spine{toc}>{spine}</spine></package>'
    with zipfile.ZipFile(ROOT / name, 'w') as archive:
        for path, value in entries.items():
            info = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value.encode('utf-8'))


def make_pages(name, cover=True, count=70, toc=True):
    """Many nested entries (two levels, some long) for the synthetic TOC page tests."""
    paragraphs = ''.join(f'<p id="a{i}">Body paragraph {i} text.</p>' for i in range(count))
    entries, items = {}, ''
    if toc:
        longs = {5: ' with a deliberately long subtitle that has to wrap over several lines of the page',
                 6: ' Supercalifragilisticexpialidocious-and-Antidisestablishmentarianism-wrapping'}
        # level 2 for every entry that is not a multiple of 4: nest them under the previous level-1 entry
        rows = ''
        for i in range(count):
            title = f'Zyxwv entry {i:02d}' + longs.get(i, '')
            link = f'<a href="../Text/body.xhtml#a{i}">{title}</a>'
            if i % 4 == 0:
                rows += ('</ol></li>' if i else '') + f'<li>{link}<ol>'
            else:
                rows += f'<li>{link}</li>'
        rows += '</ol></li>'
        entries['OPS/Nav/nav.xhtml'] = ('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>'
                                        f'<nav epub:type="toc"><ol>{rows}</ol></nav></body></html>')
        items += '<item id="nav" href="Nav/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    items += '<item id="b" href="Text/body.xhtml" media-type="application/xhtml+xml"/>'
    spine = '<itemref idref="b"/>'
    if cover:
        entries['OPS/Text/cover.xhtml'] = '<html xmlns="http://www.w3.org/1999/xhtml"><body><img src="cover.jpg" alt=""/></body></html>'
        items += '<item id="cover" href="Text/cover.xhtml" media-type="application/xhtml+xml"/>'
        spine = '<itemref idref="cover"/>' + spine
    entries['OPS/Text/body.xhtml'] = f'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Opening text.</p>{paragraphs}</body></html>'
    entries = {'mimetype': 'application/epub+zip',
               'META-INF/container.xml': '<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
               **entries,
               'OPS/book.opf': f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/><manifest>{items}</manifest><spine>{spine}</spine></package>'}
    with zipfile.ZipFile(ROOT / name, 'w') as archive:
        for path, value in entries.items():
            info = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value.encode('utf-8'))


if __name__ == '__main__':
    make_pages('toc-pages.epub')
    make_pages('toc-pages-none.epub', cover=False, count=3, toc=False)
    make('toc-nav.epub', nav=NAV)
    make('toc-ncx.epub')
    license_ncx = '<ncx><navMap><navPoint><navLabel><text>THE FULL PROJECT GUTENBERG LICENSE</text></navLabel><content src="../Text/A%20B.xhtml#license"/></navPoint></navMap></ncx>'
    make('toc-recovery.epub', ncx=license_ncx, body=RECOVERY)
    make('toc-no-navigation.epub', ncx=None, body=RECOVERY)
    make('toc-semantic.epub', ncx=None, body=BODY.replace('第一章 ', '').replace('第二章 ', ''))
    # A page-list is not a TOC and must not suppress the NCX navMap.
    make('toc-pages-only.epub', nav=NAV.replace('epub:type="toc"', 'epub:type="landmarks"'))
    make('toc-split.epub', body='<html><body id="Start"><img src="ornament.jpg"/></body></html>', continuation=BODY)
    make('toc-unicodecase.epub', ncx=NCX.replace('A%20B', '%C3%A9tage'), path='Étage.xhtml')
    make('toc-license-nav.epub', nav='<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li><a href="../Text/A%20B.xhtml#Start">LICENSE</a></li></ol></nav></body></html>')
    make('toc-recovery-repeated.epub', ncx=license_ncx,
         body=RECOVERY.replace('</body>', '<p>第一回 Recovered heading</p></body>'))
    make('toc-recovery-boundary.epub', ncx=license_ncx,
         body='<html><body><p>第一回 Boundary heading</p></body></html>',
         continuation='<html><body><p>第一回 Boundary heading\nActual body.</p><p>第二回 Next</p></body></html>')
