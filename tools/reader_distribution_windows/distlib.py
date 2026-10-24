#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Shared primitives for the Windows distribution path-audit pipeline.

Only the Windows distribution package (J25) imports this module. It performs no
network or build work: it reads already-produced files, parses COFF/PE/archive
containers, and seals a deterministic archive. Every failure is a ValueError
naming the exact file and surface, so a blocked distribution can never degrade
into a silent pass.
"""
import hashlib
import json
from pathlib import Path
import time
import zipfile

ARCHIVE_MAGIC = b'!<arch>' + bytes([10])
MEMBER_FMAG = bytes([0x60, 0x0A])

# Machine-specific prefixes that must never reach a shipped Windows archive.
BUILD_MACHINE_PATTERNS = {
    'runner-workspace-d-drive': b'd:\\a\\',
    'runner-workspace-d-drive-slash': b'd:/a/',
    'self-hosted-actions-runner': b'c:\\actions-runner',
    'self-hosted-actions-runner-slash': b'c:/actions-runner',
    'hosted-tool-cache-windows': b'c:\\hostedtoolcache',
    'hosted-tool-cache-unix': b'/opt/hostedtoolcache',
    'hosted-work-unix': b'/home/runner/work',
    'hosted-work-macos': b'/users/runner/work',
}

CATEGORY_ORDER = ('header', 'config', 'license', 'library', 'doc', 'example', 'other')
REWRITABLE_SUFFIXES = frozenset({
    '.md', '.txt', '.json', '.cmake', '.py', '.c', '.h', '.hpp', '.cpp', '.html', '.htm',
    '.xml', '.yml', '.yaml', '.cfg', '.ini', '.in', '.rst', '.ps1', '.sh', '.map', '.def',
})
DEFAULT_SCAN_LIMIT = 256 * 1024 * 1024
SEAL_EPOCH = 946684800  # 2000-01-01T00:00:00Z so resealing is byte-identical.


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def digest_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def category_of(path):
    parts = Path(path).as_posix().split('/')
    name = parts[-1]
    joined = '/'.join(parts)
    if parts[0] == 'include':
        return 'header'
    if joined.startswith('lib/cmake') or name.endswith('.cmake'):
        return 'config'
    if (joined.startswith('share/exreader/licenses') or name.startswith('LICENSE') or
            name.startswith('THIRD_PARTY') or name == 'COPYING'):
        return 'license'
    if parts[0] in ('lib', 'bin'):
        return 'library'
    if parts[0] == 'docs' or name.lower().endswith('.md'):
        return 'doc'
    if parts[0] == 'examples':
        return 'example'
    return 'other'


def inventory(root):
    """Every installed file with size and digest; symlinks and escapes are refused."""
    root = Path(root)
    require(root.is_dir(), 'distribution stage is not a directory: ' + str(root))
    root = root.resolve()
    entries = []
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'symlink in distribution stage: ' + str(path))
        if path.is_dir():
            continue
        require(path.resolve().is_relative_to(root), 'path escapes the stage: ' + str(path))
        relative = path.relative_to(root).as_posix()
        entries.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': digest(path),
                        'category': category_of(relative)})
    require(entries, 'empty distribution stage: ' + str(root))
    require(len({item['path'] for item in entries}) == len(entries),
            'duplicate distribution path in ' + str(root))
    return entries


def category_digests(entries):
    grouped = {name: [] for name in CATEGORY_ORDER}
    for entry in entries:
        grouped[entry['category']].append(entry)
    result = {}
    for name in CATEGORY_ORDER:
        members = grouped[name]
        lines = sorted('%s %s %d' % (item['sha256'], item['path'], item['bytes']) for item in members)
        result[name] = {'files': len(members), 'bytes': sum(item['bytes'] for item in members),
                        'sha256': digest_bytes(('\n'.join(lines) + '\n').encode()) if lines else None}
    return result


def build_patterns(roots):
    """Fixed machine prefixes plus each absolute root in both separator spellings."""
    patterns = {key: value for key, value in BUILD_MACHINE_PATTERNS.items()}
    for index, item in enumerate(roots):
        if not item:
            continue
        text = str(Path(str(item)).absolute()).rstrip('\\/')
        if len(text) < 4:
            continue
        windows = text.replace('/', '\\')
        posix = text.replace('\\', '/')
        patterns['root-%d-windows' % index] = windows.encode('utf-8')
        patterns['root-%d-posix' % index] = posix.encode('utf-8')
    return patterns


def is_text(payload):
    if b'\x00' in payload:
        return False
    try:
        payload.decode('utf-8')
    except UnicodeDecodeError:
        return False
    return True


def find_hits(name, payload, patterns, text=None, limit=4096):
    """Every literal occurrence of an offending root, with a printable excerpt."""
    lowered = payload.lower()
    text = is_text(payload) if text is None else text
    hits = []
    for key in sorted(patterns):
        needle = patterns[key]
        index = lowered.find(needle.lower())
        while index >= 0:
            context = payload[max(0, index - 40):index + len(needle) + 40]
            hits.append({'file': name, 'pattern': key,
                         'needle': needle.decode('utf-8', 'replace'), 'offset': index,
                         'class': 'text' if text else 'binary',
                         'context': context.decode('utf-8', 'replace').replace('\x00', '.')})
            require(len(hits) <= limit, 'too many matches in %s; refusing an unbounded report' % name)
            index = lowered.find(needle.lower(), index + 1)
    return hits


def _coff_sections(payload):
    require(len(payload) >= 20, 'truncated COFF header')
    machine = int.from_bytes(payload[0:2], 'little')
    sections = int.from_bytes(payload[2:4], 'little')
    optional_size = int.from_bytes(payload[16:18], 'little')
    table = 20 + optional_size
    require(len(payload) >= table + 40 * sections, 'truncated COFF section table')
    result = []
    for index in range(sections):
        offset = table + index * 40
        name = payload[offset:offset + 8].split(bytes([0]))[0].decode('latin-1')
        raw_size = int.from_bytes(payload[offset + 16:offset + 20], 'little')
        raw_pointer = int.from_bytes(payload[offset + 20:offset + 24], 'little')
        result.append({'name': name, 'size': raw_size, 'offset': raw_pointer})
    return machine, result


def coff_section_names(payload):
    """Section names and per-section sizes of a standalone COFF object."""
    require(payload[:2] in (b'\x64\x86', b'\x4c\x01', b'\xc4\x01', b'\xaa\x64'),
            'not a COFF object under a known machine id')
    machine, sections = _coff_sections(payload)
    return machine, [{'name': item['name'], 'size': item['size']} for item in sections]


def split_directives(text):
    directives, current, quoted = [], '', False
    for char in text:
        if char == '"':
            quoted = not quoted
            current += char
        elif char in ' \t' and not quoted:
            if current:
                directives.append(current)
            current = ''
        else:
            current += char
    if current:
        directives.append(current)
    return directives


def absolute_directive(directive):
    """The offending path of an absolute /DEFAULTLIB//LIBPATH directive, else None."""
    lowered = directive.lower()
    for prefix in ('/defaultlib:', '/libpath:', '/wholearchive:', '-defaultlib:', '/include:'):
        if lowered.startswith(prefix):
            value = directive[len(prefix):].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            if len(value) >= 3 and value[0].isalpha() and value[1] == ':' and value[2] in '\\/':
                return value
            if value[:2] in ('..', './', '.\\') or value[:1] in ('/', '\\'):
                return value
            return None
    return None


