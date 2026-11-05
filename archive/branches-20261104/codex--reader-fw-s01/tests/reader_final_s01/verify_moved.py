#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Move the S01 candidate into a Unicode path with spaces and run it there.

Actions only. The job that runs this script never checks out the producer tree
and never sees its build directory: the only inputs are the uploaded candidate
archive, the candidate manifest and the retained acceptance code that this
checkout already carries byte for byte.

Sequence: authenticate the archive against its manifest, extract under a first
path that carries non-ASCII characters and spaces, verify every packaged file
from the extracted bytes, move the whole package to a second such path, run the
packaged native self-test there, and then run the producer's own unchanged
compact acceptance (open, import of four formats, page turns, settings dialog,
restart) against that moved program.
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from contract import (PACKAGE_ROOT, REQUIRED_FILES, RETAINED_SOURCES, classify_dependencies,
                      dependency_names, dependency_problems, manifest_problems, load_payload,
                      describe_path_hits, pe_identity, private_path_needles, read_json, require,
                      secret_hits, sha256, verify_payload, verify_zip, write_json)

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_FOLDER = 's01 原始 位置'
FINAL_FOLDER = '最终 阅读器 候选 中文'
NESTED_FOLDER = '第 1 次 迁移 后 目录 带 空格'


def find_one(root, name):
    found = [path for path in Path(root).rglob(name) if path.is_file()]
    require(len(found) == 1, 'expected exactly one %s under %s, found %d' % (name, root, len(found)))
    return found[0]


def extract(archive_path, destination):
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'duplicate archive member')
        for name in names:
            require(name.startswith(PACKAGE_ROOT + '/'), 'member outside the package root: ' + name)
            target = destination / name.split('/', 1)[1]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))


def retained_problems(manifest):
    problems = []
    recorded = {row['path']: row['sha256'] for row in manifest.get('retained') or []}
    for relative in RETAINED_SOURCES:
        path = ROOT / relative
        if not path.is_file():
            problems.append('retained source is missing here: ' + relative)
            continue
        if recorded.get(relative) != sha256(path):
            problems.append('retained source differs from the producer file: ' + relative)
    if set(recorded) != set(RETAINED_SOURCES):
        problems.append('manifest does not record every retained source')
    return problems


