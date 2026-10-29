"""Actions-only F12 delivery/licence handoff inspection.

Read-only: it parses source, packaging scripts and the registered licence manifest,
and downloads + opens already-published Actions artifacts. It builds nothing and
never judges legal compliance; it reports which licence materials are present in
which delivery archive, and which are not.

  guard                      source identity and path allow-list
  source                     source-declared switches, packaging copies, docs links
  artifacts RUN ATTEMPT      inspect the six f06-<target>-RUN-ATTEMPT artifacts
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import safezip  # noqa: E402
OUT = ROOT / 'build/reader-delivery-handoff'
BASE = 'bd28d4946f17a184dd3cd47a584cf49fce34e973'
TARGETS = ('windows', 'linux', 'macos', 'android', 'iphone', 'ipad')
REPO = os.environ.get('GITHUB_REPOSITORY', 'NoGod3524/EXReader')
ALLOWED_PREFIXES = ('docs/reader-delivery-handoff/', 'tests/reader_delivery_manifest_handoff/')
ALLOWED_FILES = {'.github/workflows/reader-delivery-manifest-handoff.yml',
                '.github/workflows/reader-delivery-android-sdk342-licenses.yml'}
PROTECTED = ('src', 'include', 'cmake', 'CMakeLists.txt', 'CMakePresets.json', 'LICENSE',
             'THIRD_PARTY_NOTICES.md', 'licenses', 'apps', 'examples', 'bindings', 'tools')
# Paths whose change makes an older package say nothing about the current source.
PACKAGING_RELEVANT = ('src/', 'include/', 'cmake/', 'CMakeLists.txt', 'CMakePresets.json', 'LICENSE',
                      'THIRD_PARTY_NOTICES.md', 'licenses/', 'apps/', 'examples/', 'bindings/', 'tools/',
                      'extras/')
REQUIRED_DOCS = ('README.md', 'USER-GUIDE.md', 'LICENSE-DEPENDENCY-MATRIX.md')
ROOT_MATERIAL = {'LICENSE', 'LICENSE.txt', 'EXReader-LICENSE.txt', 'THIRD_PARTY_NOTICES.md'}
LICENSE_PREFIX = 'share/exreader/licenses/'
DIR_RE = re.compile(r'(?:^|/)licenses/(.+)$')


def run(*args):
    return subprocess.check_output([str(a) for a in args], cwd=ROOT, text=True, stderr=subprocess.STDOUT)


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def summary_line(text):
    print(text, flush=True)
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path, 'a', encoding='utf-8') as stream:
            stream.write(text + '\n')


def guard():
    head = run('git', 'rev-parse', 'HEAD').strip()
    assert head == os.environ['GITHUB_SHA'], (head, os.environ['GITHUB_SHA'])
    run('git', 'merge-base', '--is-ancestor', BASE, 'HEAD')
    changed = run('git', 'diff', '--name-only', BASE, 'HEAD').splitlines()
    outside = [p for p in changed if p not in ALLOWED_FILES and not p.startswith(ALLOWED_PREFIXES)]
    # A packaging patch must be declared in docs/reader-delivery-handoff/PACKAGING-PATCH.md and here.
    declared = declared_patches()
    unexpected = [p for p in outside if p not in declared]
    assert not unexpected, unexpected
    run('git', 'diff', '--exit-code', BASE, 'HEAD', '--', *PROTECTED)
    save('guard.json', dict(source_sha=head, base=BASE, changed=changed, declared_packaging_patch=sorted(declared),
                            run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'], passed=True))


def declared_patches():
    path = ROOT / 'docs/reader-delivery-handoff/PACKAGING-PATCH.md'
    if not path.is_file():
        return set()
    return set(re.findall(r'^- `([^`]+)`', path.read_text(encoding='utf-8'), re.M))


def registry():
    spec = importlib.util.spec_from_file_location('reading_licenses', ROOT / 'tools/check_reading_licenses.py')
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / 'tools'))
    spec.loader.exec_module(module)
    return module


def normal(value):
    if isinstance(value, dict):
        value = value.get('value')
    return 'ON' if str(value).upper() in ('ON', 'TRUE', '1', 'YES', 'Y') else 'OFF'


def option_defaults():
    text = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    return {m.group(1): m.group(2) for m in re.finditer(r'^option\((EXR_\w+)\s+"[^"]*"\s+(ON|OFF)\)', text, re.M)}


def preset_switches(name):
    presets = {p['name']: p for p in json.loads((ROOT / 'CMakePresets.json').read_text(encoding='utf-8'))['configurePresets']}

    def walk(item):
        out = {}
        parents = presets[item].get('inherits', [])
        for parent in ([parents] if isinstance(parents, str) else parents):
            out.update(walk(parent))
        out.update(presets[item].get('cacheVariables', {}))
        return out
    return {k: normal(v) for k, v in walk(name).items() if k.startswith('EXR_')}


def flags(text):
    return {m.group(1): m.group(2) for m in re.finditer(r'-D(EXR_\w+)=(ON|OFF)', text)}


def function_body(text, name, following):
    match = re.search(r'^def ' + name + r'\(.*?(?=^def ' + following + r'|\Z)', text, re.M | re.S)
    assert match, name
    return match.group(0)


def declared_switches():
    """Switches the build script/preset declares for each target's SDK; unlisted ones use CMakeLists defaults."""
    defaults = option_defaults()
    build = (ROOT / 'tests/reader_f06_packages/build.py').read_text(encoding='utf-8')
    android = (ROOT / '.github/workflows/android-composition-candidate.yml').read_text(encoding='utf-8')
    apple = flags(function_body(build, 'apple', 'android'))
    library = preset_switches('reading-library')
    declared = {'windows': ('preset reading-library (tests/reader_f06_packages/build.py windows)', library),
                'linux': ('preset reading-library (tests/reader_gtk_raw_wave3/run.py)', library),
                'macos': ('flags in tests/reader_f06_packages/build.py apple()', apple),
                'iphone': ('flags in tests/reader_f06_packages/build.py apple()', apple),
                'ipad': ('iPhone payload repackaged (tests/reader_f06_packages/identity.py)', apple),
                'android': ('flags in .github/workflows/android-composition-candidate.yml',
                            flags(android.split('cmake -S . -B "$ws/sdk"', 1)[1].split('--target install', 1)[0]))}
    out = {}
    for target, (origin, values) in declared.items():
        merged = dict(defaults)
        merged.update(values)
        out[target] = dict(origin=origin, explicit=values, switches=merged)
    return out


