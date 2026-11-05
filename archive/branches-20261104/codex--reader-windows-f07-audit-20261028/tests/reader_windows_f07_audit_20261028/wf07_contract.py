"""Fail-closed Windows static ownership audit; execution is Actions-only."""
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
SOURCE = '739089d782c2d76f2708446175ccd24fce3b2e3b'
RUN, ATTEMPT = 40776571774, 1
BRANCH = 'codex/reader-windows-f07-audit-20261028'
OWNED = 'tests/reader_windows_f07_audit_20261028/'
WORKFLOW = '.github/workflows/reader-windows-f07-audit-20261028.yml'
DOC = 'docs/reader-total-progress/reader-windows-f07-audit-20261028.md'
OUT = ROOT / 'build/reader-windows-f07-audit-20261028'
BUILD = 'build/f06/windows-build/'
STAGES = ('sdk-stage', 'product-stage', 'raw-stage')
FROZEN_SHA = '3c82fd9329ea1515733c80fa71b81a8381470b806525acbdd81bf59e1ad45030'
PINS = {
    'capture': (12854809371, 'windows-f07-capture-40776571774-1', 96047453,
                '8fa16dfeae48214991b35231070b6842ff2720a0a4a37c1d7247980c57fec1ea'),
    'authentication': (12855277110, 'windows-f07-capture-authenticated-40776571774-1', 4625,
                'cdb8ae819bc03c8f7623862c08ac0a24e3139946674830ffb73efadfa6924a8a'),
}
GAPS = [
    'Original external MSVC/Windows SDK static libraries and inspector tool hashes were not retained; current runner tools are inspection only, not original provider identity.',
    'Original platform DLL bytes were not retained; observed PE import edges are not verified DLL provider identity.',
    'This audit covers the pinned new Windows capture, not the old six-platform run, other platforms, behavior or release admission.',
]


def require(value, message):
    if not value: raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): value.update(block)
    return value.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def identity():
    return dict(audit_sha=os.environ['GITHUB_SHA'], audit_run=os.environ['GITHUB_RUN_ID'],
                audit_attempt=os.environ['GITHUB_RUN_ATTEMPT'], package_sha=SOURCE,
                package_run=RUN, package_attempt=ATTEMPT)


def guard():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'repository Actions only')
    def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    require(git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'checkout source differs')
    require(os.environ['GITHUB_REF'] == 'refs/heads/' + BRANCH, 'dedicated audit branch only')
    git('merge-base', '--is-ancestor', BASE, 'HEAD')
    changes = git('diff', '--name-status', '--no-renames', BASE, 'HEAD').splitlines()
    require(changes, 'empty audit source')
    for row in changes:
        status, path = row.split('\t')
        require(status == 'A' and (path.startswith(OWNED) or path in (WORKFLOW, DOC)), 'foreign/old path changed')
    require(not git('status', '--porcelain', '--untracked-files=no'), 'dirty tracked source')
    require(digest(ROOT / OWNED / 'frozen_capture.py') == FROZEN_SHA, 'frozen capture validator changed')
    original = subprocess.check_output(['git', 'show', SOURCE + ':tests/reader_windows_f07_capture_20261028/capture_contract.py'], cwd=ROOT)
    require(hashlib.sha256(original).hexdigest() == FROZEN_SHA, 'validator differs from original successful capture source')
    for tree in ('src', 'include', 'cmake', 'bindings', 'apps', 'examples', 'tools'):
        require(git('rev-parse', 'HEAD:' + tree) == git('rev-parse', SOURCE + ':' + tree), 'producer project tree differs: ' + tree)
    return dict(identity(), changed=changes)


def exact_path(value, workspace):
    value = value.strip('"').replace('/', '\\')
    path, root = PureWindowsPath(value), PureWindowsPath(workspace)
    require(path.is_absolute() and '..' not in path.parts, 'noncanonical original path: ' + value)
    relative = path.relative_to(root)
    require(relative.parts and all(p not in ('.', '..') for p in relative.parts), 'invalid original relative path')
    return relative.as_posix()


def tokens(text):
    # CMake's retained MSVC command/rsp spelling: quotes group literal paths;
    # do not use POSIX backslash unescaping on Windows paths.
    result, value, quoted = [], [], False
    for char in text:
        if char == '"': quoted = not quoted
        elif char.isspace() and not quoted:
            if value: result.append(''.join(value)); value = []
        else: value.append(char)
    require(not quoted, 'unbalanced command quoting')
    if value: result.append(''.join(value))
    return result


