"""Count overlapping boundaries in SDK space_probe body dumps, per block.

Usage: python count_whitespace.py BEFORE/text AFTER/text
Paragraph separators are records, not intra-paragraph whitespace.
"""
from pathlib import Path
import json
import re
import sys
import unicodedata

HAN = '\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ee5f\U0002f800-\U0002fa1f\U00030000-\U0003347f'
# Chinese punctuation: punctuation-category members of the existing projection
# ranges, plus its explicit middle dot, ellipsis, dashes and curly quotes.
PUNCT = ''.join(chr(cp) for lo, hi in [(0x3001, 0x303f), (0xfe10, 0xfe1f),
                 (0xfe30, 0xfe4f), (0xff00, 0xffef), (0x2018, 0x201d),
                 (0x2014, 0x2015), (0x2026, 0x2026), (0xb7, 0xb7)]
                for cp in range(lo, hi + 1) if unicodedata.category(chr(cp)).startswith('P'))
PAIRS = {'han_ws_han': (HAN, HAN), 'han_ws_punct': (HAN, PUNCT),
         'punct_ws_han': (PUNCT, HAN)}


def count(folder):
    files = sorted(Path(folder).glob('body-*.txt'))
    if not files:
        raise ValueError(f'No body dumps: {folder}')
    blocks = [line for file in files for line in file.read_text(encoding='utf-8').split('\n')]
    result = {name: sum(len(re.findall(f'(?<=[{a}])\\s+(?=[{b}])', line)) for line in blocks)
              for name, (a, b) in PAIRS.items()}
    text = '\n'.join(blocks)
    return dict(parts=len(files), **result, u3000=text.count('\u3000'),
                nbsp=text.count('\xa0'), ascii_space=text.count(' '))


if __name__ == '__main__':
    for folder in sys.argv[1:]:
        print(json.dumps(dict(directory=folder, **count(folder)), ensure_ascii=False))
