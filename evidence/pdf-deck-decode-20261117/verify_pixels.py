"""Compare active RGBA snapshots from canonical benchmark captures."""
import argparse
import hashlib
import json
import zlib
from pathlib import Path


def compare(before, after, widths):
    rows = []
    for width in widths:
        old_dir = before / '.repeat-0' / str(width)
        new_dir = after / '.repeat-0' / str(width)
        old = json.loads((old_dir / 'summary.json').read_text())
        new = json.loads((new_dir / 'summary.json').read_text())
        assert old['input_sha256'] == new['input_sha256']
        old_pages = old['results'][str(width)]['pages']
        new_pages = new['results'][str(width)]['pages']
        assert len(old_pages) == len(new_pages)
        for a, b in zip(old_pages, new_pages):
            assert (a['page'], a['dimensions']) == (b['page'], b['dimensions'])
            name = f"{width}-page-{a['page']:03d}.rgba.zlib"
            left = zlib.decompress((old_dir / name).read_bytes())
            right = zlib.decompress((new_dir / name).read_bytes())
            assert len(left) == len(right) == a['dimensions'][0] * a['dimensions'][1] * 4
            assert hashlib.sha256(left).hexdigest() == a['rgba_sha256']
            assert hashlib.sha256(right).hexdigest() == b['rgba_sha256']
            equal = left == right
            maximum = 0 if equal else max(abs(x-y) for x, y in zip(left, right))
            different = 0 if equal else sum(left[i:i+4] != right[i:i+4] for i in range(0, len(left), 4))
            rows.append(dict(width=width, page=a['page'], pixels=len(left)//4,
                             different_pixels=different, max_channel_delta=maximum,
                             before_sha256=a['rgba_sha256'], after_sha256=b['rgba_sha256']))
    return dict(identical=all(r['different_pixels'] == 0 for r in rows),
                combinations=len(rows), active_rgba_pixels=sum(r['pixels'] for r in rows),
                different_pixels=sum(r['different_pixels'] for r in rows),
                max_channel_delta=max(r['max_channel_delta'] for r in rows), pages=rows)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--before', type=Path, required=True)
    ap.add_argument('--after', type=Path, required=True)
    ap.add_argument('--widths', type=int, nargs='+', required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    report = compare(args.before, args.after, args.widths)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print({k: v for k, v in report.items() if k != 'pages'})
    raise SystemExit(0 if report['identical'] else 1)
