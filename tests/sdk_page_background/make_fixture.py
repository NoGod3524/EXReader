"""Actions-only long, real ZIP EPUB fixture for later bounded pages."""
import os
from pathlib import Path
import sys
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
target = Path(sys.argv[1]);target.parent.mkdir(parents=True, exist_ok=True)
paragraph = 'A fi AV ordinary words with spacing and Unicode café. ' * 16
body = '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Background probe</title></head><body>'
body += ''.join('<p>' + str(n) + ' ' + paragraph + '</p>' for n in range(400)) + '</body></html>'
with zipfile.ZipFile(target, 'w') as archive:
    archive.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
    archive.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    archive.writestr('content.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Background probe</dc:title><dc:identifier>background-probe</dc:identifier></metadata><manifest><item id="body" href="body.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="body"/></spine></package>')
    archive.writestr('body.xhtml', body)
