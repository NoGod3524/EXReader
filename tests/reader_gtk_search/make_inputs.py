# SPDX-License-Identifier: MIT
"""Actions-only blank PDF and larger bounded EPUB for real cancellation input."""
import os
from pathlib import Path
import re
import sys
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
folder=Path(sys.argv[1])
data=(folder/'pages.pdf').read_bytes()
(folder/'empty.pdf').write_bytes(re.sub(rb'(?s)(stream\n)(.*?)(\nendstream)',lambda m:m[1]+b' '*len(m[2])+m[3],data))
with zipfile.ZipFile(folder/'long.epub') as source,zipfile.ZipFile(folder/'cancel.epub','w') as output:
    for item in source.infolist():
        body=source.read(item.filename)
        if item.filename=='c.xhtml':
            content=body.split(b'<body>',1)[1].split(b'</body>',1)[0]
            body=body.replace(b'</body>',content*3+b'</body>')
        output.writestr(item,body)
