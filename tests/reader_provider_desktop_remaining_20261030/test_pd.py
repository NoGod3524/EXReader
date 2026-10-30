"""Synthetic protocol cases for the C09 desktop audit. Executed only in GitHub Actions."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_core as C  # noqa: E402
import pd_mac as A  # noqa: E402
import pd_win as W  # noqa: E402

CASES = []


def case(function):
    CASES.append(function)
    return function


def raises(call, text=''):
    try:
        call()
    except Exception as error:
        assert text in str(error), 'wrong error: %s' % error
        return
    raise AssertionError('expected failure: ' + text)


# ---- COFF builders -----------------------------------------------------------------------------

def make_obj(symbols, comdat_section=2):
    """symbols: (name, value, section, storage class). Section 2 is a COMDAT section."""
    strtab, recs = b'', b''
    for name, value, section, cls in symbols:
        raw = name.encode()
        if len(raw) <= 8:
            field = raw.ljust(8, b'\0')
        else:
            field = b'\0\0\0\0' + struct.pack('<I', 4 + len(strtab))
            strtab += raw + b'\0'
        recs += field + struct.pack('<IhHBB', value, section, 0, cls, 0)

    def sec(chars):
        return b'.text'.ljust(8, b'\0') + struct.pack('<IIIIIIHHI', 0, 0, 0, 0, 0, 0, 0, 0, chars)
    header = struct.pack('<HHIIIHH', 0x8664, 2, 0, 20 + 80, len(symbols), 0, 0)
    return header + sec(0x60000020) + sec(0x60001020) + recs + struct.pack('<I', 4 + len(strtab)) + strtab


def make_import(name, dll):
    return struct.pack('<HHHHIIHH', 0, 0xFFFF, 0, 0x8664, 0, len(name) + len(dll) + 2, 1, 0) + name.encode() + b'\0' + dll.encode() + b'\0'


def make_archive(members):
    longnames, entries = b'', []
    for name, body in members:
        if len(name) < 15:
            field = name + '/'
        else:
            field = '/%d' % len(longnames)
            longnames += name.encode() + b'\0'
        entries.append((field, body))

    def block(field, body):
        head = (field.ljust(16) + '0'.ljust(12) + '0'.ljust(6) + '0'.ljust(6) + '644'.ljust(8) + str(len(body)).ljust(10)).encode()
        return head + b'`\n' + body + (b'\n' if len(body) & 1 else b'')
    out = b'!<arch>\n' + block('/', b'') + block('/', b'')
    if longnames:
        out += block('//', longnames)
    for field, body in entries:
        out += block(field, body)
    return out


@case
def coff_archive_rows_and_weak():
    archive = make_archive([
        ('catalog.c.obj', make_obj([('sqlite3_open_v2', 0, 1, 2), ('needs_it', 0, 0, 2)])),
        ('a-very-long-member-name.obj', make_obj([('inline_fn', 0, 2, 2), ('real_fn', 0, 1, 2), ('weakdef', 0, 0, 105), ('common_v', 8, 0, 2)])),
        ('thunk.obj', make_import('CreateFileW', 'KERNEL32.dll'))])
    table, kinds = W.parse_coff_archive(archive)
    assert set(table) == {'catalog.c.obj', 'a-very-long-member-name.obj', 'thunk.obj'}, sorted(table)
    assert table['catalog.c.obj']['defined'] == {'sqlite3_open_v2'}
    assert table['catalog.c.obj']['undefined'] == {'needs_it'}
    long_row = table['a-very-long-member-name.obj']
    assert long_row['defined'] == {'real_fn'} and long_row['weak'] == {'inline_fn', 'weakdef', 'common_v'}
    assert kinds['thunk.obj'] == 'import' and table['thunk.obj']['defined'] == {'CreateFileW', '__imp_CreateFileW'}
    raises(lambda: W.parse_coff_archive(b'not an archive'), 'not a COFF archive')


@case
def msvc_map_members_and_objects():
    text = '\n'.join([
        ' Start         Length     Name                   Class',
        ' 0001:00000000 00001000H .text$mn                CODE',
        '',
        '  Address         Publics by Value              Rva+Base               Lib:Object',
        '',
        ' 0001:00000000       main                       0000000140001000 f   CMakeFiles\\host.dir\\main.cpp.obj',
        ' 0001:00000100       sqlite3_open_v2            0000000140001100 f   reader_catalog_sqlite.lib:sqlite3.c.obj',
        ' 0001:00000200       __imp_CreateFileW          0000000140001200     kernel32.lib:KERNEL32.dll',
        ' 0002:00000000       sqlite_data                0000000140005000     C:\\x y\\lib\\reader_catalog.lib:catalog.c.obj',
        ' 0001:00000300       ?inline@@YAXXZ             0000000140001300 f i libx.lib:y.obj',
        ' 0003:00000000       __ImageBase                0000000140000000     <linker-defined>'])
    parsed = W.parse_msvc_map(text)
    assert parsed['members'] == [('C:\\x y\\lib\\reader_catalog.lib', 'catalog.c.obj'), ('kernel32.lib', 'killer'.replace('killer', 'kernel32.dll')),
                                 ('libx.lib', 'y.obj'), ('reader_catalog_sqlite.lib', 'sqlite3.c.obj')], parsed['members']
    assert parsed['objects'] == ['CMakeFiles\\host.dir\\main.cpp.obj'], parsed['objects']
    raises(lambda: W.parse_msvc_map('no publics here'), 'not an MSVC link map')
    assert W.resolve_input('C:\\x y\\Lib\\A.lib', 'd:/build', []) == 'c:/x y/lib/a.lib'


@case
def dumpbin_parsers():
    imports = '\n'.join([
        '  Section contains the following imports:', '', '    KERNEL32.dll',
        '                 140123456 Import Address Table', '                 140123457 Import Name Table',
        '                         0 time date stamp', '                         0 Index of first forwarder reference', '',
        '                          1A2 CreateFileW', '                           3 Sleep',
        '  Section contains the following delay load imports:', '', '    ADVAPI32.dll',
        '                         0 Characteristics', '                          1B RegCloseKey', '  Summary'])
    rows = W.parse_dumpbin_imports(imports)
    assert [(r['library'], r['symbol'], r['kind']) for r in rows] == [
        ('KERNEL32.dll', 'CreateFileW', 'normal'), ('KERNEL32.dll', 'Sleep', 'normal'), ('ADVAPI32.dll', 'RegCloseKey', 'delay')], rows
    exports = '\n'.join(['    ordinal hint RVA      name', '', '          1    0 0000B640 AcquireSRWLockExclusive',
                         '          2    1          AddAtomA (forwarded to KERNELBASE.AddAtomA)', '    1234 number of functions'])
    assert W.parse_dumpbin_exports(exports) == {'AcquireSRWLockExclusive', 'AddAtomA'}
    deps = '  Image has the following dependencies:\n\n    KERNEL32.dll\n    bcrypt.dll\n\n  Summary\n'
    assert W.parse_dumpbin_dependents(deps) == ['KERNEL32.dll', 'bcrypt.dll']


# ---- Apple -------------------------------------------------------------------------------------

NM_ARCHIVE = '\n'.join([
    'libreader_catalog_sqlite.a(sqlite3.c.o):',
    '0000000000000010 (__TEXT,__text) external _sqlite3_open_v2',
    '                 (undefined) external _malloc (from libSystem)',
    '0000000000000020 (__TEXT,__text) weak external __ZN3foo3barEv',
    '0000000000000030 (__TEXT,__text) private external _hidden_fn',
    '                 (undefined) weak external _optional_api (from libSystem)',
    '0000000000000040 (__DATA,__common) [no dead strip] external _data_sym',
    '',
    'libreader_catalog_sqlite.a(other.c.o):',
    '                 (undefined) external _sqlite3_open_v2'])


@case
def nm_macho_members_both_header_styles():
    table = A.parse_nm_members(NM_ARCHIVE)
    row = table['sqlite3.c.o']
    assert row['defined'] == {'_sqlite3_open_v2', '_hidden_fn', '_data_sym'}, row
    assert row['weak'] == {'__ZN3foo3barEv'} and row['undefined'] == {'_malloc', '_optional_api'}
    assert row['weakref'] == {'_optional_api'} and table['other.c.o']['undefined'] == {'_sqlite3_open_v2'}
    colon = A.parse_nm_members('/x/libz.a:one.o:\n0000000000000010 (__TEXT,__text) external _one\n')
    assert colon['one.o']['defined'] == {'_one'}
    single = A.parse_nm_members('0000000000000010 (__TEXT,__text) external _main\n', single='x.o')
    assert single['x.o']['defined'] == {'_main'}
    imports = A.parse_image_imports(NM_ARCHIVE)
    assert [(r['symbol'], r['weak'], r['library']) for r in imports] == [
        ('_malloc', False, 'libSystem'), ('_optional_api', True, 'libSystem'), ('_sqlite3_open_v2', False, None)], imports


@case
def apple_map_otool_and_short_names():
    text = '\n'.join(['# Path: /x/EXReader', '# Arch: arm64', '# Object files:', '[  0] linker synthesized',
                      '[  1] /tmp/swift-abc.o', '[  2] /x/products/lib/libreader_catalog.a(catalog.c.o)',
                      '[  3] /x/sdk/lib/libexreader.3.dylib', '[  4] /Applications/Xcode.app/usr/lib/libSystem.tbd',
                      '# Sections:', '# Symbols:', '0x100 0x10 [  1] _main'])
    parsed = A.parse_apple_map(text)
    assert parsed['members'] == [('/x/products/lib/libreader_catalog.a', 'catalog.c.o')]
    assert parsed['objects'] == ['/tmp/swift-abc.o'] and len(parsed['dylibs']) == 2, parsed
    raises(lambda: A.parse_apple_map('nothing'), 'not an Apple ld map')
    libs = A.parse_otool_libraries('/x/EXReader:\n\t@rpath/libexreader.3.dylib (compatibility version 3.0.0, current version 3.42.0)\n'
                                   '\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1351.0.0)\n')
    assert libs == ['@rpath/libexreader.3.dylib', '/usr/lib/libSystem.B.dylib']
    assert [A.short_name(n) for n in libs] == ['libexreader', 'libSystem']
    assert A.short_name('/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation') == 'Foundation'


TBD = """--- !tapi-tbd
tbd-version:     4
targets:         [ arm64-macos ]
install-name:    '/usr/lib/libSystem.B.dylib'
reexported-libraries:
  - targets:         [ arm64-macos ]
    libraries:       [ '/usr/lib/system/libsystem_c.dylib' ]
