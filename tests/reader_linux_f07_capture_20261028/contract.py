"""Linux F07 closure capture contract; execution and artifact parsing: Actions only."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
REPO = 'NoGod3524/EXReader'
BRANCH = 'codex/reader-linux-f07-capture-20261028'
OWNED = 'tests/reader_linux_f07_capture_20261028/'
WORKFLOW = '.github/workflows/reader-linux-f07-capture-20261028.yml'
DOC = 'docs/reader-total-progress/reader-linux-f07-capture-20261028.md'
OUT = ROOT / 'build/linux-f07-capture'
SDK = 'build/reading-library/stage'
RAW = 'build/gtk-raw-wave3/raw-stage'
LEGACY = 'build/gtk-raw-wave3/legacy-stage'
HOST = 'build/gtk-raw-wave3/retained-host'
PROGRAM = HOST + '/gtk-host/exreader-linux'
MAP = HOST + '/gtk-account-host.map'
PAYLOAD = 'build/gtk-raw-wave3/retained-package'
ENTRY = 'EXReader-Linux/bin/exreader-linux'
F06 = 'build/f06/linux'
UNPACK = 'build/f06/unpacked-linux'
PREFIXES = (SDK, RAW, LEGACY)
REQUIRED = (PROGRAM, MAP, HOST + '/build.ninja', HOST + '/CMakeFiles/rules.ninja',
    HOST + '/CMakeCache.txt', HOST + '/gtk-host/libexreader-linux-reading.a',
    PAYLOAD + '/' + ENTRY, PAYLOAD + '/build.json', PAYLOAD + '/EXReader-Linux.tar.gz',
    UNPACK + '/' + ENTRY, F06 + '/result.json', F06 + '/manifest.json',
    F06 + '/configuration.json', F06 + '/unpack.json', F06 + '/entry.json',
    'build/gtk-sdk342/build.json', 'build/gtk-raw-wave3/raw-install.json',
    'build/gtk-raw-wave3/legacy-install.json', 'build/gtk-raw-wave3/result.json',
    'build/gtk-navigation-ui/result.json', 'build/gtk-batch-ui/report.json')


def require(value, message):
    if not value:
        raise ValueError(message)


def actions_only():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only')
    require(os.environ.get('GITHUB_REPOSITORY') == REPO, 'wrong repository')


def identity():
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'], base_sha=BASE, target='linux', sdk_version='3.42.0')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def command(*args, cwd=ROOT):
    return subprocess.check_output(list(map(str, args)), cwd=cwd, text=True, stderr=subprocess.STDOUT)


def guard():
    actions_only()
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH, 'dedicated branch only')
    require(command('git', 'rev-parse', 'HEAD').strip() == os.environ['GITHUB_SHA'], 'checkout identity')
    command('git', 'merge-base', '--is-ancestor', BASE, 'HEAD')
    changes = command('git', 'diff', '--name-status', BASE, 'HEAD').splitlines()
    require(changes, 'no owned source changes')
    for line in changes:
        status, path = line.split('\t')
        require(status == 'A' and (path.startswith(OWNED) or path in (WORKFLOW, DOC)),
                'only new owned files allowed: ' + line)
    require(not command('git', 'status', '--porcelain', '--untracked-files=no').strip(), 'tracked source dirty')
    return dict(identity(), changed=changes, frozen_producer='tests/gtk_sdk342_package/run.py',
        producer_blob=command('git', 'rev-parse', 'HEAD:tests/gtk_sdk342_package/run.py').strip(),
        source_scope_passed=True)


def safe_name(name):
    parts = name.split('/')
    require(name and not PurePosixPath(name).is_absolute() and '\\' not in name and ':' not in name
            and all(p not in ('', '.', '..') for p in parts), 'unsafe path: ' + name)
    return parts


def safe_members(bundle):
    files, directories, aliases, seen, size = set(), set(), {}, set(), 0
    for info in bundle.infolist():
        name = info.filename[:-1] if info.is_dir() else info.filename
        parts = safe_name(name)
        mode = (info.external_attr >> 16) & 0o170000
        require(mode in (0, stat.S_IFREG, stat.S_IFDIR), 'special archive member')
        require(mode != stat.S_IFDIR or info.is_dir(), 'directory mode mismatch')
        require(mode != stat.S_IFREG or not info.is_dir(), 'file mode mismatch')
        for index in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:index]); key = unicodedata.normalize('NFC', prefix).casefold()
            require(key not in aliases or aliases[key] == prefix, 'case/Unicode path alias')
            aliases[key] = prefix
            if index < len(parts):
                require(key not in files, 'file parent collision')
                directories.add(key)
        require(key not in seen, 'duplicate member'); seen.add(key)
        if info.is_dir():
            require(key not in files, 'file/directory collision'); directories.add(key)
        else:
            require(key not in directories, 'directory/file collision'); files.add(key)
        size += info.file_size
        require(not (info.flag_bits & 1) and info.file_size <= 2 * 1024**3 and size <= 8 * 1024**3,
                'encrypted or excessive archive')
    return bundle.infolist()


def extract(raw, destination):
    destination = Path(destination)
    require(not destination.exists(), 'fresh extraction required')
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        members = safe_members(bundle)
        destination.mkdir(parents=True)
        for info in members:
            if info.is_dir():
                continue
            path = destination / info.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bundle.read(info))
    return destination


def project_loads(text, workspace):
    """Resolve actual GNU ld LOAD paths relative to the final retained-host cwd."""
    workspace = Path(workspace)
    root = str(workspace) + '/'
    loads = re.findall(r'^LOAD (.+)$', text, re.M)
    require(loads, 'final map has no LOAD records')
    selected, system = [], []
    for name in loads:
        path = Path(name)
        if not path.is_absolute():
            path = workspace / HOST / path
        normalized = Path(os.path.normpath(path))
        if str(normalized).startswith(root):
            relative = normalized.relative_to(workspace).as_posix(); safe_name(relative)
            require(relative.startswith((SDK + '/', RAW + '/', HOST + '/')), 'unexpected project link input: ' + relative)
            selected.append(relative)
        else:
            require(str(normalized).startswith(('/usr/lib/', '/lib/', '/usr/lib64/', '/lib64/')), 'unowned link input: ' + str(normalized))
            system.append(str(normalized))
    require(any(p.startswith(SDK + '/') for p in selected), 'no installed SDK in final map')
    require(any(p.startswith(RAW + '/') for p in selected), 'no installed product/modules in final map')
    require(HOST + '/gtk-host/libexreader-linux-reading.a' in selected, 'missing actual host archive')
    return dict(project=sorted(set(selected)), system=sorted(set(system)))


def verify_files(folder, manifest):
    expected = manifest['files']
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    require(actual == set(expected) | {'inventory.json'}, 'capture inventory set mismatch')
    for name, item in expected.items():
        safe_name(name); path = folder / name
        require(path.stat().st_size == item['bytes'] and digest(path) == item['sha256'], 'captured bytes changed: ' + name)
    for path in REQUIRED:
        require(path in expected and expected[path]['bytes'] > 0, 'required final evidence absent: ' + path)
    for prefix in PREFIXES:
        require(any(p.startswith(prefix + '/include/') for p in expected), 'public headers absent: ' + prefix)
        require(any(p.startswith(prefix + '/lib/') and p.endswith('.a') for p in expected), 'installed archives absent: ' + prefix)
        require(any(p.startswith(prefix + '/lib/cmake/') and p.endswith('.cmake') for p in expected), 'installed exports absent: ' + prefix)
    return True


def verify_package(folder):
    """Recompute final host -> producer tar -> F06 ZIP -> unpacked entry identity."""
    import tarfile
    def read(name):
        return json.loads((folder / name).read_text())
    result, manifest = read(F06 + '/result.json'), read(F06 + '/manifest.json')
    configuration = read(F06 + '/configuration.json')
    entry, unpack = read(F06 + '/entry.json'), read(F06 + '/unpack.json')
    producer, build = read(PAYLOAD + '/build.json'), read('build/gtk-sdk342/build.json')
    for record in (result, configuration, build):
        for key in ('source_sha', 'run_id', 'attempt'):
            require(record[key] == identity()[key], 'F06/build identity mismatch: ' + key)
    require(result['target'] == 'linux' and result['passed'] is True and build['passed'] is True, 'producer/F06 result failed')
    require(manifest['source_sha'] == identity()['source_sha'] and manifest['sdk_version'] == '3.42.0'
            and manifest['target'] == 'linux' and manifest['entry'] == ENTRY, 'manifest source/SDK/target')
    require(manifest['provenance']['run_id'] == identity()['run_id'] and manifest['provenance']['attempt'] == identity()['attempt'], 'manifest run/attempt')
    require(producer['source_sha'] == identity()['source_sha'] and producer['sdk_version'] == '3.42.0', 'producer source/SDK')
    require(configuration['producer'] == producer and manifest['producer']['source_sha'] == identity()['source_sha']
            and manifest['producer']['sdk_version'] == '3.42.0'
            and manifest['producer']['build_json_sha256'] == digest(folder / PAYLOAD / 'build.json'), 'configuration/manifest producer mismatch')
    require(configuration['build_recipe_sha256'] == digest(ROOT / 'tests/reader_f06_packages/build.py'), 'unchanged original F06 recipe mismatch')
    require(entry['passed'] is True and entry['source_sha'] == identity()['source_sha'] and entry['sdk_version'] == '3.42.0', 'relocated entry report')
    require(unpack['inner_matches_outer'] is True and unpack['source_sha'] == identity()['source_sha']
            and unpack['sdk_version'] == '3.42.0' and unpack['entry'] == ENTRY, 'unpack report identity')
    require(digest(folder / (F06 + '/entry.json')) == result['entry_report_sha256'], 'entry report hash')
    require(digest(folder / (F06 + '/configuration.json')) == result['configuration_sha256'], 'configuration hash')
    program = digest(folder / PROGRAM)
    for path in (PAYLOAD + '/' + ENTRY, UNPACK + '/' + ENTRY):
        require(digest(folder / path) == program, 'final host byte mismatch: ' + path)
    require(program == result['program_sha256'] == build['program_sha256'] == entry['entry_sha256'] == unpack['entry_sha256']
            == producer['files']['bin/exreader-linux'], 'final program manifest mismatch')
    archive = manifest['archive']; safe_name(archive['name'])
    require('/' not in archive['name'] and result['archive'] == archive, 'F06 archive identity')
    archive_path = folder / F06 / archive['name']
    require(archive_path.stat().st_size == archive['bytes'] and digest(archive_path) == archive['sha256'], 'F06 archive bytes')
    require(unpack['archive']['name'] == archive['name'] and unpack['archive']['bytes'] == archive['bytes']
            and unpack['archive']['sha256'] == archive['sha256'] and unpack['checksums_checked'] == len(manifest['files']), 'unpack archive/count mismatch')
    with zipfile.ZipFile(archive_path) as bundle:
        safe_members(bundle)
        require(sha(bundle.read(ENTRY)) == program, 'F06 nested native image mismatch')
        inner = json.loads(bundle.read('manifest.json'))
        require({k: v for k, v in inner.items() if k != 'archive'} == {k: v for k, v in manifest.items() if k != 'archive'}, 'inner/outer F06 metadata')
        require(set(bundle.namelist()) == set(manifest['files']) | set(manifest['metadata_files']), 'F06 archive file set')
        checksum_bytes = bundle.read('SHA256SUMS')
        expected_sums = ''.join(record['sha256'] + '  ' + name + '\n' for name, record in sorted(manifest['files'].items())).encode('utf-8')
        require(checksum_bytes == expected_sums and sha(checksum_bytes) == archive['checksums_sha256'], 'F06 actual checksum list mismatch')
        require((folder / UNPACK / 'manifest.json').read_bytes() == bundle.read('manifest.json')
                and (folder / UNPACK / 'SHA256SUMS').read_bytes() == checksum_bytes, 'unpacked metadata mismatch')
        require(unpack['digests'] == {name: row['sha256'] for name, row in manifest['files'].items()}, 'unpack digest report mismatch')
        for name, record in manifest['files'].items():
            data = bundle.read(name)
            require(len(data) == record['bytes'] and sha(data) == record['sha256'], 'F06 delivered file changed: ' + name)
            require(digest(folder / UNPACK / name) == record['sha256'], 'unpacked delivered file changed: ' + name)
    # The original producer tar predates F06's Start-EXReader.sh addition. Authenticate
    # its complete original build.json file set, not a regenerated tar or launcher.
    with tarfile.open(folder / PAYLOAD / 'EXReader-Linux.tar.gz', 'r:gz') as bundle:
        seen, files, total = set(), {}, 0
        for info in bundle.getmembers():
            if info.name in ('.', './') and info.isdir():
                continue
            name = info.name.removeprefix('./'); safe_name(name)
            require(name not in seen and (info.isfile() or info.isdir()), 'duplicate/special raw tar member')
            seen.add(name); total += info.size
            require(info.size <= 2 * 1024**3 and total <= 8 * 1024**3, 'raw tar size limit')
            if info.isfile():
                data = bundle.extractfile(info).read(); files[name] = sha(data)
        require(files == producer['files'], 'original raw tar differs from producer manifest')
        require(files['bin/exreader-linux'] == program, 'raw tar final program mismatch')
    installed = build['installed_sha256']
    for name, expected in installed.items():
        safe_name(name)
        require(name.startswith(tuple(p + '/' for p in PREFIXES)), 'unexpected installed manifest prefix')
        require(digest(folder / name) == expected, 'actual installed package drift: ' + name)
    for prefix in PREFIXES:
        actual = {p.relative_to(folder).as_posix() for p in (folder / prefix).rglob('*') if p.is_file()}
        require(actual == {p for p in installed if p.startswith(prefix + '/')}, 'installed prefix file set drift: ' + prefix)
    for name in ('raw-install.json', 'legacy-install.json', 'result.json'):
        require(read('build/gtk-raw-wave3/' + name)['accepted'] is True, 'original raw/legacy gate failed: ' + name)
    raw = read('build/gtk-raw-wave3/result.json')
    navigation = read('build/gtk-navigation-ui/result.json')
    batch = read('build/gtk-batch-ui/report.json')
    # Preserve the original gtk_sdk342_package/authenticate.py gate semantics;
    # only its older branch-scope source guard is replaced by additions-only BASE.
    require(raw['source'] == identity()['source_sha'] and raw['legacy_host']['configured_and_linked'] is True, 'original raw/legacy source/link gate')
    require(navigation['navigation_scope_passed'] is True, 'original navigation GUI gate')
    require(batch['batch_import_scope_passed'] is True and batch['checks_failed'] == 0
            and batch['source_sha'] == identity()['source_sha'] and batch['program_sha256'] == program, 'original folder GUI identity/gate')
    return dict(program_sha256=program, archive=archive, same_source_run_attempt=True,
                raw_tar_sha256=digest(folder / PAYLOAD / 'EXReader-Linux.tar.gz'))