def coff_symbols(text):
    rows = []
    for line in text.splitlines():
        if re.search(r'\b(?:External|WeakExternal)\s*\|', line):
            match = re.fullmatch(r'\s*[0-9A-Fa-f]+\s+([0-9A-Fa-f]+)\s+(UNDEF|ABS|SECT[0-9A-Fa-f]+)\s+.*?\b(External|WeakExternal)\s*\|\s*(\S+)(?:\s+.*)?', line)
            require(match is not None, 'unparsed COFF external row: ' + line)
            value, section, storage, name = match.groups()
            undefined = section == 'UNDEF' and int(value, 16) == 0
            # Weak fallback records remain unresolved dependencies, never an
            # empty-symbol success or a C++ prefix exemption.
            rows.append(dict(name=name, undefined=undefined, weak=storage == 'WeakExternal', section=section))
    require('COFF SYMBOL TABLE' in text and rows, 'empty/unsupported COFF archive/object (including LTCG/import-only)')
    return dict(defined=sorted({r['name'] for r in rows if not r['undefined']}),
                undefined=sorted({r['name'] for r in rows if r['undefined']}),
                weak=sorted({r['name'] for r in rows if r['weak']}))


def declaration_scopes(text):
    # Preserve linkage declaration scope, but discard balanced implementation /
    # aggregate bodies. A local extern declaration inside an inline body is not
    # an installed public API. Quoted text cannot manufacture declarations.
    output, stack = list(text), []
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', text, re.S):
        value, start, end = token.group(), token.start(), token.end()
        if value == '{':
            linkage = re.search(r'\bextern\s+"C"\s*$', text[:start]) is not None
            stack.append((start, linkage))
        elif value == '}':
            require(stack, 'unbalanced public-header declaration scope')
            opening, linkage = stack.pop()
            if not linkage:
                for index in range(opening + 1, start):
                    if output[index] != '\n': output[index] = ' '
        elif not (value == '"C"' and re.search(r'\bextern\s*$', text[:start])):
            for index in range(start, end):
                if output[index] != '\n': output[index] = ' '
    require(not stack, 'unclosed public-header declaration scope')
    return ''.join(output)


def public_entries(text, sdk=False):
    # Comment markers inside quoted examples are not actual comments.
    text = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*',
                  lambda m: m.group() if m.group()[0] in ('"', "'") else '\n' * m.group().count('\n') + ' ',
                  text, flags=re.S)
    text = re.sub(r'^\s*#(?:[^\n]*\\\n)*[^\n]*', '', text, flags=re.M)
    text = declaration_scopes(text)
    names = set()
    # Actual public C declarations, not guessed application prefixes. Installed
    # rfl_* and roe_* APIs belong to their declaring package too. Static/inline
    # implementation declarations and callback typedefs do not grant imports.
    for match in re.finditer(r'(?:(?<=;)|(?<={)|(?<=})|\A)\s*([^;{}()]+?)\b([A-Za-z_]\w*)\s*\(([^;{}]*)\)\s*;', text, re.S):
        prefix, name, _ = match.groups()
        if re.search(r'\b(?:typedef|static|inline|namespace|template|class|return|throw|co_return|goto|case|if|else|for|while|do|switch|break|continue|try|catch|delete|new|sizeof|alignof|decltype|static_assert|_Static_assert)\b|=', prefix): continue
        type_prefix = re.sub(r'\bextern\s+"C"\s*', '', prefix)
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9\s*]*', type_prefix.strip()): continue
        if sdk and not (re.search(r'\bEXR_API\b', prefix) and name.startswith('exr_')): continue
        names.add(name)
    names.update(re.findall(r'\bSQLITE_API\b[^;{}()]*\b(sqlite3_[A-Za-z0-9_]+)\s*(?:\[[^]]*\])?\s*;', text))
    return names


def archive_objects(graph, target):
    graph = graph.replace('$\n', '')
    matches = re.findall(r'^build\s+' + re.escape(target) + r'\.lib:\s+(\S+)\s+([^\n]*)$', graph, re.M)
    require(len(matches) == 1 and '_STATIC_LIBRARY_LINKER_' in matches[0][0], 'missing/ambiguous actual archive link rule: ' + target)
    values = matches[0][1].split(' |', 1)[0].split()
    require(values and all(value.endswith('.obj') and '$' not in value for value in values), 'unsupported archive object spellings')
    objects = [value.replace('\\', '/') for value in values]
    require(len(objects) == len(set(objects)), 'duplicate archive link object')
    return set(objects)


