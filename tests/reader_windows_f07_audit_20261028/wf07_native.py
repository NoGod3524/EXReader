"""Inspect retained COFF/PE bytes, installed packages and actual final link graph."""
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import wf07_contract as C
from wf07_coff import read_symbols, member_defines


def audit(raw, inventory, source):
    C.require(os.name == 'nt', 'Windows native inspector only')
    out = C.OUT / 'native'; out.mkdir()
    commands = []
    def inspect(label, argv, subject=None):
        done = subprocess.run(list(map(str, argv)), capture_output=True, timeout=300)
        (out / (label + '.stdout')).write_bytes(done.stdout)
        (out / (label + '.stderr')).write_bytes(done.stderr)
        commands.append(dict(label=label, argv=list(map(str, argv)), exit=done.returncode,
            subject_sha256=C.digest(subject) if subject else None,
            stdout_sha256=C.digest(out / (label + '.stdout')), stderr_sha256=C.digest(out / (label + '.stderr'))))
        C.save(out / 'commands.json', commands)
        C.require(done.returncode == 0, 'native inspector failed: ' + label)
        return done.stdout.decode('utf-8-sig', errors='strict')
    dumpbin = Path(shutil.which('dumpbin'))
    ninja = Path(shutil.which('ninja'))
    C.save(out / 'inspection-tools.json', dict(dumpbin=dict(path=str(dumpbin), sha256=C.digest(dumpbin)),
             ninja=dict(path=str(ninja), sha256=C.digest(ninja)), original_tool_identity_proven=False))

    configs = {name: (raw / name).read_text(encoding='utf-8-sig') for name in inventory
               if any(name.startswith(C.BUILD + stage + '/') for stage in C.STAGES) and
               re.search(r'/(?:lib/cmake/[^/]+|share/[^/]+/cmake)/[^/]+\.cmake$', name)}
    libraries = {name for name in inventory if any(name.startswith(C.BUILD + stage + '/') for stage in C.STAGES)
                 and name.lower().endswith('.lib')}
    owners, targets, dependencies = C.installed_exports(configs, libraries)
    C.save(out / 'installed-exports.json', dict(owners=owners, targets=targets,
        dependencies={k: sorted(v) for k, v in dependencies.items()}, files={p: inventory[p] for p in configs}))

    manifests, header_owners, public, private_headers, ambiguous_headers = {}, {}, {}, {}, []
    module_builds = ['sdk-build', 'product-build'] + ['raw-' + value for value in __import__('frozen_capture').MODULES]
    build_packages = {}
    for label in module_builds:
        path = C.BUILD + label + '/install_manifest.txt'
        operations = (raw / path).read_text(encoding='utf-8-sig').splitlines()
        names, repeated = C.install_entries(operations, source['workspace'], inventory)
        packages = {owners[name] for name in names if name in owners}
        C.require(packages, 'install manifest lacks exported package owner')
        build_packages[label] = packages
        manifests[label] = dict(path=path, packages=sorted(packages), files=names,
                               operation_rows=len(operations), repeated_exact_paths=repeated)
        if repeated: print(json.dumps(dict(install_manifest=path, repeated_exact_paths=repeated), sort_keys=True), flush=True)
        for name in names:
            if '/include/' not in name: continue
            C.require(name not in header_owners, 'header has multiple install-manifest owners')
            header_packages = packages
            if label == 'sdk-build':
                relative = name.split('/include/', 1)[1]
                frozen = C.ROOT / 'include' / relative
                if frozen.is_file():
                    C.require('EXReader' in packages and frozen.read_bytes() == (raw / name).read_bytes(),
                              'actual installed frozen SDK header identity differs')
                    header_packages = {'EXReader'}
            header_owners[name] = sorted(header_packages)
            text = (raw / name).read_text(encoding='utf-8-sig')
            if re.search(r'private\s+C\+\+\s+implementation', text, re.I):
                private_headers[name] = sorted(header_packages); continue
            if len(header_packages) != 1:
                ambiguous_headers.append(dict(header=name, packages=sorted(header_packages),
                    reason='one build installs multiple exported packages; no broad header ownership union'))
                continue
            package = next(iter(header_packages))
            if package == 'EXReader':
                # Vendor APIs remain private even if a dependency installed an extra header.
                if not name.startswith(C.BUILD + 'sdk-stage/include/exr/'): continue
                original = C.ROOT / 'include/exr' / Path(name).name
                C.require(original.is_file() and original.read_bytes() == (raw / name).read_bytes(), 'installed SDK header differs')
            public.setdefault(package, set()).update(C.public_entries(text, sdk=package == 'EXReader'))
    actual_headers = {name for name in inventory if any(name.startswith(C.BUILD + s + '/include/') for s in C.STAGES)}
    C.require(set(header_owners) == actual_headers, 'installed header/manifest coverage differs')
    sdk_prefix = C.BUILD + 'sdk-stage/include/exr/'
    C.require({name.removeprefix(sdk_prefix) for name in header_owners if name.startswith(sdk_prefix)} ==
              {p.relative_to(C.ROOT / 'include/exr').as_posix() for p in (C.ROOT / 'include/exr').rglob('*') if p.is_file()},
              'installed frozen SDK public header inventory differs')
    C.require('exr_version' in public.get('EXReader', ()), 'SDK public declaration parser incomplete')

    # Recover actual final response closure independently from retained capture
    # metadata. Every project input must be an exact retained file; no basename
    # fallback across installed stages and no duplicate link basename.
    final = json.loads((C.OUT / 'capture-recomputed.json').read_text())['verified']
    C.require(' -- ' in final['final_link_command'], 'actual vs_link_exe link segment missing')
    text = final['final_link_command'].split(' -- ', 1)[1].split('&&', 1)[0].strip()
    for name in final['final_response_files']:
        blob = (raw / name).read_bytes()
        text += '\n' + blob.decode('utf-16' if blob[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')
    inputs, external_inputs = set(), set()
    hostroot = PureWindowsPath(source['workspace']) / C.BUILD / 'host'
    for token in C.tokens(text):
        if token.startswith('@'): continue  # Already recursively expanded by frozen validator.
        if token.startswith('/'):
            lower = token.lower()
            if lower.startswith(('/defaultlib:', '/wholearchive:')):
                token = token.split(':', 1)[1]
                C.require(token, 'empty explicit library switch')
                if lower.startswith('/defaultlib:') and not token.lower().endswith('.lib'): token += '.lib'
            elif lower.startswith('/libpath:'):
                external_inputs.add(token); continue
            elif lower.startswith('/implib:'): continue  # Output, never an input.
            elif lower.endswith(('.lib', '.obj')):
                raise ValueError('unsupported input-bearing link switch: ' + token)
            else: continue
        if not token.lower().endswith(('.lib', '.obj')): continue
        path = PureWindowsPath(token)
        if not path.is_absolute(): path = hostroot / path
        try: name = C.exact_path(str(path), source['workspace'])
        except ValueError:
            external_inputs.add(token); continue
        if name in inventory: inputs.add(name)
        elif len(PureWindowsPath(token).parts) == 1: external_inputs.add(token)
        else: raise ValueError('final named project input not retained: ' + token)
    C.require(inputs and any(name.endswith('.obj') for name in inputs), 'actual final project input list unrecognized')
    C.map_origin('unresolved-check', inputs)  # Also rejects every duplicate basename.
    host_inputs = {name for name in inputs if name.startswith(C.BUILD + 'host/')}
    C.require(all(name in owners or name in host_inputs for name in inputs), 'unowned final project input')
    for name in host_inputs: owners[name] = 'WindowsHost'
    dependencies['WindowsHost'] = {owners[name] for name in inputs if name not in host_inputs}

    tables, member_tables = {}, {}
    for index, name in enumerate(sorted(libraries | host_inputs)):
        text = inspect(f'symbols-{index:03}', [dumpbin, '/nologo', '/symbols', raw / name], raw / name)
        table = C.coff_symbols(text)
        member_tables[name] = read_symbols((raw / name).read_bytes(), name)
        C.require(member_tables[name]['summary'] == table, 'direct COFF member parse differs from native dumpbin')
        original = 'capture/symbols/' + name.removeprefix(C.BUILD) + '.txt'
        C.require(original in inventory and C.coff_symbols((raw / original).read_text(encoding='utf-8-sig')) == table,
                  'native COFF replay differs from original captured symbols')
        tables[name] = table
    program = raw / (C.BUILD + 'host/EXReaderWave3.exe')
    imports = C.pe_imports(inspect('image-imports', [dumpbin, '/nologo', '/imports', program], program))
    C.require(imports == C.pe_imports((raw / 'capture/image/imports.txt').read_text(encoding='utf-8-sig')),
              'actual PE imports differ from retained diagnostics')
    for mode in ('headers', 'exports', 'dependents'):
        inspect('image-' + mode, [dumpbin, '/nologo', '/' + mode, program], program)
    imported = {symbol for row in imports for symbol in (row['symbol'], '__imp_' + row['symbol'])}
    private, public_conflicts = C.private_imports(tables, owners, public, dependencies, imported)

    # Read actual Ninja dependency databases; no configure/build invocation.
    # Only dependency groups belonging to exported archive targets are counted,
    # not standalone test targets. This detects header-only/private inline uses.
    header_uses, dependency_coverage, gaps, project_gaps = [], {}, list(C.GAPS), []
    repository_dependencies, source_roots = [], {'src': {'EXReader'}, 'include': {'EXReader'}}
    for label, packages in dict(build_packages, host={'WindowsHost'}).items():
        if label == 'sdk-build': continue
        cache = (raw / (C.BUILD + label + '/CMakeCache.txt')).read_text(encoding='utf-8-sig')
        homes = re.findall(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$', cache, re.M)
        C.require(len(homes) == 1, 'actual module configure source root missing')
        source_root = C.exact_path(homes[0], source['workspace'])
        C.require(source_root not in source_roots, 'duplicate module configure source root')
        source_roots[source_root] = packages
        graph = (raw / (C.BUILD + label + '/build.ninja')).read_text(encoding='utf-8-sig')
        expected_objects = {}
        if label == 'host':
            for name in host_inputs:
                if name.endswith('.obj'): expected_objects[name.removeprefix(C.BUILD + 'host/')] = 'WindowsHost'
                else:
                    for obj in C.archive_objects(graph, PureWindowsPath(name).stem): expected_objects[obj] = 'WindowsHost'
        else:
            for name in libraries:
                if owners[name] not in packages: continue
                for obj in C.archive_objects(graph, targets[name]):
                    C.require(obj not in expected_objects, 'same object belongs to multiple package archives')
                    expected_objects[obj] = owners[name]
        C.require(expected_objects, 'empty actual archive/host compile object inventory')
        deps = raw / (C.BUILD + label + '/.ninja_deps')
        if not deps.is_file():
            project_gaps.append('Missing actual Ninja header dependency database: ' + label); continue
        text = inspect('deps-' + label, [ninja, '-C', raw / (C.BUILD + label), '-t', 'deps'], deps)
        empty_groups = []
        uses, covered = C.private_header_dependencies(text, expected_objects, private_headers, source['workspace'], label,
                                                     repository_dependencies, empty_dependency_groups=empty_groups)
        header_uses.extend(uses)
        dependency_coverage[label] = dict(expected_objects=expected_objects, observed=sorted(covered),
            empty_dependency_groups=empty_groups,
            extraction_mtime_not_original_validity_proof=True)
        if empty_groups:
            project_gaps.append('Unresolved empty original dependency groups (not covered): ' + label)
        if set(expected_objects) != covered: project_gaps.append('Incomplete actual archive/host object header dependency coverage: ' + label)
    source_uses, unknown_source = C.source_include_boundaries(repository_dependencies, source_roots, set(header_owners))
    if unknown_source:
        project_gaps.append('Original dependency database includes repository/build paths without a unique installed/public or configured-package source owner; no complete source-boundary clearance.')
    C.save(out / 'repository-dependency-rows.json', repository_dependencies)

    mapping = (raw / (C.BUILD + 'host/windows-host.map')).read_text(encoding='utf-8-sig')
    rows = C.map_rows(mapping)
    for row in rows:
        row['input'] = C.map_origin(row['origin'], inputs, source['workspace'])
        row['owner'] = owners.get(row['input'])
        _, member = C.map_parts(row['origin'])
        row['member'] = member
        row['member_definition_verified'] = bool(row['input'] in member_tables and member_defines(
            member_tables[row['input']], member or PureWindowsPath(row['input']).name, row['symbol']))
    provider_findings = []
    provider_symbols = {}
    for symbol, expected in [('exr_version', 'EXReader'), ('sqlite3_open_v2', 'EXReaderProductCatalog')]:
        found = [r for r in rows if r['symbol'] == symbol]
        provider_symbols[symbol] = found
        if len(found) != 1 or found[0]['owner'] != expected or not found[0]['member_definition_verified']:
            provider_findings.append(dict(symbol=symbol, expected_owner=expected, observed=found))
    sqlite_owners = {r['owner'] for r in rows if r['symbol'].startswith('sqlite3_')}
    if sqlite_owners != {'EXReaderProductCatalog'}:
        provider_findings.append(dict(sqlite_definition_owners=sorted(str(x) for x in sqlite_owners)))
    sdk_bad = [r for r in rows if r['symbol'] in public['EXReader'] and
               (r['owner'] != 'EXReader' or not r['member_definition_verified'])]
    if sdk_bad: provider_findings.append(dict(sdk_public_definitions_outside_sdk=sdk_bad))
    if any(re.search(r'sqlite|exreader', row['dll'], re.I) for row in imports):
        provider_findings.append(dict(unexpected_sdk_or_sqlite_dll=imports))
    C.save(out / 'map-symbols.json', rows)
    C.save(out / 'coff-tables.json', tables)
    C.save(out / 'coff-member-tables.json', member_tables)
    report = dict(C.identity(), inspection_completed=True, windows_f07_accepted=False, full_six_platform_f07_accepted=False,
        capture_verified=True, program_sha256=C.digest(program), map_sha256=inventory[C.BUILD + 'host/windows-host.map']['sha256'],
        original_artifact=C.PINS['capture'][0], owners=owners, archive_targets=targets,
        installed_manifests=manifests, public={k: sorted(v) for k, v in public.items()},
        header_owners=header_owners, explicitly_private_headers=private_headers,
        ambiguous_header_ownership=ambiguous_headers, private_header_dependencies=header_uses,
        source_include_dependencies=source_uses, unknown_source_dependencies=unknown_source,
        configured_source_owners={k: sorted(v) for k, v in source_roots.items()},
        dependency_coverage=dependency_coverage, module_private_or_unknown_imports=private,
        public_definition_conflicts=public_conflicts, final_inputs=sorted(inputs), external_link_inputs=sorted(external_inputs),
        response_files=final['final_response_files'], provider_symbols=provider_symbols,
        provider_findings=provider_findings, image_imports=imports, gaps=gaps, project_coverage_gaps=project_gaps)
    report['project_boundary_clean'] = not (any(private.values()) or public_conflicts or header_uses or
                                          ambiguous_headers or provider_findings or project_gaps or source_uses)
    # Absence of original external input bytes is fixed evidence, not a boolean
    # another collector can waive. Full admission deliberately remains false.
    C.save(C.OUT / 'audit.json', report)
    print(json.dumps(dict(inspection_completed=True, windows_f07_accepted=False,
        project_boundary_clean=report['project_boundary_clean'], private_header_dependencies=header_uses,
        source_include_dependencies=source_uses, unknown_source_dependency_count=len(unknown_source),
        empty_dependency_groups=[row for coverage in dependency_coverage.values() for row in coverage['empty_dependency_groups']],
        ambiguous_header_ownership=ambiguous_headers, provider_findings=provider_findings,
        private_or_unknown_import_count=sum(map(len, private.values())), public_definition_conflict_count=len(public_conflicts),
        gaps=gaps, project_coverage_gaps=project_gaps), indent=2), flush=True)
    return report
