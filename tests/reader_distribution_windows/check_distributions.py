#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic fixtures for the Windows distribution tooling.

Every case here is a local fixture, never SDK evidence: it proves that the
scanner detects a deliberate leak, that the sanitizer rewrites only invertible
text and refuses binary surfaces, that the seal is reproducible, and that the
archive readers reject escaping, aliased or truncated containers.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'tools/reader_distribution_windows'
sys.path.insert(0, str(TOOLS))
import distlib

CASES = []


def case(label):
    CASES.append(label)
    print('case:', label, flush=True)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def coff_object(section, payload):
    header = bytearray(20)
    header[0:2] = (0x8664).to_bytes(2, 'little')
    header[2:4] = (1).to_bytes(2, 'little')
    header[15] = 0
    header[16:18] = (0).to_bytes(2, 'little')
    header[18:20] = (0x100).to_bytes(2, 'little')
    section_header = bytearray(40)
    section_header[0:8] = section.encode('ascii').ljust(8, bytes([0]))
    section_header[16:20] = len(payload).to_bytes(4, 'little')
    section_header[20:24] = (60).to_bytes(4, 'little')
    section_header[36:40] = (0x100A00).to_bytes(4, 'little')
    return bytes(header) + bytes(section_header) + payload


def make_archive(members):
    body = bytearray(b'!<arch>' + bytes([10]))
    for name, payload in members:
        header = bytearray(60)
        encoded = name.encode('ascii')
        header[0:len(encoded)] = encoded
        header[16:28] = b'0'.ljust(12, b' ')
        header[28:34] = b'0'.ljust(6, b' ')
        header[34:40] = b'0'.ljust(6, b' ')
        header[40:48] = b'644'.ljust(8, b' ')
        header[48:58] = str(len(payload)).encode('ascii').ljust(10, b' ')
        header[58:60] = distlib.MEMBER_FMAG
        body += bytes(header) + payload
        if len(payload) % 2:
            body += bytes([10])
    return bytes(body)


def stage(root, extra=None, binary_leak=False):
    write(root / 'include/exr/base.h', '#define EXR_VERSION "3.40.0"\n#define EXR_ABI_VERSION 1u\n')
    write(root / 'lib/cmake/EXReader/EXReaderConfig.cmake', 'set(EXReader_VERSION "3.40.0")\n')
    write(root / 'lib/exreader/exr_vendor_zlib.lib', 'not a real archive\n')
    write(root / 'share/exreader/licenses/zlib/LICENSE', 'synthetic license\n')
    write(root / 'LICENSE', 'synthetic license\n')
    write(root / 'THIRD_PARTY_NOTICES.md', 'synthetic notices\n')
    write(root / 'examples/sample.txt', 'synthetic example\n')
    write(root / 'docs/guide.md',
          'Build evidence from D:\\a\\EXReader\\EXReader\\build\\reading-core\\stage.\nand /home/runner/work/EXReader/EXReader/keep.\n')
    if extra:
        write(root / extra, 'extra material\n')
    if binary_leak:
        (root / 'lib/exreader/leak.bin').write_bytes(
            bytes([0, 0, 0, 0]) + b'build root D:\\a\\EXReader\\EXReader\\leak' + bytes([0]) * 8)
    return root


