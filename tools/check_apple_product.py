# SPDX-License-Identifier: MIT
"""Require the installed product SQLite in each actual native Apple binary."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def validate(dependencies, symbols, link_map):
    assert not re.search(r'libsqlite3(?:\.|\s)', dependencies), 'system SQLite linked directly'
    definitions = re.findall(r'(?m)^.*\b[Tt]\s+_sqlite3_open_v2\s*$', symbols)
    assert len(definitions) == 1, 'product SQLite definition missing or duplicated'
    providers = [line.strip() for line in link_map.splitlines()
                 if 'libreader_catalog_sqlite.a' in line and 'sqlite3.c.o' in line]
    assert len(providers) == 1, 'installed product SQLite object missing or duplicated'
    objects = dict(re.findall(r'^\[\s*(\d+)\]\s+(.+)$', link_map, re.M))
    owners = re.findall(r'^0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+\[\s*(\d+)\]\s+_sqlite3_open_v2\s*$', link_map, re.M)
    assert len(owners) == 1 and re.search(r'libreader_catalog_sqlite\.a(?:\[\d+\])?\(sqlite3\.c\.o\)$',
                                        objects.get(owners[0], '')), 'SQLite symbol belongs to another provider'
    assert not re.search(r'libexr_(?:library|core)\.a', link_map), 'second static SDK provider'
    assert 'libreader_reading_state.a' not in link_map, 'host must use its dynamic SDK resolver'
    return providers[0]


def inspect(binary, link_map):
    dependencies = subprocess.check_output(['otool', '-L', str(binary)], text=True)
    symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
    mapping = Path(link_map).read_text()
    Path(str(link_map) + '.symbols.txt').write_text(symbols)
    Path(str(link_map) + '.dependencies.txt').write_text(dependencies)
    try:
        provider = validate(dependencies, symbols, mapping)
    except AssertionError:
        print(json.dumps({'binary': str(binary),
                          'sqlite_open_symbols': [line for line in symbols.splitlines() if 'sqlite3_open' in line],
                          'sqlite_provider_objects': [line for line in mapping.splitlines() if 'sqlite3.c.o' in line],
                          'dependencies': dependencies}), flush=True)
        raise
    search_linked = bool(re.search(r'\b[Tt]\s+_reader_search_next\s*$', symbols, re.M))
    if search_linked:
        providers = [line for line in mapping.splitlines()
                     if 'libreader_search.a' in line and 'search.cpp.o' in line]
        assert len(providers) == 1, 'installed F1 search object missing or duplicated'
        assert re.search(r'\blibexreader(?:\.[0-9]+)*\.dylib', dependencies), 'search host lacks the dynamic SDK'
        assert re.search(r'\bU\s+_exr_anchor_resolve_ex\s*$', symbols, re.M), 'resolver must come from the dynamic SDK'
        assert not re.search(r'\b[Tt]\s+_exr_(?:document_free|anchor_free|anchor_resolve_ex|pager_create)\s*$',
                             symbols, re.M), 'search embedded a second SDK implementation'
    rejected = []
    wrong_owner = re.sub(r'(?m)^(0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+\[\s*)\d+(\]\s+_sqlite3_open_v2\s*)$',
                         r'\g<1>999999\2', mapping)
    cases = [('system_sqlite', dependencies + '\n/usr/lib/libsqlite3.dylib', symbols, mapping),
             ('missing_symbol', dependencies, '', mapping),
             ('duplicate_symbol', dependencies, symbols + '\n0 T _sqlite3_open_v2\n', mapping),
             ('duplicate_provider', dependencies, symbols, mapping + '\n' + provider),
             ('wrong_symbol_owner', dependencies, symbols, wrong_owner),
             ('static_sdk', dependencies, symbols, mapping + '\nlibexr_library.a'),
             ('static_resolver', dependencies, symbols, mapping + '\nlibreader_reading_state.a')]
    for name, deps, syms, data in cases:
        try:
            validate(deps, syms, data)
        except AssertionError:
            rejected.append(name)
        else:
            raise AssertionError('accepted altered provider evidence: ' + name)
    return {'accepted': True, 'binary_sha256': hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
            'sqlite_provider': provider, 'system_sqlite_fallback': False,
            'static_sdk_linked': False, 'reading_resolver_linked': False,
            'installed_search_linked': search_linked,
            'dependencies': dependencies, 'negative_checks': rejected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.binary, args.map)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'dependencies'}))


if __name__ == '__main__':
    main()