def original_build_directory(cache, workspace, label):
    directories = re.findall(r'^CMAKE_CACHEFILE_DIR:INTERNAL=(.+)$', cache, re.M)
    require(len(directories) == 1 and exact_path(directories[0], workspace) == BUILD + label,
            'original dependency build directory differs from retained CMake cache')
    return str(PureWindowsPath(workspace) / BUILD / label)


def dependency_path(value, workspace, original_directory=None):
    """Resolve lexical include parents, never silently drop project aliases."""
    path, root = PureWindowsPath(value), PureWindowsPath(workspace)
    if not path.is_absolute():
        require(original_directory is not None and not path.drive and not path.root,
                'relative dependency lacks unambiguous original build directory')
        # Context comes from the original retained CMake cache, not extraction
        # cwd or a basename search. Drive-relative/root-relative aliases reject.
        exact_path(original_directory, workspace)
        path = PureWindowsPath(original_directory) / path
    require(path.is_absolute(), 'relative/ambiguous original include dependency')
    normalized = []
    for part in path.parts[1:]:
        if part == '..':
            require(normalized, 'include dependency escapes filesystem root')
            normalized.pop()
        elif part != '.': normalized.append(part)
    resolved = PureWindowsPath(path.anchor, *normalized)
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        # A spelling that begins inside the project but escapes it is unknown,
        # not a proven system header. Ordinary absolute outside-workspace paths
        # remain under the fixed original-external-provider provenance gap.
        try: path.relative_to(root)
        except ValueError: return None
        raise ValueError('original project include escapes workspace')


def private_header_dependencies(text, expected_objects, private_headers, workspace, label, repository_dependencies=None,
                                empty_dependency_groups=None, original_directory=None):
    active, covered, seen, uses = None, set(), set(), []
    advertised, observed = 0, 0
    for line in text.splitlines():
        match = re.match(r'([^\s].+?\.obj):\s+#deps\s+(\d+)', line)
        if match:
            require(active is None or observed == advertised, 'truncated object dependency group')
            obj = match[1].replace('\\', '/')
            active = (expected_objects[obj], obj) if obj in expected_objects else None
            advertised, observed = int(match[2]), 0
            if active:
                empty_record = dict(
                    build=label, owner=active[0], object=obj, advertised=advertised,
                    original_group_header=line)
                # Strict callers still reject. The native partial-report path
                # may retain this unresolved group, but never count it covered.
                if empty_dependency_groups is None:
                    require(advertised > 0, 'empty exported-target dependency record: ' + json.dumps(empty_record, sort_keys=True))
                require(obj not in seen, 'duplicate object dependency group')
                seen.add(obj)
                if advertised > 0: covered.add(obj)
                else: empty_dependency_groups.append(empty_record)
            continue
        if not line.startswith('    '):
            require(active is None or observed == advertised, 'unparsed/truncated object dependency group')
            active = None
        if active and line.startswith('    '):
            observed += 1
            require(line.strip() and observed <= advertised, 'extra/empty object dependency row')
            try: name = dependency_path(line.strip(), workspace, original_directory)
            except ValueError:
                if repository_dependencies is not None:
                    repository_dependencies.append(dict(consumer=active[0], object=active[1], path=line.strip(),
                        build=label, unclassified=True, original_build_directory=original_directory))
                continue
            if name is None: continue
            if repository_dependencies is not None:
                repository_dependencies.append(dict(consumer=active[0], object=active[1], path=name, build=label,
                    original_spelling=line.strip(), original_build_directory=original_directory))
            if name in private_headers and active[0] not in private_headers[name]:
                uses.append(dict(consumer=active[0], object=active[1], header=name,
                     owners=private_headers[name], build=label, evidence='actual retained Ninja dependency database'))
    require(active is None or observed == advertised, 'truncated final object dependency group')
    return uses, covered


