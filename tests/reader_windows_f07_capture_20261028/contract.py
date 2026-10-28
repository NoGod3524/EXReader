"""New Windows F07 raw-evidence capture contract; execution is Actions-only.

Capture completeness is not F07 dependency admission. The old F06 producer and
all existing product/test sources stay untouched.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import subprocess
import tempfile
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
SDK_BASE = '8357eafa28423a7ab93ba08b823af80f01ad1505'
REPO = 'NoGod3524/EXReader'
BRANCH = 'codex/reader-windows-f07-capture-20261028'
OWNED = 'tests/reader_windows_f07_capture_20261028/'
WORKFLOW = '.github/workflows/reader-windows-f07-capture-20261028.yml'
DOC = 'docs/reader-total-progress/reader-windows-f07-capture-20261028.md'
OUT = ROOT / 'build/reader-windows-f07-capture-20261028'
F06 = 'build/f06/'
BUILD = F06 + 'windows-build/'
STAGES = ('sdk-stage', 'product-stage', 'raw-stage')
MODULES = ('webdav', 'credentials', 'sideload', 'revisions', 'commands',
    'desktop-metadata', 'sync', 'session', 'reading-state', 'reading-commands',
    'annotation-view', 'search', 'navigation', 'cloud-import',
    'bulk-organization', 'preferences', 'txt-progress', 'annotation-export',
    'annotation-import', 'font-library', 'original-export', 'jump-history',
    'sync-status-view')
BUILDS = ('sdk-build', 'product-build', *('raw-' + n for n in MODULES), 'host')
PROGRAM = BUILD + 'host/EXReaderWave3.exe'
MAP = BUILD + 'host/windows-host.map'
PACKAGED = F06 + 'windows-payload/EXReader/EXReader.exe'
RELOCATED = F06 + 'unpacked-windows/EXReader/EXReader.exe'
RECIPE = 'tests/reader_f06_packages/build.py'
MAX_BYTES = 8 * 1024**3


def require(value, message):
    if not value:
        raise ValueError(message)


def actions_only(windows=False):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only')
    require(os.environ.get('GITHUB_REPOSITORY') == REPO, 'wrong repository')
    if windows:
        require(os.name == 'nt' and os.environ.get('RUNNER_OS') == 'Windows',
                'Windows Actions only')


def identity():
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'], sdk_version='3.42.0')


def same(record, expected):
    for key in ('source_sha', 'run_id', 'attempt'):
        require(record.get(key) == expected[key], 'cross-source/run/attempt: ' + key)


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def digest(stream):
    value = hashlib.sha256()
    size = 0
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(block)
        size += len(block)
    return dict(bytes=size, sha256=value.hexdigest())


def file_digest(path):
    with Path(path).open('rb') as stream:
        return digest(stream)


def guard():
    actions_only()
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH, 'dedicated branch only')
    require(re.fullmatch('[0-9a-f]{40}', os.environ['GITHUB_SHA']), 'full source SHA required')
    require(git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'checkout/source mismatch')
    git('merge-base', '--is-ancestor', BASE, 'HEAD')
    changes = git('diff', '--name-status', '--no-renames', BASE, 'HEAD').splitlines()
    require(changes, 'empty capture source')
    for line in changes:
        status, path = line.split('\t')
        require(status == 'A' and (path.startswith(OWNED) or path in (WORKFLOW, DOC)),
                'only newly added owned paths allowed: ' + line)
    require(not git('status', '--porcelain', '--untracked-files=no'), 'dirty tracked source')
    git('diff', '--exit-code', SDK_BASE, 'HEAD', '--', 'src', 'include', 'cmake',
        'CMakeLists.txt', 'bindings')
    recipes = (RECIPE, 'tests/reader_f06_packages/identity.py',
        'tests/reader_wave3_c09/build.py', 'tests/reader_windows_raw3/host_build.py',
        'tools/build_windows_host.py', 'apps/reader/desktop/windows_feature_integration.cmake',
        'CMakePresets.json')
    result = dict(identity(), base_sha=BASE, frozen_sdk_sha=SDK_BASE, changed_paths=changes,
        workspace=str(ROOT), recipes={p: file_digest(ROOT / p) for p in recipes},
        trees={p: git('rev-parse', 'HEAD:' + p) for p in ('src', 'include', 'cmake',
            'bindings', 'apps', 'examples', 'tools')}, passed=True)
    save(OUT / 'source.json', result)
    return result


def diagnostic_argv(argv):
    """No configure/compiler/linker change; keep only actual Ninja response files."""
    original = [str(v) for v in argv]
    actual = list(original)
    if actual[:2] == ['cmake', '--build']:
        require('--' not in actual, 'unexpected old native build arguments')
        if '--verbose' not in actual:
            actual.append('--verbose')
        actual.extend(['--', '-d', 'keeprsp'])
    return actual


def safe_members(archive):
    """Validate without extracting; reject parent, case and Unicode aliases."""
    files, directories, aliases, seen, size = set(), set(), {}, set(), 0
    for info in archive.infolist():
        name = info.filename[:-1] if info.is_dir() else info.filename
        parts = name.split('/')
        require(name and '\\' not in name and ':' not in name and
            not PurePosixPath(name).is_absolute() and
            all(p not in ('', '.', '..') for p in parts), 'unsafe ZIP path: ' + name)
        mode = (info.external_attr >> 16) & 0o170000
        require(mode in (0, stat.S_IFREG, stat.S_IFDIR) and
            (mode != stat.S_IFDIR or info.is_dir()) and
            (mode != stat.S_IFREG or not info.is_dir()), 'special ZIP file: ' + name)
        for count in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:count])
            key = unicodedata.normalize('NFC', prefix).casefold()
            require(key not in aliases or aliases[key] == prefix, 'ZIP path alias: ' + name)
            aliases[key] = prefix
            if count < len(parts):
                require(key not in files, 'ZIP file is a parent: ' + name)
                directories.add(key)
        require(key not in seen, 'duplicate ZIP entry: ' + name)
        seen.add(key)
        if info.is_dir():
            require(key not in files, 'ZIP directory overwrites file')
            directories.add(key)
        else:
            require(key not in directories, 'ZIP file overwrites directory')
            files.add(key)
        require(not (info.flag_bits & 1), 'encrypted ZIP entry')
        size += info.file_size
        require(0 <= info.file_size <= MAX_BYTES and size <= MAX_BYTES, 'ZIP size limit')
    return {i.filename: i for i in archive.infolist() if not i.is_dir()}


def verify_files(archive, inventory):
    members = safe_members(archive)
    require(set(members) == set(inventory), 'snapshot inventory/member mismatch')
    for name, expected in inventory.items():
        with archive.open(name) as stream:
            require(digest(stream) == expected, 'snapshot byte identity mismatch: ' + name)
    return members


def final_link(archive, members, workspace):
    text = archive.read('capture/ninja/host.commands.txt').decode('utf-8-sig')
    candidates = [line for line in text.splitlines() if 'EXReaderWave3' in line and
        ('vs_link_exe' in line or re.search(r'(?i)(?:^|[\\/\s"])link\.exe(?:[\s"]|$)', line))]
    require(len(candidates) == 1, 'missing/ambiguous actual final host link command')
    command = candidates[0]
    root = PureWindowsPath(workspace)
    host = root / BUILD / 'host'
    responses = set()

    def expand(value):
        output = [value]
        for match in re.finditer(r'@(?:"([^"]+)"|([^\s"&]+))', value):
            target = PureWindowsPath(match.group(1) or match.group(2))
            if not target.is_absolute():
                target = host / target
            relative = target.relative_to(root)
            require('..' not in relative.parts, 'final response file escapes source')
            name = relative.as_posix()
            require(name in members and name.endswith('.rsp'), 'referenced final response file missing: ' + name)
            require(name not in responses, 'repeated/cyclic response file reference')
            responses.add(name)
            raw = archive.read(name)
            output.append(expand(raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')))
        return '\n'.join(output)

    expanded = expand(command).replace('\\', '/').lower()
    require('exreaderwave3.exe' in expanded and 'windows-host.map' in expanded,
            'final linker does not bind captured EXE and existing map')
    for stage in STAGES:
        require('/' + stage + '/' in expanded, 'final link lacks actual installed prefix: ' + stage)
    return dict(final_link_command=command, final_response_files=sorted(responses),
        response_file_status='retained' if responses else 'not_used_by_final_link')


def validate_capture(archive, inventory, expected):
    """Recompute raw byte bindings; deliberately does not judge F07 symbols."""
    members = verify_files(archive, inventory)
    def read_json(name):
        require(name in members and members[name].file_size < 32 * 1024**2,
                'missing/oversized JSON: ' + name)
        return json.loads(archive.read(name))
    source = read_json('capture/source.json')
    same(source, expected)
    require(source['passed'] is True and source['base_sha'] == BASE and
            source['sdk_version'] == '3.42.0', 'source guard failed')
    journal = read_json('capture/commands.json')
    same(journal, expected)
    require(journal['commands'], 'missing exact command journal')
    for row in journal['commands']:
        require(row['completed'] is True and row['exit_code'] == 0 and
            row['actual'] == diagnostic_argv(row['original']), 'build command failed/changed')
    for label in BUILDS:
        selected = [r for r in journal['commands'] if r['original'][:2] == ['cmake', '--build']
            and PureWindowsPath(r['original'][2]) == PureWindowsPath(source['workspace']) / BUILD / label]
        require(len(selected) == 1, 'missing/duplicate actual build command: ' + label)
        if label == 'host':
            require(selected[0]['original'][3:] == ['--target', 'EXReaderWave3', '--parallel', '4'],
                    'final host build command changed')
        for filename in ('CMakeCache.txt', 'build.ninja', 'CMakeFiles/rules.ninja'):
            require(BUILD + label + '/' + filename in members, 'missing actual build graph: ' + label)
        require('capture/ninja/' + label + '.commands.txt' in members, 'missing Ninja commands: ' + label)
        if label == 'host':
            continue
        manifest = BUILD + label + '/install_manifest.txt'
        require(manifest in members, 'missing install manifest: ' + label)
        installs = archive.read(manifest).decode('utf-8-sig').splitlines()
        require(installs, 'empty install manifest: ' + label)
        stage = 'sdk-stage' if label == 'sdk-build' else 'product-stage' if label == 'product-build' else 'raw-stage'
        prefix = PureWindowsPath(source['workspace']) / BUILD / stage
        for installed in installs:
            relative = PureWindowsPath(installed).relative_to(prefix)
            require('..' not in relative.parts, 'install manifest escapes prefix')
            require(BUILD + stage + '/' + relative.as_posix() in members,
                    'installed file omitted: ' + installed)
    for stage in STAGES:
        names = [n for n in members if n.startswith(BUILD + stage + '/')]
        require(any(n.endswith('.lib') for n in names) and any(n.endswith('.h') for n in names)
            and any(n.endswith('.cmake') for n in names), 'incomplete installed tree: ' + stage)
    require(MAP in members and inventory[MAP]['bytes'] > 0, 'final link map missing')
    require(any(n.startswith(BUILD + 'host/') and n.endswith('.obj') for n in members), 'host objects missing')
    require(any(n.startswith(BUILD + 'host/') and n.endswith('.lib') for n in members), 'host libraries missing')
    require(any(n.startswith(BUILD + 'logs/') for n in members), 'original F06 build logs missing')
    link = final_link(archive, members, source['workspace'])
    for program in (PROGRAM, PACKAGED, RELOCATED):
        require(program in members and inventory[program] == inventory[PROGRAM], 'final program identity mismatch')
    result = read_json(F06 + 'windows/result.json')
    same(result, expected)
    require(result['passed'] is True and result['target'] == 'windows' and
        result['program_sha256'] == inventory[PROGRAM]['sha256'], 'F06 result/program mismatch')
    manifest = read_json(F06 + 'windows/manifest.json')
    require(manifest['source_sha'] == expected['source_sha'] and manifest['sdk_version'] == '3.42.0'
        and manifest['producer']['source_sha'] == expected['source_sha']
        and manifest['producer']['sdk_version'] == '3.42.0', 'F06 producer mismatch')
    require(manifest['provenance']['run_id'] == expected['run_id'] and
        manifest['provenance']['attempt'] == expected['attempt'], 'F06 manifest run/attempt mismatch')
    package_name = 'EXReader-windows-' + expected['source_sha'][:12] + '.zip'
    package_path = F06 + 'windows/' + package_name
    require(manifest['archive']['name'] == package_name and result['archive'] == manifest['archive']
        and inventory[package_path] == {k: manifest['archive'][k] for k in ('bytes', 'sha256')},
        'F06 nested archive mismatch')
    with tempfile.TemporaryFile() as stream:
        with archive.open(package_path) as nested:
            shutil.copyfileobj(nested, stream, 1024 * 1024)
        stream.seek(0)
        with zipfile.ZipFile(stream) as nested:
            nested_members = safe_members(nested)
            require(manifest['target'] == 'windows' and manifest['entry'] == 'EXReader/EXReader.exe',
                    'wrong F06 archive target/entry')
            inner = json.loads(nested.read('manifest.json'))
            require(inner == {k: v for k, v in manifest.items() if k != 'archive'},
                    'F06 inner/outer manifests differ')
            require(set(nested_members) == set(manifest['files']) | set(manifest['metadata_files']),
                    'F06 delivered file inventory differs')
            checksums = ''.join(row['sha256'] + '  ' + name + '\n'
                for name, row in sorted(manifest['files'].items())).encode('utf-8')
            require(nested.read('SHA256SUMS') == checksums and
                hashlib.sha256(checksums).hexdigest() == manifest['archive']['checksums_sha256'],
                'F06 actual checksum list differs')
            for name, row in manifest['files'].items():
                expected_file = {key: row[key] for key in ('bytes', 'sha256')}
                with nested.open(name) as payload:
                    require(digest(payload) == expected_file, 'F06 delivered file differs: ' + name)
                require(inventory[F06 + 'unpacked-windows/' + name] == expected_file,
                        'F06 unpacked file differs: ' + name)
            for name in manifest['metadata_files']:
                require(archive.read(F06 + 'unpacked-windows/' + name) == nested.read(name),
                        'F06 unpacked metadata differs: ' + name)
            with nested.open('EXReader/EXReader.exe') as program:
                require(digest(program) == inventory[PROGRAM], 'actual F06 archived executable mismatch')
    for filename, key in (('configuration.json', 'configuration_sha256'), ('entry.json', 'entry_report_sha256')):
        require(inventory[F06 + 'windows/' + filename]['sha256'] == result[key], 'F06 report hash mismatch')
    config = read_json(F06 + 'windows/configuration.json')
    same(config, expected)
    require(config['build_recipe_sha256'] == source['recipes'][RECIPE]['sha256'], 'old F06 recipe changed')
    entry = read_json(F06 + 'windows/entry.json')
    require(entry['passed'] is True and entry['source_sha'] == expected['source_sha'] and
        entry['sdk_version'] == '3.42.0' and entry['entry_sha256'] == inventory[PROGRAM]['sha256'],
        'relocated F06 entry mismatch')
    producer = read_json(F06 + 'windows-payload/build.json')
    require(producer['source_sha'] == expected['source_sha'] and producer['sdk_version'] == '3.42.0'
        and producer['files']['EXReader.exe'] == inventory[PROGRAM]['sha256']
        and inventory[F06 + 'windows-payload/build.json']['sha256'] == manifest['producer']['build_json_sha256'],
        'actual F06 payload producer mismatch')
    original = read_json(F06 + 'windows-payload/report.json')
    require(original['passed'] is True and original['checks'] >= 26, 'original F06 package checks failed')
    diagnostics = read_json('capture/diagnostics.json')
    same(diagnostics, expected)
    require(diagnostics['commands'] and all(r['exit_code'] == 0 for r in diagnostics['commands']),
            'raw native diagnostics failed')
    for row in diagnostics['commands']:
        require('capture/' + row['output'] in members, 'raw native diagnostic output missing')
        if 'subject' in row:
            require(inventory[row['subject']] == row['subject_identity'], 'diagnostic subject identity mismatch')
    return dict(link, program_sha256=inventory[PROGRAM]['sha256'], map_sha256=inventory[MAP]['sha256'],
        package=inventory[package_path], installed_prefixes=list(STAGES),
        response_files=[n for n in members if n.endswith('.rsp')],
        capture_complete=True, f06_identity_verified=True, f07_accepted=False,
        gaps=['SQLite/SDK provider and module-private-entry adjudication is not performed by this capture.',
              'This new Windows source/run does not repair the old six-platform F06 run.',
              'No other platform, full behavioral regression, physical-device or release admission.'])
