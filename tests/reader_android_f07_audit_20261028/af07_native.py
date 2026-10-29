"""Replay native symbols and audit exact installed module/API/provider boundaries."""
import json
import os
from pathlib import Path
import re
import subprocess

import af07_contract as C
import af07_ndk_inputs as N
from af07_ndk_probe import FAILED_INPUT_SHA, verify_script


def audit(raw, capture, inventory, images, bindings):
    out = C.OUT / 'native'; out.mkdir(parents=True)
    commands = []
    ndk = Path(os.environ['ANDROID_HOME']) / 'ndk/27.0.12077973'
    toolroot = ndk / 'toolchains/llvm/prebuilt/linux-x86_64'
    tools = toolroot / 'bin'
    original_toolchain = json.loads((raw.parent / 'toolchain.json').read_text())
    cache_text = (raw / 'build/wave3/sdk/CMakeCache.txt').read_text()
    workspace_match = re.search(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(/.+)$', cache_text, re.M)
    C.require(workspace_match is not None, 'original SDK workspace missing')
    workspace = workspace_match[1]
    original_commands = json.loads((raw.parent / 'commands.json').read_text())
    C.require(any(row['label'] == 'llvm-readelf-version' and row['cwd'] == workspace for row in original_commands), 'recorded original workspace mismatch')
    C.require((ndk / 'source.properties').read_text() == original_toolchain['source_properties'], 'NDK revision content differs')
    for name in ('llvm-nm', 'llvm-readelf'):
        C.require(C.digest(tools / name) == original_toolchain['tools'][name]['sha256'], 'native inspector differs from pinned original NDK')

    def inspect(label, path, tool, flags):
        argv = [str(tools / tool), *flags, str(path)]
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        (out / (label + '.stdout')).write_text(done.stdout)
        (out / (label + '.stderr')).write_text(done.stderr)
        commands.append(dict(label=label, argv=argv, exit=done.returncode, input_sha256=C.digest(path),
                             stdout_sha256=C.sha(done.stdout.encode()), stderr_sha256=C.sha(done.stderr.encode())))
        C.save(out / 'commands.json', commands)
        C.require(done.returncode == 0, 'native inspection failed: ' + label)
        return done.stdout

    # .so is not sufficient to identify a runtime stub: the API26 libc++.so
    # observed in failed run 40780887828 is an implicit linker script. Only the
    # pinned NDK's explicit OS manifest may grant a system runtime provider name.
    system, stub_definitions = set(), {}
    sysroot = toolroot / 'sysroot'
    triple = sysroot / 'usr/lib/x86_64-linux-android'
    api_directory = triple / '26'
    metadata_path = ndk / 'meta/system_libs.json'
    metadata_bytes = metadata_path.read_bytes()
    (out / 'system-library-metadata.json').write_bytes(metadata_bytes)
    C.save(out / 'system-library-metadata-identity.json', dict(path=str(metadata_path),
           sha256=C.sha(metadata_bytes), bytes=len(metadata_bytes), **C.identity()))
    metadata = json.loads(metadata_bytes)
    required_stubs = N.system_names(metadata, 26)
    stubs = sorted(api_directory.glob('*.so'))
    input_report = dict(api=26, metadata_sha256=C.digest(metadata_path), metadata=metadata,
                        runtime_stubs={}, link_only_scripts={})
    C.require({path.name for path in stubs if path.name in required_stubs} == required_stubs,
              'pinned API26 system manifest/stub inventory differs')
    for index, path in enumerate(stubs):
        resolved = N.resolve(path, sysroot, (api_directory, triple))
        if path.name not in required_stubs:
            C.require(path.name == 'libc++.so' and C.digest(path) == FAILED_INPUT_SHA,
                      'unrecognized non-system API26 shared input')
            verify_script(path.read_bytes())
            C.require(resolved['kind'] == 'INPUT-script' and len(resolved['children']) == 1 and
                      resolved['children'][0]['kind'] == 'ELF' and
                      resolved['children'][0]['path'] == 'usr/lib/x86_64-linux-android/libc++_shared.so' and
                      resolved['children'][0]['sha256'] == '936e1150309bdae86216f14e493f478d39e588095f1577105856da6d0f24f149',
                      'exact observed NDK script target differs')
            input_report['link_only_scripts'][path.name] = resolved
            C.save(out / 'system-inputs.json', input_report)
            continue  # A validated link script is not a DT_NEEDED provider.
        C.require(resolved['kind'] == 'ELF', 'NDK system runtime stub is not ELF')
        input_report['runtime_stubs'][path.name] = resolved
        C.save(out / 'system-inputs.json', input_report)
        text = inspect('system-%03d' % index, path, 'llvm-nm', ['-D', '-g', '--defined-only'])
        stub_definitions[path.name] = set(C.symbols(text)['defined'])
        system.update(stub_definitions[path.name])
    external = {row['path']: row for graph in capture['build_graphs'] for row in graph['external_named_inputs']}
    original_ndk = original_toolchain['ndk'].rstrip('/')
    for index, (name, record) in enumerate(sorted(external.items())):
        C.require(name.startswith(original_ndk + '/'), 'external link input not inside pinned NDK')
        path = ndk / name[len(original_ndk) + 1:]
        C.require(path.is_file() and path.stat().st_size == record['bytes'] and C.digest(path) == record['sha256'], 'actual external NDK input changed')
        if path.suffix in ('.a', '.o') or '.so' in path.name:
            text = inspect('external-%03d' % index, path, 'llvm-nm', ['-g', '--defined-only'])
            if text.strip(): system.update(C.symbols(text)['defined'])
    C.save(out / 'system-symbols.json', dict(api=26, ndk='27.0.12077973', symbols=sorted(system), external=external))

    image_reports = {}
    for index, path in enumerate(images):
        raw_paths = {row['path'] for row in bindings[path.name]['linked']}
        C.require(len({C.digest(raw / name) for name in raw_paths}) == 1, 'ambiguous raw linked image')
        original = raw / sorted(raw_paths)[0]
        full = C.symbols(inspect('image-%03d-full' % index, original, 'llvm-nm', []))
        dynamic = C.symbols(inspect('image-%03d-dynamic' % index, path, 'llvm-nm', ['-D', '-g']))
        text = inspect('image-%03d-loader' % index, path, 'llvm-readelf', ['-d'])
        needed = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', text)
        soname = re.findall(r'\(SONAME\).*?\[([^\]]+)\]', text)
        paths = re.findall(r'\((?:RPATH|RUNPATH)\).*?\[([^\]]+)\]', text)
        C.require(len(soname) <= 1 and all(p in ('$ORIGIN', '$ORIGIN/') for p in paths), 'unsupported Android loader names/path')
        image_reports[path.name] = dict(full=full, dynamic=dynamic, needed=needed,
            soname=soname[0] if soname else path.name, raw_paths=sorted(raw_paths), paths=paths,
            apk_image_sha256=C.digest(path), raw_image_sha256=C.digest(original))
    sonames = {}
    for name, record in image_reports.items():
        C.require(record['soname'] not in sonames, 'duplicate bundled SONAME')
        sonames[record['soname']] = name
    edges, system_by_image, reachable = {}, {}, {}
    for name, record in image_reports.items():
        C.require(all('/' not in dependency and (dependency in sonames or dependency in stub_definitions) for dependency in record['needed']), 'unknown/unresolved APK loader dependency: ' + name)
        edges[name] = [sonames[d] for d in record['needed'] if d in sonames]
    for name in image_reports:
        visited, allowed = C.system_scope(name, image_reports, sonames, stub_definitions, system)
        system_by_image[name] = allowed; reachable[name] = visited

    sdk_headers = sorted((raw / C.SDK / 'include/exr').glob('*.h'))
    C.require({p.name for p in sdk_headers} == {p.name for p in (C.ROOT / 'include/exr').glob('*.h')}, 'SDK public header inventory')
    for path in sdk_headers:
        C.require(path.read_bytes() == (C.ROOT / 'include/exr' / path.name).read_bytes(), 'SDK public header drift')
    public = {'EXReader': set().union(*(C.public_entries(p.read_text(), sdk=True) for p in sdk_headers))}
    C.require('exr_version' in public['EXReader'], 'SDK declaration parsing failed')

    # Actual installed CMake package exports own targets/archives. Module install
    # manifests own public headers; a shared broad include directory is NOT used
    # to borrow another package's private declarations.
    targets, locations, dependencies = {}, {}, {}
    configs = sorted((raw / C.MODULES / 'lib/cmake').rglob('*.cmake'))
    C.require(configs, 'actual installed package exports absent')
    for path in configs:
        package = path.parent.name; text = path.read_text()
        for target, kind in re.findall(r'add_library\(([A-Za-z0-9_:]+)\s+(STATIC|SHARED|INTERFACE)\s+IMPORTED\)', text):
            C.require(target.startswith(package + '::'), 'export namespace/package differs')
            C.require(target not in targets, 'duplicate imported target')
            targets[target] = dict(owner=package, kind=kind)
        for target, body in C.target_properties(text):
            package = target.split('::', 1)[0]
            dependencies.setdefault(package, set()).update(re.findall(r'([A-Za-z0-9_]+)::[A-Za-z0-9_]+', body))
            for location in re.findall(r'IMPORTED_LOCATION(?:_[A-Z]+)?\s+"([^"]+)"', body):
                C.require(location.startswith('${_IMPORT_PREFIX}/'), 'unrecognized installed archive prefix')
                relative = C.MODULES + '/' + location[len('${_IMPORT_PREFIX}/'):]
                C.safe_name(relative)
                if relative.endswith('.a'):
                    C.require(target not in locations or locations[target] == relative, 'multiple archive target locations')
                    locations[target] = relative
    owners = {}
    for target, name in locations.items():
        C.require(target in targets and targets[target]['kind'] == 'STATIC', 'archive lacks declared static owner')
        C.require(name not in owners, 'archive has multiple exported owners')
        owners[name] = targets[target]['owner']
    actual_archives = {p.relative_to(raw).as_posix() for p in (raw / C.MODULES).rglob('*.a')}
    ownership = dict(targets=targets, locations=locations, owners=owners,
        installed_archives=sorted(actual_archives), missing_export=sorted(actual_archives - set(owners)),
        absent_archive=sorted(set(owners) - actual_archives))
    C.save(C.OUT / 'installed-ownership.json', ownership)
    print(json.dumps(dict(installed_ownership=ownership), sort_keys=True), flush=True)
    C.require(actual_archives and set(owners) == actual_archives, 'installed archive/export set differs: ' +
              json.dumps(dict(missing_export=ownership['missing_export'], absent_archive=ownership['absent_archive'])))
    recipe = (C.ROOT / '.github/workflows/android-composition-candidate.yml').read_text()
    source_modules = dict(re.findall(r'^\s*build_module\s+([\w-]+)\s+([\w/.-]+)', recipe, re.M))
    manifests, header_owners, private_headers, observed_modules = {}, {}, {}, set()
    for path in sorted((raw / 'build/wave3').glob('module-*/install_manifest.txt')):
        module_name = path.parent.name.removeprefix('module-')
        C.require(module_name in source_modules and module_name not in observed_modules, 'unexpected/duplicate build-module manifest')
        observed_modules.add(module_name)
        names = []
        for line in path.read_text().splitlines():
            name = C.exact_workspace_path(line, workspace, C.MODULES)
            C.safe_name(name); C.require(name in inventory['files'], 'installed manifest file not retained')
            C.require(name not in names, 'duplicate entry inside module install manifest')
            names.append(name)
        packages = {owners[name] for name in names if name in owners}
        C.require(len(packages) == 1, 'module install manifest has missing/ambiguous archive package')
        package = packages.pop()
        C.assign_unique(manifests, package, dict(path=path.relative_to(raw).as_posix(), files=names))
        for name in names:
            if '/include/' not in name or not name.endswith(('.h', '.hpp')): continue
            text = (raw / name).read_text()
            C.assign_unique(header_owners, name, package)
            if re.search(r'private\s+C\+\+\s+implementation', text, re.I):
                private_headers[name] = package
                continue
            public.setdefault(package, set()).update(C.public_entries(text))
    # Every installed include file must have one recognized manifest owner.
    # Unknown suffixes fail closed too: they cannot silently bypass private
    # header-only implementation checks merely by not ending in .h or .hpp.
    installed_headers = {p.relative_to(raw).as_posix() for p in (raw / C.MODULES / 'include').rglob('*') if p.is_file()}
    coverage = C.header_coverage(installed_headers, header_owners)
    C.save(C.OUT / 'installed-header-coverage.json', dict(C.identity(), **coverage, owners=header_owners))
    print(json.dumps(dict(installed_header_coverage=coverage), sort_keys=True), flush=True)
    C.require_header_coverage(coverage)
    C.require(set(manifests) == set(owners.values()), 'an exported module lacks its actual install/header manifest')
    C.require(observed_modules == set(source_modules), 'original producer build-module inventory not completely captured')
    sdk_definitions = set()
    sdk_archives = sorted((raw / C.SDK).rglob('*.a'))
    for index, path in enumerate(sdk_archives):
        sdk_definitions.update(C.symbols(inspect('sdk-archive-%03d' % index, path, 'llvm-nm', ['-g']))['defined'])
    tables = {name: C.symbols(inspect('module-%03d' % index, raw / name, 'llvm-nm', ['-g']))
              for index, name in enumerate(sorted(owners))}
    consumers, system_by_archive = {}, {}
    for name in tables:
        consumers[name] = [image for image, binding in bindings.items() if any(name in row['inputs'] for row in binding['linked'])]
        system_by_archive[name] = set().union(*(system_by_image[image] for image in consumers[name])) if consumers[name] else set()
    private = C.private_imports(tables, owners, public, dependencies, sdk_definitions, system_by_archive)

    # Installed-but-explicitly-private C++ implementation headers cannot be
    # promoted to public APIs by their installation alone. Retain source-backed
    # include dependencies as separate gate blockers (including header-only code).
    header_uses = []
    for package, manifest in manifests.items():
        module = Path(manifest['path']).parent.name.removeprefix('module-')
        C.require(module in source_modules, 'module source root missing from frozen actual build recipe')
        source_root = C.ROOT / source_modules[module]
        for path in source_root.rglob('*'):
            if not path.is_file() or path.suffix not in ('.c', '.cpp', '.h', '.hpp'): continue
            text = path.read_text(errors='strict')
            for header, owner in private_headers.items():
                if owner != package and re.search(r'#\s*include\s*[<"]' + re.escape(Path(header).name) + r'[>"]', text):
                    header_uses.append(dict(consumer=package, owner=owner, header=header,
                        source=path.relative_to(C.ROOT).as_posix(), source_sha256=C.digest(path),
                        status='explicit private header dependency; no public-only claim from symbol-table absence'))
    C.save(C.OUT / 'module-boundaries.json', dict(C.identity(), owners=owners,
        public={k: sorted(v) for k, v in public.items()}, manifests=manifests,
        dependencies={k: sorted(v) for k, v in dependencies.items()},
        private_imports=private, private_header_dependencies=header_uses,
        explicitly_private_installed_headers=private_headers))
    print(json.dumps(dict(module_private_imports={k: v for k, v in private.items() if v},
                          private_header_dependencies=header_uses), sort_keys=True))

    provider_failures = []
    sdk_providers = [name for name, record in image_reports.items() if 'exr_version' in record['full']['defined']]
    if len(sdk_providers) != 1: provider_failures.append('Expected one actual SDK definition owner, got ' + str(sdk_providers))
    else:
        provider = sdk_providers[0]
        if not provider.startswith('libexreader.so'): provider_failures.append('SDK implementation is not the bundled aggregate SDK')
        for name, record in image_reports.items():
            if name != provider:
                duplicate = sorted(set(record['full']['defined']) & public['EXReader'])
                if duplicate: provider_failures.append(dict(image=name, duplicate_sdk_public_definitions=duplicate))
                unresolved = sorted(set(record['dynamic']['undefined']) & public['EXReader'] - set(image_reports[provider]['dynamic']['defined']))
                if unresolved: provider_failures.append(dict(image=name, unresolved_sdk_public_imports=unresolved))
    product = image_reports.get('libexreader_product.so')
    C.require(product is not None, 'product JNI image absent')
    sqlite_rows = [row for row in product['full']['rows'] if row['name'] == 'sqlite3_open_v2' and not row['undefined']]
    if len(sqlite_rows) != 1: provider_failures.append('Product sqlite3_open_v2 definition is not unique')
    if any(name.startswith('sqlite3_') for name in product['dynamic']['defined']): provider_failures.append('Product SQLite symbols leak dynamically')
    if any('exr_vendor_exr_sqlite' in name for name in product['full']['defined'] + product['full']['undefined']): provider_failures.append('SDK private SQLite entered product JNI')
    if any(re.search(r'sqlite|exreader', name, re.I) for name in product['needed']): provider_failures.append('Product JNI depends on another SDK/SQLite provider')
    for name, record in image_reports.items():
        if name != 'libexreader_product.so' and 'sqlite3_open_v2' in record['full']['defined']:
            provider_failures.append('Second public product SQLite implementation: ' + name)
    image_private = {}
    for image, record in image_reports.items():
        image_private[image] = C.image_imports(image, image_reports, reachable[image], system_by_image[image], sdk_providers, public['EXReader'])
    map_reports = {}
    map_diagnostic_index = 0
    for image in ('libexreader_host.so', 'libexreader_product.so'):
        found = []
        for row in bindings[image]['linked']:
            for name in row['maps']:
                text = (raw / name).read_text()
                paths = set(re.findall(r'([^\s()]+\.a)\([^()\n]+\)', text))
                # Observe the exact retained map/named-input mismatch before the
                # unchanged refusal. This does not admit implicit NDK inputs.
                ndk_paths = {path for path in paths if path.startswith(original_ndk + '/')}
                diagnostic = dict(C.identity(), image=image, map_path=name,
                    map_sha256=C.digest(raw / name), original_workspace=workspace,
                    original_ndk=original_ndk, archive_paths=sorted(paths),
                    matching_linked_output=row['path'], matching_named_inputs=sorted(row['inputs']),
                    external_named_inputs=external,
                    missing_ndk_named_inputs=sorted(ndk_paths - set(external)),
                    admission_changed=False, full_six_platform_f07_accepted=False)
                C.save(C.OUT / ('map-input-diagnostic-%03d.json' % map_diagnostic_index), diagnostic)
                print(json.dumps(dict(map_input_diagnostic=diagnostic), sort_keys=True), flush=True)
                map_diagnostic_index += 1
                C.require(paths, 'LLD final map archive inputs unrecognized')
                mapped = []
                for path in sorted(paths):
                    if path.startswith(workspace + '/' + C.MODULES + '/'):
                        relative = C.exact_workspace_path(path, workspace, C.MODULES)
                        C.require(relative in owners and relative in inventory['files'] and relative in row['inputs'],
                                  'map archive not in exact installed ownership and matching actual link inputs')
                        mapped.append(relative)
                    elif path.startswith(original_ndk + '/'):
                        C.require(path in external, 'map NDK archive not authenticated as actual link input')
                    else:
                        provider_failures.append(dict(image=image, unowned_map_archive=path))
                if image == 'libexreader_product.so':
                    expected = C.MODULES + '/lib/libreader_catalog_sqlite.a'
                    C.require(expected in mapped and owners[expected] == 'EXReaderProductCatalog', 'actual product SQLite map owner absent')
                    C.require('sqlite3_open_v2' in text, 'SQLite definition absent from actual map')
                    C.require(C.sqlite_map_owner(text) == workspace + '/' + expected + '(sqlite3.c.o)', 'SQLite symbol attributed to another archive/object in final map')
                found.append(dict(path=name, sha256=C.digest(raw / name), installed_archives=sorted(mapped)))
        map_reports[image] = found
    report = dict(C.identity(), public={k: sorted(v) for k, v in public.items()}, owners=owners,
        manifests=manifests, dependencies={k: sorted(v) for k, v in dependencies.items()},
        private_imports=private, private_header_dependencies=header_uses, image_private_imports=image_private,
        explicitly_private_installed_headers=private_headers, image_reports=image_reports,
        loader_edges=edges, sdk_providers=sdk_providers, provider_failures=provider_failures,
        maps=map_reports, module_final_consumers=consumers, unlinked_installed_modules=[name for name, values in consumers.items() if not values],
        system_symbol_count=len(system), full_six_platform_f07_accepted=False,
        include_dependency_coverage_complete=False,
        include_dependency_gap='Original capture omitted actual compiler dependency records; module-root source scans cannot prove out-of-root/header-only include completeness.')
    report['android_native_symbol_boundary_accepted'] = not (any(private.values()) or any(image_private.values()) or header_uses or provider_failures)
    report['android_static_closure_accepted'] = False  # missing actual compiler-dependency coverage
    C.save(C.OUT / 'android-native-audit.json', report)
    return report