def source_include_boundaries(records, source_roots, installed_files):
    findings, unknown = [], []
    for row in records:
        name = row['path']
        if row.get('unclassified'):
            unknown.append(row); continue
        if name in installed_files: continue
        candidates = [root for root in source_roots if name == root or name.startswith(root.rstrip('/') + '/')]
        if not candidates:
            unknown.append(row); continue
        longest = max(candidates, key=len)
        owners = source_roots[longest]
        if row['consumer'] not in owners:
            findings.append(dict(row, source_root=longest, owners=sorted(owners),
                reason='cross-package implementation source/include; not an installed public entry'))
        elif len(owners) != 1:
            unknown.append(dict(row, reason='source root shared by multiple exported package owners'))
    return findings, unknown


def installed_exports(configurations, libraries):
    targets, locations, dependencies = {}, {}, {}
    for path, text in configurations.items():
        layout = re.fullmatch(r'(.+)/(?:lib/cmake/([^/]+)|share/([^/]+)/cmake)/[^/]+\.cmake', path)
        require(layout is not None, 'unsupported installed export layout: ' + path)
        stage, package = layout[1], layout[2] or layout[3]
        for target, kind in re.findall(r'add_library\(([\w:]+)\s+(STATIC|INTERFACE|SHARED)\s+IMPORTED\)', text):
            require(target.startswith(package + '::') and target not in targets, 'duplicate/wrong export namespace')
            targets[target] = dict(owner=package, kind=kind)
        for target, body in re.findall(r'set_target_properties\(([\w:]+)\s+PROPERTIES\s+(.*?)\)', text, re.S):
            dependencies.setdefault(target.split('::')[0], set()).update(re.findall(r'([A-Za-z0-9_]+)::[A-Za-z0-9_]+', body))
            for value in re.findall(r'IMPORTED_LOCATION(?:_[A-Z]+)?\s+"([^"]+)"', body):
                match = re.fullmatch(r'\$\{(?:_IMPORT_PREFIX|PACKAGE_PREFIX_DIR)\}/(.+\.lib)', value)
                require(match is not None and '..' not in match[1].split('/'), 'unsupported installed library location')
                name = stage + '/' + match[1]
                require(target not in locations or locations[target] == name, 'multiple target locations')
                locations[target] = name
        for target, body in re.findall(r'set_property\(TARGET\s+([\w:]+)\s+PROPERTY\s+INTERFACE_LINK_LIBRARIES\s+"([^"]*)"\)', text):
            dependencies.setdefault(target.split('::')[0], set()).update(re.findall(r'([A-Za-z0-9_]+)::[A-Za-z0-9_]+', body))
    owners, archive_targets = {}, {}
    for target, name in locations.items():
        require(target in targets and targets[target]['kind'] == 'STATIC' and name not in owners, 'ambiguous/missing static library owner')
        owners[name], archive_targets[name] = targets[target]['owner'], target.split('::', 1)[1]
    require(set(owners) == set(libraries) and owners, 'installed library/export coverage differs: ' + json.dumps(dict(
        unowned_libraries=sorted(set(libraries) - set(owners)), exports_without_files=sorted(set(owners) - set(libraries)),
        static_targets_without_locations=sorted(target for target, info in targets.items()
            if info['kind'] == 'STATIC' and target not in locations)), sort_keys=True))
    return owners, archive_targets, dependencies


def install_entries(lines, workspace, inventory):
    # Actual CMake SDK manifest repeats identical WebP installation operations.
    # Preserve their counts; assign each retained final file once in this manifest.
    # Different spellings and ownership from another manifest remain forbidden.
    names = [exact_path(line, workspace) for line in lines]
    require(names and set(names) <= set(inventory),
            'unretained installed file: ' + str(sorted(set(names) - set(inventory))))
    aliases, spellings, counts = {}, {}, {}
    for line, name in zip(lines, names):
        key = name.casefold()
        require(key not in aliases or aliases[key] == name, 'installed path spelling alias')
        require(name not in spellings or spellings[name] == line, 'installed operation spelling alias')
        aliases[key] = name; spellings[name] = line; counts[name] = counts.get(name, 0) + 1
    return list(dict.fromkeys(names)), {name: count for name, count in counts.items() if count > 1}


