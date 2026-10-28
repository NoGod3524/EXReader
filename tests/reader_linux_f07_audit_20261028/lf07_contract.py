"""Retrospective Linux F07: independent audit source, pinned original program."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SHA = BASE = 'ffea3f173415a7c46afd6d69d09539e71b0648a1'
PACKAGE_RUN, PACKAGE_ATTEMPT = 40773096934, 1
PACKAGE_WORKFLOW = '.github/workflows/reader-linux-f07-capture-20261028.yml'
PACKAGE_BRANCH = 'codex/reader-linux-f07-capture-20261028'
BRANCH = 'codex/reader-linux-f07-audit-20261028'
OWNED = 'tests/reader_linux_f07_audit_20261028/'
WORKFLOW = '.github/workflows/reader-linux-f07-audit-20261028.yml'
DOC = 'docs/reader-total-progress/reader-linux-f07-audit-20261028.md'
OUT = ROOT / 'build/linux-f07-audit'
CAPTURE = dict(id=12853144850, name='linux-f07-capture-40773096934-1', size_in_bytes=105804861,
    digest='sha256:76352c1f88200b65e7bdbb97c4196a0638f2a542f3ab36e86cc74bdfc59e9cdb')


def require(value, message):
    if not value: raise ValueError(message)


def actions_only():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only')
    require(os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'wrong repository')


def sha(data): return hashlib.sha256(data).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): result.update(block)
    return result.hexdigest()


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def identity():
    return dict(audit_sha=os.environ['GITHUB_SHA'], audit_run=os.environ['GITHUB_RUN_ID'],
        audit_attempt=os.environ['GITHUB_RUN_ATTEMPT'], package_sha=PACKAGE_SHA,
        package_run=PACKAGE_RUN, package_attempt=PACKAGE_ATTEMPT)


def package_identity():
    return dict(source_sha=PACKAGE_SHA, run_id=str(PACKAGE_RUN), attempt=str(PACKAGE_ATTEMPT),
        base_sha='8f8acf3234cba747165f001c0c96efe1b911e6ad', target='linux', sdk_version='3.42.0')


def guard():
    actions_only()
    def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    require(git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'checkout SHA differs')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH, 'dedicated audit branch only')
    git('merge-base', '--is-ancestor', BASE, 'HEAD')
    changed = git('diff', '--name-status', '--no-renames', BASE, 'HEAD').splitlines()
    expected = {OWNED + p for p in ('lf07_contract.py', 'lf07_evidence.py', 'lf07_native.py', 'run.py', 'test_lf07.py')} | {WORKFLOW, DOC}
    require({line.split('\t')[1] for line in changed} == expected, 'exact seven additive audit files required')
    require(all(line.startswith('A\t') for line in changed), 'old sources must remain unchanged')
    require(not git('status', '--porcelain', '--untracked-files=no'), 'tracked source dirty')
    return dict(identity(), changed=changed)


def frozen_capture():
    # Load only frozen source, never its producer entrypoint or generic `contract`.
    # Explicit retrospective identity binding is separate from current audit SHA.
    spec = importlib.util.spec_from_file_location('frozen_linux_f07_capture',
        ROOT / 'tests/reader_linux_f07_capture_20261028/contract.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.identity = package_identity
    return module


def symbols(text):
    rows, member = [], None
    for line in text.splitlines():
        match = re.fullmatch(r'\s*(?:([0-9a-fA-F]+)\s+)?([A-Za-z])\s+(\S+)\s*', line)
        if not match:
            if not line.strip(): continue
            require(line.endswith(':') and not re.search(r'\s', line.strip()), 'unrecognized nm row: ' + line)
            member = line[:-1]; continue
        address, kind, versioned = match.groups()
        require(kind in 'ABCDGIRSTUVWabcdgirstuvwNn', 'unsupported nm symbol kind: ' + kind)
        name = versioned.split('@', 1)[0]
        missing = kind in ('U', 'w', 'v')
        rows.append(dict(name=name, versioned=versioned, kind=kind, undefined=missing,
            global_definition=not missing and (kind.isupper() or kind in ('u', 'i')),
            address=int(address, 16) if address else None, member=member))
    require(rows, 'empty/unrecognized native table')
    return dict(rows=rows, defined=sorted({r['name'] for r in rows if not r['undefined']}),
        global_defined=sorted({r['name'] for r in rows if r['global_definition']}),
        undefined=sorted({r['name'] for r in rows if r['undefined']}))


def public_entries(text, sdk=False):
    # Conservative C ABI declarations only. No prefix-wide or C++-helper waiver.
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    text = re.sub(r'^\s*#(?:[^\n]*\\\n)*[^\n]*', '', text, flags=re.M)
    names = set()
    for match in re.finditer(r'(?:(?<=;)|(?<={)|(?<=})|\A)\s*([^;{}()]+?)\b([A-Za-z_]\w*)\s*\(([^;{}]*)\)\s*;', text, re.S):
        prefix, name, _ = match.groups()
        if re.search(r'\b(?:typedef|static|inline|namespace|template|class)\b|=', prefix): continue
        if sdk and not (re.search(r'\bEXR_API\b', prefix) and name.startswith('exr_')): continue
        names.add(name)
    # Public SQLite version data is declared, not a sqlite3_* blanket allowance.
    names.update(re.findall(r'\bSQLITE_API\s+(?:extern\s+)?const\s+char\s+(sqlite3_\w+)\s*\[\s*\]\s*;', text))
    return names


def module_findings(tables, owners, public, dependencies, sdk_definitions, system):
    definitions = {'EXReader': set(sdk_definitions)}
    for path, table in tables.items(): definitions.setdefault(owners[path], set()).update(table['global_defined'])
    result = {}
    for path, table in tables.items():
        owner = owners[path]; own = definitions[owner]
        reachable, queue = {owner}, list(dependencies.get(owner, ()))
        while queue:
            package = queue.pop()
            if package in reachable: continue
            reachable.add(package); queue.extend(dependencies.get(package, ()))
        findings = []
        for name in sorted(set(table['undefined']) - own):
            providers = {p for p, names in definitions.items() if name in names}
            public_providers = {p for p in providers if p in reachable and name in public.get(p, set())}
            # A different package's private symbol cannot be laundered through a
            # same-spelled public declaration or another provider's system symbol.
            if len(providers) == 1 and public_providers == providers: continue
            if not providers and name in system: continue
            # Standard ABI names still need an actually observed platform export.
            # This never exempts an arbitrary private/nonprefixed C++ helper.
            if name in system and abi_symbol(name): continue
            findings.append(dict(symbol=name, providers=sorted(providers), declared_owners=sorted(reachable),
                reason='cross-package-private-or-undeclared-or-ambiguous' if providers else 'unproven-system-or-unresolved'))
        result[path] = findings
    return result


def map_ranges(text):
    require('Linker script and memory map' in text, 'GNU final memory map absent')
    text = text.split('Linker script and memory map', 1)[1]
    text = text.split('Cross Reference Table', 1)[0]
    ranges, section = [], None
    for line in text.splitlines():
        # Input sections carry indentation, address, byte extent and exact object.
        heading = re.match(r'^\s+(\.[^\s]+)(?:\s|$)', line)
        if heading: section = heading[1]
        if line and not line[0].isspace(): section = None
        if not section or not re.match(r'^\.(?:text|data|rodata|bss|sdata|sbss|tdata|tbss)(?:[.$]|$)', section): continue
        match = re.fullmatch(r'\s+(?:\.[^\s]+\s+)?0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)\s+(\S+(?:\.a\([^()]+\)|\.o))\s*', line)
        if match:
            start, size, path = match.groups()
            if int(size, 16): ranges.append(dict(start=int(start, 16), size=int(size, 16), object=path))
    require(ranges, 'GNU map input-section ranges unrecognized')
    return ranges


def symbol_owner(row, ranges):
    require(row['address'] is not None and not row['undefined'], 'defined address required')
    matches = {r['object'] for r in ranges if r['start'] <= row['address'] < r['start'] + r['size']}
    require(len(matches) == 1, 'symbol input owner missing/ambiguous: ' + row['name'] + ' ' + str(sorted(matches)))
    return next(iter(matches))


def archive_compile_sources(graph, archives):
    """Actual installed-library objects only; never probe/test source targets."""
    graph = graph.replace('$\n', '')
    require('$ ' not in graph and '$:' not in graph, 'escaped Ninja paths unsupported')
    rules = {}
    for output, rule, inputs in re.findall(r'^build ([^:\n]+): (\S+)([^\n]*)$', graph, re.M):
        if ' ' not in output: rules[output] = (rule, inputs.split(' |', 1)[0].split())
    sources = set()
    for archive in archives:
        require(archive in rules and '_STATIC_LIBRARY_LINKER' in rules[archive][0], 'installed archive has no native static link rule: ' + archive)
        objects = rules[archive][1]
        require(objects, 'archive has no actual object inputs')
        for obj in objects:
            require(obj in rules and re.match(r'^(?:C|CXX)_COMPILER', rules[obj][0]), 'archive object has no known compilation rule: ' + obj)
            require(len(rules[obj][1]) == 1, 'ambiguous compiler source input')
            sources.add(rules[obj][1][0])
    return sorted(sources)


def abi_symbol(name):
    return re.match(r'^(?:__cxa|__gxx|_Unwind|__dynamic_cast|_Z(?:NK?St|St|NS|TISt|TSSt|TVSt|dl|da|n[aw]))', name) is not None


def final_undefined_findings(full, dynamic, project_definitions, system_rows):
    """Final image U/weak-U union; preserve ELF symbol versions and actual scope."""
    def key(row): return row['versioned'].replace('@@', '@')
    own = {key(row) for table in (full, dynamic) for row in table['rows'] if row['global_definition']}
    system = set()
    for row in system_rows:
        if not row['global_definition']: continue
        system.add(key(row))
        if '@@' in row['versioned'] or '@' not in row['versioned']: system.add(row['name'])
    undefined = {key(row): row for table in (full, dynamic) for row in table['rows'] if row['undefined']}
    findings = []
    for symbol, row in sorted(undefined.items()):
        if symbol in own: continue
        providers = sorted(p for p, names in project_definitions.items() if row['name'] in names)
        if symbol in system and (not providers or abi_symbol(row['name'])): continue
        findings.append(dict(symbol=symbol, kind=row['kind'], project_providers=providers,
            reason='project-definition-not-in-actual-final-image' if providers else 'unresolved-final-image-import-or-version'))
    return findings


def target_properties(text):
    # Generated *Targets-release.cmake indents its closing parenthesis, unlike
    # the principal *Targets.cmake. Whitespace changes no owner/location rule.
    return re.findall(r'set_target_properties\(([A-Za-z0-9_:]+)\s+PROPERTIES\s+(.*?)\n\s*\)', text, re.S)