def expected_materials(module, switches):
    """Registered upstream/third-party licence files that the build enables, relative to licenses/."""
    expected = {}
    for component in module.COMPONENTS:
        if component['id'] == 'exreader' or not module.enabled(component['when'], switches):
            continue
        for item in component['files']:
            if item.get('when') and not module.enabled(item['when'], switches):
                continue
            if item['installed'].startswith(LICENSE_PREFIX):
                expected[item['installed'][len(LICENSE_PREFIX):]] = component['id']
    return expected


def packaging_copies():
    files = {'windows': ['tools/build_windows_host.py'], 'linux': ['tools/build_linux_host.py'],
             'macos': ['tools/build_apple_host.py'], 'iphone': ['tools/build_apple_host.py'],
             'ipad': ['tools/build_apple_host.py'],
             'android': ['tests/android_sdk342_package/run.py']}
    out = {}
    for target, paths in files.items():
        entry = {}
        for path in paths:
            text = (ROOT / path).read_text(encoding='utf-8')
            if path.endswith('build.py'):
                text = function_body(text, 'android', 'zzz-none')
            entry[path] = dict(license='LICENSE' in text, notices='THIRD_PARTY_NOTICES.md' in text,
                               licenses_directory='share/exreader/licenses' in text)
        out[target] = entry
    return out


def link_problems():
    problems = []
    for name in REQUIRED_DOCS:
        path = ROOT / 'docs/reader-delivery-handoff' / name
        if not path.is_file() or path.stat().st_size == 0:
            problems.append('missing or empty ' + name)
            continue
        for target in re.findall(r'\]\(([^)#\s]+)(?:#[^)]*)?\)', path.read_text(encoding='utf-8')):
            if re.match(r'[a-z]+:', target):
                continue
            if not (path.parent / target).resolve().exists():
                problems.append(name + ' -> ' + target)
    return problems