def run(*arguments):
    return subprocess.run([sys.executable] + [str(item) for item in arguments],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        # 1. Category and inventory behaviour.
        original = stage(root / 'stage')
        entries = distlib.inventory(original)
        by_path = {item['path']: item['category'] for item in entries}
        assert by_path['include/exr/base.h'] == 'header'
        assert by_path['lib/cmake/EXReader/EXReaderConfig.cmake'] == 'config'
        assert by_path['share/exreader/licenses/zlib/LICENSE'] == 'license'
        assert by_path['lib/exreader/exr_vendor_zlib.lib'] == 'library'
        assert by_path['docs/guide.md'] == 'doc'
        assert by_path['examples/sample.txt'] == 'example'
        categories = distlib.category_digests(entries)
        assert categories['header']['files'] == 1 and categories['license']['files'] == 3
        assert categories['config']['sha256'] and categories['library']['sha256']
        case('inventory-and-category-digests')
        try:
            distlib.inventory(root / 'missing-stage')
        except ValueError:
            case('inventory-refuses-missing-stage')
        else:
            raise AssertionError('accepted a missing stage')
        try:
            distlib.inventory(root / 'stage/includes')
        except ValueError:
            case('inventory-refuses-absent-directory')
        else:
            raise AssertionError('accepted an absent directory')

        # 2. Scanning: text hits are classified, and the scanner is not vacuous.
        patterns = distlib.build_patterns(['D:/a/EXReader/EXReader', 'C:/Users/runner'])
        records = distlib.scan_tree(original, patterns)
        hits = [hit for item in records for hit in item['hits']]
        assert len(hits) >= 2, hits
        assert all(hit['class'] == 'text' for hit in hits)
        assert any(hit['pattern'] == 'runner-workspace-d-drive' for hit in hits)
        assert any(hit['pattern'] == 'hosted-work-unix' for hit in hits)
        case('scan-detects-declared-and-machine-patterns')

        scan_report = root / 'scan.json'
        completed = run(TOOLS / 'scan_paths.py', '--root', original, '--root-arg',
                        'D:/a/EXReader/EXReader', '--output', scan_report)
        assert completed.returncode == 0, completed.stderr
        completed = run(TOOLS / 'scan_paths.py', '--root', original, '--root-arg',
                        'D:/a/EXReader/EXReader', '--require-clean', '--output', root / 'scan-clean.json')
        assert completed.returncode == 3, completed.stderr
        case('scan-cli-blocks-dirty-tree-only-when-required')

        # 3. Binary leaks block; the sanitizer never edits a container.
        leaking = stage(root / 'leaking', binary_leak=True)
        completed = run(TOOLS / 'scan_paths.py', '--root', leaking, '--root-arg',
                        'D:/a/EXReader/EXReader', '--output', root / 'scan-leaking.json')
        assert completed.returncode == 0, completed.stderr
        completed = run(TOOLS / 'scan_paths.py', '--root', leaking, '--root-arg',
                        'D:/a/EXReader/EXReader', '--require-clean',
                        '--output', root / 'scan-leaking-clean.json')
        assert completed.returncode == 2, completed.stderr
        case('scan-cli-blocks-binary-hit')

        leaking_scan = root / 'scan-leaking.json'
        completed = run(TOOLS / 'sanitize_stage.py', '--source', leaking, '--destination',
                        root / 'leaking-sanitized', '--scan', leaking_scan,
                        '--output', root / 'sanitize-leaking.json')
        assert completed.returncode == 2, completed.stderr
        report = json.loads((root / 'sanitize-leaking.json').read_text())
        assert report['accepted'] is False and report['refused']
        assert report['refused'][0]['path'] == 'lib/exreader/leak.bin'
        case('sanitizer-refuses-binary-surface')

        # 4. Text sanitization is invertible, idempotent and line-stable.
        stage(root / 'copy-source')
        source = root / 'copy-source'
        scan_copy = root / 'scan-copy.json'
        assert run(TOOLS / 'scan_paths.py', '--root', source, '--root-arg',
                   'D:/a/EXReader/EXReader', '--output', scan_copy).returncode == 0
        destination = root / 'sanitized'
        sanitize = root / 'sanitize.json'
        completed = run(TOOLS / 'sanitize_stage.py', '--source', source, '--destination', destination,
                        '--scan', scan_copy, '--output', sanitize)
        assert completed.returncode == 0, completed.stderr
        audit = json.loads(sanitize.read_text())
        assert audit['accepted'] is True and audit['residual'] == {'text_hits': 0, 'binary_hits': 0}
        assert len(audit['rewritten']) == 1 and audit['rewritten'][0]['path'] == 'docs/guide.md'
        rewritten = (destination / 'docs/guide.md').read_text()
        assert 'D:\\a\\' not in rewritten and '<path:' in rewritten
        original_text = (source / 'docs/guide.md').read_text()
        assert len(rewritten.splitlines()) == len(original_text.splitlines())
        record = json.loads(sanitize.read_text())['rewritten'][0]
        assert sorted(record['patterns']) == ['hosted-work-unix', 'runner-workspace-d-drive']
        matched = [item['matched'] for item in record['occurrences']]
        assert matched[0] == 'D:\\a\\' and matched[-1] == '/home/runner/work'
        rebuilt = distlib.restore_occurrences(
            (destination / 'docs/guide.md').read_bytes(), record['occurrences'])
        assert rebuilt == (source / 'docs/guide.md').read_bytes()
        case('sanitizer-rewrites-invertibly-without-changing-lines')
        completed = run(TOOLS / 'sanitize_stage.py', '--source', source, '--destination', destination,
                        '--scan', scan_copy, '--output', root / 'sanitize-again.json')
        assert completed.returncode != 0
        case('sanitizer-refuses-existing-destination')

        # 5. Sealing is reproducible, bound to the audited stage and tamper-evident.
        archive = root / 'distribution.zip'
        report_path = root / 'distribution.json'
        completed = run(TOOLS / 'seal_distribution.py', '--stage', destination,
                        '--scan', root / 'scan-sanitized.json', '--sanitize', sanitize,
                        '--archive-out', archive, '--report', report_path,
                        '--source-sha', 'a' * 40)
        assert completed.returncode != 0, 'sealing accepted a stage that was never re-scanned'
        case('seal-refuses-unscanned-stage')
        scan_sanitized = root / 'scan-sanitized.json'
        assert run(TOOLS / 'scan_paths.py', '--root', destination, '--root-arg',
                   'D:/a/EXReader/EXReader', '--require-clean',
                   '--output', scan_sanitized).returncode == 0
        completed = run(TOOLS / 'seal_distribution.py', '--stage', destination,
                        '--scan', scan_sanitized, '--sanitize', sanitize,
                        '--archive-out', archive, '--report', report_path,
                        '--source-sha', 'a' * 40)
        assert completed.returncode == 0, completed.stderr
        sealed = json.loads(report_path.read_text())
        assert sealed['accepted'] is True and sealed['published'] is False
        assert sealed['reproducibility']['identical'] is True
        assert sealed['archive']['sha256'] == distlib.digest(archive)
        assert sealed['categories']['header']['files'] == 1
        case('seal-deterministic-and-archive-bound-to-stage')
        completed = run(TOOLS / 'seal_distribution.py', '--stage', destination,
                        '--scan', scan_sanitized, '--sanitize', sanitize,
                        '--archive-out', archive, '--report', root / 'second.json',
                        '--source-sha', 'a' * 40)
        assert completed.returncode != 0
        case('seal-refuses-existing-archive')
        altered = root / 'altered-sanitize.json'
        payload = json.loads(sanitize.read_text())
        payload['stage_digest_after'] = 'b' * 64
        altered.write_text(json.dumps(payload), encoding='utf-8')
        completed = run(TOOLS / 'seal_distribution.py', '--stage', destination,
                        '--scan', scan_sanitized, '--sanitize', altered,
                        '--archive-out', root / 'altered.zip', '--report', root / 'altered.json',
                        '--source-sha', 'a' * 40)
        assert completed.returncode != 0
        case('seal-refuses-stage-that-differs-from-the-audited-digest')

        # 6. Archive reader refusals.
        for label, mutate in (
                ('zip-refuses-escaping-entry', lambda archive: archive.writestr('../escape.txt', b'x')),
                ('zip-refuses-backslash-entry', lambda archive: archive.writestr('dir\\file.txt', b'x')),
                ('zip-refuses-absolute-entry', lambda archive: archive.writestr('/absolute.txt', b'x')),
                ('zip-refuses-directory-entry', lambda archive: archive.writestr('dir/', b''))):
            crafted = root / (label + '.zip')
            with zipfile.ZipFile(crafted, 'w') as handle:
                mutate(handle)
            try:
                distlib.read_zip(crafted)
            except ValueError:
                case(label)
            else:
                raise AssertionError('accepted a crafted archive: ' + label)

        # 7. COFF archive surfaces: member names and absolute .drective directives.
        absolute = b'/DEFAULTLIB:"D:\\a\\EXReader\\EXReader\\vendor.lib"'
        member = coff_object('.drectve', absolute)
        library = root / 'surface.lib'
        library.write_bytes(make_archive([('control.obj', member)]))
        facts = distlib.scan_archive('surface.lib', library.read_bytes())
        print('surface facts', json.dumps(facts, default=str)[:600], flush=True)
        assert facts['member_names_sample'] == ['control.obj'], facts['member_names_sample']
        assert not facts['member_names_with_separator'], facts['member_names_with_separator']
        assert facts['debug_section_count'] == 0, facts['debug_section_count']
        assert facts['drective_absolute'], facts['drective_absolute']
        assert 'D:\\a\\' in facts['drective_absolute'][0]['absolute'], facts['drective_absolute']
        case('archive-reader-classifies-members-and-drective')
        debug_member = coff_object('.debug$S', b'\x04' + b'0' * 8 + b'D:\\a\\EXReader\\EXReader\\x.c' + bytes([0]))
        debug_library = root / 'debug.lib'
        debug_library.write_bytes(make_archive([('control.obj', debug_member)]))
        debug_facts = distlib.scan_archive('debug.lib', debug_library.read_bytes())
        print('debug facts', json.dumps(debug_facts, default=str)[:600], flush=True)
        assert debug_facts['debug_section_count'] == 1, debug_facts['debug_section_count']
        assert debug_facts['debug_sections'][0]['section'] == '.debug$S', debug_facts['debug_sections']
        case('archive-reader-detects-debug-sections')
        for label, payload in (('archive-rejects-bad-magic', b'!<arch>' + bytes([10]) + b'x' * 61),
                               ('archive-rejects-truncated-member', b'!<arch>' + bytes([10]) + bytes(60))):
            try:
                distlib.scan_archive(label, payload)
            except ValueError:
                case(label)
            else:
                raise AssertionError('accepted a malformed archive: ' + label)
        try:
            distlib.scan_pe('broken.dll', b'MZ' + bytes(100))
        except ValueError:
            case('pe-reader-refuses-truncated-image')
        else:
            raise AssertionError('accepted a truncated PE image')

        # 8. Directive parsing and the named-result gate.
        directives = distlib.split_directives('/DEFAULTLIB:"C:\\x y\\z.lib" -link /LIBPATH:rel')
        assert directives[0] == '/DEFAULTLIB:"C:\\x y\\z.lib"', directives
        assert distlib.absolute_directive(directives[0]).startswith('C:\\x y')
        assert distlib.absolute_directive('/DEFAULTLIB:exr_vendor_zlib.lib') is None
        assert distlib.absolute_directive('/LIBPATH:..\\lib') == '..\\lib'
        case('directive-parsing-separates-absolute-and-relative')
        results = []
        distlib.named(results, 'one', True)
        distlib.require_named_pass(results, ['one'])
        try:
            distlib.require_named_pass(results, ['two'])
        except ValueError:
            case('gate-refuses-missing-named-result')
        else:
            raise AssertionError('accepted a missing named result')
        distlib.named(results, 'two', False)
        try:
            distlib.require_named_pass(results, ['one', 'two'])
        except ValueError:
            case('gate-refuses-failed-named-result')
        else:
            raise AssertionError('accepted a failed named result')

        # 9. Sealing refuses an empty stage and an unbounded document set.
        empty = root / 'empty'
        empty.mkdir()
        try:
            distlib.seal_zip(empty, root / 'empty.zip')
        except ValueError:
            case('seal-refuses-empty-stage')
        else:
            raise AssertionError('sealed an empty stage')


        # 10. Bounded archive reads: declared sizes are refused before any content read.
        import struct
        def central_offsets(payload):
            offsets = []
            position = payload.find(b'PK' + bytes([1, 2]))
            while position >= 0:
                offsets.append(position)
                position = payload.find(b'PK' + bytes([1, 2]), position + 4)
            return offsets

        small = root / 'declared-oversize.zip'
        with zipfile.ZipFile(small, 'w', zipfile.ZIP_STORED) as handle:
            handle.writestr('payload.bin', b'x' * 64)
        payload = bytearray(small.read_bytes())
        assert len(payload) < 4096
        for offset in central_offsets(bytes(payload)):
            payload[offset + 24:offset + 28] = (0x40000000).to_bytes(4, 'little')
        small.write_bytes(bytes(payload))
        assert small.stat().st_size < 4096, 'the oversize fixture must stay tiny'
        try:
            distlib.read_zip(small, limit=1024 * 1024)
        except ValueError as error:
            assert 'declares' in str(error), str(error)
            case('zip-refuses-declared-oversize-before-reading')
        else:
            raise AssertionError('accepted an entry that declares more than the limit')
        try:
            distlib.read_zip(small, limit=1024 * 1024, max_entry=64)
        except ValueError as error:
            case('zip-refuses-declared-per-entry-oversize')
        else:
            raise AssertionError('accepted a per-entry oversize declaration')

        truncated = root / 'truncated.zip'
        good = root / 'good.zip'
        with zipfile.ZipFile(good, 'w', zipfile.ZIP_STORED) as handle:
            handle.writestr('payload.bin', b'y' * 256)
        raw = good.read_bytes()
        truncated.write_bytes(raw[:-40])
        try:
            distlib.read_zip(truncated)
        except ValueError:
            case('zip-refuses-truncated-container')
        else:
            raise AssertionError('accepted a truncated archive')

        tampered = root / 'tampered.zip'
        payload = bytearray(raw)
        start = payload.find(b'PK' + bytes([3, 4]))
        name_length = struct.unpack_from('<H', payload, start + 26)[0]
        extra_length = struct.unpack_from('<H', payload, start + 28)[0]
        body = start + 30 + name_length + extra_length
        payload[body] = payload[body] ^ 0xFF
        tampered.write_bytes(bytes(payload))
        try:
            distlib.read_zip(tampered)
        except ValueError:
            case('zip-refuses-tampered-content')
        else:
            raise AssertionError('accepted an entry whose CRC no longer matches')

        duplicated = root / 'duplicate.zip'
        with zipfile.ZipFile(duplicated, 'w', zipfile.ZIP_STORED) as handle:
            handle.writestr('same.bin', b'one')
            handle.writestr('same.bin', b'two')
        try:
            distlib.read_zip(duplicated)
        except ValueError as error:
            assert 'duplicate' in str(error), str(error)
            case('zip-refuses-duplicate-members')
        else:
            raise AssertionError('accepted duplicate member names')

        aliased = root / 'case-alias.zip'
        with zipfile.ZipFile(aliased, 'w', zipfile.ZIP_STORED) as handle:
            handle.writestr('Member.txt', b'one')
            handle.writestr('member.txt', b'two')
        try:
            distlib.read_zip(aliased)
        except ValueError as error:
            assert 'duplicate' in str(error), str(error)
            case('zip-refuses-case-aliased-members')
        else:
            raise AssertionError('accepted case-aliased member names')

        honest = root / 'honest.zip'
        with zipfile.ZipFile(honest, 'w', zipfile.ZIP_DEFLATED) as handle:
            handle.writestr('bin/one.bin', b'z' * 2048)
            handle.writestr('two.txt', 'text\n')
        records = distlib.read_zip(honest)
        assert [item['path'] for item in records] == ['bin/one.bin', 'two.txt']
        assert all(item['bytes'] > 0 and len(item['sha256']) == 64 for item in records)
        case('zip-accepts-honest-archive')

        # 11. pkg-config metadata is relocated relatively, not replaced by a token.
        pc_stage = stage(root / 'pc-stage')
        pc_prefix = str(pc_stage).replace('\\', '/')
        write(pc_stage / 'lib/pkgconfig/demo.pc',
              'prefix=' + pc_prefix + '\n'
              'exec_prefix=' + chr(36) + '{prefix}\n'
              'libdir=' + chr(36) + '{exec_prefix}/lib\n'
              'includedir=' + chr(36) + '{prefix}/include\n'
              'Name: demo\nDescription: synthetic relocation fixture\nVersion: 1.0\n'
              'Libs: -L' + chr(36) + '{libdir} -ldemo\n'
              'Cflags: -I' + chr(36) + '{includedir}\n')
        pc_scan = root / 'scan-pc.json'
        assert run(TOOLS / 'scan_paths.py', '--root', pc_stage, '--root-arg',
                   str(pc_stage), '--output', pc_scan).returncode == 0
        pc_destination = root / 'pc-sanitized'
        pc_sanitize = root / 'pc-sanitize.json'
        completed = run(TOOLS / 'sanitize_stage.py', '--source', pc_stage,
                        '--destination', pc_destination, '--scan', pc_scan,
                        '--output', pc_sanitize)
        assert completed.returncode == 0, completed.stderr
        audit = json.loads(pc_sanitize.read_text())
        record = [item for item in audit['rewritten'] if item['path'].endswith('demo.pc')][0]
        assert record['mode'] == 'pcfiledir', record['mode']
        assert record['expression'] == chr(36) + '{pcfiledir}/../..', record['expression']
        assert all(item['replacement'] == record['expression'] for item in record['occurrences'])
        text = (pc_destination / 'lib/pkgconfig/demo.pc').read_text()
        assert 'prefix=' + chr(36) + '{pcfiledir}/../..' in text
        assert 'Libs: -L' + chr(36) + '{libdir} -ldemo' in text
        assert 'Cflags: -I' + chr(36) + '{includedir}' in text
        rebuilt = distlib.restore_occurrences(
            (pc_destination / 'lib/pkgconfig/demo.pc').read_bytes(), record['occurrences'])
        assert rebuilt == (pc_stage / 'lib/pkgconfig/demo.pc').read_bytes()
        case('pkgconfig-metadata-relocated-relative-to-its-own-directory')

        outside = stage(root / 'pc-outside')
        write(outside / 'lib/pkgconfig/escape.pc',
              'prefix=D:/a/EXReader/EXReader/build/elsewhere\n'
              'Libs: -L' + chr(36) + '{prefix}/lib -lescape\n')
        outside_scan = root / 'scan-pc-outside.json'
        assert run(TOOLS / 'scan_paths.py', '--root', outside, '--root-arg',
                   str(outside), '--output', outside_scan).returncode == 0
        completed = run(TOOLS / 'sanitize_stage.py', '--source', outside,
                        '--destination', root / 'pc-outside-sanitized',
                        '--scan', outside_scan, '--output', root / 'pc-outside.json')
        assert completed.returncode != 0
        case('pkgconfig-refuses-prefix-outside-the-installed-tree')

    print(json.dumps({'accepted': True, 'checks': len(CASES), 'cases': CASES}))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except AssertionError as error:
        print('fixture failure: ' + str(error), file=sys.stderr)
        sys.exit(1)