def scan_archive(name, payload):
    """Member names, member COFF surfaces and .drectve directives of one archive."""
    members, section_hits, directives, machines = [], [], [], set()
    position, lookback = len(ARCHIVE_MAGIC), b''
    require(payload[:len(ARCHIVE_MAGIC)] == ARCHIVE_MAGIC, 'not an archive: ' + name)
    while position + 60 <= len(payload):
        header = payload[position:position + 60]
        require(header[58:60] == MEMBER_FMAG,
                'invalid archive member header in %s at %d' % (name, position))
        raw_name = header[0:16].decode('latin-1').rstrip()
        size = int((header[48:58].decode('latin-1').strip() or '0'))
        body_start = position + 60
        body = payload[body_start:body_start + size]
        require(len(body) == size, 'truncated member %s in %s' % (raw_name, name))
        member_name = raw_name
        if raw_name.startswith('/') and raw_name[1:].isdigit():
            offset = int(raw_name[1:])
            tail = payload.find(MEMBER_FMAG, 0)
            text = lookback[offset:offset + 64] if lookback else ''
            member_name = '<long-name:%s>' % (text.split(bytes([0]))[0].decode('latin-1') if text else raw_name)
        members.append(member_name)
        if raw_name not in ('/', '//') and body[:2] not in (bytes([0, 0]),):
            try:
                machine, sections = _coff_sections(body)
                machines.add(machine)
                for section in sections:
                    if section['name'].startswith('.debug'):
                        section_hits.append({'member': member_name, 'section': section['name'],
                                             'bytes': section['size']})
                    if section['name'] == '.drectve':
                        span = body[section['offset']:section['offset'] + section['size']]
                        for directive in split_directives(span.decode('latin-1')):
                            offending = absolute_directive(directive)
                            if offending:
                                directives.append({'member': member_name, 'directive': directive,
                                                   'absolute': offending})
            except ValueError:
                pass
        position = body_start + size + (size & 1)
    names = [item for item in members if not (item.startswith('/') or item.startswith('<long-name'))]
    separated = [item for item in names if '\\' in item or '/' in item]
    return {'kind': 'archive', 'members': len(members),
            'member_names_sample': sorted(names)[:8],
            'member_names_with_separator': separated[:8],
            'coff_machines': sorted(machines),
            'debug_section_count': len(section_hits),
            'debug_sections': section_hits[:8],
            'drective_absolute': directives[:8]}