def source():
    module = registry()
    declared = declared_switches()
    copies = packaging_copies()
    notices = (ROOT / 'THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8')
    components = []
    for component in module.COMPONENTS:
        marker = component.get('notice_marker')
        components.append(dict(id=component['id'], name=component['name'], version=component['version'],
                               license=component['license'], when=component['when'],
                               notice_marker_present=(marker in notices) if marker else None,
                               enabled={t: module.enabled(component['when'], d['switches']) for t, d in declared.items()}))
    repo_licenses = {p.name: p.stat().st_size for p in sorted((ROOT / 'licenses').iterdir()) if p.is_file()}
    expected = {t: expected_materials(module, d['switches']) for t, d in declared.items()}
    aac = sorted(str(p.relative_to(ROOT)) for p in list((ROOT / 'tools').glob('build_*.py')) +
                 list((ROOT / 'tests').glob('reader_f06_packages/*.py')) + list((ROOT / 'tests').glob('*_sdk342_package/*.py')) +
                 list((ROOT / '.github/workflows').glob('*sdk342*.yml')) + list((ROOT / '.github/workflows').glob('reader-f06*.yml'))
                 if 'EXR_ENABLE_AAC=ON' in p.read_text(encoding='utf-8', errors='replace'))
    data = dict(source_sha=os.environ['GITHUB_SHA'], declared=declared, expected_licence_files=expected,
                packaging_copies=copies, components=components, repository_licence_files=repo_licenses,
                empty_repository_licence_files=[n for n, s in repo_licenses.items() if s == 0],
                aac_default=option_defaults().get('EXR_ENABLE_AAC'), preset_aac=preset_switches('reading-library').get('EXR_ENABLE_AAC'),
                scripts_enabling_aac=aac, doc_problems=link_problems(),
                licence_sha256=sha256_file(ROOT / 'LICENSE'), notices_sha256=sha256_file(ROOT / 'THIRD_PARTY_NOTICES.md'))
    problems = list(data['doc_problems']) + ['empty licence file ' + n for n in data['empty_repository_licence_files']]
    problems += ['%s: %s does not copy %s' % (t, p, k) for t, files in copies.items() for p, v in files.items()
                 for k in ('license', 'notices', 'licenses_directory') if not v[k]]
    problems += ['notice marker absent for ' + c['id'] for c in components if c['notice_marker_present'] is False]
    data['problems'] = problems
    save('source.json', data)
    summary_line('### Source-declared licence expectations (source `' + os.environ['GITHUB_SHA'][:12] + '`)')
    for target in TARGETS:
        summary_line('- ' + target + ': ' + str(len(expected[target])) + ' registered licence files expected; packaging copies `' +
                     json.dumps(copies[target], sort_keys=True) + '`')
    summary_line('- AAC (FAAD2) default `' + str(data['aac_default']) + '`, reading-library preset `' + str(data['preset_aac']) +
                 '`, scripts enabling it: ' + (', '.join(aac) or 'none'))
    assert not problems, problems


def api(path):
    return json.loads(run('gh', 'api', path))


def download(artifact, folder):
    archive = folder.with_suffix('.zip')
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open('wb') as stream:
        subprocess.run(['gh', 'api', 'repos/' + REPO + '/actions/artifacts/' + str(artifact['id']) + '/zip'],
                       cwd=ROOT, stdout=stream, check=True)
    digest = sha256_file(archive)
    assert artifact.get('digest') == 'sha256:' + digest, ('digest absent or different', artifact['name'], artifact.get('digest'), digest)
    assert artifact.get('size_in_bytes') == archive.stat().st_size, ('size differs', artifact['name'])
    # Strict member validation (duplicates, absolute, parent, backslash, symlink); no extractall.
    outer = safezip.extract(archive, folder, artifact['name'])
    return digest, outer