def compact_contract():
    spec = importlib.util.spec_from_file_location(
        'retained_compact_contract', ROOT / 'tests' / 'reader_windows_compact' / 'contract.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True, help='downloaded candidate artifact directory')
    parser.add_argument('--fixtures', type=Path, required=True, help='authored fixtures generated in this job')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unicode-root', type=Path,
                        help='parent directory for the Unicode destinations; defaults to the runner desktop')
    args = parser.parse_args()

    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'run the moved package checks in GitHub Actions only')
    require(os.name == 'nt', 'the moved package checks drive the real Windows program')
    output = args.output.resolve()
    require(not output.exists(), 'choose a new moved-package output directory')
    output.mkdir(parents=True)
    run = {'run_id': os.environ.get('GITHUB_RUN_ID'), 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
           'job': os.environ.get('GITHUB_JOB'), 'source': os.environ.get('GITHUB_SHA')}
    problems = []

    manifest_path = find_one(args.artifacts, 'manifest.json')
    manifest = read_json(manifest_path)
    problems += manifest_problems(manifest)
    require(manifest['implementation_source'] == run['source'],
            'the manifest belongs to a different implementation source')
    require(manifest['program']['authenticode'] == 'unsigned',
            'the manifest does not declare the program signature status')
    problems += retained_problems(manifest)

    archive = find_one(args.artifacts, manifest['zip']['name'])
    require(archive.stat().st_size == manifest['zip']['bytes'], 'candidate archive size differs')
    require(sha256(archive) == manifest['zip']['sha256'], 'candidate archive digest differs')

    expected = {row['path']: {'bytes': row['bytes'], 'sha256': row['sha256']} for row in manifest['files']}
    declared = {row['path'] for row in manifest['files']}
    for name in REQUIRED_FILES:
        if name not in declared:
            problems.append('manifest does not declare the mandatory file: ' + name)

    # ------------------------------------------------------------ first Unicode path
    home = os.environ.get('USERPROFILE') or str(Path.home())
    base = args.unicode_root.resolve() if args.unicode_root else Path(home) / 'Desktop'
    base.mkdir(parents=True, exist_ok=True)
    require(base.is_dir(), 'the Unicode destination root is not a directory: ' + str(base))
    workspace = str(os.environ.get('GITHUB_WORKSPACE') or '')
    if workspace:
        require(not str(base).lower().startswith(workspace.lower()),
                'the Unicode destination sits inside the workflow workspace')
    first_parent = base / ORIGINAL_FOLDER
    require(not first_parent.exists(), 'the first Unicode destination already exists')
    first_parent.mkdir(parents=True)
    first = first_parent / PACKAGE_ROOT
    first.mkdir()
    extract(archive, first)
    payload = load_payload(first)
    problems += verify_zip(archive, payload, PACKAGE_ROOT)
    problems += verify_payload(payload, expected, REQUIRED_FILES)
    print(json.dumps({'stage': 'extracted', 'destination': str(first)}), flush=True)
    require(str(first).isascii() is False and ' ' in str(first), 'the first destination is not Unicode with spaces')
    require(not ({'producer-src', 'build'} & set(first.parts)), 'the first destination sits inside a build tree')
    needles = private_path_needles([os.environ.get('GITHUB_WORKSPACE'), base])
    path_hits = describe_path_hits(payload, needles)
    secret_scan = secret_hits(payload)
    for hit in secret_scan:
        problems.append('%s ships a test secret marker (%s)' % (hit['path'], hit['marker']))
    release_blockers = ['%s ships a build-machine absolute path (%s, %s, byte offset %d)'
                        % (hit['path'], hit['needle'], hit['encoding'], hit['offset'])
                        for hit in path_hits]

    identity = pe_identity(payload['EXReader.exe'])
    for key in ('machine', 'subsystem', 'authenticode', 'certificate_bytes'):
        if identity[key] != manifest['program']['pe'][key]:
            problems.append('the extracted program header differs from the manifest: ' + key)
    raw = manifest['dependencies'].get('raw_output') or ''
    require(sha256(raw.encode('utf-8')) == manifest['dependencies'].get('raw_output_sha256'),
            'the captured dependency output differs from its own digest')
    names = dependency_names(raw)
    require(names == [row['name'] for row in manifest['dependencies']['entries']],
            'the recorded dependency entries do not follow the captured output')
    rows = classify_dependencies(names, Path(os.environ.get('SystemRoot', 'C:\\Windows')) / 'System32',
                                 list(payload))
    problems += dependency_problems(rows)

    # ------------------------------------------------------------ move to the final path
    final_parent = base / FINAL_FOLDER / NESTED_FOLDER
    require(not final_parent.exists(), 'the final Unicode destination already exists')
    final_parent.mkdir(parents=True)
    final = final_parent / PACKAGE_ROOT
    shutil.move(str(first), str(final))
    require(not first.exists(), 'the first destination survived the move')
    require(str(final).isascii() is False and ' ' in str(final), 'the final destination is not Unicode with spaces')
    require(not ({'producer-src', 'build'} & set(final.parts)), 'the final destination sits inside a build tree')
    moved_payload = load_payload(final)
    for name in sorted(expected):
        if name not in moved_payload or sha256(moved_payload[name]) != expected[name]['sha256']:
            problems.append('the move changed a packaged file: ' + name)
    if set(moved_payload) != set(payload):
        problems.append('the move changed the packaged file set')

    print(json.dumps({'stage': 'moved', 'destination': str(final)}), flush=True)
    program_digest_before = sha256(final / 'EXReader.exe')
    font = final / 'Reader.otf'

    # ------------------------------------------------------------ packaged self-test
    selftest_folder = output / 'selftest'
    selftest_folder.mkdir()
    report_path = selftest_folder / 'report.json'
    image_path = selftest_folder / 'page.png'
    command = [str(final / 'EXReader.exe'), '--self-test', str(font), str(final / 'Sample.epub'),
               str(final / 'Sample.pdf'), str(report_path), str(image_path)]
    selftest_command = ['EXReader.exe', '--self-test', '<font>', '<epub>', '<pdf>', '<report>', '<image>']
    started = time.time()
    completed = subprocess.run(command, cwd=str(final), capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=600)
    elapsed = round(time.time() - started, 3)
    selftest_exit = completed.returncode
    (selftest_folder / 'stdout.log').write_text((completed.stdout or '') + '\n--- stderr ---\n' +
                                                (completed.stderr or ''), encoding='utf-8')
    require(selftest_exit == 0, 'the moved program self-test exited %s' % selftest_exit)
    require(report_path.is_file(), 'the moved program wrote no self-test report')
    selftest = read_json(report_path)
    version = manifest['sdk']['version']
    require(selftest.get('passed') is True, 'the moved program self-test did not pass')
    require(isinstance(selftest.get('checks'), int) and selftest['checks'] >= 26,
            'the moved program self-test reported fewer than 26 checks')
    require(selftest.get('engine_version') == version, 'the moved program reports another engine version')
    require(image_path.is_file() and image_path.stat().st_size > 0, 'the moved program wrote no self-test image')
    print(json.dumps({'stage': 'self-test', 'checks': selftest['checks'],
                      'engine_version': selftest['engine_version']}), flush=True)

    # ------------------------------------------------------------ retained compact acceptance
    fixtures = args.fixtures.resolve()
    require((fixtures / 'Reading sample.txt').is_file() and (fixtures / 'Large comic.cbz').is_file(),
            'the authored fixtures were not generated in this job')
    checker = ROOT / 'tests' / 'reader_windows_compact' / 'check_ui.py'
    compact_folder = output / 'compact'
    command = [sys.executable, str(checker), '--candidate', str(final / 'EXReader.exe'), '--font', str(font),
               '--fixtures', str(fixtures), '--output', str(compact_folder)]
    started = time.time()
    completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=3000)
    elapsed_compact = round(time.time() - started, 3)
    (output / 'compact-stdout.log').write_text((completed.stdout or '') + '\n--- stderr ---\n' +
                                               (completed.stderr or ''), encoding='utf-8')
    print(json.dumps({'stage': 'compact-run', 'exit_code': completed.returncode,
                      'elapsed_seconds': elapsed_compact}), flush=True)
    compact_report_path = compact_folder / 'report.json'
    require(compact_report_path.is_file(), 'the retained compact acceptance wrote no report')
    compact = read_json(compact_report_path)
    contract = compact_contract()
    contract.validate(compact, run['source'], run['run_id'], run['attempt'], expected['EXReader.exe']['sha256'])
    require(compact['count'] == len(contract.REQUIRED), 'the retained compact acceptance ran fewer checks')
    require(compact['accepted'] is True and not compact['problems'], 'the retained compact acceptance refused')
    require(completed.returncode == 0, 'the retained compact acceptance exited %s' % completed.returncode)
    screenshots = {}
    for name, record in sorted((compact.get('screenshots') or {}).items()):
        path = compact_folder / name
        require(path.is_file(), 'the retained compact acceptance lost a screenshot: ' + name)
        require(path.stat().st_size == record['bytes'] and sha256(path) == record['sha256'],
                'a compact acceptance screenshot differs: ' + name)
        screenshots[name] = {'bytes': record['bytes'], 'sha256': record['sha256']}

    # ------------------------------------------------------------ after the runs
    after = load_payload(final)
    mutated = sorted(name for name in after if name not in expected or sha256(after[name]) != expected[name]['sha256'])
    added = sorted(set(after) - set(expected))
    removed = sorted(set(expected) - set(after))
    for name in mutated:
        if name in ('EXReader.exe',) or name.startswith('licenses/'):
            problems.append('running the program changed a shipped file: ' + name)
    program_digest_after = sha256(final / 'EXReader.exe')
    require(program_digest_after == program_digest_before, 'the program changed while it ran')

    result = {'schema': 1, 'accepted': not problems, 'run': run,
              'implementation_source': run['source'], 'producer_source': manifest['producer_source'],
              'producer_tree': manifest['producer_tree'],
              'program': {'sha256': program_digest_after, 'bytes': expected['EXReader.exe']['bytes'],
                          'authenticode': identity['authenticode'],
                          'identical_to_published_program':
                              manifest['program']['reference']['identical_to_published_program']},
              'sdk': manifest['sdk'], 'archive': manifest['zip'],
              'destinations': {'first': str(first), 'final': str(final),
                               'unicode': True, 'spaces': True,
                               'outside_workspace': not str(final).lower().startswith(
                                   str(os.environ.get('GITHUB_WORKSPACE', '')).lower())},
              'move': {'files': len(expected), 'changed': [], 'removed': removed, 'added': added,
                       'first_removed': not first.exists()},
              'self_test': {'command': selftest_command, 'exit_code': selftest_exit,
                            'checks': selftest['checks'], 'engine_version': selftest['engine_version'],
                            'elapsed_seconds': elapsed,
                            'report_sha256': sha256(report_path), 'image_sha256': sha256(image_path)},
              'compact': {'checks': compact['count'], 'accepted': compact['accepted'],
                          'report_sha256': sha256(compact_report_path),
                          'producer_source_field': compact['source_sha'],
                          'source_field_meaning': 'the run source recorded by the unchanged checker; the program source is the producer commit above',
                          'elapsed_seconds': elapsed_compact, 'screenshots': screenshots},
              'dependencies': manifest['dependencies']['entries'],
              'scans': {'private_paths': {'hits': path_hits, 'needles': len(needles)},
                        'test_secrets': {'hits': secret_scan}},
              'mutation': {'changed': mutated, 'added': added, 'removed': removed},
              'release_blockers': release_blockers, 'release_ready': not problems and not release_blockers,
              'network': {'server_started': 0, 'credentials_used': 0,
                          'isolation': 'not claimed: the run needed no network resource but no interface cut was performed'},
              'not_verified': ['default-OFF full host acceptance (tools/check_windows_host.py)',
                               'network interface isolation', 'real-device or screen-reader use',
                               'code signature or notarisation', 'release, tag or store publication'],
              'problems': problems}
    write_json(output / 'moved.json', result)
    print(json.dumps({'accepted': result['accepted'], 'compact_checks': compact['count'],
                      'self_test_checks': selftest['checks'], 'problems': problems}), flush=True)
    require(not problems, 'moved package checks refused: ' + json.dumps(problems))


if __name__ == '__main__':
    main()
