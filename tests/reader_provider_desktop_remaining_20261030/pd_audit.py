"""Collect real final-program evidence on Windows and macOS and judge it (read-only inspection)."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import traceback

import pd_core as C
import pd_mac as A
import pd_win as W

M = C.M


def staged(label, pending, call, default=None):
    """Run one analysis stage; a failure becomes an explicit pending entry, never a silent pass."""
    try:
        return call()
    except Exception as error:
        pending.append(dict(kind='stage_failed', stage=label, reason=str(error)[:500],
                            trace=traceback.format_exc()[-1200:]))
        return default


def catalog_archive_names(roots, pending, suffixes):
    names, exports = set(), []
    for base in roots:
        for path in sorted(Path(base).rglob('EXReaderProductCatalogTargets*.cmake')):
            exports.append(str(path))
            names.update(re.findall(r'/([\w.+-]+\.(?:%s))"' % '|'.join(suffixes), path.read_text(encoding='utf-8', errors='replace')))
    if not names:
        pending.append(dict(kind='product_catalog_export_not_found', searched=[str(r) for r in roots]))
    return sorted(names), exports


def weak_definitions(evidence, canon):
    """Explain every weak definition among selected members from the selected definers only."""
    strong, weak = {}, {}
    for archive, member in evidence['selected']:
        row = evidence['archives'].get(archive, {}).get(member)
        if not row:
            continue
        for s in row['defined']:
            strong.setdefault(canon(s), []).append([archive, member])
        for s in row['weak']:
            weak.setdefault(canon(s), []).append([archive, member])
    rows = []
    for symbol, owners in sorted(weak.items()):
        rows.append(dict(symbol=symbol, weak_definers=len(owners), strong_definers=len(strong.get(symbol, [])),
                         first_definer=owners[0],
                         status='weak_overridden_by_selected_strong_definer' if symbol in strong
                         else 'coalesced_weak_definition_no_strong_definer'))
    return rows


def finish(evidence, canon, out, extra):
    """Policy, negative controls, result.json. Never writes an acceptance flag as True."""
    findings = C.policy(evidence, canon)
    controls = C.negative_controls(evidence, canon)
    weak = weak_definitions(evidence, canon)
    pending = extra['pending']
    unresolved = [r for r in extra.get('imports', []) if r['status'] != 'resolved']
    if unresolved:
        pending.append(dict(kind='imports_unresolved', count=len(unresolved), sample=unresolved[:20]))
    result = dict(evidence['identity'], platform=evidence['platform'], findings=findings, finding_kinds=C.kinds(findings),
                  negative_controls=controls, negative_controls_all_rejected=all(c['rejected'] for c in controls),
                  passed=not findings and all(c['rejected'] for c in controls),
                  pending=pending, evidence_complete=not findings and not pending and all(c['rejected'] for c in controls),
                  image=evidence['image'], map=evidence['map'], selected_members=len(evidence['selected']),
                  archives_inspected=len(evidence['archives']), installed_libraries=len(evidence['installed_libraries']),
                  dynamic_needed=evidence['dynamic_needed'], runtime_identity=evidence.get('runtime_identity', []),
                  weak_definitions=dict(count=len(weak), by_status=C.kinds([dict(kind=r['status']) for r in weak])),
                  imports=dict(count=len(extra.get('imports', [])), unresolved=len(unresolved),
                               weak_or_delay=sum(1 for r in extra.get('imports', []) if r.get('weak')),
                               by_status=C.kinds([dict(kind=r['status']) for r in extra.get('imports', [])])),
                  sqlite_references=M.sqlite_reference_rows(C.as_sets(evidence), canon))
    for flag in C.ACCEPT_FLAGS:
        result[flag] = False
    C.save(out / 'evidence.json', evidence)
    C.save(out / 'imports.json', extra.get('imports', []))
    C.save(out / 'weak-definitions.json', weak)
    C.save(out / 'result.json', result)
    return result


def sqlite_classes(result):
    counts = {}
    for row in result['sqlite_references']:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    return counts


# ---- Windows -----------------------------------------------------------------------------------

def collect_windows(cfg, out):
    out = Path(out)
    pending = []
    fold = lambda p: C.norm(p, True)
    link_cwd = fold(cfg['link_cwd'])
    lib_dirs = [fold(d) for d in cfg['lib_dirs'] if d]
    image = Path(cfg['image'])
    package = Path(cfg['package_image'])
    text = Path(cfg['map']).read_text(encoding='utf-8', errors='replace')
    parsed = W.parse_msvc_map(text)
    roles = dict(sdk=[fold(cfg['sdk']) + '/'], product=[fold(p) + '/' for p in cfg['product']],
                 host=[link_cwd + '/'], system=[d + '/' for d in lib_dirs] + ['c:/windows/', 'c:/program files/', 'c:/program files (x86)/'])
    installed = C.library_identities([('sdk', cfg['sdk']), *[('product', p) for p in cfg['product']], ('host', cfg['link_cwd'])],
                                     ('.lib', '.dll', '.a'), True)
    archives, kinds = {}, {}

    def table_of(path):
        if path not in archives:
            archives[path], kinds[path] = W.parse_coff_archive(Path(path).read_bytes())
        return archives[path]

    for row in installed:
        if row['path'].endswith(('.lib', '.a')):
            staged('archive ' + row['path'], pending, lambda r=row: table_of(r['path']))
    selected = []
    for archive, member in parsed['members']:
        path = W.resolve_input(archive, link_cwd, lib_dirs)
        selected.append([path, member])
        if C.M.classify(path, roles) != 'system' and path not in archives and os.path.isfile(path):
            staged('archive ' + path, pending, lambda p=path: table_of(p))
    for loose in parsed['objects']:
        path = W.resolve_input(loose, link_cwd, lib_dirs)
        if not path.endswith('.obj'):
            pending.append(dict(kind='non_object_map_input', input=loose))
            continue
        if M.classify(path, roles) == 'system':
            continue
        if not os.path.isfile(path):
            pending.append(dict(kind='loose_object_not_retained', input=loose, resolved=path))
            continue

        def read_object(p=path):
            what, row = W.parse_coff_object(Path(p).read_bytes())
            if what != 'object':
                raise ValueError('map input is not a COFF object: ' + what)
            archives[p] = {W.member_key(p): row}
        if staged('object ' + path, pending, read_object, default='failed') != 'failed':
            selected.append([path, W.member_key(path)])
    names, exports = catalog_archive_names([cfg['sdk'], *cfg['product']], pending, ('lib', 'a'))
    needed_text = W.run_text(['dumpbin', '/nologo', '/dependents', image])
    imports_text = W.run_text(['dumpbin', '/nologo', '/imports', image])
    (out / 'native').mkdir(parents=True, exist_ok=True)
    (out / 'native/dependents.txt').write_text(needed_text, encoding='utf-8')
    (out / 'native/imports.txt').write_text(imports_text, encoding='utf-8')
    needed = W.parse_dumpbin_dependents(needed_text)
    imports = W.parse_dumpbin_imports(imports_text)
    dll_exports = {}

    def exports_of(dll):
        key = dll.lower()
        if key not in dll_exports:
            found = None
            for base in (Path(cfg['package_dir']), Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'):
                if (base / dll).is_file():
                    found = base / dll
                    break
            if found is None:
                dll_exports[key] = (None, None)
            else:
                dump = W.run_text(['dumpbin', '/nologo', '/exports', found])
                (out / 'native' / ('exports-%s.txt' % key)).write_text(dump, encoding='utf-8')
                dll_exports[key] = (str(found), W.parse_dumpbin_exports(dump))
        return dll_exports[key]

    for row in imports:
        row['weak'] = row['kind'] == 'delay'
        found, names_ = staged('exports ' + row['library'], pending, lambda r=row: exports_of(r['library']), default=(None, None))
        if found is None:
            row.update(status='pending', reason='library_not_found_on_runner')
        elif row['symbol'] in names_ or row['symbol'].startswith('#'):
            row.update(status='resolved', provider=found,
                       explanation='delay-load import resolved against the library export table' if row['weak']
                       else 'import resolved against the library export table')
        else:
            row.update(status='pending', reason='symbol_not_in_exports', provider=found)
    runtime = []
    same = C.digest(image) == C.digest(package)
    runtime.append(dict(name='package_image_equals_host_image', status='ok' if same else 'mismatch',
                        expected_sha256=C.digest(image), actual_sha256=C.digest(package)))
    package_dir = Path(cfg['package_dir'])
    package_files = [dict(path=str(p.relative_to(package_dir)).replace(os.sep, '/'), size=p.stat().st_size, sha256=C.digest(p))
                    for p in sorted(package_dir.rglob('*')) if p.is_file() and p.suffix.lower() in ('.exe', '.dll')]
    evidence = dict(identity=C.identity('windows', cfg['sdk_version']), platform='windows',
                    image=dict(path=str(image), size=image.stat().st_size, sha256=C.digest(image), package_files=package_files),
                    map=dict(path=str(cfg['map']), sha256=C.digest(cfg['map']), format=parsed['format']),
                    roles=roles, archives={a: {m: {k: sorted(v) for k, v in row.items()} for m, row in t.items()} for a, t in archives.items()},
                    selected=selected, product_catalog_archives=names,
                    product_catalog_exports=exports, dynamic_needed=needed,
                    dynamic_imports=imports, runtime_identity=runtime, forbidden_dynamic_sdk=['exreader'],
                    installed_libraries=installed, member_kinds={a: k for a, k in kinds.items()})
    if not names:
        owners = [s for s in selected if M.classify(s[0], roles) == 'product']
        evidence['product_catalog_archives'] = sorted({os.path.basename(s[0]) for s in owners})
    return finish(evidence, lambda s: s, out, dict(pending=pending, imports=imports))


# ---- macOS -------------------------------------------------------------------------------------

def collect_macos(cfg, out):
    out = Path(out)
    pending = []
    image = Path(cfg['image'])
    parsed = A.parse_apple_map(Path(cfg['map']).read_text(encoding='utf-8', errors='replace'))
    developer = A.run_text(['xcode-select', '-p']).strip()
    sdk_path = A.run_text(['xcrun', '--sdk', 'macosx', '--show-sdk-path']).strip()
    temp = {tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir()), '/var/folders', '/private/var/folders'}
    roles = dict(sdk=[C.norm(cfg['sdk']) + '/'], product=[C.norm(cfg['products']) + '/'],
                 host=[C.norm(cfg['host']) + '/'] + [C.norm(t) + '/' for t in sorted(temp)],
                 system=[C.norm(developer) + '/', '/usr/lib/', '/System/', '/Library/', '/Applications/Xcode'])
    installed = C.library_identities([('sdk', cfg['sdk']), ('product', cfg['products']), ('host', cfg['frameworks'])],
                                     ('.a', '.dylib'))
    (out / 'native').mkdir(parents=True, exist_ok=True)
    archives = {}
    for row in installed:
        if row['path'].endswith('.a'):
            def read_archive(r=row):
                text = A.run_text(['nm', '-m', '-g', r['path']])
                (out / 'native' / ('archive-%s.nm.txt' % C.sha(r['path'].encode())[:12])).write_text(text, encoding='utf-8')
                archives[r['path']] = A.parse_nm_members(text)
            staged('archive ' + row['path'], pending, read_archive)
    selected = []
    for archive, member in parsed['members']:
        path = C.norm(archive)
        selected.append([path, member])
        if M.classify(path, roles) != 'system' and path not in archives and os.path.isfile(path):
            def read_extra(p=path):
                archives[p] = A.parse_nm_members(A.run_text(['nm', '-m', '-g', p]))
            staged('archive ' + path, pending, read_extra)
    for loose in parsed['objects']:
        path = C.norm(loose)
        if M.classify(path, roles) == 'system':
            continue
        if not loose.endswith('.o') or not os.path.isfile(path):
            pending.append(dict(kind='loose_object_not_inspectable', input=loose, exists=os.path.isfile(path)))
            continue

        def read_object(p=path):
            archives[p] = A.parse_nm_members(A.run_text(['nm', '-m', '-g', p]), single=os.path.basename(p))
        if staged('object ' + path, pending, read_object, default='failed') != 'failed':
            selected.append([path, os.path.basename(path)])
    names, exports = catalog_archive_names([cfg['products']], pending, ('a',))
    libs_text = A.run_text(['otool', '-L', image])
    (out / 'native/otool-L.txt').write_text(libs_text, encoding='utf-8')
    needed = A.parse_otool_libraries(libs_text)
    imports_text = A.run_text(['nm', '-m', '-u', image])
    (out / 'native/image-undefined.nm.txt').write_text(imports_text, encoding='utf-8')
    imports = A.parse_image_imports(imports_text)
    by_short = {}
    for name in needed:
        by_short.setdefault(A.short_name(name), []).append(name)
    stubs = A.StubIndex(sdk_path)
    frameworks = Path(cfg['frameworks'])
    sdk_exports = {}

    def exports_of_dylib(path):
        if path not in sdk_exports:
            text = A.run_text(['nm', '-gU', path])
            sdk_exports[path] = set(re.findall(r'^[0-9a-fA-F]{8,16}\s+\S\s+(\S+)$', text, re.M))
        return sdk_exports[path]

    runtime = []
    for row in imports:
        row['weak'] = bool(row['weak'])
        libs = by_short.get(row['library'] or '', [])
        if not libs:
            row.update(status='pending', reason='import_library_not_in_otool_list')
            continue
        hit = None
        for install in libs:
            if os.path.basename(install).startswith('libexreader'):
                bundled = frameworks / os.path.basename(install)
                if bundled.is_file():
                    found = staged('exports ' + str(bundled), pending, lambda b=bundled: exports_of_dylib(str(b)), default=set())
                    if row['symbol'] in found:
                        hit = dict(stub=str(bundled), install_name=install, weak_definition=False)
            else:
                hit = staged('stub ' + install, pending, lambda i=install: stubs.provider(i, row['symbol']))
            if hit:
                break
        if hit:
            row.update(status='resolved', provider=hit, explanation=(
                'weak import (optional at runtime); provider exports the symbol' if row['weak'] else 'import resolved against the provider export table'))
        else:
            row.update(status='pending', reason='symbol_not_in_provider_stubs', candidates=libs)
    for install in needed:
        if os.path.basename(install).startswith('libexreader'):
            installed_sdk = Path(cfg['sdk']) / 'lib' / os.path.basename(install)
            bundled = frameworks / os.path.basename(install)
            if installed_sdk.is_file() and bundled.is_file():
                same = C.digest(installed_sdk) == C.digest(bundled)
                runtime.append(dict(name=install, status='ok' if same else 'mismatch', expected_sha256=C.digest(installed_sdk),
                                    actual_sha256=C.digest(bundled)))
            else:
                runtime.append(dict(name=install, status='mismatch', expected_sha256=None, actual_sha256=None,
                                    reason='installed SDK runtime or bundled copy missing'))
    for dylib in parsed['dylibs']:
        if dylib.endswith('.dylib') and os.path.basename(dylib).startswith('libexreader') and os.path.isfile(dylib):
            bundled = frameworks / os.path.basename(os.path.realpath(dylib))
            runtime.append(dict(name='map input ' + dylib, status='ok' if bundled.is_file() and C.digest(dylib) == C.digest(bundled) else 'mismatch',
                                expected_sha256=C.digest(dylib), actual_sha256=C.digest(bundled) if bundled.is_file() else None))
    extra_findings = []
    sdk_archives = [s for s in selected if M.classify(s[0], roles) == 'sdk']
    if sdk_archives and any(os.path.basename(n).startswith('libexreader') for n in needed):
        extra_findings.append(dict(kind='second_sdk_provider_static_and_dynamic', members=sdk_archives[:10], count=len(sdk_archives)))
    evidence = dict(identity=C.identity('macos', cfg['sdk_version']), platform='macos',
                    image=dict(path=str(image), size=image.stat().st_size, sha256=C.digest(image)),
                    map=dict(path=str(cfg['map']), sha256=C.digest(cfg['map']), format=parsed['format'], dylib_inputs=parsed['dylibs']),
                    roles=roles, archives={a: {m: {k: sorted(v) for k, v in row.items()} for m, row in t.items()} for a, t in archives.items()},
                    selected=selected, product_catalog_archives=names, product_catalog_exports=exports,
                    dynamic_needed=needed, dynamic_imports=imports, runtime_identity=runtime, extra_findings=extra_findings,
                    installed_libraries=installed, sdk_path=sdk_path)
    if not names:
        owners = [s for s in selected if M.classify(s[0], roles) == 'product']
        evidence['product_catalog_archives'] = sorted({os.path.basename(s[0]) for s in owners})
    return finish(evidence, lambda s: s[1:] if s.startswith('_') else s, out, dict(pending=pending, imports=imports))
