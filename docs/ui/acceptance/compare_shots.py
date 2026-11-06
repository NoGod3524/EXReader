#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare two evidence trees screenshot by screenshot.

Usage:
  compare_shots.py <evidence-a> <evidence-b> [--client-top N]
  compare_shots.py --self-test

Each tree holds the phase directories A, B and C written by --drive --evidence.
Every pixel whose RGBA differs is counted; there is no getbbox() shortcut,
because on RGBA images Pillow's getbbox() looks at alpha only and misses RGB
changes (that shortcut made the step-1 record read 0 for differing images).

The screenshots are PrintWindow captures of the whole window, so their top
rows are the title bar, which DWM draws with a backdrop tint that depends on
what is behind the window and whether it is active: two runs of the same
binary already differ there. --client-top N (the client origin's y, from
`check|shell` or the drive log) also reports the count below row N, which is
the reader's own UI. The verdict uses the client count when N is given and
the full count otherwise; both counts are always printed.

--self-test is the negative example: it builds synthetic trees where the
client area differs (RGB only, alpha unchanged) and where only the title bar
differs, and fails unless the client change is reported and the title-bar
change is not.
"""
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageChops


def differing(diff, top=0):
    width = diff.size[0]
    data = diff.tobytes()
    return sum(1 for i in range(top * width * 4, len(data), 4) if any(data[i:i + 4]))


def compare(a, b, top=0, out=print):
    names = sorted(p.relative_to(a) for p in a.glob('[ABC]/*.png'))
    failed = 0
    for name in names:
        left, right = Image.open(a / name).convert('RGBA'), b / name
        if not right.exists():
            out(name.as_posix(), 'missing'); failed += 1; continue
        right = Image.open(right).convert('RGBA')
        if left.size != right.size:
            out(name.as_posix(), 'size', left.size, right.size); failed += 1; continue
        diff = ImageChops.difference(left, right)
        full, client = differing(diff), differing(diff, top) if top else None
        failed += (client if top else full) > 0
        out(name.as_posix(), '%dx%d' % left.size, 'diffpx', full, '' if client is None else 'client_diffpx %d' % client)
    out('images=%d nonzero=%d%s' % (len(names), failed, ' (client area, rows >= %d)' % top if top else ' (full window)'))
    return len(names), failed


def self_test():
    with tempfile.TemporaryDirectory() as root:
        a, b = Path(root) / 'a', Path(root) / 'b'
        names = ['A/0%d.png' % i for i in range(5)] + ['B/10.png', 'B/11.png', 'C/20.png']
        for tree in (a, b):
            for n in names:
                (tree / n).parent.mkdir(parents=True, exist_ok=True)
                Image.new('RGBA', (120, 90), (255, 255, 255, 255)).save(tree / n)
        client = Image.open(b / names[1]); client.putpixel((60, 50), (254, 255, 255, 255)); client.save(b / names[1])
        title = Image.open(b / names[2]); title.putpixel((60, 10), (0, 0, 0, 255)); title.save(b / names[2])
        lines = []
        _, failed = compare(a, b, 38, lambda *x: lines.append(' '.join(str(v) for v in x)))
        print('\n'.join('  ' + l for l in lines))
        expect = {names[1]: ('1', '1'), names[2]: ('1', '0')}
        ok = failed == 1
        for line in lines:
            parts = line.split()
            if parts[0] in expect:
                ok &= (parts[3], parts[5]) == expect[parts[0]]
        print('self-test: client RGB change (1 px, alpha same) reported, title-bar change ignored:', 'PASS' if ok else 'FAIL')
        return 0 if ok else 1


if __name__ == '__main__':
    args = sys.argv[1:]
    if args == ['--self-test']:
        sys.exit(self_test())
    top = 0
    if '--client-top' in args:
        k = args.index('--client-top'); top = int(args[k + 1]); del args[k:k + 2]
    count, failed = compare(Path(args[0]), Path(args[1]), top)
    sys.exit(1 if failed or count != 8 else 0)
