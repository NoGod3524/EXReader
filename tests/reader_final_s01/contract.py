#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pure verification primitives for the S01 portable Windows candidate package.

Nothing in this module builds, installs, downloads or launches anything. Every
function takes bytes or text that a GitHub Actions job produced and decides
whether the claim is proven by those bytes. The archive generator, the moved
package consumer and the refusal self-tests all share these functions, so a
claim cannot be restated in one place and checked differently elsewhere.

Source roles are kept apart on purpose:

* producer source  = eab342ef456be4a8a1811e5249e3c217d906ce8a (the fixed actual
  Windows compact producer, whose own program hash is published in
  docs/READER-WINDOWS-COMPACT.md at seal f355525b74ae261db536c56200e46643919ef323);
* SDK source       = the approved 3.41 SDK tree (approved commit edddc463)
  whose src/include trees are asserted byte identical to the producer checkout;
* implementation source = the codex/reader-fw-s01 branch head that carries this
  verifier, its workflow and its documentation.

The G09 distribution inventory (tests/reader_distribution_inventory/contract.py)
stays the single source of truth for private-path scans, test-secret scans and
registered license material; this module consumes it instead of restating it.
"""
import hashlib
import importlib.util
import json
import re
import struct
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

IMPLEMENTATION_START = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
PRODUCER_SOURCE = 'eab342ef456be4a8a1811e5249e3c217d906ce8a'
PRODUCER_TREE = '6c4fad985bf46603f0afc5baaa4e2b2b9e82c870'
FROZEN_SDK = '9854061be331fe603a1822d9b2b36ee357154927'
APPROVED_SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
SDK_CORE_PATHS = ('CMakeLists.txt', 'CMakePresets.json', 'cmake', 'include', 'src')
SDK_SRC_TREE = '01753c0ada7a8c948a19173b965fbc0f42c1341b'
SDK_INCLUDE_TREE = '2a81956f632c2bc2769d06692a80b5ac9bb22b8c'
SDK_VERSION = '3.41.0'
SDK_CORE_VERSION = '3.40.0'
SDK_ABI = '1'
PRODUCER_HEADER = 'include/exr/base.h'

PACKAGE_ROOT = 'EXReader-Windows-3.41'
PACKAGE_NAME = PACKAGE_ROOT + '.zip'
REQUIRED_FILES = ('EXReader.exe', 'Reader.otf', 'OFL.txt', 'LICENSE.txt', 'THIRD_PARTY_NOTICES.md',
                  'Sample.epub', 'Sample-positive.epub', 'Sample.pdf', 'Sample-Text.pdf')
SAMPLE_PDFS = {'Sample.pdf': 'tests/fixtures/pdf-public.pdf',
               'Sample-Text.pdf': 'tests/fixtures/pdf-public-text.pdf'}
FIRST_PARTY_FILES = {'LICENSE.txt': 'LICENSE', 'THIRD_PARTY_NOTICES.md': 'THIRD_PARTY_NOTICES.md'}

# Published program identity of the fixed producer's actual compact build. It is
# a reference value read from the sealed document, never a build input.
REFERENCE_PROGRAM = '37caa77499e94ed060a2fc71f503fbf22be8abf2f3bb943af59890d785dcc7ff'
REFERENCE_DOC = 'docs/READER-WINDOWS-COMPACT.md'
REFERENCE_SEAL = 'f355525b74ae261db536c56200e46643919ef323'

# The producer's own retained acceptance code and packaging tool. The verifier
# asserts these blobs are byte identical at the producer commit and at the
# implementation source, so "reuse" is not a restatement: the code that ran is
# the code the owner shipped.
RETAINED_SOURCES = (
    'tools/build_windows_host.py',
    'tools/host_font.py',
    'tests/reader_windows_compact/check_ui.py',
    'tests/reader_windows_compact/contract.py',
    'tests/reader_windows_preferences/check_ui.py',
    'tests/reader_windows_preferences/make_fixtures.py',
    'tests/reader_windows_account/check_a11y_ui.py',
    'tests/windows_host/check_metadata_ui.py',
    'tests/windows_host/worker_review/check_worker.py',
    'tests/windows_host/make_fixtures.py',
    'examples/reader.c',
    'apps/reader/windows-account/CMakeLists.txt',
    'apps/reader/desktop/windows_compact_ui.inc',
)

ALLOWED_PATHS = ('tests/reader_final_s01/', '.github/workflows/reader-final-s01.yml',
                 'docs/reader-final-s01/', 'HANDOFF-RESULT.md')

# A distributed program must not need a development tree, a browser runtime, a
# dynamic C runtime redistributable or the compatibility SDK beside it.
FORBIDDEN_DEPENDENCIES = ('exreader.dll', 'webview', 'webkit', 'chromium', 'electron',
                          'libcef', 'cefclient', 'msvcp', 'vcruntime', 'ucrtbased',
                          'api-ms-win-crt')
FORBIDDEN_PACKAGE_TOKENS = ('webview', 'webkit', 'chromium', 'electron', 'libcef', 'cefclient')
NON_SHIPPING_SUFFIXES = ('.lib', '.exp', '.obj', '.pdb', '.ilk', '.map', '.idb')
GENERIC_PRIVATE_PATHS = ('/home/runner/', '/Users/runner/', 'D:\\a\\', 'C:\\Users\\', 'C:/Users/')

ZIP_TIME = (2026, 1, 1, 0, 0, 0)
MACHINES = {0x14c: 'i386', 0x8664: 'amd64', 0x1c4: 'armnt', 0xaa64: 'arm64'}
SUBSYSTEMS = {1: 'native', 2: 'windows-gui', 3: 'windows-console'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha256(data):
    if isinstance(data, (bytes, bytearray)):
        return hashlib.sha256(bytes(data)).hexdigest()
    result = hashlib.sha256()
    with Path(data).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def safe_name(name):
    """A package path that a plain ZIP extractor on any OS reproduces exactly."""
    require(isinstance(name, str) and name != '', 'empty package path')
    require('\\' not in name and ':' not in name, 'non-portable package path: ' + name)
    require(not name.startswith('/') and not name.startswith('~'), 'absolute package path: ' + name)
    require(all(part not in ('', '.', '..') for part in name.split('/')), 'unsafe package path: ' + name)
    require(name.isascii(), 'package path is not ASCII: ' + name)
    return name


def load_payload(root):
    root = Path(root)
    require(root.is_dir(), 'payload directory is missing: ' + str(root))
    payload = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            payload[safe_name(path.relative_to(root).as_posix())] = path.read_bytes()
    require(payload, 'payload directory is empty')
    return payload


# ------------------------------------------------------------------ package identity

def verify_payload(payload, expected, required):
    """Every packaged file is declared, undamaged, and every mandatory file exists."""
    problems = []
    for name in sorted(required):
        if name not in payload:
            problems.append('missing required package file: ' + name)
    for name in sorted(expected):
        if name not in payload:
            problems.append('missing documented package file: ' + name)
            continue
        record = expected[name]
        if record.get('bytes') != len(payload[name]):
            problems.append('package file size mismatch: ' + name)
        if record.get('sha256') != sha256(payload[name]):
            problems.append('package file digest mismatch: ' + name)
    for name in sorted(set(payload) - set(expected)):
        problems.append('undocumented package file: ' + name)
    return problems


def write_zip(payload, path, prefix=PACKAGE_ROOT):
    """Byte reproducible archive: sorted members, pinned timestamps, pinned mode."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(re.fullmatch(r'[A-Za-z0-9._-]+', prefix) is not None, 'unsafe archive prefix: ' + str(prefix))
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(payload):
            info = zipfile.ZipInfo(prefix + '/' + safe_name(name), date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload[name])
    return {'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha256(path), 'prefix': prefix,
            'members': len(payload)}


