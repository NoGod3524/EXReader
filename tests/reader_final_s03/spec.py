#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pinned identities and pure decisions for the S03 macOS .app candidate.

Every function here decides whether bytes that an Actions job produced prove the
claim. Collecting those bytes is bundle.py (dependency, resource and
product-library manifest), identity.py (source, SDK and installed stage) and
smoke.py (relocation, offline open and reopen). aggregate.py only combines the
recorded verdicts.

Nothing in this module builds, installs, downloads, signs or notarizes.
"""
import hashlib
import os
from pathlib import Path
import posixpath

# ---------------------------------------------------------------- pinned identities

BRANCH = 'codex/reader-fw-s03'
START_SHA = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'

# The actual macOS native producer this package consumes. It is a separate
# source identity from this verifier branch and must never be replaced by it.
PRODUCER_BRANCH = 'codex/reader-apple-raw3'
PRODUCER_SHA = '15dab6b2270dc296ed6239db67ced2e22d255e65'
PRODUCER_SEAL_SHA = '44eabdc86b3b84d986f81dbaf8cee92b1829cea8'
PRODUCER_RUN = 40196978163
PRODUCER_RUN_ATTEMPT = 1
PRODUCER_JOBS = {'native': 121179826434, 'strict': 121186031984}
PRODUCER_ARTIFACT = {
    'id': 12600789926,
    'name': 'apple-raw3-native-40196978163-1',
    'bytes': 77056135,
    'digest': 'sha256:92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5',
    'expires_at': '2027-01-23T13:18:06Z',
}

# Approved 3.41 SDK source. The producer's SDK-bearing paths are byte-identical
# to this commit; guard.py and identity.py both prove that instead of trusting it.
SDK_SHA = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
SDK_VERSION = '3.41.0'
SDK_ABI = '1u'
FROZEN_SDK_340 = '9854061be331fe603a1822d9b2b36ee357154927'
SDK_SOURCE_PATHS = ('include', 'src', 'cmake', 'CMakeLists.txt', 'bindings', 'licenses')

PRODUCER_REQUIRED_FILES = (
    'tools/build_apple_host.py',
    'tools/build_apple_product.py',
    'tools/check_apple_host.py',
    'tools/check_apple_product.py',
    'tools/apple_swift.py',
    'examples/apple/ReaderApp.swift',
    'examples/apple/LegacySelfTest.swift',
    'examples/apple/HostModel.swift',
    'bindings/swift/EXReader.swift',
)
PRODUCER_REQUIRED_FLAGS = (
    ('tools/build_apple_host.py', '--selector-bytes-candidate'),
    ('tools/build_apple_host.py', '--product-prefix'),
    ('tools/build_apple_product.py', '--selector-bytes-candidate'),
    ('tools/build_apple_product.py', '--product-prefix'),
    ('tools/apple_swift.py', '--selector-bytes-candidate'),
    ('tools/check_apple_host.py', '--device'),
)
SELF_TEST_MINIMUM_MARKER = 'checks.count >= 20'

# ---------------------------------------------------------------- bundle layout

BUNDLE_EXECUTABLE = 'Contents/MacOS/EXReader'
BUNDLE_FRAMEWORKS = 'Contents/Frameworks'
BUNDLE_RESOURCES = 'Contents/Resources'
INFO_PLIST = 'Contents/Info.plist'
LICENSE_DIR = 'licenses'
REQUIRED_RESOURCES = ('Sample.pdf', 'Sample.epub', 'reader-catalog-v1.sql', 'Reader.otf',
                      'Noto-OFL.txt', 'EXReader-LICENSE.txt', 'THIRD_PARTY_NOTICES.md',
                      LICENSE_DIR)
MINIMUM_MACOS = '12.0'
ARCHITECTURE = 'arm64'
SYSTEM_PREFIXES = ('/usr/lib/', '/System/Library/')
SDK_LIBRARY_TOKEN = 'libexreader'

INFO_PINS = {
    'CFBundleExecutable': 'EXReader',
    'CFBundleIdentifier': 'org.exreader.host',
    'CFBundleName': 'EXReader',
    'CFBundleDisplayName': 'EXReader',
    'CFBundlePackageType': 'APPL',
    'CFBundleShortVersionString': SDK_VERSION,
    'LSMinimumSystemVersion': MINIMUM_MACOS,
    'NSHighResolutionCapable': True,
}
INFO_LOCAL_KEYS = ('CFBundleVersion', 'EXRSourceSHA', 'EXRRawSelectorEnabled')

# Pinned host font assets (tools/host_font.py pins the same digests).
FONT_PINS = {
    'Reader.otf': '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b',
    'Noto-OFL.txt': '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2',
}
SAMPLE_PDF = 'tests/fixtures/pdf-public.pdf'
CANONICAL_RESOURCE_SOURCES = {
    'reader-catalog-v1.sql': 'apps/reader/store/001_catalog.sql',
    'EXReader-LICENSE.txt': 'LICENSE',
    'THIRD_PARTY_NOTICES.md': 'THIRD_PARTY_NOTICES.md',
    'Sample.pdf': SAMPLE_PDF,
}

# ---------------------------------------------------------------- candidates

CANDIDATES = {
    'default': {
        'label': 'default installed product family',
        'selector_bytes': False,
        'product_prefix': None,
    },
    'raw': {
        'label': 'explicit selector-bytes raw3 candidate family',
        'selector_bytes': True,
        'product_prefix': 'products-raw',
    },
}
# Raw family symbols the producer's own product checker asserts. Counted again
# here from the real nm output and the real link map.
RAW_PROVIDERS = (
    ('reader_revisions_open_raw_v3', 'reader_revisions', 'revisions'),
    ('reader_rs_decode_raw_v3', 'reader_reading_state_codec', 'reading_state'),
    ('reader_rc_apply_raw_v3', 'reader_reading_commands', 'reading_commands'),
    ('reader_av_page_get_raw_v3', 'reader_annotation_view', 'annotation_view'),
    ('reader_command_apply_book_raw_v3', 'reader_commands', 'commands'),
    ('reader_sync_step_raw_v3', 'reader_sync', 'sync'),
    ('reader_session_create_raw_v3', 'reader_session', 'session'),
)

# ---------------------------------------------------------------- relocation and offline

RELOCATED_SEGMENT = '最终 阅读器 候选 ünïcode 空格'
OFFLINE_PROFILE = ('(version 1)\n'
                   '(allow default)\n'
                   '(deny network-outbound)\n'
                   '(deny network-inbound)\n')
OFFLINE_PROBE = ("import socket, sys\n"
                 "try:\n"
                 "    socket.create_connection(('1.1.1.1', 443), 3).close()\n"
                 "except OSError:\n"
                 "    sys.exit(7)\n"
                 "sys.exit(0)\n")
OFFLINE_PROBE_DENIED = 7
SMOKE_PHASES = ('baseline', 'offline-open', 'offline-reopen')
MIN_CHECKS = 20


def candidate(name):
    if name not in CANDIDATES:
        raise KeyError('unknown candidate: ' + str(name))
    return CANDIDATES[name]


def digest(data):
    if isinstance(data, (bytes, bytearray)):
        return hashlib.sha256(bytes(data)).hexdigest()
    path = Path(str(data))
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            result.update(block)
    return result.hexdigest()


def git_blob_digest(data):
    """The object name git would give these exact bytes (SHA-1 repository)."""
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def file_map(root):
    """Hash every regular file and record every symbolic link under root."""
    root = Path(root)
    files, links = {}, {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            links[relative] = os.readlink(path)
        elif path.is_file():
            files[relative] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    return files, links


def sub_map(files, prefix):
    """The part of a file map under one bundle directory, keyed relatively."""
    return {path[len(prefix) + 1:]: entry for path, entry in files.items()
            if path.startswith(prefix + '/')}


# ---------------------------------------------------------------- Info.plist

def plist_problems(info, name, source_sha):
    if not isinstance(info, dict):
        return ['info_plist_not_a_dictionary']
    problems = []
    for key, value in sorted(INFO_PINS.items()):
        if info.get(key) != value:
            problems.append('info_plist_value:' + key)
    bundle_version = info.get('CFBundleVersion')
    if not isinstance(bundle_version, str) or not bundle_version.strip():
        problems.append('info_plist_value:CFBundleVersion')
    if info.get('EXRSourceSHA') != source_sha:
        problems.append('info_plist_value:EXRSourceSHA')
    expected_flag = candidate(name)['selector_bytes']
    recorded_flag = info.get('EXRRawSelectorEnabled')
    if not isinstance(recorded_flag, bool) or recorded_flag != expected_flag:
        problems.append('info_plist_value:EXRRawSelectorEnabled')
    return problems


def plist_unexpected_keys(info):
    known = set(INFO_PINS) | set(INFO_LOCAL_KEYS)
    return sorted(key for key in info if key not in known)


# ---------------------------------------------------------------- architecture

def architecture_problems(arch_map):
    problems = []
    for relative in sorted(arch_map):
        observed = arch_map[relative]
        if observed != [ARCHITECTURE]:
            problems.append('architecture:' + relative + '=' + ','.join(observed))
    return problems


def build_version_problems(build_map):
    problems = []
    for relative in sorted(build_map):
        entry = build_map[relative]
        if entry.get('platform') != '1':
            problems.append('build_platform:' + relative + '=' + str(entry.get('platform')))
        if entry.get('minos') != MINIMUM_MACOS:
            problems.append('minimum_os:' + relative + '=' + str(entry.get('minos')))
        if not entry.get('sdk'):
            problems.append('build_sdk_missing:' + relative)
    return problems


# ---------------------------------------------------------------- dependency closure

def expand_path_like(path_like, executable_dir, loader_dir):
    """Expand one @executable_path/@loader_path token into an absolute POSIX path."""
    if path_like == '@executable_path':
        return executable_dir
    if path_like.startswith('@executable_path/'):
        return posixpath.normpath(posixpath.join(executable_dir,
                                                 path_like[len('@executable_path/'):]))
    if path_like == '@loader_path':
        return loader_dir
    if path_like.startswith('@loader_path/'):
        return posixpath.normpath(posixpath.join(loader_dir, path_like[len('@loader_path/'):]))
    if path_like.startswith('/'):
        return posixpath.normpath(path_like)
    return None


def resolve_install_name(name, rpaths, executable_dir, loader_dir, bundle_root):
    """Classify one otool -L entry as self, system, bundle-relative or external.

    A dependency is only closed when it is a system library, or a file that the
    bundle itself carries at the resolved path.
    """
    if name.startswith(SYSTEM_PREFIXES):
        return 'system', None
    if name.startswith('@rpath/'):
        tail = name[len('@rpath/'):]
        for rpath in rpaths:
            base = expand_path_like(rpath, executable_dir, loader_dir)
            if base is None:
                continue
            resolved = posixpath.normpath(posixpath.join(base, tail))
            if resolved == bundle_root or resolved.startswith(bundle_root + '/'):
                return 'bundle', resolved[len(bundle_root) + 1:]
        return 'external', None
    expanded = expand_path_like(name, executable_dir, loader_dir)
    if expanded is not None:
        if expanded == bundle_root or expanded.startswith(bundle_root + '/'):
            return 'bundle', expanded[len(bundle_root) + 1:]
    return 'external', None


def dependency_problems(records, files):
    problems = []
    for record in records:
        name = record['install_name']
        kind = record['kind']
        if kind == 'system':
            continue
        if kind == 'bundle':
            resolved = record.get('resolved')
            if not resolved or resolved not in files:
                problems.append('dependency_missing:' + name)
            continue
        problems.append('dependency_external:' + record['owner'] + '->' + name)
    return problems


def reachability_problems(records, macho_files):
    referenced = {record['resolved'] for record in records
                  if record['kind'] == 'bundle' and record.get('resolved')}
    problems = []
    for relative in sorted(macho_files):
        if relative.startswith(BUNDLE_FRAMEWORKS + '/') and relative not in referenced:
            problems.append('framework_not_referenced:' + relative)
    return problems


def sdk_uniqueness_problems(files, records):
    problems = []
    libraries = [path for path in files
                 if path.startswith(BUNDLE_FRAMEWORKS + '/')
                 and posixpath.basename(path).startswith(SDK_LIBRARY_TOKEN)
                 and path.endswith('.dylib')]
    if len(libraries) != 1:
        problems.append('sdk_library_count:' + str(len(libraries)))
    copies = [path for path in files
              if posixpath.basename(path).startswith(SDK_LIBRARY_TOKEN)
              and path not in libraries]
    if copies:
        problems.append('sdk_library_duplicate:' + ','.join(sorted(copies)))
    executable_links = [record['install_name'] for record in records
                        if record['owner'] == BUNDLE_EXECUTABLE]
    if not any(posixpath.basename(name).startswith(SDK_LIBRARY_TOKEN)
               for name in executable_links):
        problems.append('sdk_library_not_referenced_by_executable')
    static = [path for path in files if path.endswith('.a')]
    if static:
        problems.append('static_archive_shipped:' + ','.join(sorted(static)))
    return problems


# ---------------------------------------------------------------- resources

def resource_problems(resources, digests):
    problems = []
    for name in REQUIRED_RESOURCES:
        if name == LICENSE_DIR:
            if not any(path.startswith(LICENSE_DIR + '/') for path in resources):
                problems.append('resource_missing:' + LICENSE_DIR)
        elif name not in resources:
            problems.append('resource_missing:' + name)
    for name, pin in sorted(FONT_PINS.items()):
        if digests.get(name) != pin:
            problems.append('font_pin:' + name)
    return problems


def license_copy_problems(stage_licenses, digests):
    """The bundle must carry the installed licence originals and nothing else."""
    problems = []
    for relative in sorted(stage_licenses):
        bundled = digests.get(LICENSE_DIR + '/' + relative)
        if bundled != stage_licenses[relative]:
            problems.append('license_copy_mismatch:' + relative)
    for relative in sorted(digests):
        if not relative.startswith(LICENSE_DIR + '/'):
            continue
        name = relative[len(LICENSE_DIR) + 1:]
        if name not in stage_licenses:
            problems.append('license_unregistered:' + name)
    return problems


def provenance_problems(records):
    problems = []
    for record in records:
        if record.get('observed') != record.get('expected'):
            problems.append('resource_provenance:' + record['bundle_path'])
    return problems


# ---------------------------------------------------------------- producer build manifest

def build_manifest_problems(manifest, files, source_sha, name):
    if not isinstance(manifest, dict):
        return ['build_manifest_missing']
    problems = []
    if manifest.get('schema') != 1:
        problems.append('build_manifest_schema')
    if manifest.get('source_sha') != source_sha:
        problems.append('build_manifest_source_sha')
    if manifest.get('sdk_version') != SDK_VERSION:
        problems.append('build_manifest_sdk_version')
    if manifest.get('platform') != 'macos':
        problems.append('build_manifest_platform')
    recorded_flag = manifest.get('selector_bytes_candidate')
    if not isinstance(recorded_flag, bool) or recorded_flag != candidate(name)['selector_bytes']:
        problems.append('build_manifest_selector_flag')
    recorded = manifest.get('files')
    if not isinstance(recorded, dict):
        problems.append('build_manifest_files')
        return problems
    actual = {path: entry['sha256'] for path, entry in files.items()}
    for path in sorted(actual):
        if recorded.get(path) != actual[path]:
            problems.append('build_manifest_file:' + path)
    for path in sorted(recorded):
        if path not in actual:
            problems.append('build_manifest_extra_file:' + path)
    return problems


# ---------------------------------------------------------------- native self-test report

def report_problems(report, name, source_sha, minimum=MIN_CHECKS):
    if not isinstance(report, dict):
        return ['report_missing']
    problems = []
    if report.get('schema') != 1:
        problems.append('report_schema')
    if report.get('passed') is not True:
        problems.append('report_not_passed')
    count = report.get('check_count')
    if not isinstance(count, int) or isinstance(count, bool) or count < minimum:
        problems.append('report_check_count:' + str(count))
    checks = report.get('checks')
    if not isinstance(checks, list) or len(checks) != count:
        problems.append('report_check_list')
    elif len(set(checks)) != len(checks):
        problems.append('report_duplicate_checks')
    if report.get('engine_version') != SDK_VERSION:
        problems.append('report_engine_version:' + str(report.get('engine_version')))
    if report.get('source_sha') != source_sha:
        problems.append('report_source_sha')
    if report.get('platform') != 'macOS':
        problems.append('report_platform')
    if report.get('error') is not None:
        problems.append('report_error:' + str(report.get('error')))
    return problems


# ---------------------------------------------------------------- relocation and offline

def relocation_problems(source_files, moved_files, relocated_path):
    problems = []
    if ' ' not in relocated_path:
        problems.append('relocation_path_without_space')
    if all(ord(character) < 128 for character in relocated_path):
        problems.append('relocation_path_without_unicode')
    if set(source_files) != set(moved_files):
        problems.append('relocation_file_set')
        return problems
    for path in sorted(source_files):
        if source_files[path] != moved_files[path]:
            problems.append('relocation_file_bytes:' + path)
    return problems


def offline_problems(offline):
    problems = []
    if offline.get('mechanism') != 'sandbox-exec':
        problems.append('offline_mechanism:' + str(offline.get('mechanism')))
    if offline.get('control_reachable') is not True:
        problems.append('offline_control_not_reachable')
    if offline.get('denied') is not True:
        problems.append('offline_not_denied')
    if offline.get('profile', '') != OFFLINE_PROFILE:
        problems.append('offline_profile_changed')
    return problems


# ---------------------------------------------------------------- source identity

def identity_problems(identity, verifier_sha=None):
    if not isinstance(identity, dict):
        return ['identity_missing']
    problems = []
    producer = identity.get('producer') or {}
    sdk = identity.get('sdk') or {}
    if producer.get('sha') != PRODUCER_SHA:
        problems.append('producer_sha:' + str(producer.get('sha')))
    if producer.get('branch') != PRODUCER_BRANCH:
        problems.append('producer_branch:' + str(producer.get('branch')))
    if sdk.get('source_sha') != SDK_SHA:
        problems.append('sdk_source_sha:' + str(sdk.get('source_sha')))
    if sdk.get('version') != SDK_VERSION:
        problems.append('sdk_version:' + str(sdk.get('version')))
    if sdk.get('abi') != SDK_ABI:
        problems.append('sdk_abi:' + str(sdk.get('abi')))
    if identity.get('start_sha') != START_SHA:
        problems.append('start_sha:' + str(identity.get('start_sha')))
    if verifier_sha is not None and identity.get('verifier_sha') != verifier_sha:
        problems.append('verifier_sha:' + str(identity.get('verifier_sha')))
    runner = identity.get('runner') or {}
    if runner.get('machine') != ARCHITECTURE:
        problems.append('runner_machine:' + str(runner.get('machine')))
    problems.extend(identity.get('problems') or [])
    return problems
