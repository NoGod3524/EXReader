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


def inspect(binary, link_map, selector_bytes_candidate=False):
    dependencies = subprocess.check_output(['otool', '-L', str(binary)], text=True)
    symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
    mapping = Path(link_map).read_text(encoding='utf-8', errors='surrogateescape')
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
    navigation_linked = bool(re.search(r'\b[Tt]\s+_reader_navigation_children\s*$', symbols, re.M))
    reading_commands_linked = bool(re.search(r'\b[Tt]\s+_reader_rc_apply\s*$', symbols, re.M))
    annotation_view_linked = bool(re.search(r'\b[Tt]\s+_reader_av_page_get\s*$', symbols, re.M))
    for linked, archive, unit in [(reading_commands_linked, 'libreader_reading_commands.a', 'reading_commands.cpp.o'),
                                  (annotation_view_linked, 'libreader_annotation_view.a', 'annotation_view.cpp.o')]:
        if linked:
            providers = [line for line in mapping.splitlines() if archive in line and unit in line]
            assert len(providers) == 1, 'installed reading module provider missing or duplicated'
            assert re.search(r'\blibexreader(?:\.[0-9]+)*\.dylib', dependencies), 'reading host lacks dynamic SDK'
            assert not re.search(r'\b[Tt]\s+_exr_(?:anchor_create|anchor_resolve_ex|fixed_anchor_create|fixed_anchor_resolve)\s*$',
                                 symbols, re.M), 'reading host embedded a second SDK implementation'
    if navigation_linked:
        providers = [line for line in mapping.splitlines()
                     if 'libreader_navigation.a' in line and 'navigation.cpp.o' in line]
        assert len(providers) == 1, 'installed F2 navigation object missing or duplicated'
        assert re.search(r'\blibexreader(?:\.[0-9]+)*\.dylib', dependencies), 'navigation host lacks dynamic SDK'
        assert re.search(r'\bU\s+_exr_publication_cfi_resolve\s*$', symbols, re.M), 'navigation resolver must come from dynamic SDK'
        assert not re.search(r'\b[Tt]\s+_exr_(?:document_resolve|publication_cfi_resolve|publication_load)\s*$',
                             symbols, re.M), 'navigation embedded a second SDK implementation'
    if search_linked:
        providers = [line for line in mapping.splitlines()
                     if 'libreader_search.a' in line and 'search.cpp.o' in line]
        assert len(providers) == 1, 'installed F1 search object missing or duplicated'
        assert re.search(r'\blibexreader(?:\.[0-9]+)*\.dylib', dependencies), 'search host lacks the dynamic SDK'
        assert re.search(r'\bU\s+_exr_anchor_resolve_ex\s*$', symbols, re.M), 'resolver must come from the dynamic SDK'
        assert not re.search(r'\b[Tt]\s+_exr_(?:document_free|anchor_free|anchor_resolve_ex|pager_create)\s*$',
                             symbols, re.M), 'search embedded a second SDK implementation'
    rejected = []
    if selector_bytes_candidate:
        for symbol, archive, unit in (
            ('reader_revisions_open_raw_v3', 'reader_revisions', 'revisions'),
            ('reader_rs_decode_raw_v3', 'reader_reading_state_codec', 'reading_state'),
            ('reader_rc_apply_raw_v3', 'reader_reading_commands', 'reading_commands'),
            ('reader_av_page_get_raw_v3', 'reader_annotation_view', 'annotation_view'),
            ('reader_command_apply_book_raw_v3', 'reader_commands', 'commands'),
            ('reader_sync_step_raw_v3', 'reader_sync', 'sync'),
            ('reader_session_create_raw_v3', 'reader_session', 'session')):
            definitions = re.findall(r'(?m)^.*\b[Tt]\s+_' + symbol + r'\s*$', symbols)
            providers = [line for line in mapping.splitlines() if 'lib' + archive + '.a' in line and unit + '.cpp.o' in line]
            assert len(definitions) == len(providers) == 1, 'missing/duplicate actual raw provider: ' + symbol
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
            'selector_bytes_candidate': selector_bytes_candidate,
            'sqlite_provider': provider, 'system_sqlite_fallback': False,
            'static_sdk_linked': False, 'reading_resolver_linked': False,
            'installed_search_linked': search_linked,
            'installed_navigation_linked': navigation_linked,
            'installed_reading_commands_linked': reading_commands_linked,
            'installed_annotation_view_linked': annotation_view_linked,
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
