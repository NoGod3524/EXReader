# SPDX-License-Identifier: MIT
"""Actions-only additions; frozen F2 originals and their manifest stay intact."""
import importlib.util
import os
from pathlib import Path
import sys
import zipfile


def main(folder):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = Path(__file__).parents[1] / 'reader_navigation/make_navigation_fixtures.py'
    spec = importlib.util.spec_from_file_location('frozen_navigation_inputs', source)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    roots = ''.join('<li><a href="../Text/a.xhtml#start">Root %03d</a></li>' % i for i in range(45))
    navigation = '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>' + roots + '</ol></nav></body></html>'
    module.epub(folder / 'many.epub', 3, navigation=navigation)
    roots = ''.join('<li><a href="../Text/a.xhtml#start">%04d %s</a></li>' % (i, 'Long plain directory label ' * 10) for i in range(9000))
    module.epub(folder / 'cancel.epub', 3, navigation='<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>' + roots + '</ol></nav></body></html>')
    with zipfile.ZipFile(folder / 'nav3.epub') as book:
        entries = {name: book.read(name) for name in book.namelist()}
    name = module.B
    entries[name] = entries[name].decode().replace('</body>', '<p id="unicode">🙂文字</p><p id="collapsed"> a   b </p></body>').encode()
    with zipfile.ZipFile(folder / 'unicode.epub', 'w') as book:
        for name, data in entries.items():module.entry(book, name, data)


if __name__ == '__main__':main(Path(sys.argv[1]))
