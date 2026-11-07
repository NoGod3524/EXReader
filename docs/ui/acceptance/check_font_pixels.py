#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fixed-font Latin Sample client pixels against the pre-fix step-5 host."""
import json
from pathlib import Path
import sys
from PIL import Image, ImageChops
from check_step5 import run, dump


def check(exe, before, font, book, out):
    rows = []
    for size in (17, 24):
        for theme in ('light', 'dark'):
            for label, binary in (('before', before), ('after', exe)):
                dest = out/f'{size}-{theme}'/label
                script = (f'import|{book}\nopen|EXReader benchmark\nwait_idle\nshell|on\nshell_dpi|96\n'
                          f'shell_font|{size}\nshell_client|1280|800\nwait_idle\nshell_click|{theme}\n')
                for i in range(3):
                    script += f'wait_idle\nshell_measure|page-{i}\nsnapshot|page-{i}\nnext\n'
                run(binary, font, script+'wait_idle\nquit\n', dest/'profile', dest)
            for i in range(3):
                images = []
                for label in ('before', 'after'):
                    dest = out/f'{size}-{theme}'/label
                    m = json.loads((dest/f'page-{i}.json').read_text())
                    x, y, w, h = m['client_box']
                    images.append(Image.open(dest/f'page-{i}.png').convert('RGB').crop((x,y,x+w,y+h)))
                assert images[0].size == images[1].size
                diff = ImageChops.difference(*images)
                count = sum(p != (0,0,0) for p in diff.getdata())
                rows.append(dict(font=size, theme=theme, page=i+1, different_pixels=count))
                assert count == 0, rows[-1]
    result = dict(images=len(rows), different_pixels=sum(r['different_pixels'] for r in rows), rows=rows)
    dump(out/'result.json', result)
    return result


if __name__ == '__main__':
    print(json.dumps(check(*(Path(p).resolve() for p in sys.argv[1:])), indent=2))