def cache_switches(configuration):
    caches = []
    for path, entry in configuration.get('cmake', {}).items():
        values = {}
        for line in entry.get('entries', []):
            match = re.match(r'(EXR_\w+):\w+=(.*)$', line)
            if match:
                values[match.group(1)] = normal(match.group(2))
        if 'EXR_ENABLE_PDF' in values and 'EXR_ENABLE_AUDIO' in values:
            caches.append((path, values))
    return caches


def inspect_target(target, run_id, attempt, records, expected_head, module, declared):
    name = 'f06-' + target + '-' + run_id + '-' + attempt
    matches = [a for a in records if a['name'] == name and not a['expired']]
    assert len(matches) == 1, 'missing or duplicate artifact ' + name
    artifact = matches[0]
    assert isinstance(artifact['id'], int) and artifact['workflow_run']['id'] == int(run_id), (name, artifact['workflow_run'])
    assert artifact['workflow_run']['head_sha'] == expected_head, (name, artifact['workflow_run']['head_sha'])
    folder = ROOT / 'inspect' / name
    zip_digest, outer = download(artifact, folder)
    for required in ('manifest.json', 'result.json', 'configuration.json', 'entry.json'):
        assert required in outer, (name, 'missing ' + required)
    manifest = json.loads(outer['manifest.json'].decode('utf-8'))
    result = json.loads(outer['result.json'].decode('utf-8'))
    configuration = json.loads(outer['configuration.json'].decode('utf-8'))
    assert manifest['source_sha'] == expected_head and result['passed'] is True and manifest['target'] == target
    assert manifest['provenance']['run_id'] == run_id and manifest['provenance']['attempt'] == attempt
    for label, record in (('result', result), ('configuration', configuration)):
        assert (record['source_sha'], record['run_id'], record['attempt']) == (expected_head, run_id, attempt), label
    assert result['target'] == target and configuration['target'] == target
    archive_name = manifest['archive']['name']
    assert '/' not in archive_name and archive_name in outer, 'archive named by the manifest is not in the artifact'
    archive_path = folder / archive_name
    assert sha256_file(archive_path) == manifest['archive']['sha256'] == result['archive']['sha256'], 'archive digest differs'
    assert archive_path.stat().st_size == manifest['archive']['bytes'], 'archive size differs from manifest'
    contents = safezip.read_members(archive_path, archive_name)
    members = {n: dict(bytes=len(d), sha256=sha256(d)) for n, d in contents.items()}
    # Closed set: archive members == manifest files + the manifest's own metadata files, nothing else.
    closed = set(manifest['files']) | set(manifest['metadata_files'])
    assert set(members) == closed, ('member set differs from manifest', sorted(set(members) ^ closed))
    mismatched = [n for n, r in manifest['files'].items()
                  if members[n]['sha256'] != r['sha256'] or members[n]['bytes'] != r['bytes']]
    assert not mismatched, mismatched
    inner = json.loads(contents['manifest.json'].decode('utf-8'))
    assert inner == {k: v for k, v in manifest.items() if k != 'archive'}, 'inner manifest differs from artifact manifest'
    expected_sums = ''.join(r['sha256'] + '  ' + n + '\n' for n, r in sorted(manifest['files'].items()))
    assert contents['SHA256SUMS'].decode('utf-8') == expected_sums, 'SHA256SUMS differs from manifest'
    apk_entries = []
    for n in sorted(n for n in members if n.endswith('.apk')):
        with zipfile.ZipFile(io.BytesIO(contents[n])) as apk:
            apk_entries += [n + '!' + e for e in apk.namelist()
                            if re.search(r'licen[cs]e|notice|copying|OFL|patents', e, re.I) or e.startswith('assets/')]
    found = {}
    for n in members:
        match = DIR_RE.search(n)
        if match:
            found[match.group(1)] = n
    root_material = sorted(n for n in members if n.rsplit('/', 1)[-1] in ROOT_MATERIAL and not DIR_RE.search(n))
    caches = cache_switches(configuration)
    union = {}
    for _, values in caches:
        for key, value in values.items():
            union[key] = 'ON' if 'ON' in (union.get(key), value) else 'OFF'
    actual = dict(declared[target]['switches'])
    actual.update(union)
    expected = expected_materials(module, actual)
    declared_expected = expected_materials(module, declared[target]['switches'])
    missing = sorted(set(expected) - set(found))
    extra = sorted(set(found) - set(expected))
    return dict(artifact=name, artifact_id=artifact['id'], artifact_bytes=artifact['size_in_bytes'], artifact_digest=artifact.get('digest'),
                downloaded_sha256=zip_digest, archive=manifest['archive'], source_sha=manifest['source_sha'], sdk_version=manifest['sdk_version'],
                member_count=len(members), files_verified=len(manifest['files']), root_material=root_material,
                licence_files_in_archive=len(found), cmake_caches=[p for p, _ in caches],
                switch_source='archive CMakeCache entries' if caches else 'source-declared only (no SDK CMakeCache recorded)',
                aac_enabled_in_archive_build=actual.get('EXR_ENABLE_AAC'), faad2_in_archive=any(k.startswith('faad2/') for k in found),
                mp3_enabled=actual.get('EXR_ENABLE_MP3') == 'ON' and actual.get('EXR_ENABLE_AUDIO') == 'ON',
                expected_count=len(expected), missing=missing, unexpected=extra,
                declared_vs_cache_differs=sorted(set(expected) ^ set(declared_expected)),
                apk_entries=apk_entries, ofl_font_files=sorted(n for n in members if n.endswith(('OFL.txt', 'Noto-OFL.txt', 'Reader.otf'))))


