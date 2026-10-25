#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic primitives for the J24 Unix relocatable distribution candidate.

The module holds no workflow knowledge. It walks an installed SDK tree, renders
and validates the pkg-config contract relative to ${pcfiledir}, plans removal of
byte-identical archive materials, seals a hardlink-aware archive and re-extracts
it. tests/reader_distribution_unix/selfcheck.py exercises every decision path on
synthetic fixtures in the cloud protocol job.
"""
import gzip
import hashlib
import io
import json
import os
import re
import tarfile
from pathlib import Path, PurePosixPath

PC_PREFIX = '${pcfiledir}/../..'
MATERIAL_ROOTS = ('docs/', 'share/', 'examples/', 'bindings/')
MATERIAL_FILES = ('README.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md')
NO_LINK_SUFFIX = ('.a', '.lib', '.so', '.dylib', '.h', '.modulemap')
TEXT_SUFFIX = ('.pc', '.cmake', '.md', '.txt', '.json', '.yml', '.yaml', '.in', '.c',
               '.h', '.cpp', '.cc', '.inc', '.css', '.html', '.xml', '.modulemap',
               '.cfg', '.sh', '.py', '.swift', '.java')
TEXT_NAMES = ('LICENSE', 'README', 'CHANGELOG', 'NOTICE', 'THIRD_PARTY_NOTICES.md')


class ContractError(RuntimeError):
    """A distribution contract was violated; the message names the invariant."""


def need(value, message):
    if not value:
        raise ContractError(message)
    return value


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def decode_json(value):
    if isinstance(value, (bytes, bytearray)):
        return json.loads(bytes(value).decode('utf-8'))
    return json.loads(Path(value).read_text(encoding='utf-8'))


def safe_relative(name):
    path = PurePosixPath(name)
    need(isinstance(name, str) and bool(name), 'empty path')
    need('\\' not in name and ':' not in name, 'non-posix path: ' + name)
    need(not path.is_absolute(), 'absolute path: ' + name)
    need(all(part not in ('', '.', '..') for part in path.parts), 'escaping path: ' + name)
    return name


def walk(root):
    """Record every regular file; symlinks are rejected instead of followed."""
    root = Path(root)
    need(root.is_dir(), 'missing directory: ' + str(root))
    records = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        safe_relative(relative)
        need(not path.is_symlink(), 'symlink in tree: ' + relative)
        if path.is_dir():
            continue
        status = path.stat()
        records.append({'path': relative, 'bytes': status.st_size, 'sha256': digest(path),
                        'executable': bool(status.st_mode & 0o111),
                        'nlink': status.st_nlink, 'inode': status.st_ino})
    need(records, 'empty tree: ' + str(root))
    return records


def tree_problems(root, records):
    """Compare a tree against recorded identities; nlink may change, bytes must not."""
    problems = []
    root = Path(root)
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*')
              if path.is_file() and not path.is_symlink()}
    claimed = {record['path'] for record in records}
    if actual != claimed:
        problems.append('tree inventory differs: missing=%s unlisted=%s' % (
            sorted(claimed - actual)[:6], sorted(actual - claimed)[:6]))
    for record in records:
        path = root / record['path']
        if not path.is_file() or path.is_symlink():
            problems.append('missing file: ' + record['path'])
            continue
        if path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            problems.append('file changed: ' + record['path'])
    return problems


def text_files(root):
    root = Path(root)
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        if path.name in TEXT_NAMES or path.suffix in TEXT_SUFFIX:
            if path.stat().st_size <= 4 * 1024 * 1024:
                yield path.relative_to(root).as_posix(), path


def scan_tokens(root, tokens):
    """Find absolute workspace/build/prefix tokens inside installed text files."""
    encoded = [(token, token.encode('utf-8')) for token in tokens if token]
    hits = []
    for relative, path in text_files(root):
        data = path.read_bytes()
        for token, needle in encoded:
            count = data.count(needle)
            if count:
                hits.append({'path': relative, 'token': token, 'count': count})
    return hits


def compile_definitions(targets_text):
    """Compile definitions the installed CMake package imposes on its consumers.

    A pkg-config consumer never reads EXReaderTargets.cmake, so a unit that only
    carries `-I` gives a different compile interface than the package it describes
    (on Windows the missing `EXR_STATIC` alone changes every declaration).
    """
    names = []
    for match in re.finditer(
            r'set_target_properties\(EXReader::(exr_\w+) PROPERTIES(.*?)'
            r'(?=\nset_target_properties\(|\nadd_library\(|\n#|\Z)',
            targets_text, re.S):
        found = re.search(r'INTERFACE_COMPILE_DEFINITIONS "((?:[^"\\]|\\.)*)"', match.group(2))
        if not found:
            continue
        for item in found.group(1).split(';'):
            item = item.replace('\\"', '"').replace('\\\\', '\\').strip()
            if item and item not in names:
                names.append(item)
    return sorted(names)


def exported_links(name, properties, static, seen=()):
    """Resolve one component's exported archives, splicing interface targets.

    An exported component may name another exported target that owns no archive of
    its own (the public interface target). Its own link interface is expanded here so
    a real dependency behind an interface target is never dropped from the order.
    """
    links = []
    for link in properties.get(name, []):
        if not link.startswith('EXReader::exr_'):
            continue
        dependency = link.split('::', 1)[1]
        if dependency in seen:
            continue
        if dependency in static:
            if dependency not in links:
                links.append(dependency)
        elif dependency in properties:
            for expanded in exported_links(dependency, properties, static, seen + (dependency,)):
                if expanded not in links:
                    links.append(expanded)
    return links


def link_order(targets_text):
    """Return static component archives so every archive precedes its dependencies."""
    properties = {}
    for match in re.finditer(
            r'set_target_properties\(EXReader::(exr_\w+) PROPERTIES(.*?)'
            r'(?=\nset_target_properties\(|\nadd_library\(|\n#|\Z)',
            targets_text, re.S):
        links = re.search(r'INTERFACE_LINK_LIBRARIES "([^"]*)"', match.group(2))
        properties[match.group(1)] = [item for item in (links.group(1).split(';') if links else []) if item]
    static = sorted({match.group(1) for match in
                     re.finditer(r'add_library\(EXReader::(exr_\w+) STATIC IMPORTED\)', targets_text)})
    need(static, 'no static component archive is exported')
    import heapq

    dependencies = {name: exported_links(name, properties, static) for name in static}
    dependents = {name: 0 for name in static}
    for name in static:
        for dependency in dependencies[name]:
            dependents[dependency] += 1
    ready = [name for name in static if dependents[name] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        for dependency in dependencies[name]:
            dependents[dependency] -= 1
            if dependents[dependency] == 0:
                heapq.heappush(ready, dependency)
    need(len(order) == len(static), 'component dependency cycle in the exported package')
    return order


def vendor_archives(dependencies_text):
    """Installed private archive names in the order upstream declared them."""
    names = []
    for match in re.finditer(
            r'IMPORTED_LOCATION "\$\{PACKAGE_PREFIX_DIR\}/lib/exreader/([^"]+)"',
            dependencies_text):
        if match.group(1) not in names:
            names.append(match.group(1))
    need(names, 'no private dependency archive is declared by the installed package')
    return names


def system_libraries(dependencies_text):
    names = set()
    for match in re.finditer(r'INTERFACE_LINK_LIBRARIES "([^"]*)"', dependencies_text):
        for item in match.group(1).split(';'):
            if item:
                names.add(item)
    libraries = ['-pthread']
    if 'm' in names:
        libraries.append('-lm')
    if 'dl' in names:
        libraries.append('-ldl')
    return libraries


def archive_flag(filename):
    """libexr_render.a -> -lexr_render, libexr_vendor_miniz.a -> -lexr_vendor_miniz."""
    stem = filename
    for prefix in ('lib',):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    for suffix in ('.a', '.lib', '.so', '.dylib'):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
    need(stem, 'empty archive name: ' + filename)
    return '-l' + stem


def render_pc(version, description, components, vendor, system, definitions=()):
    need(components and vendor and system, 'incomplete pkg-config input')
    cflags = ['-I${includedir}'] + ['-D' + item for item in definitions]
    lines = [
        'prefix=' + PC_PREFIX,
        'exec_prefix=${prefix}',
        'libdir=${prefix}/lib',
        'includedir=${prefix}/include',
        'vendordir=${libdir}/exreader',
        '',
        'Name: EXReader',
        'Description: ' + description,
        'URL: https://github.com/NoGod3524/EXReader',
        'Version: ' + version,
        'Cflags: ' + ' '.join(cflags),
        'Libs: -L${libdir} ' + ' '.join(archive_flag(name) for name in components),
        'Libs.private: -L${vendordir} ' + ' '.join(archive_flag(name) for name in vendor) +
        ' ' + ' '.join(system),
        '',
    ]
    return '\n'.join(lines)


def _expand(value, variables, depth=0):
    need(depth < 8, 'pkg-config variable recursion')
    if '${' not in value:
        return value

    def replace(match):
        name = match.group(1)
        if name == 'pcfiledir':
            return match.group(0)
        need(name in variables, 'undefined pkg-config variable: ' + name)
        return _expand(variables[name], variables, depth + 1)

    return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', replace, value)


def pc_contract(text, version, components, vendor, system, definitions=()):
    """Validate the installed pkg-config file; report every violation."""
    problems = []
    lines = text.splitlines()
    if not lines or lines[0] != 'prefix=' + PC_PREFIX:
        problems.append('pkg-config prefix is not "prefix=' + PC_PREFIX + '"')
    variables, fields = {}, {}
    for line in lines:
        if not line.strip() or line.startswith('#'):
            continue
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if match:
            variables[match.group(1)] = match.group(2)
            continue
        match = re.match(r'^([A-Za-z][A-Za-z0-9.\-]*):\s*(.*)$', line)
        if match:
            fields[match.group(1)] = match.group(2)
    for name in ('prefix', 'exec_prefix', 'libdir', 'includedir', 'vendordir'):
        if name not in variables:
            problems.append('missing pkg-config variable: ' + name)
    if fields.get('Version') != version:
        problems.append('pkg-config version differs: ' + str(fields.get('Version')))
    for name in ('Name', 'Description', 'Cflags', 'Libs', 'Libs.private'):
        if not fields.get(name):
            problems.append('missing pkg-config field: ' + name)
    try:
        expanded = {name: _expand(fields.get(name, ''), variables) for name in
                    ('Cflags', 'Libs', 'Libs.private')}
    except ContractError as error:
        problems.append(str(error))
        expanded = {}
    for name, value in expanded.items():
        for token in value.split():
            if token.startswith(('-I', '-L')):
                path = token[2:]
                if path.startswith('/') or path.startswith('~'):
                    problems.append('%s: absolute install path %s' % (name, token))
                elif not path.startswith('${pcfiledir}'):
                    problems.append('%s: path is not relative to pcfiledir: %s' % (name, token))
            elif token.startswith('-Wl,'):
                problems.append('%s: linker-wrapper flag is not relocatable: %s' % (name, token))
    expected_definitions = {'-D' + item for item in definitions}
    observed_definitions = {token for token in expanded.get('Cflags', '').split()
                            if token.startswith('-D')}
    if observed_definitions != expected_definitions:
        missing = expected_definitions - observed_definitions
        extra = observed_definitions - expected_definitions
        if missing:
            problems.append('Cflags omits the exported definition(s): ' + ' '.join(sorted(missing)))
        if extra:
            problems.append('Cflags lists unexpected definition(s): ' + ' '.join(sorted(extra)))
    libs = expanded.get('Libs', '').split()
    private = expanded.get('Libs.private', '').split()
    expected_components = {archive_flag(name) for name in components}
    expected_vendor = {archive_flag(name) for name in vendor}
    if {item for item in libs if item.startswith('-l')} != expected_components:
        problems.append('Libs does not list exactly the component archives')
    expected_private = expected_vendor | {item for item in system if item.startswith('-l')}
    observed_private = {item for item in private if item.startswith('-l')}
    missing = expected_private - observed_private
    if missing:
        problems.append('Libs.private is missing: ' + ' '.join(sorted(missing)))
    extra = observed_private - expected_private
    if extra:
        problems.append('Libs.private lists unexpected libraries: ' + ' '.join(sorted(extra)))
    for item in system:
        if item not in private:
            problems.append('Libs.private is missing the system flag ' + item)
    for forbidden in ('/home/', '/Users/', '\\'):
        if forbidden in text:
            problems.append('pkg-config text contains ' + forbidden)
    return {'prefix': variables.get('prefix'), 'version': fields.get('Version'),
            'libs': libs, 'private': private, 'cflags': expanded.get('Cflags', ''),
            'fields': sorted(fields), 'variables': sorted(variables)}, problems


def foreign_pkgconfig(root, keep='lib/pkgconfig/exreader.pc'):
    """Record private-dependency pkg-config units that upstream installed with an
    absolute prefix. They are never part of the public SDK contract: the private
    archives they describe are already listed in Libs.private of exreader.pc."""
    found = []
    for directory in ('lib/pkgconfig', 'share/pkgconfig'):
        base = Path(root) / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob('*.pc')):
            relative = path.relative_to(Path(root)).as_posix()
            if relative == keep:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            match = re.search(r'^prefix=(.*)$', text, re.M)
            prefix = match.group(1).strip() if match else None
            found.append({'path': relative, 'bytes': path.stat().st_size,
                          'sha256': digest(path), 'prefix': prefix,
                          'absolute': bool(prefix and re.match(r'^(?:/|[A-Za-z]:[\\/])', prefix))})
    return found


def is_material(relative):
    return relative in MATERIAL_FILES or relative.startswith(MATERIAL_ROOTS)


def dedupe_plan(records):
    """Plan hardlinks for identical archive material; archives and headers stay apart.

    A hardlink shares one inode, so it also shares one permission mode. Two copies
    with the same bytes but a different executable bit are therefore not duplicates:
    linking them would silently change an installed mode.
    """
    groups = {}
    for record in records:
        relative = record['path']
        if not is_material(relative) or relative.endswith(NO_LINK_SUFFIX) or record['bytes'] == 0:
            continue
        key = (record['sha256'], bool(record.get('executable')))
        groups.setdefault(key, []).append(record)
    plan = []
    for key in sorted(groups):
        entries = sorted(groups[key], key=lambda item: item['path'])
        if len(entries) < 2:
            continue
        primary = entries[0]
        for duplicate in entries[1:]:
            plan.append({'primary': primary['path'], 'duplicate': duplicate['path'],
                         'bytes': duplicate['bytes'], 'sha256': key[0],
                         'executable': key[1]})
    return plan


def inode_groups(records):
    """Group paths that already share an inode, keyed by digest for validation."""
    groups = {}
    for record in records:
        if record['nlink'] > 1:
            groups.setdefault((record['inode'], record['sha256']), []).append(record['path'])
    return {key: sorted(paths) for key, paths in groups.items() if len(paths) > 1}


def seal(prefix, output, name, epoch, identity):
    """Write a deterministic tar.gz that stores duplicate material once as hardlinks."""
    prefix, output = Path(prefix).resolve(strict=True), Path(output)
    need(not output.exists(), 'seal output already exists: ' + str(output))
    records = walk(prefix)
    groups = inode_groups(records)
    primary_of = {}
    for (_, sha), paths in groups.items():
        need(all((prefix / path).is_file() for path in paths), 'hardlink group lost a member')
        for path in paths[1:]:
            primary_of[path] = paths[0]
    output.mkdir(parents=True)
    archive = output / name
    members = []
    with archive.open('xb') as destination, gzip.GzipFile(
            fileobj=destination, filename='', mtime=epoch) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as tar:
            root = PurePosixPath(name[:-len('.tar.gz')]) if name.endswith('.tar.gz') else PurePosixPath(name)
            for record in records:
                path = prefix / record['path']
                info = tarfile.TarInfo(str(root / record['path']))
                info.mtime, info.uid, info.gid, info.uname, info.gname = epoch, 0, 0, '', ''
                info.mode = 0o755 if record['executable'] else 0o644
                if record['path'] in primary_of:
                    info.type, info.linkname = tarfile.LNKTYPE, str(root / primary_of[record['path']])
                    tar.addfile(info)
                    members.append({'path': record['path'], 'link_to': primary_of[record['path']],
                                    'bytes': record['bytes'], 'sha256': record['sha256'],
                                    'executable': record['executable']})
                    continue
                payload = path.read_bytes()
                need(digest_bytes(payload) == record['sha256'], 'tree changed during seal: ' + record['path'])
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
                members.append({'path': record['path'], 'bytes': record['bytes'],
                                'sha256': record['sha256'],
                                'executable': record['executable']})
    manifest = {'schema': 1, 'identity': identity, 'root': name[:-len('.tar.gz')],
                'archive': {'name': name, 'bytes': archive.stat().st_size, 'sha256': digest(archive)},
                'files': members, 'hardlink_groups': [sorted(paths) for paths in groups.values()],
                'duplicate_members': sum(1 for member in members if 'link_to' in member)}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def extract(archive, destination, manifest):
    """Extract a sealed archive and re-verify every recorded member identity."""
    archive, destination = Path(archive), Path(destination)
    need(archive.is_file(), 'archive missing: ' + str(archive))
    need(not destination.exists(), 'extraction target exists: ' + str(destination))
    destination.mkdir(parents=True)
    root = manifest.get('root')
    need(isinstance(root, str) and root and '/' not in root, 'invalid archive root')
    actual = {}
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar.getmembers():
            safe_relative(member.name)
            need(member.name == root or member.name.startswith(root + '/'),
                 'archive member outside the root: ' + member.name)
            if member.name == root or member.isdir():
                continue
            relative = member.name[len(root) + 1:]
            need(member.isfile() or member.islnk(), 'unexpected archive member type: ' + member.name)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.islnk():
                safe_relative(member.linkname)
                need(member.linkname.startswith(root + '/'), 'hardlink outside the root')
                linked = destination / member.linkname[len(root) + 1:]
                need(linked.is_file(), 'hardlink target is missing: ' + member.linkname)
                if target.exists():
                    target.unlink()
                os.link(linked, target)
            else:
                source = tar.extractfile(member)
                need(source is not None, 'unreadable archive member: ' + member.name)
                with source:
                    target.write_bytes(source.read())
                os.chmod(target, member.mode & 0o777)
            actual[relative] = target
    recorded = {member['path']: member for member in manifest['files']}
    problems = []
    if set(actual) != set(recorded):
        problems.append('extracted member set differs from the manifest')
    for relative, path in actual.items():
        member = recorded.get(relative)
        if member is None:
            continue
        status = path.stat()
        if status.st_size != member['bytes'] or digest(path) != member['sha256']:
            problems.append('extracted file differs: ' + relative)
        if 'executable' not in member:
            problems.append('manifest member records no mode: ' + relative)
        elif bool(status.st_mode & 0o111) != bool(member['executable']):
            problems.append('extracted mode differs: ' + relative)
    for group in manifest.get('hardlink_groups') or []:
        if len(group) < 2:
            continue
        digests = {digest(destination / path) for path in group}
        if len(digests) != 1:
            problems.append('hardlink group content differs: ' + group[0])
    return {'schema': 1, 'archive': manifest.get('archive'), 'root': root,
            'members': len(actual), 'files': walk(destination), 'problems': problems,
            'accepted': not problems}
