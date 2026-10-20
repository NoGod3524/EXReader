#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pinned, open-licensed font asset for the native reference hosts."""
import hashlib
from pathlib import Path
import urllib.request

REVISION = 'f8d157532fbfaeda587e826d4cd5b21a49186f7c'
BASE = 'https://raw.githubusercontent.com/notofonts/noto-cjk/'+REVISION+'/Sans/'
ASSETS = {
    'Reader.otf': ('OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf',
                   '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b'),
    'OFL.txt': ('LICENSE', '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2'),
}


def fetch(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, (source, expected) in ASSETS.items():
        path = folder/name
        if path.exists():
            data = path.read_bytes()
        else:
            with urllib.request.urlopen(BASE+source, timeout=120) as response:
                data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Reference host font hash mismatch: '+name)
        if not path.exists():
            path.write_bytes(data)
    return folder
