#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated, parallel-safe discovery fixtures; no fontTools at test time."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

exe, fixtures, group = sys.argv[1:]
with tempfile.TemporaryDirectory(prefix="exr-font-manager-") as directory:
    root = Path(directory)
    (root / "fonts" / "字庫").mkdir(parents=True)
    (root / "extra").mkdir()
    (root / "empty").mkdir()
    for name in ("latin-serif.ttf", "cjk-serif.ttf", "cjk-sans.ttf"):
        target = root / "fonts" / ("字庫" if name == "cjk-serif.ttf" else "") / name
        shutil.copyfile(Path(fixtures) / name, target)
    for name in ("cjk-serif-bold.ttf", "cjk-serif-italic.ttf", "collection.ttc"):
        shutil.copyfile(Path(fixtures) / name, root / "extra" / name)
    if group == "selection":
        (root / "duplicates").mkdir()
        for i in range(40):
            shutil.copyfile(Path(fixtures) / "latin-serif.ttf", root / "duplicates" / f"copy-{i}.ttf")
    if group == "integration":
        with zipfile.ZipFile(root / "embedded.epub", "w") as book:
            book.writestr("mimetype", "application/epub+zip")
            book.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
            book.writestr("book.opf", '<package><metadata/><manifest><item id="text" href="text.xhtml" media-type="application/xhtml+xml"/><item id="font" href="bold.ttf" media-type="font/ttf"/></manifest><spine><itemref idref="text"/></spine></package>')
            book.writestr("text.xhtml", '<html><head><style>@font-face{font-family:Embedded;src:url(bold.ttf)}</style></head><body><p><span style="font-family:Embedded">龍</span><span style="font-family:EXR FM CJK Sans">中</span></p></body></html>')
            book.write(Path(fixtures) / "cjk-serif-bold.ttf", "bold.ttf")
    subprocess.run([exe, group, directory], check=True)