def scan_pe(name, payload):
    """PE import DLLs; absolute or path-bearing imports are refused."""
    require(len(payload) >= 64, 'truncated DOS header in ' + name)
    e_lfanew = int.from_bytes(payload[60:64], 'little')
    require(payload[e_lfanew:e_lfanew + 4] == b'PE' + bytes([0, 0]), 'missing PE signature in ' + name)
    coff = e_lfanew + 4
    machine = int.from_bytes(payload[coff:coff + 2], 'little')
    sections = int.from_bytes(payload[coff + 2:coff + 4], 'little')
    optional_size = int.from_bytes(payload[coff + 16:coff + 18], 'little')
    optional = coff + 20
    magic = int.from_bytes(payload[optional:optional + 2], 'little')
    require(magic in (0x10B, 0x20B), 'unsupported PE optional header in ' + name)
    directories = optional + (96 if magic == 0x10B else 112)
    directory_count = int.from_bytes(payload[directories - 4:directories], 'little')
    table = optional + optional_size
    require(len(payload) >= table + 40 * sections, 'truncated PE section table in ' + name)
    layout = []
    for index in range(sections):
        offset = table + index * 40
        virtual_size = int.from_bytes(payload[offset + 8:offset + 12], 'little')
        virtual_address = int.from_bytes(payload[offset + 12:offset + 16], 'little')
        raw_size = int.from_bytes(payload[offset + 16:offset + 20], 'little')
        raw_pointer = int.from_bytes(payload[offset + 20:offset + 24], 'little')
        layout.append((virtual_address, max(virtual_size, raw_size), raw_pointer, raw_size))

    def convert(rva):
        for virtual_address, span, raw_pointer, raw_size in layout:
            if virtual_address <= rva < virtual_address + span:
                delta = rva - virtual_address
                require(delta < raw_size, 'RVA outside raw data in ' + name)
                return raw_pointer + delta
        raise ValueError('unmapped RVA in ' + name)

    imports, absolute = [], []
    if directory_count > 1:
        rva = int.from_bytes(payload[directories + 8:directories + 12], 'little')
        size = int.from_bytes(payload[directories + 12:directories + 16], 'little')
        if rva and size:
            offset = convert(rva)
            for index in range(size // 20):
                name_rva = int.from_bytes(payload[offset + index * 20 + 12:offset + index * 20 + 16], 'little')
                if not name_rva:
                    break
                start = convert(name_rva)
                end = payload.find(bytes([0]), start)
                require(end > start, 'unterminated import name in ' + name)
                value = payload[start:end].decode('latin-1')
                imports.append(value)
                if ('\\' in value or '/' in value or
                        (len(value) > 2 and value[0].isalpha() and value[1] == ':')):
                    absolute.append(value)
    return {'kind': 'pe', 'machine': hex(machine),
            'imports': sorted({item.lower() for item in imports}),
            'absolute_imports': absolute[:8]}


def scan_bytes(name, payload, patterns):
    """Classify one blob and collect pattern hits plus container facts."""
    text = is_text(payload)
    facts = {'path': name, 'bytes': len(payload), 'kind': 'file', 'text': text}
    if payload[:len(ARCHIVE_MAGIC)] == ARCHIVE_MAGIC:
        facts.update(scan_archive(name, payload))
    elif payload[:2] == b'MZ':
        facts.update(scan_pe(name, payload))
    facts['hits'] = find_hits(name, payload, patterns, text=text)
    return facts


def scan_file(path, patterns, label=None, limit=DEFAULT_SCAN_LIMIT):
    path = Path(path)
    size = path.stat().st_size
    require(size <= limit, 'file exceeds the declared scan limit: ' + str(path))
    facts = scan_bytes(label or path.name, path.read_bytes(), patterns)
    facts['bytes'] = size
    return facts


def scan_tree(root, patterns, limit=DEFAULT_SCAN_LIMIT):
    root = Path(root)
    require(root.is_dir(), 'scan root is not a directory: ' + str(root))
    root = root.resolve()
    records = []
    for path in sorted(root.rglob('*')):
        if path.is_dir():
            continue
        require(not path.is_symlink(), 'symlink while scanning: ' + str(path))
        facts = scan_file(path, patterns, path.relative_to(root).as_posix(), limit=limit)
        facts['path'] = path.relative_to(root).as_posix()
        facts['sha256'] = digest(path)
        facts['category'] = category_of(facts['path'])
        records.append(facts)
    require(records, 'nothing to scan under ' + str(root))
    return records


def blocking(hits):
    """Binary hits always block; text hits are rewritable by the sanitizer."""
    return [item for item in hits if item['class'] == 'binary']


def digest_of_entries(records):
    lines = sorted('%s %s %d' % (item['sha256'], item['path'], item['bytes']) for item in records)
    return digest_bytes(('\n'.join(lines) + '\n').encode())


def seal_zip(stage, output, epoch=SEAL_EPOCH):
    """Deterministic ZIP: sorted entries, fixed timestamps, no extra fields."""
    require(Path(stage).is_dir(), 'distribution stage is not a directory: ' + str(stage))
    stage, output = Path(stage).resolve(), Path(output)
    entries = []
    for path in sorted(stage.rglob('*')):
        require(not path.is_symlink(), 'symlink in distribution stage: ' + str(path))
        if path.is_file():
            require(path.resolve().is_relative_to(stage), 'path escapes the stage: ' + str(path))
            entries.append(path)
    require(entries, 'empty distribution stage: ' + str(stage))
    stamp = time.gmtime(max(int(epoch), 315532800))[:6]
    require(not output.exists(), 'distribution archive already exists: ' + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as destination:
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in entries:
                info = zipfile.ZipInfo(path.relative_to(stage).as_posix(), date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                info.create_system = 0
                archive.writestr(info, path.read_bytes())
    return {'archive': output.name, 'bytes': output.stat().st_size, 'sha256': digest(output),
            'entries': len(entries)}


def read_zip(path, limit=1024 * 1024 * 1024):
    """Entry names and payload digests; escaping entries are refused."""
    records, total = [], 0
    require(Path(path).is_file(), 'distribution archive is missing: ' + str(path))
    with zipfile.ZipFile(Path(path)) as archive:
        for info in archive.infolist():
            name = info.filename
            require('\\' not in name, 'backslash zip entry: ' + name)
            require(not name.startswith('/'), 'absolute zip entry: ' + name)
            require('..' not in name.split('/'), 'escaping zip entry: ' + name)
            require(not info.is_dir(), 'unexpected directory zip entry: ' + name)
            payload = archive.read(info)
            total += len(payload)
            require(total <= limit, 'distribution archive exceeds the declared limit')
            records.append({'path': name, 'bytes': len(payload), 'sha256': digest_bytes(payload),
                            'crc32': info.CRC})
            require(len(records) <= 20000, 'distribution archive has too many entries')
    require(records, 'empty distribution archive: ' + str(path))
    return records


def load_json(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    require(isinstance(value, dict), 'JSON document must be an object: ' + str(path))
    return value


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def named(results, name, passed, detail=None):
    entry = {'name': name, 'status': 'pass' if passed else 'fail'}
    if detail is not None:
        entry['detail'] = detail
    results.append(entry)
    return passed


def require_named_pass(results, names):
    present = {item['name'] for item in results}
    missing = [name for name in names if name not in present]
    require(not missing, 'missing named results: ' + ', '.join(missing))
    failed = [item['name'] for item in results if item['status'] != 'pass']
    require(not failed, 'failed named results: ' + ', '.join(failed))


def path_token(key):
    return ('<path:%s>' % key).encode('utf-8')


def rewrite_occurrences(payload, needles):
    """Replace every case-insensitive occurrence, longest match first per position.

    Returns the new payload and the occurrence list in new-payload order, so the
    original bytes can be rebuilt exactly (including the original casing).
    """
    lowered = payload.lower()
    matches = []
    for key in sorted(needles):
        needle = needles[key].lower()
        if not needle:
            continue
        start = lowered.find(needle)
        while start >= 0:
            matches.append((start, len(needle), key))
            start = lowered.find(needle, start + 1)
    matches.sort(key=lambda item: (item[0], -item[1], item[2]))
    output, occurrences, cursor = bytearray(), [], 0
    for offset, length, key in matches:
        if offset < cursor:
            continue
        output += payload[cursor:offset]
        output += path_token(key)
        matched = payload[offset:offset + length].decode('utf-8')
        occurrences.append({'key': key, 'matched': matched, 'offset': offset})
        cursor = offset + length
    output += payload[cursor:]
    return bytes(output), occurrences


def restore_occurrences(payload, occurrences):
    """Rebuild the original bytes from a rewritten payload and its occurrence list."""
    output, cursor = bytearray(), 0
    for occurrence in occurrences:
        token = path_token(occurrence['key'])
        index = payload.find(token, cursor)
        require(index >= 0, 'rewritten payload lost the token for ' + occurrence['key'])
        output += payload[cursor:index]
        output += occurrence['matched'].encode('utf-8')
        cursor = index + len(token)
    output += payload[cursor:]
    return bytes(output)
