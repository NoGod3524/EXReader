"""Four deterministic original EPUBs: chapter notes, auxiliary endnotes, none, vertical CJK chapter notes."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED


def make(root):
    root.mkdir(parents=True, exist_ok=True)
    for kind in ('chapter', 'end', 'none', 'vertical'):
        target = 'notes.xhtml' if kind == 'end' else 'body.xhtml'
        ids = ['note-one'] + [f'fn{i}' for i in range(2, 11)]
        body = '<h1 id="start">Style and footnotes</h1>'
        body += '<p>Alpha highlight one. Beta highlight two. Gamma note three.</p>'
        for i, ident in enumerate(ids, 1):
            href = f'{target}#{ident}' if kind != 'none' else '#ordinary'
            body += f'<p>Reference {i}: a short passage <a epub:type="noteref" href="{href}">[{i}]</a> continues here.</p>'
        body += '<p id="ordinary">Ordinary text, not a footnote.</p>'
        body += '<p><a href="#fnmissing">Missing</a> <a href="https://example.org/#fn99">External</a></p>'
        notes = ''
        if kind != 'none':
            for i, ident in enumerate(ids, 1):
                attr = ['epub:type="footnote"', 'epub:type="endnote"',
                        'epub:type="rearnote"', 'role="doc-footnote"'][i-1] if i <= 4 else ''
                detail = ('This long note remains horizontal and scrolls inside its own popup. ' * 40) if i == 1 else 'Short explanatory text.'
                notes += f'<aside id="{ident}" {attr}><p>Footnote {i} correct content. <em>{detail}</em></p></aside>'
        body += ''.join(f'<p>Paragraph {i}: content anchors follow these original words through reflow.</p>' for i in range(60))
        if kind == 'vertical':
            body = '<h1 id="start">竖排脚注</h1>'
            for i, ident in enumerate(ids, 1):
                body += f'<p>第{i}段：竖排正文中的引用<a epub:type="noteref" href="body.xhtml#{ident}">[{i}]</a>，后文继续。</p>'
            body += ''.join(f'<p>段落{i}：内容锚点随重排跟随原文。</p>' for i in range(40))
            body += ''.join(f'<aside id="{ident}" epub:type="footnote"><p>Footnote {i} correct content. 注释{i}保持横排显示。</p></aside>'
                            for i, ident in enumerate(ids, 1))
        if kind == 'chapter':
            body += notes

        def xhtml(text):
            style = '<style>html{writing-mode:vertical-rl}</style>' if kind == 'vertical' else ''
            lang = ' lang="zh-Hans"' if kind == 'vertical' else ''
            return f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"{lang}><head><title>Style {kind}</title>{style}</head><body>{text}</body></html>'
        entries = {
            'mimetype': 'application/epub+zip',
            'META-INF/container.xml': '<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
            'OPS/body.xhtml': xhtml(body),
            'OPS/nav.xhtml': xhtml('<nav epub:type="toc"><ol><li><a href="body.xhtml#start">Style and footnotes</a></li></ol></nav>'),
        }
        manifest = '<item id="body" href="body.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        if kind == 'end':
            entries['OPS/notes.xhtml'] = xhtml(notes)
            manifest += '<item id="notes" href="notes.xhtml" media-type="application/xhtml+xml"/>'
        entries['OPS/book.opf'] = f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Style {kind}</dc:title></metadata><manifest>{manifest}</manifest><spine><itemref idref="body"/></spine></package>'
        with ZipFile(root / f'style-{kind}.epub', 'w') as archive:
            for path, text in entries.items():
                info = ZipInfo(path, (2026, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_STORED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, text.encode())


if __name__ == '__main__':
    make(Path(__file__).parent / 'fixtures/style-footnotes')