def verify_zip(path, payload, prefix=PACKAGE_ROOT):
    problems = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            problems.append('duplicate archive member')
        expected = {prefix + '/' + safe_name(name) for name in payload}
        for name in sorted(expected - set(names)):
            problems.append('archive omits package file: ' + name)
        for name in sorted(set(names) - expected):
            problems.append('archive adds undeclared member: ' + name)
        for name in sorted(set(names) & expected):
            if not name.isascii():
                problems.append('archive member name is not ASCII: ' + name)
            if archive.read(name) != payload[name.split('/', 1)[1]]:
                problems.append('archive member bytes differ: ' + name)
        for info in archive.infolist():
            if info.is_dir():
                problems.append('archive contains a directory entry: ' + info.filename)
            if info.date_time != ZIP_TIME:
                problems.append('archive member timestamp is not pinned: ' + info.filename)
    return problems


def manifest_problems(manifest):
    """Shape, source separation and path safety of the candidate manifest itself."""
    problems = []
    if manifest.get('schema') != 1:
        problems.append('manifest schema is not 1')
    for key in ('producer_source', 'producer_tree', 'implementation_source', 'sdk', 'program',
                'packager', 'zip', 'files', 'licenses', 'dependencies', 'scans', 'run', 'scope'):
        if key not in manifest:
            problems.append('manifest lacks ' + key)
    for key in ('files', 'licenses', 'dependencies', 'scans', 'run', 'sdk', 'program', 'packager', 'zip'):
        if key in manifest and not isinstance(manifest[key], (list, dict)):
            problems.append('manifest field has the wrong type: ' + key)
    if manifest.get('producer_source') != PRODUCER_SOURCE:
        problems.append('manifest producer source differs from the fixed producer')
    if manifest.get('producer_tree') != PRODUCER_TREE:
        problems.append('manifest producer tree differs from the fixed producer tree')
    if not re.fullmatch('[0-9a-f]{40}', str(manifest.get('implementation_source') or '')):
        problems.append('manifest implementation source is not a full commit id')
    program = manifest.get('program') or {}
    if not re.fullmatch('[0-9a-f]{64}', str(program.get('sha256') or '')):
        problems.append('manifest program hash is not a digest')
    if program.get('authenticode') != 'unsigned':
        problems.append('manifest does not state the program signature status')
    archive = manifest.get('zip') or {}
    if archive.get('prefix') != PACKAGE_ROOT:
        problems.append('manifest archive prefix differs')
    if not re.fullmatch('[0-9a-f]{64}', str(archive.get('sha256') or '')):
        problems.append('manifest archive hash is not a digest')
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        problems.append('manifest has no package file records')
        files = []
    names = set()
    for row in files:
        if not isinstance(row, dict):
            problems.append('manifest package record is not an object')
            continue
        try:
            name = safe_name(row.get('path'))
        except ValueError as error:
            problems.append('manifest package path refused: ' + str(error))
            continue
        if name in names:
            problems.append('manifest repeats a package path: ' + name)
        names.add(name)
        if not re.fullmatch('[0-9a-f]{64}', str(row.get('sha256') or '')):
            problems.append('manifest package record has no digest: ' + name)
        if not isinstance(row.get('bytes'), int) or row['bytes'] <= 0:
            problems.append('manifest package record has no size: ' + name)
        if not row.get('license'):
            problems.append('manifest package record has no license attribution: ' + name)
        if not row.get('provenance'):
            problems.append('manifest package record has no provenance: ' + name)
    if REQUIRED_FILES and not set(REQUIRED_FILES) <= names:
        problems.append('manifest omits mandatory package files')
    return problems


