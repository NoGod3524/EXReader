"""Count overlapping CJK SP CJK boundaries in space_probe body-*.txt dumps."""
from pathlib import Path
import json
import re
import sys

han = '\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ee5f\U0002f800-\U0002fa1f\U00030000-\U0003347f'
cjk = han + '\u3000-\u303f\ufe10-\ufe1f\ufe30-\ufe4f\uff01-\uff60\uffe0-\uffe6'
for folder in sys.argv[1:]:
    files = sorted(Path(folder).glob('body-*.txt'))
    if not files:
        raise SystemExit(f'No body projection dumps in {folder}')
    text = '\n'.join(p.read_text(encoding='utf-8') for p in files)
    counts = {label: len(re.findall('(?<=[' + chars + ']) (?=[' + chars + '])', text))
              for label, chars in [('han_space_han', han), ('cjk_space_cjk', cjk)]}
    print(json.dumps(dict(directory=folder, parts=len(files), **counts), ensure_ascii=False))
