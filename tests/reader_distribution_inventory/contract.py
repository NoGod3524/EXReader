#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pure verification primitives for the offline product distribution inventory.

Nothing in this module builds, installs or downloads anything. Every function
takes text or bytes that a GitHub Actions job produced and decides whether the
claimed inventory is proven by those bytes. The generator, the rejection
fixtures and the same-source aggregate all share these functions so a claim
cannot be restated in one place and checked differently in another.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import zipfile
import zlib

MAX_ZIP = 64 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_FILES = 8192
MAX_JSON = 48 * 1024 * 1024

LICENSES = 'share/exreader/licenses/'
VENDOR_DIR = 'lib/exreader/'
ARCHIVE_RE = re.compile(r'^(?:lib)?exr_(vendor_)?(.+)\.(?:a|lib)$')
AUDIO_COMPONENTS = ('minimp3', 'faad2')
FORBIDDEN_NAME_TOKENS = ('webview', 'webkit', 'chromium', 'electron', 'libcef', 'cefclient')
FORBIDDEN_DEPENDENCY_TOKENS = ('webview', 'webkit', 'chromium', 'electron', 'libcef', 'cefclient',
                               'faad', 'faad2', 'minimp3')
CREDENTIAL_TOKENS = ('credential', 'keychain', 'secret_service', 'libsecret')
# Machine-private prefixes that must never appear in distributed bytes. They are
# the CI contract's own roots, so every job can re-scan them identically from the
# uploaded artifact without recording a runner path in the report.
GENERIC_PRIVATE_PATHS = ('/home/runner/', '/Users/runner/', 'D:\\a\\', 'C:\\Users\\', 'C:/Users/')
SYMBOL_KINDS = ('nm', 'dumpbin-symbols')
DEFINED_TYPES = frozenset('TDBRGSVACW')
MODULE_SWITCHES = ('EXR_ENABLE_PDF', 'EXR_ENABLE_PDF_CRYPTO', 'EXR_ENABLE_PDF_JPX', 'EXR_ENABLE_ICC',
                   'EXR_ENABLE_IMAGE_WEBP', 'EXR_ENABLE_IMAGE_TIFF', 'EXR_ENABLE_IMAGE_AVIF',
                   'EXR_ENABLE_AUDIO', 'EXR_ENABLE_MP3', 'EXR_ENABLE_AAC', 'EXR_ENABLE_LIBRARY',
                   'EXR_ENABLE_TEXT_INDEX', 'EXR_BUILD_TEXT_INDEX', 'EXR_ENABLE_PDF_EDIT',
                   'EXR_BUILD_SHARED_COMPAT', 'EXR_BUILD_TOOLS', 'EXR_BUILD_TESTS', 'EXR_BUILD_FUZZ',
                   'EXR_BUILD_JNI')
PROFILES = ('reading-core', 'reading-library')
PLATFORMS = ('linux', 'windows', 'macos')


class InventoryError(Exception):
    """A verification failed. The code names the exact rejected property."""

    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def need(value, code):
    if not value:
        raise InventoryError(code)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def digest(data):
    if isinstance(data, (bytes, bytearray)):
        return hashlib.sha256(bytes(data)).hexdigest()
    path = str(data)
    result = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            result.update(block)
    return result.hexdigest()


def digest1(data):
    if isinstance(data, (bytes, bytearray)):
        return hashlib.sha1(bytes(data)).hexdigest()
    path = str(data)
    result = hashlib.sha1()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            result.update(block)
    return result.hexdigest()


def text_digest(values):
    return hashlib.sha256(('\n'.join(values) + '\n').encode('utf-8')).hexdigest()


def spdx_verification_code(sha1_values):
    """SPDX 7.9.4: sort the SHA1 hex strings, concatenate, hash the result."""
    joined = ''.join(sorted(sha1_values))
    return hashlib.sha1(joined.encode('ascii')).hexdigest()


def decode_json(data):
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, 'duplicate_json_key')
            result[key] = value
        return result

    def constant(_):
        raise InventoryError('nonfinite_json')

    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
        need(type(value) is dict, 'json_root')
        return value
    except (ValueError, UnicodeError):
        raise InventoryError('json_format') from None