# ------------------------------------------------------------------ PE identity

def pe_identity(data):
    """Machine, subsystem and Authenticode state straight out of the PE headers."""
    data = bytes(data)
    require(len(data) >= 0x100, 'file is too small to be a PE image')
    require(data[:2] == b'MZ', 'missing DOS signature')
    offset = struct.unpack_from('<I', data, 0x3c)[0]
    require(0 < offset <= len(data) - 24, 'invalid PE header offset')
    require(data[offset:offset + 4] == b'PE\0\0', 'missing PE signature')
    machine, sections = struct.unpack_from('<HH', data, offset + 4)
    optional_size = struct.unpack_from('<H', data, offset + 20)[0]
    optional = offset + 24
    require(optional_size >= 96 and optional + optional_size <= len(data), 'truncated optional header')
    magic = struct.unpack_from('<H', data, optional)[0]
    require(magic in (0x10b, 0x20b), 'unknown optional header magic')
    subsystem = struct.unpack_from('<H', data, optional + 68)[0]
    dll_characteristics = struct.unpack_from('<H', data, optional + 70)[0]
    directories = optional + (96 if magic == 0x10b else 112)
    count = struct.unpack_from('<I', data, optional + (92 if magic == 0x10b else 108))[0]
    certificate = 0
    if count > 4:
        require(directories + 40 <= optional + optional_size, 'truncated data directories')
        certificate = struct.unpack_from('<II', data, directories + 32)[1]
    return {'format': 'pe32+' if magic == 0x20b else 'pe32',
            'machine': MACHINES.get(machine, '0x%04x' % machine),
            'sections': sections,
            'subsystem': SUBSYSTEMS.get(subsystem, str(subsystem)),
            'dll_characteristics': dll_characteristics,
            'certificate_bytes': certificate,
            'authenticode': 'signed' if certificate else 'unsigned'}


