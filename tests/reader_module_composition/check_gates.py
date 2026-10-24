# SPDX-License-Identifier: MIT
"""Negative gates for the installed-prefix composition (Actions only).

Every rejection here is produced by running the real tool on real installed
files. A gate that only claims to reject is worthless, so each requirement is
paired with a control that must pass:

* broken exported target        -> configure must fail
* absent declared dependency    -> find_package() must fail
* second SQLite provider        -> the link must fail
* leaked source include         -> the prefix audit must reject the copy,
                                   while the untouched prefix must pass
* duplicate-provider detector   -> synthetic maps with two providers must be
                                   counted as two, single-provider maps as one
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_composition import archive_providers, direct_providers

GNU_TWO = """
Archive member included to satisfy reference by file (symbol)
/opt/prefix/lib/libexr_vendor_exr_sqlite.a(sqlite3.c.o)  exr_library.c.o (sqlite3_open_v2)
/opt/prefix/lib/libreader_catalog_sqlite.a(sqlite3.c.o)  reader_catalog.c.o (sqlite3_open_v2)
"""
GNU_ONE = """
/opt/prefix/lib/libreader_catalog_sqlite.a(sqlite3.c.o)  reader_catalog.c.o (sqlite3_open_v2)
"""
MSVC_TWO = """
 0001:00000000 _sqlite3_open_v2 0000000140001000 reader_catalog_sqlite.lib:sqlite3.c.obj
 0001:00000010 _sqlite3_open_v2 0000000140002000 exr_sqlite.lib:sqlite3.c.obj
"""
DETACHED_TWO = """
[  5] /build/exreader-product/sqlite3.c.o
[  6] /build/exreader-product/other.o
"""


def run(command, log, environment=None):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', env=environment)
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    Path(log).write_text('$ ' + ' '.join(map(str, command)) + '\nexit=' + str(result.returncode) +
                         '\n--- stdout\n' + result.stdout + '\n--- stderr\n' + result.stderr, encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--consumer-source', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--generator', default='')
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'negative gates are cloud only'
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix.resolve()
    source = args.consumer_source.resolve()
    generator = ['-G', args.generator] if args.generator else []
    python = sys.executable
    auditor = str(Path(__file__).resolve().parent / 'check_prefix.py')
    items = []

    def record(ok, name, detail=''):
        items.append({'name': name, 'pass': bool(ok), 'detail': detail})
        print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))
        return ok

    # Control: the untouched prefix must satisfy the audit.
    clean = run([python, auditor, '--prefix', str(prefix), '--source-root', str(args.source_root),
                 '--expect', 'clean'], out / 'audit-clean.log')
    record(clean.returncode == 0, 'the untouched prefix passes the include audit', str(clean.returncode))

    # 1. A broken exported target must fail configuration.
    broken = run(['cmake', '-S', str(source / 'negative_broken_target'),
                  '-B', str(scratch / 'broken-target'), *generator,
                  '-DEXR_MODULE_PREFIX=' + str(prefix)], out / 'broken-target.log')
    record(broken.returncode != 0 and 'reader_revisions_typo' in (broken.stdout + broken.stderr),
           'a broken exported target is rejected at configure time', str(broken.returncode))

    # 2. A declared dependency that is absent must fail find_package().
    partial = scratch / 'prefix-without-webdav'
    if partial.exists():
        shutil.rmtree(partial)
    shutil.copytree(prefix, partial)
    hidden = partial / 'lib' / 'cmake' / 'EXReaderWebDAV'
    hidden.rename(hidden.with_name('EXReaderWebDAV.hidden'))
    missing = run(['cmake', '-S', str(source / 'negative_missing_dependency'),
                   '-B', str(scratch / 'missing-dependency'), *generator,
                   '-DEXR_MODULE_PREFIX=' + str(partial)], out / 'missing-dependency.log')
    record(missing.returncode != 0 and 'EXReaderWebDAV' in (missing.stdout + missing.stderr),
           'an absent declared dependency is rejected by find_package()', str(missing.returncode))
    shutil.rmtree(partial, ignore_errors=True)

    # 3. A second SQLite provider in the composed link graph must be refused.
    duplicate_build = scratch / 'duplicate-provider'
    configure = run(['cmake', '-S', str(source), '-B', str(duplicate_build), *generator,
                     '-DEXR_MODULE_PREFIX=' + str(prefix),
                     '-DEXR_NEGATIVE_DUPLICATE_PROVIDER=ON'], out / 'duplicate-configure.log')
    record(configure.returncode == 0, 'the duplicate-provider control configures', str(configure.returncode))
    build = run(['cmake', '--build', str(duplicate_build), '--target', 'composition-cxx'],
                out / 'duplicate-build.log')
    text = (build.stdout + build.stderr).lower()
    record(build.returncode != 0 and any(marker in text for marker in
                                        ('multiple definition', 'lnk2005', 'duplicate symbol', 'already defined')),
           'a second SQLite provider is refused by the linker', str(build.returncode))

    # 4. A leaked source include must be rejected by the audit.
    leaked = scratch / 'prefix-with-source-include'
    if leaked.exists():
        shutil.rmtree(leaked)
    shutil.copytree(prefix, leaked)
    targets = leaked / 'lib' / 'cmake' / 'EXReaderRevisions' / 'EXReaderRevisionsTargets.cmake'
    original = targets.read_text(encoding='utf-8')
    targets.write_text(original + '\nset_property(TARGET EXReaderRevisions::reader_revisions APPEND '
                       'PROPERTY INTERFACE_INCLUDE_DIRECTORIES "' +
                       str(args.source_root.resolve()) + '/include")\n', encoding='utf-8')
    leak = run([python, auditor, '--prefix', str(leaked), '--source-root', str(args.source_root),
                '--expect', 'leak'], out / 'audit-leak.log')
    record(leak.returncode == 0 and 'names the source tree' in (leak.stdout + leak.stderr),
           'a leaked source include is rejected by the audit', str(leak.returncode))
    strict = run([python, auditor, '--prefix', str(leaked), '--source-root', str(args.source_root),
                  '--expect', 'clean'], out / 'audit-leak-strict.log')
    record(strict.returncode != 0, 'the leaked prefix cannot pass the clean audit', str(strict.returncode))
    shutil.rmtree(leaked, ignore_errors=True)

    # 5. The duplicate-provider detector must fire on every map dialect.
    record(len(archive_providers(GNU_ONE)) == 1 and 'reader_catalog_sqlite' in archive_providers(GNU_ONE)[0],
           'the detector counts one GNU provider')
    record(len(archive_providers(GNU_TWO)) == 2, 'the detector counts two GNU providers',
           ','.join(archive_providers(GNU_TWO)))
    record(len(archive_providers(MSVC_TWO)) == 2, 'the detector counts two MSVC providers',
           ','.join(archive_providers(MSVC_TWO)))
    record(len(direct_providers(DETACHED_TWO)) == 1, 'the detector sees a directly linked amalgamation',
           ','.join(direct_providers(DETACHED_TWO)))

    summary = {'accepted': all(item['pass'] for item in items),
               'source_sha': os.environ.get('GITHUB_SHA'),
               'run_id': os.environ.get('GITHUB_RUN_ID'),
               'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
               'platform': sys.platform,
               'runner_os': os.environ.get('RUNNER_OS'),
               'items': items}
    (out / 'gates.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
    return 0 if summary['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