def private_imports(tables, owners, public, dependencies, image_imports):
    definitions = {}
    for name, table in tables.items(): definitions.setdefault(owners[name], set()).update(table['defined'])
    findings = {}
    for archive, table in tables.items():
        owner = owners[archive]
        allowed, queue = {owner}, list(dependencies.get(owner, ()))
        while queue:
            candidate = queue.pop()
            if candidate in allowed: continue
            allowed.add(candidate); queue.extend(dependencies.get(candidate, ()))
        rows = []
        for symbol in sorted(set(table['undefined']) - definitions[owner]):
            providers = sorted(package for package, names in definitions.items() if symbol in names)
            if len(providers) == 1 and providers[0] in allowed and symbol in public.get(providers[0], ()):
                continue
            # Only an exact actually observed final PE import is classified as
            # a dynamic edge. Static CRT/system references remain explicit gaps.
            if not providers and symbol in image_imports:
                rows.append(dict(symbol=symbol, providers=[], reason='observed-pe-import-but-original-dll-provider-unverified'))
                continue
            rows.append(dict(symbol=symbol, providers=providers,
                reason='private-undeclared-or-ambiguous-cross-package' if providers else 'unknown-or-unretained-static-provider'))
        findings[archive] = rows
    public_owners = {}
    for package, symbols in public.items():
        for symbol in symbols:
            providers = sorted(owner for owner, values in definitions.items() if symbol in values)
            if len(providers) > 1 or (providers and providers[0] != package):
                public_owners.setdefault(symbol, dict(declared_by=[], defined_by=providers))['declared_by'].append(package)
    return findings, public_owners


def map_rows(text):
    active, rows = False, []
    for line in text.splitlines():
        if 'Publics by Value' in line or line.strip() == 'Static symbols': active = True; continue
        if 'entry point at' in line: active = False; continue
        if not active or not re.match(r'\s*[0-9A-Fa-f]{4}:', line): continue
        match = re.fullmatch(r'\s*([0-9A-Fa-f]{4}):([0-9A-Fa-f]{8,16})\s+(\S+)\s+([0-9A-Fa-f]{8,16})\s+(?:[fi]\s+)*(.+?)\s*', line)
        require(match is not None, 'unparsed final map contribution: ' + line)
        section, offset, symbol, address, origin = match.groups()
        rows.append(dict(symbol=symbol, address=int(address, 16), section=section, offset=offset, origin=origin))
    require(rows and 'Preferred load address' in text, 'unrecognized/empty MSVC final map')
    return rows


def map_parts(origin):
    match = re.fullmatch(r'(.+):([^:]+\.(?:obj|o))', origin, re.I)
    return (match[1], match[2]) if match else (origin, None)


def map_origin(origin, inputs, workspace=None):
    keys = {}
    for name in inputs:
        leaf = PureWindowsPath(name).name.lower()
        for key in ({leaf, leaf.removesuffix('.lib')} if leaf.endswith('.lib') else {leaf}):
            require(key not in keys or keys[key] == name, 'duplicate final link basename: ' + key)
            keys[key] = name
    # Link.exe reports archive-basename:member; resolve only through the exact
    # final command/rsp input set, never through the whole installed inventory.
    label, member = map_parts(origin)
    if '/' in label or '\\' in label:
        require(workspace is not None, 'explicit map input path requires original workspace')
        path = PureWindowsPath(label)
        if not path.is_absolute(): path = PureWindowsPath(workspace) / BUILD / 'host' / path
        relative = exact_path(str(path), workspace)
        options = {relative, relative + '.lib'} if member and not relative.lower().endswith('.lib') else {relative}
        found = options & set(inputs)
        return next(iter(found)) if len(found) == 1 else None
    leaf = PureWindowsPath(label).name.lower()
    return keys.get(leaf)


def pe_imports(text):
    dll, records = None, []
    for line in text.splitlines():
        if line.strip() == 'Summary': dll = None; continue
        match = re.fullmatch(r'\s*([\w.+-]+\.dll)\s*', line, re.I)
        if match: dll = match[1].lower(); continue
        match = re.fullmatch(r'\s*(?:[0-9A-Fa-f]+\s+){1,3}([A-Za-z_?][^\s]*)\s*', line)
        if dll and match:
            name = match[1]
            if name not in ('time', 'Index', 'Table', 'Address', 'Summary'):
                records.append(dict(dll=dll, symbol=name))
                continue
        if dll and re.match(r'\s*[0-9A-Fa-f]+\s', line) and not any(value in line for value in
                ('Import Address Table', 'Import Name Table', 'time date stamp', 'Index of first forwarder reference')):
            raise ValueError('unsupported/ordinal actual PE import row: ' + line)
    require(records, 'empty/unrecognized actual PE imports')
    return records
