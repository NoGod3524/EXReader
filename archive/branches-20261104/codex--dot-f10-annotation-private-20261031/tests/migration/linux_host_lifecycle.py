#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Open and close the GTK reader owner around a transactional migration."""
import argparse
import os
from pathlib import Path
import subprocess
import legacy_data as L


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tool', required=True)
    p.add_argument('--old-tool', required=True)
    p.add_argument('--host', required=True)
    p.add_argument('--font', required=True)
    p.add_argument('--work', type=Path, required=True)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    a.work.mkdir(parents=True, exist_ok=False)
    target = a.work/'library.sqlite'
    first = a.work/'first.exrpack'
    second = a.work/'second.exrpack'
    first.write_bytes(L.build_pack([L.entry(L.book_record('one','one.txt'), L.TXT)], []))
    second.write_bytes(L.build_pack([L.entry(L.book_record('two','two.txt'), L.TXT_OTHER)], []))
    def run(*args):
        p = subprocess.run(list(map(str,args)), capture_output=True, text=True)
        print(p.stdout, p.stderr, flush=True)
        assert p.returncode == 0, (args, p.returncode)
    run(a.old_tool, 'migrate', '--pack', first, '--target', target)
    run(a.tool, 'migrate', '--pack', first, '--target', target)
    run(a.host, target, a.font, '1')
    run(a.tool, 'migrate', '--pack', second, '--target', target)
    run(a.host, target, a.font, '2')
    run(a.tool, 'verify', '--pack', first, '--target', target)
    run(a.tool, 'verify', '--pack', second, '--target', target)
    print('GTK reader open/close, migration and reopen passed', flush=True)


if __name__ == '__main__':
    main()
