#!/usr/bin/env python3
"""Generate pinned Unicode 17 script, Indic category and combining-class tables."""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

SOURCES = {
    'IndicSyllabicCategory.txt': '3fc122f4cf58b0c19268d5f810263b04ab4e1e67743386ec0e0ada9c76aec5be',
    'IndicPositionalCategory.txt': '68cedc29a7e57f984d90fe2c7712f2e6d0c717e253db219607daea8997d6c480',
    'Scripts.txt': '9f5e50d3abaee7d6ce09480f325c706f485ae3240912527e651954d2d6b035bf',
    'PropertyValueAliases.txt': '64e9a5f76f7a1e8b5a47d6a1f9a26522a251208f5276bdfa1559dac7cf2e827a',
    'UnicodeData.txt': '2e1efc1dcb59c575eedf5ccae60f95229f706ee6d031835247d843c11d96470c',
}


def entries(text):
    for line in text.splitlines():
        fields = [x.strip() for x in line.split('#', 1)[0].split(';')]
        if len(fields) < 2:
            continue
        interval, name = fields[:2]
        ends = interval.split('..')
        yield int(ends[0], 16), int(ends[-1], 16), name


def merged(rows):
    result = []
    for first, last, value in sorted(rows):
        assert not result or first > result[-1][1]
        if result and first == result[-1][1]+1 and result[-1][2] == value:
            result[-1] = result[-1][0], last, value
        else:
            result.append((first, last, value))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--cache-dir', type=Path, default=Path('build/indic-cache'))
    args = parser.parse_args()
    texts = {}
    for name, digest in SOURCES.items():
        path = args.cache_dir/name
        if args.download and not path.is_file():
            data = urlopen('https://www.unicode.org/Public/17.0.0/ucd/'+name, timeout=30).read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('Unicode hash mismatch: '+name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Unicode hash mismatch: '+name)
        texts[name] = data.decode('utf-8')
    aliases = {}
    for line in texts['PropertyValueAliases.txt'].splitlines():
        fields = [x.strip() for x in line.split('#', 1)[0].split(';')]
        if fields[0] == 'sc':
            aliases[fields[2]] = fields[1].lower()
    # OpenType uses kana for both kana syllabaries; its legacy Lao/Yi/Nko/Vai
    # tags are space padded rather than ISO 15924's trailing o/i letters.
    aliases.update(Hiragana='kana', Lao='lao ', Yi='yi  ', Nko='nko ', Vai='vai ')
    scripts = sorted({name for _, _, name in entries(texts['Scripts.txt'])}
                     - {'Common', 'Inherited'})
    assert len(scripts) < 256
    script_values = {name: i+1 for i, name in enumerate(scripts)}
    lines = ['/* SPDX-License-Identifier: GPL-3.0-only\n * Unicode 17.0.0, Unicode-3.0; tools/generate_indic.py. */',
             '#ifndef EXR_INDIC_DATA_H', '#define EXR_INDIC_DATA_H',
             'typedef struct { uint32_t first,last; unsigned char value; } exr_indic_range;']
    lines.append('static const uint32_t exr_indic_script_tags[] = {0,')
    for name in scripts:
        tag = aliases[name]
        assert len(tag) == 4
        lines.append(f'  UINT32_C(0x{int.from_bytes(tag.encode(), "big"):08X}), /* {name} */')
    lines.append('};')
    groups = [('script', merged((a, b, script_values[n]) for a, b, n in entries(texts['Scripts.txt']) if n in script_values))]
    for key, name, default in [('isc', 'IndicSyllabicCategory.txt', 'Other'),
                               ('ipc', 'IndicPositionalCategory.txt', 'NA')]:
        names = [default]+sorted({n for _, _, n in entries(texts[name])}-{default})
        values = {n: i for i, n in enumerate(names)}
        lines.append('enum { '+', '.join('EXR_'+key.upper()+'_'+n.upper()+'='+str(i) for i, n in enumerate(names))+' };')
        groups.append((key, merged((a, b, values[n]) for a, b, n in entries(texts[name]) if values[n])))
    ccc = []
    for line in texts['UnicodeData.txt'].splitlines():
        fields = line.split(';')
        if int(fields[3]):
            cp = int(fields[0], 16)
            ccc.append((cp, cp, int(fields[3])))
    groups.append(('ccc', merged(ccc)))
    for key, rows in groups:
        lines.append('static const exr_indic_range exr_indic_'+key+'[] = {')
        lines.extend(f'  {{0x{a:X},0x{b:X},{v}}},' for a, b, v in rows)
        lines.append('};')
    lines.extend(['#endif', ''])
    data = '\n'.join(lines)
    output = Path(__file__).resolve().parents[1]/'src/indic_data.h'
    if args.check:
        if output.read_text(encoding='utf-8') != data:
            raise ValueError('indic_data.h differs from pinned Unicode data')
    else:
        output.write_text(data, encoding='utf-8')
    print('Verified Unicode 17 Indic/script data: '+', '.join(f'{k}={len(v)}' for k, v in groups))


if __name__ == '__main__':
    main()