exports:
  - targets:         [ arm64-macos ]
    symbols:         [ _libsystem_own ]
--- !tapi-tbd
tbd-version:     4
targets:         [ arm64-macos ]
install-name:    '/usr/lib/system/libsystem_c.dylib'
exports:
  - targets:         [ arm64-macos ]
    symbols:         [ _malloc, _free,
                       _memcpy ]
    weak-symbols:    [ _optional_api ]
    objc-classes:    [ Thing ]
undefineds:
  - targets:         [ arm64-macos ]
    symbols:         [ _not_an_export ]
...
"""


@case
def tbd_resolution(tmp=None):
    import tempfile
    docs = A.parse_tbd(TBD)
    assert len(docs) == 2 and docs[1]['symbols'] >= {'_malloc', '_memcpy', '_OBJC_CLASS_$_Thing'}
    assert '_not_an_export' not in docs[1]['symbols'] and docs[1]['weak_symbols'] == {'_optional_api'}
    assert docs[0]['reexports'] == ['/usr/lib/system/libsystem_c.dylib']
    with tempfile.TemporaryDirectory() as root:
        lib = Path(root) / 'usr/lib'
        lib.mkdir(parents=True)
        (lib / 'libSystem.B.tbd').write_text(TBD)
        index = A.StubIndex(root)
        hit = index.provider('/usr/lib/libSystem.B.dylib', '_malloc')
        assert hit and hit['install_name'] == '/usr/lib/system/libsystem_c.dylib' and not hit['weak_definition'], hit
        assert index.provider('/usr/lib/libSystem.B.dylib', '_optional_api')['weak_definition'] is True
        assert index.provider('/usr/lib/libSystem.B.dylib', '_not_an_export') is None
        assert A.tbd_path_for('/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation', root) is None


# ---- Policy and negative controls --------------------------------------------------------------

def good_evidence(platform):
    row = lambda defined=(), weak=(), undefined=(): dict(defined=list(defined), weak=list(weak), undefined=list(undefined))
    mac = platform == 'macos'
    u = '_' if mac else ''
    return dict(identity=dict(), platform=platform, image=dict(), map=dict(), product_catalog_archives=['libcatalog_sqlite.a'],
                roles=dict(sdk=['/r/sdk/'], product=['/r/product/'], host=['/r/host/'], system=['/sys/']),
                archives={'/r/sdk/lib/libsdk.a': {'sdk.o': row([u + 'exr_open'])},
                          '/r/product/lib/libcatalog_sqlite.a': {'sqlite3.o': row([u + 'sqlite3_open_v2', u + 'sqlite3_close'])},
                          '/r/product/lib/libcatalog.a': {'catalog.o': row([u + 'catalog_open'], undefined=[u + 'sqlite3_open_v2', u + 'exr_open'])},
                          '/r/host/main.o': {'main.o': row([u + 'main'], weak=[u + 'inline_fn'], undefined=[u + 'catalog_open'])}},
                selected=[['/r/sdk/lib/libsdk.a', 'sdk.o'], ['/r/product/lib/libcatalog_sqlite.a', 'sqlite3.o'],
                          ['/r/product/lib/libcatalog.a', 'catalog.o'], ['/r/host/main.o', 'main.o']],
                dynamic_needed=['KERNEL32.dll'], dynamic_imports=[dict(symbol=u + 'malloc', library='x')], runtime_identity=[
                    dict(name='runtime', status='ok')], installed_libraries=[])


@case
def policy_passes_and_every_control_rejects():
    for platform, canon in (('windows', lambda s: s), ('macos', lambda s: s[1:] if s.startswith('_') else s)):
        evidence = good_evidence(platform)
        assert C.policy(evidence, canon) == [], C.policy(evidence, canon)
        controls = C.negative_controls(evidence, canon)
        assert len(controls) == (8 if platform == 'windows' else 7), controls
        assert all(c['rejected'] for c in controls), [c for c in controls if not c['rejected']]


@case
def policy_flags_real_problems():
    evidence = good_evidence('windows')
    evidence['dynamic_imports'] = [dict(symbol='sqlite3_open_v2', library='sqlite3.dll')]
    evidence['runtime_identity'] = [dict(name='runtime', status='mismatch', expected_sha256='a', actual_sha256='b')]
    kinds = C.kinds(C.policy(evidence))
    assert kinds == {'dynamic_sqlite_import': 1, 'sdk_runtime_identity_mismatch': 1}, kinds
    evidence = good_evidence('macos')
    evidence['extra_findings'] = [dict(kind='second_sdk_provider_static_and_dynamic')]
    assert C.kinds(C.policy(evidence, lambda s: s[1:] if s.startswith('_') else s)) == {'second_sdk_provider_static_and_dynamic': 1}


@case
def dynamic_sdk_ignores_unselected_static_sdk_archives():
    canon = lambda s: s[1:] if s.startswith('_') else s
    evidence = good_evidence('macos')
    evidence['selected'] = [x for x in evidence['selected'] if x[0] != '/r/sdk/lib/libsdk.a']
    assert C.kinds(C.policy(evidence, canon)) == {'sdk_entry_without_selected_sdk_owner': 1}
    evidence['sdk_runtime_dynamic'] = True
    assert C.policy(evidence, canon) == []
    assert all(c['rejected'] for c in C.negative_controls(evidence, canon))


@case
def additions_only_scope():
    C.owned_paths(['A\t' + C.OWNED + 'x.py', 'A\t' + C.WORKFLOW, 'A\t' + C.AUDITOR, 'A\t' + C.DOC])
    raises(lambda: C.owned_paths(['M\t' + C.OWNED + 'x.py']), 'only new owned files allowed')
    raises(lambda: C.owned_paths(['A\tsrc/other.c']), 'only new owned files allowed')
    raises(lambda: C.owned_paths(['A\ttests/reader_final_provider_20261030/new.py']), 'only new owned files allowed')


def main():
    for function in CASES:
        function()
        print('ok', function.__name__, flush=True)
    print('OK %d synthetic cases' % len(CASES), flush=True)


if __name__ == '__main__':
    main()