def artifacts(run_id, attempt):
    module = registry()
    declared = declared_switches()
    workflow = api('repos/' + REPO + '/actions/runs/' + run_id)
    expected_head = workflow['head_sha']
    records = api('repos/' + REPO + '/actions/runs/' + run_id + '/artifacts?per_page=100')['artifacts']
    current = os.environ['GITHUB_SHA']
    changed = run('git', 'diff', '--name-only', expected_head, current).splitlines()
    relevant = [p for p in changed if p.startswith(PACKAGING_RELEVANT) or p in PACKAGING_RELEVANT]
    report = dict(inspected_run=run_id, inspected_attempt=attempt, inspected_workflow=workflow['name'], inspected_head_sha=expected_head,
                  current_source_sha=current, packaging_relevant_changes_since_inspected=relevant,
                  verdict_for_current_source=('NOT EVIDENCE: packaged source differs from current source' if relevant
                                              else 'packaging inputs unchanged since inspected source'),
                  targets={}, gaps={})
    for target in TARGETS:
        report['targets'][target] = inspect_target(target, run_id, attempt, records, expected_head, module, declared)
        gap = report['targets'][target]
        if gap['missing'] or not gap['root_material']:
            report['gaps'][target] = dict(missing=gap['missing'], root_material=gap['root_material'])
    save('artifacts.json', report)
    summary_line('### Inspected run ' + run_id + '/' + attempt + ' (' + workflow['name'] + '), packaged source `' + expected_head[:12] + '`')
    summary_line('Current source `' + current[:12] + '`; packaging-relevant paths changed since: ' + str(len(relevant)) + ' -> ' + report['verdict_for_current_source'])
    summary_line('| target | archive bytes | files verified | licence files | expected | missing | root material | FAAD2 packaged |')
    summary_line('| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |')
    for target in TARGETS:
        t = report['targets'][target]
        summary_line('| %s | %d | %d | %d | %d | %d | %s | %s |' % (target, t['archive']['bytes'], t['files_verified'], t['licence_files_in_archive'],
                                                                   t['expected_count'], len(t['missing']), ', '.join(t['root_material']) or 'none',
                                                                   t['faad2_in_archive']))
    summary_line('Licence gaps: ' + (', '.join(sorted(report['gaps'])) or 'none'))
    if report['gaps'] and os.environ.get('REQUIRE_COMPLETE') == 'true':
        raise SystemExit('licence material gaps: ' + ', '.join(sorted(report['gaps'])))


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    operation = sys.argv[1]
    if operation == 'guard':
        guard()
    elif operation == 'source':
        source()
    elif operation == 'artifacts':
        artifacts(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit('unknown operation ' + operation)
