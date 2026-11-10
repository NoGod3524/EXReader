#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small positive/rejection checks; synthetic validator fixtures, never SDK evidence."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from reading_release import check_profile, digest, seal


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if isinstance(value, dict) else value, encoding='utf-8')


def fixture(root, profile):
    stage, reports = root / 'stage', root / 'reports'
    write(stage / 'include/exr/base.h', '#define EXR_VERSION "3.40.0"\n#define EXR_ABI_VERSION 1u\n')
    write(stage / 'LICENSE', 'synthetic material for validator self-check\n')
    write(stage / 'THIRD_PARTY_NOTICES.md', 'synthetic notices for validator self-check\n')
    library = profile == 'reading-library'
    if library:
        write(stage / 'include/exr/library.h', '#define EXR_LIBRARY_VERSION "3.34.0"\n')
    files = [{'path': p.relative_to(stage).as_posix(), 'bytes': p.stat().st_size,
              'sha256': digest(p)} for p in sorted(stage.rglob('*')) if p.is_file()]
    write(reports / 'profile.json', {'source_sha': 'a'*40, 'profile': profile,
                                   'accepted': True, 'problems': [], 'files': files})
    write(reports / 'licenses.json', {'source_sha': 'a'*40, 'profile': profile,
                                     'materials_check_passed': True, 'release_ready': True,
                                     'failures': [], 'pending': [], 'mandatory_missing': []})
    write(reports / 'corpus/summary.json', {'source_sha': 'a'*40, 'accepted': True, 'source_dirty': False,
                                         'identities_unchanged': True, 'results': [{} for _ in range(9)]})
    names = ['installed-core', 'installed-chapter', 'installed-convert']
    if library:
        names += ['installed-library', 'installed-library-source']
    write(reports / 'consumer-tests.xml', '<testsuite>' + ''.join('<testcase name="'+n+'"/>' for n in names) + '</testsuite>')
    runtime = root / 'runtime.json'
    write(runtime, {'sdk_version': '3.40.0', 'abi': 1, 'library_header_version': '3.34.0' if library else None})
    db = root / 'library.sqlite' if library else None
    if db:
        with sqlite3.connect(db) as connection:
            connection.execute('PRAGMA application_id=1163416131')
            connection.execute('PRAGMA user_version=7')
    return stage, reports, runtime, db


def main():
    cases = []
    for profile in ('reading-core', 'reading-library'):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage, reports, runtime, db = fixture(root, profile)
            check = lambda: check_profile(profile, 'a'*40, stage, reports, runtime, db)
            identity = check()
            ci = {'GITHUB_RUN_ID': '1', 'GITHUB_RUN_ATTEMPT': '1', 'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64'}
            first = seal(stage, root/'one', profile, 'a'*40, identity, ci, 1000, 'Linux', 'X64')
            second = seal(stage, root/'two', profile, 'a'*40, identity, ci, 1000, 'Linux', 'X64')
            assert first['sha256'] == second['sha256'] and first['quality_accepted'] is False
            cases.append(profile + ':positive-and-reproducible')
            composition = json.loads((reports/'profile.json').read_text())
            for host, arch in (('Windows', 'X64'), ('macOS', 'ARM64')):
                platform = dict(composition, host=host, platform_requested=host,
                                installed_files=composition['files'])
                platform.pop('files')
                write(reports/'platform-evidence.json', platform)
                platform_identity = check_profile(profile, 'a'*40, stage, reports, runtime, db, host)
                platform_ci = dict(ci, RUNNER_OS=host, RUNNER_ARCH=arch)
                candidate = seal(stage, root/host, profile, 'a'*40, platform_identity, platform_ci, 1000, host, arch)
                assert candidate['host'] == host and candidate['arch'] == arch and candidate['published'] is False
                assert candidate['archive'].endswith(f'-{host}-{arch}.tar.gz') and not candidate['quality_accepted']
                with tarfile.open(root/host/candidate['archive']) as archive:
                    manifests = [m for m in archive.getmembers() if m.name.endswith('/release-manifest.json')]
                    assert len(manifests) == 1
                    manifest = json.load(archive.extractfile(manifests[0]))
                    assert manifest['host'] == host and manifest['arch'] == arch and manifest['ci'] == platform_ci
                cases.append(profile + ':' + host + ':candidate-identity')
                for changes in ({'source_sha': 'b'*40}, {'accepted': False}, {'host': 'other'}, {'installed_files': []}):
                    write(reports/'platform-evidence.json', dict(platform, **changes))
                    try: check_profile(profile, 'a'*40, stage, reports, runtime, db, host)
                    except ValueError: cases.append(profile + ':' + host + ':refused-' + ','.join(changes))
                    else: raise AssertionError('accepted invalid platform composition')
                write(reports/'platform-evidence.json', platform)
            try: seal(stage, root/'wrong-host', profile, 'a'*40, identity, ci, 1000, 'Windows', 'X64')
            except ValueError: cases.append(profile + ':runner-mismatch')
            else: raise AssertionError('accepted mismatched runner identity')
            mutations = [
                ('profile.json', {'source_sha': 'b'*40}),
                ('profile.json', {'accepted': False}),
                ('profile.json', {'profile': 'unknown'}),
                ('profile.json', {'files': []}),
                ('licenses.json', {'release_ready': False}),
                ('licenses.json', {'pending': ['missing notice']}),
                ('licenses.json', {'mandatory_missing': ['missing notice']}),
                ('corpus/summary.json', {'accepted': False}),
                ('corpus/summary.json', {'source_dirty': True}),
                ('corpus/summary.json', {'identities_unchanged': False}),
                ('corpus/summary.json', {'results': []}),
            ]
            for name, changes in mutations:
                path = reports/name
                original = json.loads(path.read_text())
                altered = copy.deepcopy(original); altered.update(changes); write(path, altered)
                try:
                    check()
                except ValueError:
                    cases.append(profile + ':' + name + ':' + ','.join(changes))
                else:
                    raise AssertionError('accepted invalid report: ' + name)
                finally:
                    write(path, original)
            xml = reports/'consumer-tests.xml'
            original = xml.read_text()
            for text in (original.replace('<testcase name="installed-core"/>', ''),
                         original.replace('<testcase name="installed-core"/>', '<testcase name="installed-core"><skipped/></testcase>')):
                write(xml, text)
                try: check()
                except ValueError: cases.append(profile + ':missing-or-skipped-consumer')
                else: raise AssertionError('accepted incomplete installed consumer')
            write(xml, original)
            original = runtime.read_text(); write(runtime, {'sdk_version': '3.40.0', 'abi': 2})
            try: check()
            except ValueError: cases.append(profile + ':runtime-abi')
            else: raise AssertionError('accepted wrong runtime ABI')
            write(runtime, original)
            write(stage/'LICENSE', 'altered installed material')
            try: check()
            except ValueError: cases.append(profile + ':changed-stage')
            else: raise AssertionError('accepted changed installed stage')
    print(json.dumps({'accepted': True, 'checks': len(cases), 'cases': cases}))


if __name__ == '__main__':
    main()
