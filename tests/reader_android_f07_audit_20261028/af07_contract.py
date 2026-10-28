"""Fail-closed retrospective Android F07 contract; no payload execution."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = PACKAGE_SHA = 'ffdb3e5a84dbc05159c8f1982160dc39dff0f951'
PACKAGE_RUN, PACKAGE_ATTEMPT = 40773048325, 1
PACKAGE_WORKFLOW = '.github/workflows/android-f07-capture-20261028.yml'
PACKAGE_BRANCH = 'codex/android-f07-capture-20261028'
BRANCH = 'codex/android-f07-audit-20261028'
WORKFLOW = '.github/workflows/android-f07-audit-20261028.yml'
DOC = 'docs/reader-total-progress/android-f07-audit-20261028.md'
OWNED = 'tests/reader_android_f07_audit_20261028/'
OUT = ROOT / 'build/android-f07-audit'
SDK = 'build/wave3/sdk-stage'
MODULES = 'build/wave3/stage'
APK_SHA = 'c4f681aade60a4b1621153a65bbd2e6a7c2bf3f00436c5f130f49ec4762968eb'
PINS = {
    'capture': (12853023869, 'android-f07-capture-40773048325-1', 187948355,
                '3f47dd3a2a5d5549f1636b8393929fb8ae769c01635c662936618b007cdad4d1'),
    'f06': (12854136422, 'f06-android-40773048325-1', 19702592,
            '61b2de12f916f39cacd690852cb4b91130952fea6b14cdd3d2bc6e18494a88cb'),
}


def require(value, message):
    if not value: raise ValueError(message)


def actions_only():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    require(os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'wrong repository')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): result.update(chunk)
    return result.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def identity():
    return dict(audit_sha=os.environ['GITHUB_SHA'], audit_run=os.environ['GITHUB_RUN_ID'],
                audit_attempt=os.environ['GITHUB_RUN_ATTEMPT'], package_sha=PACKAGE_SHA,
                package_run=PACKAGE_RUN, package_attempt=PACKAGE_ATTEMPT)


def guard():
    actions_only()
    def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    require(git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'checkout SHA differs')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH, 'dedicated audit branch only')
    git('merge-base', '--is-ancestor', BASE, 'HEAD')
    changed = git('diff', '--name-status', '--no-renames', BASE, 'HEAD').splitlines()
    require(changed, 'no audit source changes')
    for line in changed:
        status, path = line.split('\t')
        require(status == 'A' and (path.startswith(OWNED) or path in (DOC, WORKFLOW)), 'outside additive audit scope: ' + line)
    require(not git('status', '--porcelain', '--untracked-files=no'), 'tracked source dirty')
    return dict(identity(), changed=changed)


def safe_name(name):
    require(name and '\\' not in name and ':' not in name and not name.startswith('/') and
            all(p not in ('', '.', '..') for p in name.split('/')), 'unsafe path: ' + name)
    return name


def members(bundle):
    seen, aliases, files, directories, size = set(), {}, set(), set(), 0
    for item in bundle.infolist():
        name = item.filename[:-1] if item.is_dir() else item.filename
        safe_name(name)
        mode = (item.external_attr >> 16) & 0o170000
        require(mode in (0, stat.S_IFREG, stat.S_IFDIR), 'special ZIP member')
        require(mode != stat.S_IFDIR or item.is_dir(), 'ZIP directory mismatch')
        require(mode != stat.S_IFREG or not item.is_dir(), 'ZIP file mismatch')
        parts = name.split('/')
        for count in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:count]); key = unicodedata.normalize('NFC', prefix).casefold()
            require(key not in aliases or aliases[key] == prefix, 'ZIP alias')
            aliases[key] = prefix
            if count < len(parts):
                require(key not in files, 'ZIP parent/file collision'); directories.add(key)
        require(key not in seen, 'duplicate ZIP member'); seen.add(key)
        if item.is_dir():
            require(key not in files, 'ZIP file/directory collision'); directories.add(key)
        else:
            require(key not in directories, 'ZIP directory/file collision'); files.add(key)
        size += item.file_size
        require(not item.flag_bits & 1 and item.file_size <= 1024**3 and size <= 5 * 1024**3, 'ZIP budget/encryption')
    return bundle.infolist()


def extract(archive, folder):
    require(not folder.exists(), 'fresh extraction required')
    with zipfile.ZipFile(archive) as bundle:
        infos = members(bundle); folder.mkdir(parents=True)
        for item in infos:
            if item.is_dir(): continue
            destination = folder / item.filename; destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, destination.open('wb') as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b''): target.write(chunk)
    return folder


def allocated(path):
    # Reuse the frozen successful parser under a distinct module name; never
    # execute the producer or share a generic `contract` module with it.
    source = ROOT / 'tests/reader_android_f07_capture_20261028/contract.py'
    spec = importlib.util.spec_from_file_location('frozen_android_capture_contract', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.elf_allocated(path.read_bytes())


def symbols(text):
    defined, undefined, rows = set(), set(), []
    for line in text.splitlines():
        match = re.fullmatch(r'\s*(?:[0-9a-fA-F]+\s+)?([A-Za-z])\s+(\S+)\s*', line)
        if not match:
            require(not line.strip() or (line.endswith(':') and not any(c.isspace() for c in line.strip())),
                    'unrecognized native symbol line: ' + line)
            continue  # blank lines or exact archive/member headings only
        kind, name = match.groups(); name = name.split('@', 1)[0]
        require(kind in 'ABCDGINRSTUVWabcdginrstuvw', 'unsupported ELF/nm symbol type: ' + kind)
        missing = kind in ('U', 'w', 'v')
        (undefined if missing else defined).add(name)
        rows.append(dict(name=name, kind=kind, undefined=missing))
    require(rows, 'native symbol output empty/unrecognized')
    return dict(defined=sorted(defined), undefined=sorted(undefined), rows=rows)


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


def runtime_symbol(name):
    # These are ABI/compiler/standard-library namespaces, NOT application helpers.
    return name.startswith(('__cxa', '__gxx', '__stack_chk', '__clang', '__ubsan', '__asan',
        '__tsan', '__Unwind', '_Unwind', '__dynamic_cast', '_ZNSt', '_ZNKSt', '_ZSt',
        '_ZNS', '_ZTISt', '_ZTSSt', '_ZTVSt', '_Zdl', '_Zda', '_Zn', '__libcpp'))


def private_imports(tables, owners, public, dependencies, sdk_definitions, system_definitions):
    definitions = {'EXReader': set(sdk_definitions)}
    for name, table in tables.items(): definitions.setdefault(owners[name], set()).update(table['defined'])
    findings = {}
    for archive, table in tables.items():
        owner = owners[archive]
        system_names = system_definitions.get(archive, set()) if isinstance(system_definitions, dict) else system_definitions
        own = set().union(*(set(t['defined']) for n, t in tables.items() if owners[n] == owner))
        allowed_owners, queue = {owner}, list(dependencies.get(owner, ()))
        while queue:
            candidate = queue.pop()
            if candidate in allowed_owners: continue
            allowed_owners.add(candidate); queue.extend(dependencies.get(candidate, ()))
        suspicious = set(table['undefined']) - own
        rows = []
        for name in sorted(suspicious):
            providers = sorted(package for package, names in definitions.items() if name in names)
            public_providers = [package for package in providers
                                if package in allowed_owners and name in public.get(package, ())]
            if len(providers) == 1 and public_providers == providers: continue
            # System allowance is an exact symbol observed in the pinned NDK,
            # never a blanket C++/private-name prefix. Proprietary providers take
            # precedence except independently observed standard ABI definitions.
            if name in system_names and (not providers or runtime_symbol(name)): continue
            rows.append(dict(symbol=name, reason='cross-package-private-or-undeclared-or-ambiguous-owner' if providers else 'unknown-unresolved-import',
                             observed_providers=providers, allowed_owners=sorted(allowed_owners)))
        findings[archive] = rows
    return findings


def exact_workspace_path(path, workspace, prefix):
    require(path.startswith('/') and str(PurePosixPath(path)) == path and
            all(part not in ('.', '..') for part in path.split('/')[1:]), 'noncanonical producer path')
    marker = workspace.rstrip('/') + '/' + prefix.rstrip('/') + '/'
    require(path.startswith(marker), 'wrong original workspace/prefix: ' + path)
    name = prefix.rstrip('/') + '/' + path[len(marker):]
    safe_name(name)
    return name


def sqlite_map_owner(text):
    current, found = None, []
    for line in text.splitlines():
        columns = line.split(None, 4)
        if len(columns) != 5 or not all(re.fullmatch(r'[0-9a-fA-F]+', c) for c in columns[:4]): continue
        value = columns[4].strip()
        if ':(' in value:
            origin = re.fullmatch(r'(.+):\([^\n]*\)', value)
            require(origin is not None, 'unrecognized LLD input contribution')
            current = origin[1]  # resets for archives, standalone objects and internal contributions
        elif value.startswith('.'):
            current = None  # new output section is not owned by the previous input
        elif value == 'sqlite3_open_v2':
            require(current is not None, 'SQLite symbol has no actual input contribution')
            found.append(current)
    require(len(found) == 1, 'SQLite map definition missing/duplicated')
    return found[0]


def assign_unique(mapping, key, value):
    require(key not in mapping, 'duplicate installed manifest/header owner: ' + key)
    mapping[key] = value


def target_properties(text):
    # Configuration-specific generated CMake exports indent their closing line.
    return re.findall(r'set_target_properties\(([A-Za-z0-9_:]+)\s+PROPERTIES\s+(.*?)\n\s*\)', text, re.S)


def header_coverage(installed, owners):
    installed, owned = set(installed), set(owners)
    return dict(installed=sorted(installed), owned=sorted(owned),
                unowned=sorted(installed - owned), absent=sorted(owned - installed))


def require_header_coverage(report):
    require(report['installed'] and not report['unowned'] and not report['absent'],
            'installed include ownership incomplete: ' + json.dumps(report, sort_keys=True))


def system_scope(root, records, sonames, stubs, observed_system):
    visited, queue, allowed = set(), [root], set()
    while queue:
        current = queue.pop()
        if current in visited: continue
        visited.add(current); record = records[current]
        for dependency in record['needed']:
            require('/' not in dependency, 'noncanonical ELF dependency')
            if dependency in sonames: queue.append(sonames[dependency])
            else:
                require(dependency in stubs, 'unknown system ELF dependency')
                allowed.update(stubs[dependency])
        # A root can resolve its own statically linked definitions. Another
        # image's hidden/local definitions cannot satisfy a dynamic import.
        visible = record['full'] if current == root else record['dynamic']
        allowed.update(set(visible['defined']) & set(observed_system))
    return visited, allowed


def image_imports(image, records, reached, system, sdk_providers, sdk_public):
    allowed = set(system)
    for dependency in reached - {image}:
        if dependency in sdk_providers:
            allowed.update(set(records[dependency]['dynamic']['defined']) & set(sdk_public))
    record = records[image]
    undefined = set(record['full']['undefined']) | set(record['dynamic']['undefined'])
    return sorted(undefined - set(record['full']['defined']) - allowed)