def non_shipping_files(payload):
    return sorted(name for name in payload if name.lower().endswith(NON_SHIPPING_SUFFIXES))


def forbidden_package_tokens(payload):
    hits = []
    for name in sorted(payload):
        lowered = name.lower()
        for token in FORBIDDEN_PACKAGE_TOKENS:
            if token in lowered:
                hits.append({'path': name, 'token': token})
    return hits


# ------------------------------------------------------------------ dependencies

def distribution():
    """The G09 verification primitives, loaded under a private module name."""
    spec = importlib.util.spec_from_file_location(
        'reader_distribution_inventory_contract',
        ROOT / 'tests' / 'reader_distribution_inventory' / 'contract.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stage_view(payload):
    """G09 scans an installed stage; the candidate package is verified the same way."""
    return {'stage/' + name: data for name, data in payload.items()}


def dependency_names(text):
    names = []
    for entry in distribution().parse_entries('dumpbin-dependents', text):
        name = (entry.get('name') or '').strip()
        if name and name not in names:
            names.append(name)
    return names


def classify_dependencies(names, system_root, package_names):
    system = Path(system_root) if system_root else None
    packaged = {name.lower() for name in package_names}
    rows = []
    for name in names:
        lowered = name.lower()
        rows.append({'name': name,
                     'os_provided': bool(system is not None and (system / name).is_file()),
                     'packaged': lowered in packaged,
                     'forbidden': sorted({token for token in FORBIDDEN_DEPENDENCIES if token in lowered})})
    return rows


def dependency_problems(rows):
    problems = []
    if not any((row.get('name') or '').lower() == 'kernel32.dll' for row in rows):
        problems.append('program import table does not name kernel32.dll')
    for row in rows:
        if row.get('forbidden'):
            problems.append('forbidden program dependency %s (%s)'
                            % (row.get('name'), ', '.join(row['forbidden'])))
        if row.get('packaged'):
            problems.append('program dependency ships beside the program: ' + str(row.get('name')))
        if not row.get('os_provided'):
            problems.append('program dependency is not an installed system DLL: ' + str(row.get('name')))
    return problems


# ------------------------------------------------------------------ license material

def license_items(licenses_doc):
    items = []
    for component in licenses_doc.get('components') or []:
        for item in component.get('files') or []:
            if item.get('expected') and item.get('present'):
                items.append({'installed': item.get('installed'), 'component': component.get('id'),
                              'sha256': item.get('sha256'), 'bytes': item.get('bytes'),
                              'source': item.get('source'), 'pinned': item.get('pinned_sha256'),
                              'origin': item.get('origin')})
    return items


def license_problems(payload, licenses_doc):
    """Registered license material has to be present, byte identical, and complete."""
    problems = []
    if licenses_doc.get('materials_check_passed') is not True:
        problems.append('the G09 license materials check did not pass')
    if licenses_doc.get('failures'):
        problems.append('the G09 license materials check reported failures')
    prefix = 'share/exreader/licenses/'
    registered = {}
    for item in license_items(licenses_doc):
        installed = item.get('installed') or ''
        if not installed.startswith(prefix):
            continue
        name = 'licenses/' + installed[len(prefix):]
        registered[name] = item
        if name not in payload:
            problems.append('registered license material is not packaged: ' + name)
            continue
        observed = sha256(payload[name])
        if item.get('sha256') != observed:
            problems.append('packaged license differs from the G09 record: ' + name)
        if item.get('bytes') != len(payload[name]):
            problems.append('packaged license size differs from the G09 record: ' + name)
        if item.get('pinned') and item['pinned'] != observed:
            problems.append('packaged license differs from its registered pin: ' + name)
    for name in sorted(payload):
        if name.startswith('licenses/') and name not in registered:
            problems.append('unregistered packaged license material: ' + name)
    if not registered:
        problems.append('the G09 record registers no installed license material')
    return problems, registered


# ------------------------------------------------------------------ byte scans

def private_path_needles(extra=()):
    needles = list(GENERIC_PRIVATE_PATHS)
    for value in extra:
        if not value:
            continue
        text = str(value).replace('\\', '/').rstrip('/')
        for variant in (text, text.replace('/', '\\')):
            if variant and variant not in needles:
                needles.append(variant)
    return needles


def private_path_hits(payload, needles):
    return distribution().scan_private_paths(stage_view(payload), list(needles))


def secret_hits(payload):
    return distribution().scan_test_secrets(stage_view(payload))


def scan_problems(payload, needles):
    problems = []
    for hit in private_path_hits(payload, needles):
        problems.append('%s ships a build-machine absolute path (%s)' % (hit['path'], hit['needle']))
    for hit in secret_hits(payload):
        problems.append('%s ships a test secret marker (%s)' % (hit['path'], hit['marker']))
    return problems


# ------------------------------------------------------------------ self-test

def synthetic_pe(certificate=0, subsystem=2):
    """A minimal PE32+ image header, used only by the refusal self-tests."""
    data = bytearray(0x400)
    data[0:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', data, 0x84, 0x8664, 3)
    struct.pack_into('<H', data, 0x94, 240)
    optional = 0x98
    struct.pack_into('<H', data, optional, 0x20b)
    struct.pack_into('<H', data, optional + 68, subsystem)
    struct.pack_into('<I', data, optional + 108, 16)
    struct.pack_into('<II', data, optional + 112 + 32, 0, certificate)
    return bytes(data)


def selftest():
    """Offline positive controls and refusals for every primitive above."""
    import tempfile

    checks = []

    def passed(name):
        checks.append({'name': name, 'passed': True})

    def refuses(name, operation):
        try:
            operation()
        except (ValueError, AssertionError, KeyError):
            passed(name)
        else:
            raise AssertionError('verifier admitted ' + name)

    def expect_problems(name, observed, needle):
        if not any(needle in problem for problem in observed):
            raise AssertionError('missing refusal ' + name)
        passed(name)

    files = {'EXReader.exe': b'MZ' + b'\0' * 62, 'Reader.otf': b'font', 'OFL.txt': b'ofl',
             'licenses/freetype.txt': b'freetype text'}
    records = {name: {'bytes': len(data), 'sha256': sha256(data)} for name, data in files.items()}
    required = ('EXReader.exe', 'Reader.otf', 'OFL.txt')
    require(verify_payload(files, records, required) == [], 'complete package was rejected')
    passed('positive_complete_package')
    without = dict(files)
    without.pop('OFL.txt')
    expect_problems('refuse_omitted_package_file', verify_payload(without, records, required),
                    'missing documented package file')
    changed = dict(files)
    changed['Reader.otf'] = b'changed'
    expect_problems('refuse_changed_package_bytes', verify_payload(changed, records, required),
                    'digest mismatch')
    extra = dict(files)
    extra['extra.txt'] = b'x'
    expect_problems('refuse_undeclared_package_file', verify_payload(extra, records, required),
                    'undocumented package file')
    for index, name in enumerate(('../evil', '/abs', 'C:/windows/x', 'a\\b', '', 'a/./b', 'x\u4e2d')):
        refuses('refuse_unsafe_package_path_%d' % index, lambda name=name: safe_name(name))

    identity = pe_identity(synthetic_pe())
    require(identity['machine'] == 'amd64' and identity['subsystem'] == 'windows-gui' and
            identity['authenticode'] == 'unsigned', 'PE identity was misread: ' + repr(identity))
    passed('positive_pe_identity')
    refuses('refuse_non_pe_image', lambda: pe_identity(b'not a pe image' + b'\0' * 200))
    refuses('refuse_signed_image_as_unsigned',
            lambda: require(pe_identity(synthetic_pe(certificate=64))['authenticode'] == 'unsigned',
                            'signed image read as unsigned'))

    with tempfile.TemporaryDirectory(prefix='s01-selftest-') as folder:
        folder = Path(folder)
        system = folder / 'System32'
        system.mkdir()
        for name in ('KERNEL32.dll', 'USER32.dll', 'bcrypt.dll'):
            (system / name).write_bytes(b'x')
        rows = classify_dependencies(['KERNEL32.dll', 'USER32.dll', 'bcrypt.dll'], system, ['EXReader.exe'])
        require(not dependency_problems(rows), 'system-only dependencies were rejected')
        passed('positive_system_only_dependencies')
        rows = classify_dependencies(['KERNEL32.dll', 'exreader.dll'], system, ['EXReader.exe'])
        expect_problems('refuse_compatibility_sdk_dependency', dependency_problems(rows),
                        'forbidden program dependency')
        rows = classify_dependencies(['KERNEL32.dll', 'WEBVIEW2Loader.dll'], system, ['EXReader.exe'])
        expect_problems('refuse_browser_runtime_dependency', dependency_problems(rows),
                        'forbidden program dependency')
        rows = classify_dependencies(['KERNEL32.dll'], system, ['EXReader.exe', 'kernel32.dll'])
        expect_problems('refuse_dependency_shipped_beside_program', dependency_problems(rows),
                        'ships beside the program')
        rows = classify_dependencies(['KERNEL32.dll', 'missing-local.dll'], system, ['EXReader.exe'])
        expect_problems('refuse_unknown_dependency', dependency_problems(rows),
                        'not an installed system DLL')
        rows = classify_dependencies(['USER32.dll'], system, ['EXReader.exe'])
        expect_problems('refuse_missing_kernel32', dependency_problems(rows), 'kernel32.dll')

        clean = {'README.txt': b'no machine path here'}
        require(private_path_hits(clean, private_path_needles(['D:/a/EXReader/EXReader'])) == [],
                'clean payload reported a private path')
        passed('positive_no_private_path')
        dirty = {'EXReader.exe': b'\x00C:/Users/runneradmin/build/x\x00'}
        require(private_path_hits(dirty, private_path_needles(['D:/a/EXReader/EXReader'])),
                'private build path was admitted')
        passed('refuse_private_build_path')
        wide = {'EXReader.exe': 'C:\\Users\\runneradmin\\x'.encode('utf-16-le')}
        require(private_path_hits(wide, private_path_needles([])), 'UTF-16 build path was admitted')
        passed('refuse_private_build_path_utf16')
        require(secret_hits({'keys.txt': b'ghp_' + b'a' * 36}), 'test secret was admitted')
        passed('refuse_test_secret')

        pin = sha256(b'freetype text')
        doc = {'materials_check_passed': True, 'failures': [], 'components': [
            {'id': 'freetype', 'files': [{'installed': 'share/exreader/licenses/freetype.txt',
                                          'expected': True, 'present': True, 'sha256': pin,
                                          'bytes': len(b'freetype text'), 'source': 'x',
                                          'pinned_sha256': pin}]}]}
        problems, registered = license_problems({'licenses/freetype.txt': b'freetype text'}, doc)
        require(not problems and registered, 'registered license material was rejected')
        passed('positive_registered_license')
        problems, _ = license_problems({'licenses/freetype.txt': b'changed'}, doc)
        expect_problems('refuse_changed_license', problems, 'differs from the G09 record')
        problems, _ = license_problems({'licenses/other.txt': b'x'}, doc)
        expect_problems('refuse_unregistered_license', problems, 'unregistered packaged license')
        problems, _ = license_problems({'licenses/freetype.txt': b'freetype text'},
                                       {'materials_check_passed': False, 'failures': ['x'],
                                        'components': doc['components']})
        expect_problems('refuse_failed_materials_record', problems, 'did not pass')

        archive = folder / 'a.zip'
        payload = {'EXReader.exe': b'A' * 100, 'Reader.otf': b'B' * 50}
        write_zip(payload, archive)
        write_zip(payload, folder / 'b.zip')
        require(sha256(archive) == sha256(folder / 'b.zip'), 'archive bytes are not reproducible')
        require(verify_zip(archive, payload) == [], 'valid archive was rejected')
        passed('positive_reproducible_archive')
        with zipfile.ZipFile(folder / 'c.zip', 'w') as bad:
            bad.writestr(zipfile.ZipInfo(PACKAGE_ROOT + '/EXReader.exe', date_time=ZIP_TIME), b'A')
            bad.writestr(zipfile.ZipInfo(PACKAGE_ROOT + '/extra.txt', date_time=ZIP_TIME), b'x')
        expect_problems('refuse_archive_extra_member',
                        verify_zip(folder / 'c.zip', {'EXReader.exe': b'A'}), 'adds undeclared member')
        with zipfile.ZipFile(folder / 'd.zip', 'w') as bad:
            for _ in range(2):
                bad.writestr(zipfile.ZipInfo(PACKAGE_ROOT + '/EXReader.exe', date_time=ZIP_TIME), b'A')
        expect_problems('refuse_archive_duplicate_member',
                        verify_zip(folder / 'd.zip', {'EXReader.exe': b'A'}), 'duplicate archive member')
        expect_problems('refuse_archive_changed_member',
                        verify_zip(archive, {'EXReader.exe': b'A' * 99, 'Reader.otf': b'B' * 50}),
                        'member bytes differ')
        with zipfile.ZipFile(folder / 'e.zip', 'w') as bad:
            info = zipfile.ZipInfo(PACKAGE_ROOT + '/EXReader.exe', date_time=(2020, 1, 1, 0, 0, 0))
            bad.writestr(info, b'A' * 100)
        expect_problems('refuse_unpinned_member_timestamp',
                        verify_zip(folder / 'e.zip', {'EXReader.exe': b'A' * 100}), 'timestamp is not pinned')
        require(non_shipping_files({'a.lib': b'x', 'EXReader.exe': b'y', 'b.pdb': b'z'}) == ['a.lib', 'b.pdb'],
                'non shipping build inputs were admitted')
        passed('refuse_build_inputs_in_package')
        require(forbidden_package_tokens({'WebView2Loader.dll': b'x'}), 'browser runtime file was admitted')
        passed('refuse_browser_runtime_file')

        synthetic = {name: b'synthetic ' + name.encode('ascii') for name in REQUIRED_FILES}
        synthetic['licenses/freetype.txt'] = b'freetype text'
        manifest = {'schema': 1, 'producer_source': PRODUCER_SOURCE, 'producer_tree': PRODUCER_TREE,
                    'implementation_source': 'a' * 40,
                    'program': {'sha256': 'b' * 64, 'authenticode': 'unsigned'},
                    'packager': {'sha256': 'c' * 64},
                    'zip': {'sha256': 'd' * 64, 'prefix': PACKAGE_ROOT},
                    'sdk': {'version': SDK_VERSION}, 'dependencies': {'entries': []},
                    'scans': {'private_paths': []}, 'run': {'run_id': 1, 'attempt': 1},
                    'scope': 'synthetic', 'licenses': {'registered': 1},
                    'files': [{'path': name, 'bytes': len(data), 'sha256': sha256(data),
                               'license': {'kind': 'test'}, 'provenance': {'kind': 'test'}}
                              for name, data in synthetic.items()]}
        require(manifest_problems(manifest) == [], 'complete manifest was rejected: ' +
                repr(manifest_problems(manifest)))
        passed('positive_complete_manifest')
        for name, mutation, needle in (
                ('refuse_foreign_producer', {'producer_source': 'e' * 40}, 'producer source differs'),
                ('refuse_wrong_schema', {'schema': 2}, 'schema is not 1'),
                ('refuse_unsigned_status_omitted', {'program': {'sha256': 'b' * 64, 'authenticode': 'signed'}},
                 'signature status'),
                ('refuse_short_implementation_source', {'implementation_source': 'abc'},
                 'implementation source')):
            broken = json.loads(json.dumps(manifest))
            broken.update(mutation)
            expect_problems(name, manifest_problems(broken), needle)
        broken = json.loads(json.dumps(manifest))
        broken['files'][0]['path'] = '../escape'
        expect_problems('refuse_manifest_path_escape', manifest_problems(broken), 'path refused')
        broken = json.loads(json.dumps(manifest))
        broken['files'] = broken['files'][1:]
        expect_problems('refuse_manifest_missing_mandatory', manifest_problems(broken),
                        'omits mandatory package files')
    return checks


if __name__ == '__main__':
    import sys
    if '--self-test' in sys.argv:
        results = selftest()
        print(json.dumps({'checks': len(results), 'passed': True}))
    else:
        raise SystemExit('usage: contract.py --self-test')