# ---------------------------------------------------------------- dependency tool output

def _ldd_entries(text):
    entries = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('linux-vdso') or stripped.startswith('linux-gate'):
            continue
        if stripped in ('not a dynamic executable', 'Not a valid dynamic program',
                        'file format not recognized', 'statically linked'):
            continue
        parts = stripped.split('>')
        if len(parts) == 2:
            name = parts[0].replace('=>', '').strip().split(' ')[0]
            target = parts[1].strip().split(' ')[0]
            entry = {'name': name}
            if 'not found' in parts[1]:
                entry.update(state='unresolved', path='')
            else:
                entry.update(state='resolved', path=target)
            entries.append(entry)
        else:
            entries.append({'name': stripped.split(' ')[0], 'state': 'name-only', 'path': ''})
    return entries


def _readelf_entries(text):
    entries = []
    for line in text.splitlines():
        match = re.search(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', line)
        if match:
            entries.append({'name': match.group(1), 'state': 'name-only', 'path': ''})
    return entries


def _otool_entries(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries = []
    for line in lines[1:]:
        if line.startswith(('Architecture:', 'Subsystem', 'cmd LC_')):
            continue
        token = line.split(' ', 1)[0]
        if not token:
            continue
        entries.append({'name': token, 'state': 'name-only', 'path': token})
    return entries


def _dumpbin_dependents(text):
    entries = []
    section = None
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith('image has the following delay load dependencies'):
            section = 'delay-load'
            continue
        if lowered.startswith('image has the following dependencies'):
            section = 'load'
            continue
        if section:
            if not stripped or lowered.startswith('summary'):
                section = None
                continue
            entries.append({'name': stripped, 'state': section, 'path': ''})
    return entries


def _ar_entries(text):
    return [{'name': line.strip()} for line in text.splitlines() if line.strip()]


def _lib_list_entries(text):
    entries = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith(('microsoft', 'copyright')):
            continue
        entries.append({'name': stripped.replace('\\', '/').split('/')[-1]})
    return entries


NM_UNDEFINED = re.compile(r'^\s*(?:[0-9a-fA-F]{8,16})?\s+U\s+(\S+)\s*$')
NM_DEFINED = re.compile(r'^[0-9a-fA-F]{8,16}\s+([A-Za-z])\s+(\S+)\s*$')
DUMPBIN_SYMBOL = re.compile(
    r'^[0-9A-F]{3,}\s+[0-9A-F]{8,16}\s+(UNDEF|SECT\d+|ABS)\s+\S+\s*'
    r'(?:\([^)]*\))?\s*(External|Static)\s+\|\s*(\S+)\s*$')


def _symbol_name(name, strip_underscore):
    if strip_underscore and name.startswith('_'):
        return name[1:]
    return name


def _nm_entries(text, strip_underscore):
    entries = {}
    for line in text.splitlines():
        match = NM_UNDEFINED.match(line)
        if match:
            name = _symbol_name(match.group(1), strip_underscore)
            entries[name] = 'undefined'
            continue
        match = NM_DEFINED.match(line)
        if match and match.group(1) in DEFINED_TYPES:
            name = _symbol_name(match.group(2), strip_underscore)
            entries.setdefault(name, 'defined')
    return [{'name': name, 'state': state} for name, state in sorted(entries.items())]


def _dumpbin_symbols(text, _strip_underscore):
    entries = {}
    for line in text.splitlines():
        match = DUMPBIN_SYMBOL.match(line.strip())
        if not match:
            continue
        if match.group(2) != 'External':
            continue
        name = match.group(3)
        state = 'undefined' if match.group(1) == 'UNDEF' else 'defined'
        if state == 'undefined':
            entries[name] = 'undefined'
        else:
            entries.setdefault(name, 'defined')
    return [{'name': name, 'state': state} for name, state in sorted(entries.items())]


def _ninja_link_entries(text):
    """The link command Ninja would run: the last command line that links objects."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    for line in reversed(lines):
        if re.search(r'\.(?:o|obj)\b', line) and (' -o ' in line or ' -o' in line or '/out:' in line):
            return [{'name': token} for token in line.split()]
    return [{'name': token} for token in lines[-1].split()]


PARSERS = {
    'ldd': lambda text, strip: _ldd_entries(text),
    'readelf-dynamic': lambda text, strip: _readelf_entries(text),
    'otool': lambda text, strip: _otool_entries(text),
    'dumpbin-dependents': lambda text, strip: _dumpbin_dependents(text),
    'ar': lambda text, strip: _ar_entries(text),
    'lib-list': lambda text, strip: _lib_list_entries(text),
    'nm': _nm_entries,
    'dumpbin-symbols': _dumpbin_symbols,
    'ninja-link': lambda text, strip: _ninja_link_entries(text),
}


def parse_entries(kind, text, strip_underscore=False):
    need(kind in PARSERS, 'unknown_dependency_kind')
    need(type(text) is str, 'dependency_output_type')
    return PARSERS[kind](text, bool(strip_underscore))


def symbol_summary(entries):
    defined = sorted({entry['name'] for entry in entries if entry['state'] == 'defined'})
    undefined = sorted({entry['name'] for entry in entries if entry['state'] == 'undefined'})
    return {'defined': defined, 'undefined': undefined}


def dependency_record(kind, purpose, command, exit_code, output, strip_underscore=False):
    """Build one self-verifying dependency record from a real tool invocation."""
    entries = parse_entries(kind, output, strip_underscore)
    record = {'kind': kind, 'purpose': purpose, 'command': list(command), 'exit_code': exit_code,
              'strip_underscore': bool(strip_underscore), 'raw_output_sha256': digest(output.encode('utf-8')),
              'raw_output_bytes': len(output.encode('utf-8'))}
    if kind in SYMBOL_KINDS:
        summary = symbol_summary(entries)
        record['summary'] = {
            'defined_count': len(summary['defined']), 'undefined_count': len(summary['undefined']),
            'defined_sha256': text_digest(summary['defined']),
            'undefined_sha256': text_digest(summary['undefined'])}
    else:
        record['entries'] = entries
    return record


def verify_dependency(record, output):
    """Re-derive a record from the captured output and require exact equality."""
    need(type(record) is dict and type(output) is str, 'dependency_record_type')
    need(digest(output.encode('utf-8')) == record.get('raw_output_sha256'), 'dependency_output_digest')
    need(len(output.encode('utf-8')) == record.get('raw_output_bytes'), 'dependency_output_bytes')
    entries = parse_entries(record.get('kind'), output, record.get('strip_underscore', False))
    if record.get('kind') in SYMBOL_KINDS:
        summary = symbol_summary(entries)
        observed = {'defined_count': len(summary['defined']), 'undefined_count': len(summary['undefined']),
                    'defined_sha256': text_digest(summary['defined']),
                    'undefined_sha256': text_digest(summary['undefined'])}
        need(record.get('summary') == observed, 'dependency_summary_mismatch')
        return summary
    need(record.get('entries') == entries, 'dependency_entries_mismatch')
    return {'defined': [], 'undefined': []}


def archive_symbols(records, archive):
    """Re-derive one archive's symbol sets from already verified records."""
    for record in records:
        if record.get('archive') == archive and record.get('kind') in SYMBOL_KINDS:
            entries = parse_entries(record['kind'], record['raw_output'], record.get('strip_underscore', False))
            summary = symbol_summary(entries)
            need(text_digest(summary['defined']) == record['summary']['defined_sha256'],
                 'dependency_defined_digest')
            need(text_digest(summary['undefined']) == record['summary']['undefined_sha256'],
                 'dependency_undefined_digest')
            return summary
    raise InventoryError('archive_symbols_missing')


def symbol_edges(sources, targets):
    """sources/targets: {archive: {'defined': [...], 'undefined': [...]}}."""
    edges = []
    for source in sorted(sources):
        undefined = set(sources[source]['undefined'])
        for target in sorted(targets):
            if target == source:
                continue
            shared = sorted(undefined & set(targets[target]['defined']))
            if shared:
                edges.append({'from': source, 'to': target, 'symbols': shared})
    return edges


def classify_link_tokens(tokens, archive_names):
    """Split a real link command into distributed archives, system libraries, rest."""
    distributed, system, other = [], [], []
    for token in tokens:
        base = re.split(r'[\\/]', token)[-1]
        if base in archive_names:
            distributed.append(base)
        elif token.startswith(('-l', '-Wl,', '-framework')) or base.lower().endswith('.lib'):
            system.append(token)
        else:
            other.append(token)
    return sorted(set(distributed)), sorted(set(system)), other


def reachable(edges, roots, nodes):
    seen = set(root for root in roots if root in nodes)
    frontier = sorted(seen)
    while frontier:
        current = frontier.pop()
        for edge in edges:
            if edge['from'] == current and edge['to'] in nodes and edge['to'] not in seen:
                seen.add(edge['to'])
                frontier.append(edge['to'])
    return seen


# ---------------------------------------------------------------- installed tree and licences

def verify_installed(payload, records):
    """payload: {'stage/<path>': bytes}. records: inventory['installed_files']."""
    problems = []
    listed = set()
    for record in records:
        path = record.get('path')
        try:
            name = 'stage/' + safe_path(path)
        except InventoryError:
            problems.append('installed record has an invalid path')
            continue
        if name not in payload:
            problems.append('missing installed file: ' + str(path))
            continue
        data = payload[name]
        listed.add(name)
        if record.get('bytes') != len(data) or record.get('sha256') != digest(data) or \
                record.get('sha1') != digest1(data):
            problems.append('installed file identity mismatch: ' + str(path))
        if not data:
            problems.append('empty installed file: ' + str(path))
    actual = {name for name in payload if name.startswith('stage/')}
    for name in sorted(actual - listed):
        problems.append('unrecorded installed file: ' + name[len('stage/'):])
    return problems


def expected_license_paths(components, enabled):
    """Registered installed licence paths for one profile, from the shared record."""
    expected = {}
    for component in components:
        for item in component['files']:
            when = component['when'] if item.get('when') is None else item['when']
            if not enabled(when):
                continue
            expected[item['installed']] = {'component': component['id'], 'source': item['path'],
                                          'sha256': item.get('sha256'),
                                          'pinned': item.get('pinned', True)}
    return expected


def verify_license_materials(records, payload, expected, components):
    """Re-hash the installed licence originals and compare them with the pins."""
    problems = []
    observed = {}
    for record in records:
        path = record.get('path')
        if not isinstance(path, str) or not path.startswith(LICENSES):
            continue
        name = 'stage/' + path
        if name not in payload:
            problems.append('missing installed license: ' + path)
            continue
        data = payload[name]
        observed[path] = digest(data)
        if record.get('sha256') != digest(data) or record.get('bytes') != len(data):
            problems.append('installed license identity mismatch: ' + path)
        if not data:
            problems.append('empty installed license: ' + path)
    for path, entry in sorted(expected.items()):
        if path not in observed:
            problems.append('registered license not installed: ' + path)
            continue
        if entry['sha256'] and entry['sha256'] != observed[path]:
            problems.append('installed license differs from its registered pin: ' + path)
        if not entry['sha256'] and entry['pinned']:
            problems.append('registered license has no pinned hash: ' + path)
    for path in sorted(set(observed) - set(expected)):
        problems.append('unregistered installed license material: ' + path)
    owners = {component['id'] for component in components}
    for component in components:
        installed = [item['installed'] for item in component['files']
                     if item['installed'] in observed]
        for item in component['files']:
            if item['installed'] not in expected:
                continue
            if item['installed'] not in observed:
                problems.append('license material missing for ' + component['id'] + ': ' + item['installed'])
        if component.get('notice_marker') and not installed:
            problems.append('registered component has no installed notice: ' + component['id'])
    need(owners, 'components_missing')
    return problems


def scan_private_paths(payload, needles):
    """Distributed bytes must never contain a machine-private absolute path."""
    hits = []
    encoded = [(needle, needle.encode('utf-8'), needle.encode('utf-16-le')) for needle in needles]
    for name in sorted(payload):
        if not name.startswith('stage/'):
            continue
        data = payload[name]
        for needle, utf8, utf16 in encoded:
            if utf8 in data or utf16 in data:
                hits.append({'path': name[len('stage/'):], 'needle': needle})
    return hits


def scan_forbidden(payload, inventory):
    """Audio/GPL options, WebView, credential modules and the module switch set."""
    problems = []
    observations = {}
    switches = inventory.get('config', {}).get('cache_switches', {})
    audio = {key: switches.get(key) for key in ('EXR_ENABLE_AUDIO', 'EXR_ENABLE_MP3', 'EXR_ENABLE_AAC')}
    observations['audio_switches'] = audio
    if any(value != 'OFF' for value in audio.values()):
        problems.append('audio codec switch enabled in the reading configuration: ' + repr(audio))
    layers = inventory.get('config', {}).get('layers') or []
    if 'audio' in layers:
        problems.append('audio module layer built into the reading profile')
    if 'textindex' in layers or 'pdf_edit' in layers:
        problems.append('optional module layer built into the reading profile: ' + repr(layers))
    names = sorted(name for name in payload if name.startswith('stage/'))
    audio_files = [name for name in names
                   if any(token in name.lower() for token in ('faad', 'minimp3'))]
    observations['audio_files'] = audio_files
    if audio_files:
        problems.append('audio codec archive or license installed: ' + repr(audio_files))
    webview_files = [name for name in names
                     if any(token in name.lower() for token in FORBIDDEN_NAME_TOKENS)]
    dynamic = [entry.get('name', '') for entry in inventory.get('dynamic_dependencies', {}).get('entries', [])]
    webview_dynamic = [name for name in dynamic
                       if any(token in name.lower() for token in FORBIDDEN_DEPENDENCY_TOKENS)]
    observations['webview_files'] = webview_files
    observations['webview_dependencies'] = webview_dynamic
    if webview_files:
        problems.append('web engine file installed: ' + repr(webview_files))
    if webview_dynamic:
        problems.append('web engine dependency in the consumer runtime: ' + repr(webview_dynamic))
    targets = inventory.get('identity', {}).get('targets') or []
    credential_targets = [name for name in targets if any(token in name.lower() for token in CREDENTIAL_TOKENS)]
    credential_files = [name for name in names if any(token in name.lower() for token in CREDENTIAL_TOKENS)]
    observations['credential_targets'] = credential_targets
    observations['credential_files'] = credential_files
    if credential_targets:
        problems.append('credential module exported by the installed package: ' + repr(credential_targets))
    if credential_files:
        problems.append('credential module material installed: ' + repr(credential_files))
    for name in names:
        if name.endswith('lib/cmake/EXReader/EXReaderDependencies.cmake'):
            text = payload[name].decode('utf-8', 'replace')
            if re.search(r'IMPORTED_LOCATION\s+"(?!\$\{PACKAGE_PREFIX_DIR\})', text):
                problems.append('installed dependency configuration uses an absolute location')
    observations['layers'] = list(layers)
    return problems, observations


def verify_module_switches(inventory, preset_switches):
    """The observed cache must equal the preset and must never select audio codecs."""
    problems = []
    cache = inventory.get('config', {}).get('cache_switches', {})
    for key in sorted(preset_switches):
        if cache.get(key) != preset_switches[key]:
            problems.append('cache switch %s: preset %s, observed %s'
                            % (key, preset_switches[key], cache.get(key)))
    for key in ('EXR_ENABLE_AUDIO', 'EXR_ENABLE_MP3', 'EXR_ENABLE_AAC'):
        if cache.get(key) != 'OFF':
            problems.append('audio codec switch is not OFF: ' + key)
    return problems


def verify_identity(inventory):
    problems = []
    identity = inventory.get('identity', {})
    version = identity.get('version')
    abi = identity.get('abi')
    if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        problems.append('installed SDK version is not a semantic version')
    if not integer(abi, 1):
        problems.append('installed SDK ABI version is missing')
    probe = identity.get('probe') or {}
    if probe.get('version') != version:
        problems.append('runtime version %r differs from installed header %r'
                        % (probe.get('version'), version))
    if probe.get('abi') != abi:
        problems.append('runtime ABI %r differs from installed header %r' % (probe.get('abi'), abi))
    if identity.get('config_version') != version:
        problems.append('package configuration version %r differs from installed header %r'
                        % (identity.get('config_version'), version))
    if not identity.get('targets'):
        problems.append('installed package exports no components')
    return problems


# ---------------------------------------------------------------- Actions artifact identity

def safe_path(name):
    need(type(name) is str and name and '\\' not in name and '\0' not in name and ':' not in name,
         'archive_path')
    path = PurePosixPath(name)
    need(not path.is_absolute() and '..' not in path.parts and str(path) == name and name != '.',
         'archive_path')
    return name


def select(rows, name):
    matches = [row for row in rows if row.get('name') == name]
    need(len(matches) == 1, 'named_evidence_missing_or_duplicate')
    return matches[0]


def unique(rows, code):
    need(type(rows) is list, code)
    ids, names = set(), set()
    for row in rows:
        need(type(row) is dict and integer(row.get('id'), 1) and type(row.get('name')) is str, code)
        need(row['id'] not in ids and row['name'] not in names, code)
        ids.add(row['id'])
        names.add(row['name'])


def artifact_identity(artifact, run, now):
    need(artifact.get('expired') is False and integer(artifact.get('size_in_bytes'), 1)
         and artifact['size_in_bytes'] <= MAX_ZIP, 'artifact_expired_or_empty')
    try:
        expires = datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00'))
        need(expires.tzinfo is not None and expires > now, 'artifact_expired_time')
    except (ValueError, TypeError, AttributeError, KeyError):
        raise InventoryError('artifact_expiry') from None
    need(type(artifact.get('digest')) is str and re.fullmatch(r'sha256:[a-f0-9]{64}', artifact['digest']),
         'artifact_digest')
    origin = artifact.get('workflow_run', {})
    need(origin.get('id') == run['id'] and origin.get('head_sha') == run['head_sha']
         and origin.get('repository_id') == run['repository']['id']
         and origin.get('head_repository_id') == run['head_repository']['id'], 'artifact_origin')


def archive_files(data, artifact):
    need(type(data) is bytes and len(data) == artifact['size_in_bytes'] and len(data) <= MAX_ZIP,
         'zip_size')
    need('sha256:' + digest(data) == artifact['digest'], 'zip_digest')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            need(0 < len(infos) <= MAX_FILES, 'zip_file_limit')
            names, files, total = set(), {}, 0
            for info in infos:
                name = safe_path(info.filename.rstrip('/') if info.is_dir() else info.filename)
                need(name.casefold() not in names, 'zip_duplicate_path')
                names.add(name.casefold())
                need(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR)
                     and not info.flag_bits & 1, 'zip_special_or_encrypted')
                if info.is_dir():
                    continue
                total += info.file_size
                need(total <= MAX_EXPANDED and info.compress_type in (zipfile.ZIP_STORED,
                                                                      zipfile.ZIP_DEFLATED),
                     'zip_expanded_or_compression')
                files[name] = archive.read(info)
            return files
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError, zlib.error):
        raise InventoryError('zip_format') from None


def upload_binding(log, artifact):
    need(type(log) is bytes and 0 < len(log) <= MAX_EXPANDED, 'producer_log')
    text = log.decode('utf-8', 'replace')
    matches = list(re.finditer(r'Artifact ' + re.escape(artifact['name'])
                               + r' has been successfully uploaded! Final size is (\d+) bytes\. '
                                 r'Artifact ID is (\d+)', text))
    need(len(matches) == 1 and int(matches[0][1]) == artifact['size_in_bytes']
         and int(matches[0][2]) == artifact['id'], 'producer_artifact_binding')
    hashes = re.findall(r'SHA256 digest of uploaded artifact zip is ([a-f0-9]{64})',
                        text[:matches[0].start()])
    need(hashes and 'sha256:' + hashes[-1] == artifact['digest'], 'producer_digest_binding')
    return digest(log)


def config_switch(value):
    if isinstance(value, dict):
        value = value.get('value')
    return 'ON' if str(value).upper() in ('ON', 'TRUE', '1', 'YES', 'Y') else 'OFF'
