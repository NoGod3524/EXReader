"""Inspect retained original bytes; no relink, compiler, payload or ldd execution."""
import json
import os
from pathlib import Path
import re
import subprocess

import lf07_contract as C


def audit(folder, inventory, F):
    out = C.OUT / 'native'; out.mkdir(parents=True)
    commands = []

    def inspect(label, path, tool='nm', flags=('--no-demangle',)):
        argv = [tool, *flags, str(path)]
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        (out / (label + '.stdout')).write_text(done.stdout)
        (out / (label + '.stderr')).write_text(done.stderr)
        commands.append(dict(label=label, argv=argv, exit=done.returncode, input_sha256=C.digest(path),
            stdout_sha256=C.sha(done.stdout.encode()), stderr_sha256=C.sha(done.stderr.encode())))
        C.save(out / 'commands.json', commands)
        C.require(done.returncode == 0, 'native inspection failed: ' + label)
        return done.stdout

    # Record the auditor tool versions; they are not mislabeled as producer tools.
    for tool in ('nm', 'readelf', 'ar'):
        done = subprocess.run([tool, '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        C.require(done.returncode == 0, 'native inspector unavailable: ' + tool)
        (out / (tool + '-version.txt')).write_text(done.stdout + done.stderr)

    def dynamic(label, path):
        text = inspect(label + '-dynamic', path, 'readelf', ('-d',))
        needed = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', text)
        names = re.findall(r'\(SONAME\).*?\[([^\]]+)\]', text)
        search = re.findall(r'\((?:RPATH|RUNPATH)\).*?\[([^\]]+)\]', text)
        C.require(len(names) <= 1 and not search, 'custom loader path unsupported; cannot infer exact dependency resolution')
        C.require(all('/' not in n for n in needed), 'path-bearing ELF dependency unsupported')
        return dict(needed=needed, soname=names[0] if names else None)

    program = folder / F.PROGRAM
    full = C.symbols(inspect('final-full', program))
    final_dynamic = C.symbols(inspect('final-dynsym', program, flags=('-D', '--no-demangle')))
    loader = dynamic('final', program)
    inspect('final-elf-header', program, 'readelf', ('-h',))
    inspect('final-elf-symbols', program, 'readelf', ('-Ws',))
    inspect('final-elf-versions', program, 'readelf', ('-V',))

    # The package ships one static host and no project DSO. Resolve platform
    # dependencies without ldd or executing the program. Every external symbol
    # allowance is a definition in this reachable ELF graph, not a name prefix.
    # These are audit-runner libraries, not retained producer library bytes.
    platform_dirs = tuple(Path(p) for p in ('/lib/x86_64-linux-gnu', '/usr/lib/x86_64-linux-gnu', '/lib64', '/usr/lib64'))
    system, system_rows, platform, pending = set(), [], {}, list(loader['needed'])
    while pending:
        name = pending.pop()
        if name in platform: continue
        paths = {str((p / name).resolve(strict=True)) for p in platform_dirs if (p / name).is_file()}
        C.require(len(paths) == 1, 'missing/ambiguous platform dependency: ' + name)
        path = Path(paths.pop())
        C.require(str(path).startswith(('/usr/lib/', '/lib/')), 'platform dependency escaped trusted directories')
        label = 'platform-%03d' % len(platform)
        graph = dynamic(label, path)
        C.require(graph['soname'] in (None, name), 'platform SONAME differs from loader request')
        table = C.symbols(inspect(label + '-exports', path, flags=('-D', '--defined-only', '--no-demangle')))
        system.update(table['global_defined']); system_rows.extend(table['rows'])
        platform[name] = dict(path=str(path), sha256=C.digest(path), bytes=path.stat().st_size,
            graph=graph, defined=table['global_defined'], environment='audit runner, not producer snapshot')
        pending.extend(graph['needed'])
    C.save(out / 'platform-loader.json', dict(entry=F.PROGRAM, graph=loader, libraries=platform))

    sdk_headers = sorted((folder / F.SDK / 'include/exr').glob('*.h'))
    C.require({p.name for p in sdk_headers} == {p.name for p in (C.ROOT / 'include/exr').glob('*.h')}, 'SDK public header inventory differs')
    for p in sdk_headers:
        C.require(p.read_bytes() == (C.ROOT / 'include/exr' / p.name).read_bytes(), 'same-source installed SDK header differs')
    public = {'EXReader': set().union(*(C.public_entries(p.read_text(), sdk=True) for p in sdk_headers))}
    C.require('exr_version' in public['EXReader'], 'SDK public declarations unrecognized')

    targets, locations, dependencies, configs = {}, {}, {}, {}
    for path in sorted((folder / F.RAW / 'lib/cmake').rglob('*.cmake')):
        package = path.parent.name; text = path.read_text()
        configs[path.relative_to(folder).as_posix()] = C.digest(path)
        for target, kind in re.findall(r'add_library\(([A-Za-z0-9_:]+)\s+(STATIC|SHARED|INTERFACE)\s+IMPORTED\)', text):
            C.require(target.startswith(package + '::') and target not in targets, 'duplicate/foreign CMake exported owner')
            targets[target] = dict(owner=package, kind=kind)
        for target, body in re.findall(r'set_target_properties\(([A-Za-z0-9_:]+)\s+PROPERTIES\s+(.*?)\n\)', text, re.S):
            owner = target.split('::', 1)[0]
            dependencies.setdefault(owner, set()).update(re.findall(r'([A-Za-z0-9_]+)::[A-Za-z0-9_]+', body))
            for location in re.findall(r'IMPORTED_LOCATION(?:_[A-Z]+)?\s+"([^"]+)"', body):
                C.require(location.startswith('${_IMPORT_PREFIX}/'), 'unknown imported archive prefix')
                relative = F.RAW + '/' + location[len('${_IMPORT_PREFIX}/'):]
                F.safe_name(relative)
                if relative.endswith('.a'):
                    C.require(target not in locations or locations[target] == relative, 'ambiguous imported archive location')
                    locations[target] = relative
    owners = {}
    for target, path in locations.items():
        C.require(target in targets and targets[target]['kind'] == 'STATIC' and path not in owners, 'missing/ambiguous archive target owner')
        owners[path] = targets[target]['owner']
    actual_archives = {p.relative_to(folder).as_posix() for p in (folder / F.RAW).rglob('*.a')}
    C.require(actual_archives and set(owners) == actual_archives, 'installed archive/export sets differ')

    manifests, header_owners, private_headers, compiled_sources = {}, {}, {}, {}
    workspace = inventory['producer_workspace']
    for path in sorted((folder / 'build/gtk-raw-wave3').glob('raw-*/install_manifest.txt')):
        names = []
        for line in path.read_text().splitlines():
            C.require(line.startswith(workspace + '/' + F.RAW + '/'), 'install manifest outside actual installed prefix')
            relative = line[len(workspace) + 1:]; F.safe_name(relative)
            C.require(relative in inventory['files'], 'install-manifest file missing from capture')
            names.append(relative)
        packages = {owners[name] for name in names if name in owners}
        C.require(len(packages) == 1, 'install manifest package ambiguous/absent')
        package = packages.pop()
        C.require(package not in manifests, 'multiple install manifests for one package')
        cache = (path.parent / 'CMakeCache.txt').read_text()
        homes = re.findall(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$', cache, re.M)
        C.require(len(homes) == 1 and homes[0].startswith(workspace + '/'), 'source root lacks authenticated cache origin')
        home = homes[0][len(workspace) + 1:]; F.safe_name(home)
        C.require(home.startswith(('apps/', 'extras/')), 'module source root outside owned project areas')
        graph = (path.parent / 'build.ninja').read_text()
        archives = [Path(name).name for name in names if name in owners]
        inputs = C.archive_compile_sources(graph, archives)
        source_paths, external_sources = [], []
        for name in inputs:
            normalized = Path(os.path.normpath(name if Path(name).is_absolute() else str(Path(homes[0]) / name)))
            C.require(str(normalized).startswith(workspace + '/'), 'compiler source outside authenticated checkout')
            relative = str(normalized)[len(workspace) + 1:]; F.safe_name(relative)
            if (C.ROOT / relative).is_file(): source_paths.append(relative)
            else:
                C.require(relative.startswith('build/'), 'same-source repository compiler input missing')
                external_sources.append(relative)
        C.require(source_paths, 'module actual compiled source inventory absent')
        compiled_sources[package] = source_paths
        manifests[package] = dict(path=path.relative_to(folder).as_posix(), files=names,
            source_root=home, compile_sources=source_paths, generated_or_vendor_sources=external_sources, raw_candidate='EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=ON' in cache)
        for name in names:
            if '/include/' not in name or not name.endswith(('.h', '.hpp')): continue
            C.require(name not in header_owners, 'installed public header has multiple package owners')
            header_owners[name] = package
            text = (folder / name).read_text()
            if re.search(r'private\s+C\+\+\s+implementation', text, re.I):
                private_headers[name] = package
            else:
                public.setdefault(package, set()).update(C.public_entries(text))
    C.require(set(manifests) == set(owners.values()), 'exported package missing exact installed header manifest')
    installed_headers = {p.relative_to(folder).as_posix() for p in (folder / F.RAW / 'include').rglob('*')
                         if p.is_file() and p.suffix in ('.h', '.hpp')}
    C.require(installed_headers == set(header_owners), 'unowned installed header')
    header_uses, visited = [], set()
    # Recursively follow source-local/installed includes from the exact archive
    # compile inputs. A direct-only scan would miss private inline headers pulled
    # through another header. Unknown system headers do not become public APIs.
    installed_by_name = {}
    for name in installed_headers: installed_by_name.setdefault(Path(name).name, []).append(name)
    for package, paths in compiled_sources.items():
        queue = [(C.ROOT / relative, [relative]) for relative in paths]
        while queue:
            path, chain = queue.pop(); key = (package, str(path))
            if key in visited: continue
            visited.add(key)
            text = path.read_text()
            for include in re.findall(r'#\s*include\s*[<"]([^>"\n]+)[>"]', text):
                matches = installed_by_name.get(Path(include).name, [])
                for header in matches:
                    owner = header_owners[header]
                    if header in private_headers and owner != package:
                        header_uses.append(dict(consumer=package, provider=owner, installed_header=header,
                            header_sha256=C.digest(folder / header), include_chain=chain,
                            source_sha256=C.digest(path), raw_candidate_enabled=manifests[package]['raw_candidate'],
                            finding='explicit private implementation header consumed across installed package owners'))
                candidates = [path.parent / include, C.ROOT / manifests[package]['source_root'] / 'include' / include]
                candidates += [folder / name for name in matches]
                for candidate in candidates:
                    if not candidate.is_file(): continue
                    candidate = candidate.resolve()
                    C.require(candidate.is_relative_to(C.ROOT) or candidate.is_relative_to(folder), 'include escaped bounded source/evidence roots')
                    relative = str(candidate.relative_to(C.ROOT)) if candidate.is_relative_to(C.ROOT) else str(candidate.relative_to(folder))
                    queue.append((candidate, chain + [relative]))

    sdk_tables = {}
    for index, path in enumerate(sorted((folder / F.SDK / 'lib').rglob('*.a'))):
        sdk_tables[path.relative_to(folder).as_posix()] = C.symbols(inspect('sdk-%03d' % index, path))
    C.require(sdk_tables, 'installed SDK archives absent')
    sdk_definitions = set().union(*(set(t['global_defined']) for t in sdk_tables.values()))
    tables = {name: C.symbols(inspect('module-%03d' % i, folder / name)) for i, name in enumerate(sorted(owners))}
    # Host internal resolution is bounded to actual final-map host inputs, not
    # any retained backend/probe object or unlinked build-directory library.
    loads = inventory['final_map_inputs']['project']
    host_inputs = sorted(p for p in loads if p.startswith(F.HOST + '/') and p.endswith(('.a', '.o')))
    C.require(host_inputs, 'actual host native link inputs absent')
    module_owners = dict(owners)
    for i, name in enumerate(host_inputs):
        tables[name] = C.symbols(inspect('host-input-%03d' % i, folder / name)); owners[name] = 'GTKHost'
    dependencies['GTKHost'] = {'EXReader'} | {owners[p] for p in loads if p in owners and owners[p] != 'GTKHost'}
    private = C.module_findings(tables, owners, public, dependencies, sdk_definitions, system)
    boundaries = dict(C.identity(), owners=owners, installed_targets=targets, export_configs=configs,
        dependencies={k: sorted(v) for k, v in dependencies.items()}, public={k: sorted(v) for k, v in public.items()},
        manifests=manifests, header_owners=header_owners, explicitly_private_headers=private_headers,
        private_imports=private, private_header_dependencies=header_uses)
    C.save(C.OUT / 'module-boundaries.json', boundaries)
    print(json.dumps(dict(private_imports={k: v for k, v in private.items() if v}, private_header_dependencies=header_uses), sort_keys=True), flush=True)

    # Full nm (not only dynamic/-g) and allocated GNU section extents attribute
    # the actual final definitions to exact retained archive/member bytes.
    ranges = C.map_ranges((folder / F.MAP).read_text())
    project_definitions = {p: set(t['global_defined']) for p, t in {**sdk_tables, **tables}.items()}
    final_undefined = C.final_undefined_findings(full, final_dynamic, project_definitions, system_rows)
    provider_findings, symbol_owners = [], {}
    selected = public['EXReader'] | {'sqlite3_open_v2'}
    for name in sorted(selected):
        rows = [r for r in full['rows'] if r['name'] == name and not r['undefined']]
        if not rows:
            if name in ('exr_version', 'sqlite3_open_v2'): provider_findings.append('required definition absent: ' + name)
            continue  # static SDK exports not pulled by this final host
        if len(rows) != 1:
            provider_findings.append(dict(symbol=name, duplicate_definitions=rows)); continue
        origin = C.symbol_owner(rows[0], ranges)
        archive = origin.split('(', 1)[0]
        normalized = Path(os.path.normpath(archive if Path(archive).is_absolute() else workspace + '/' + F.HOST + '/' + archive))
        C.require(str(normalized).startswith(workspace + '/'), 'project definition owner escaped original checkout')
        relative = str(normalized)[len(workspace) + 1:]
        C.require(relative in inventory['files'] and relative in loads, 'definition owner not exact retained final link input')
        expected = F.RAW + '/lib/libreader_catalog_sqlite.a' if name == 'sqlite3_open_v2' else None
        if expected is not None:
            if relative != expected or module_owners.get(relative) != 'EXReaderProductCatalog':
                provider_findings.append(dict(symbol=name, wrong_product_sqlite_owner=relative))
        elif relative not in sdk_tables:
            provider_findings.append(dict(symbol=name, wrong_sdk_owner=relative))
        symbol_owners[name] = dict(object=origin, path=relative, sha256=C.digest(folder / relative), address=rows[0]['address'])
    # No second copy may hide as a local/optimized spelling in the final image.
    for row in full['rows']:
        if not row['undefined'] and re.match(r'^(?:exr_version|sqlite3_open_v2)[.$]', row['name']):
            provider_findings.append(dict(hidden_or_renamed_provider=row))
    for name, table in tables.items():
        clones = sorted(set(table['global_defined']) & public['EXReader'])
        if clones: provider_findings.append(dict(non_sdk_input=name, sdk_public_definitions=clones))
    for name, item in platform.items():
        foreign = sorted(set(item['defined']) & (public['EXReader'] | {'sqlite3_open_v2'}))
        if foreign: provider_findings.append(dict(platform_library=name, second_provider_symbols=foreign))
    for name in final_dynamic['undefined']:
        if name in public['EXReader'] or name.startswith('sqlite3_'):
            provider_findings.append(dict(unexpected_dynamic_sdk_sqlite_import=name))
    # Explicitly require no packaged native sibling; this capture's supported
    # closure is one static host, not an invented basename-only DSO graph.
    native_siblings = []
    for path in (folder / F.PAYLOAD / 'EXReader-Linux').rglob('*'):
        if path.is_file():
            with path.open('rb') as stream: magic = stream.read(4)
            if magic == b'\x7fELF': native_siblings.append(path.relative_to(folder).as_posix())
    C.require(native_siblings == [F.PAYLOAD + '/' + F.ENTRY], 'additional packaged ELF needs explicit project loader audit')
    report = dict(C.identity(), final_program=F.PROGRAM, program_sha256=C.digest(program),
        map_sha256=C.digest(folder / F.MAP), symbol_owners=symbol_owners, provider_findings=provider_findings,
        final_undefined_findings=final_undefined,
        installed_sdk_archives={p: C.digest(folder / p) for p in sdk_tables},
        linked_project_inputs=loads, module_boundaries=boundaries, platform_libraries=platform,
        platform_scope='Exact audit-runner graph only; original producer system DSOs were not captured.',
        f07_accepted=False, full_six_platform_f07_accepted=False)
    report['linux_project_closure_accepted'] = not (provider_findings or final_undefined or any(private.values()) or header_uses)
    # This narrow flag never claims producer system-DSO byte identity, six-platform
    # convergence, physical-device acceptance or release readiness.
    C.save(C.OUT / 'linux-closure.json', report)
    print(json.dumps(dict(linux_project_closure_accepted=report['linux_project_closure_accepted'],
        provider_findings=provider_findings, final_undefined_findings=final_undefined, private_import_count=sum(map(len, private.values())),
        private_header_dependency_count=len(header_uses), f07_accepted=False), sort_keys=True), flush=True)
    return report
