"""Resolve the final image's dynamic imports against recorded system-library identities and exports.

Same-job, same-runner evidence only: libraries are hashed and their dynamic exports read in the
Actions job that built and audited the image. Unresolved items stay pending (or become findings
when the link-time contract proves them wrong); nothing is inferred from another run.
"""
import json
import os
from pathlib import Path
import re
import subprocess

import fp_core as C
import fp_maps as M

SEARCH_DIRS = ('/lib/x86_64-linux-gnu', '/usr/lib/x86_64-linux-gnu', '/lib64', '/usr/lib64', '/lib', '/usr/lib')
RESOLVED_PENDING_KINDS = ('weak_undefined_imports_unproven', 'unversioned_imports_unproven_without_system_dso')


def parse_dynamic_header(text):
    """`readelf -W -d` -> dict(soname, needed[], runpath[])."""
    if 'Dynamic section' not in text:
        raise ValueError('not a readelf dynamic section')
    return dict(soname=next(iter(re.findall(r'\(SONAME\)\s+Library soname: \[([^\]]+)\]', text)), None),
                needed=re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', text),
                runpath=re.findall(r'\((?:RUNPATH|RPATH)\)\s+Library r(?:un)?path: \[([^\]]*)\]', text))


def exports_of(symbols):
    """Defined, externally visible dynamic symbols -> [(name, version, default)]."""
    return [(s['name'], s['version'], s.get('default', True)) for s in symbols
            if s['ndx'] != 'UND' and s['name'] and s['type'] in ('FUNC', 'OBJECT', 'NOTYPE', 'TLS', 'IFUNC', 'GNU_IFUNC')
            and s.get('vis', 'DEFAULT') in ('DEFAULT', 'PROTECTED')]


def verify_recorded(libs, digest=C.digest):
    """Recompute every recorded library digest in the same job; any drift rejects the evidence."""
    for name, lib in libs.items():
        C.require(lib.get('sha256') and lib.get('path'), 'library identity incomplete: ' + name)
        C.require(digest(lib['path']) == lib['sha256'], 'recorded library digest differs from file: ' + name)
    return True


def closure(needed, libs):
    """Load-order BFS over recorded libraries. Returns (order, missing)."""
    order, missing, queue = [], [], list(needed)
    while queue:
        name = queue.pop(0)
        if name in order or name in missing:
            continue
        lib = libs.get(name)
        if lib is None or lib.get('exports') is None:
            missing.append(name)
            continue
        order.append(name)
        queue.extend(lib.get('needed', []))
    return order, missing


def _provides(lib, name, version, verneed):
    for export, export_version, default in lib['exports']:
        if export != name:
            continue
        if version:
            if export_version != version:
                continue
            files = {f for f, versions in verneed.items() if version in versions}
            if lib.get('soname') not in files and lib.get('basename') not in files:
                continue
            return True
        if default:
            return True
    return False


def resolve_imports(symbols, verneed, needed, libs, runpath=()):
    """Return (rows, findings, pending). Each import gets exactly one row."""
    rows, findings, pending = [], [], []
    order, missing = closure(needed, libs)
    complete = not missing and not runpath
    for name in missing:
        pending.append(dict(kind='needed_library_unrecorded', library=name))
    if runpath:
        pending.append(dict(kind='custom_runpath_not_resolved', runpath=sorted(set(runpath))))
    for name in order:
        for export, _, _ in libs[name]['exports']:
            if export.startswith('sqlite3'):
                findings.append(dict(kind='system_sqlite_library_in_closure', library=name, symbol=export))
                break
    for sym in symbols:
        if sym['ndx'] != 'UND' or not sym['name']:
            continue
        label = sym['name'] + ('@' + sym['version'] if sym['version'] else '')
        providers = [n for n in order if _provides(libs[n], sym['name'], sym['version'], verneed)]
        row = dict(import_=label, bind=sym['bind'], providers=[dict(library=n, sha256=libs[n]['sha256']) for n in providers])
        if providers and not runpath:
            row['status'] = 'resolved'
        elif not complete:
            row['status'] = 'pending'
            row['reason'] = 'recorded library closure incomplete or custom runpath'
        elif sym['version']:
            row['status'] = 'FINDING'
            row['reason'] = 'versioned import not exported with that version by a verneed-matching library'
            findings.append(dict(kind='versioned_import_unprovided', symbol=label))
        elif sym['bind'] == 'WEAK':
            row['status'] = 'pending'
            row['reason'] = 'weak import has no provider in the recorded closure; not waived'
        else:
            row['status'] = 'FINDING'
            row['reason'] = 'strong unversioned import absent from the recorded closure'
            findings.append(dict(kind='strong_import_unprovided', symbol=label))
        rows.append(row)
    for row in rows:
        if row['status'] == 'pending':
            pending.append(dict(kind='import_unresolved', import_=row['import_'], reason=row['reason']))
    return rows, findings, pending


def _run(args):
    return subprocess.run(list(map(str, args)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _package(path):
    owner = _run(['dpkg-query', '-S', path]) if Path('/usr/bin/dpkg-query').exists() else None
    if owner is None or owner.returncode != 0:
        return None
    package = owner.stdout.decode().split(':')[0].strip()
    version = _run(['dpkg-query', '-W', '-f=${Version}', package]).stdout.decode().strip()
    return dict(package=package, version=version)


def record_libraries(needed, out):
    """Resolve NEEDED names in default system directories and record identity + dynamic exports."""
    readelf = '/usr/bin/readelf' if Path('/usr/bin/readelf').exists() else 'readelf'
    libs, queue = {}, list(needed)
    while queue:
        name = queue.pop(0)
        if name in libs:
            continue
        hits = sorted({os.path.realpath(os.path.join(d, name)) for d in SEARCH_DIRS if os.path.exists(os.path.join(d, name))})
        if len(hits) != 1:
            libs[name] = dict(path=None, exports=None, reason='unresolved' if not hits else 'ambiguous: %s' % hits)
            continue
        real = hits[0]
        header = parse_dynamic_header(_run([readelf, '-W', '-d', real]).stdout.decode())
        dyn = _run([readelf, '-W', '--dyn-syms', real])
        symbols = M.parse_dyn_syms(dyn.stdout.decode())
        libs[name] = dict(path=real, basename=os.path.basename(real), sha256=C.digest(real), bytes=os.path.getsize(real),
                          soname=header['soname'], needed=header['needed'], runpath=header['runpath'],
                          package=_package(real), exports=exports_of(symbols))
        queue.extend(header['needed'])
    (Path(out)).mkdir(parents=True, exist_ok=True)
    return libs


def environment():
    release = Path('/etc/os-release')
    return dict(runner_os=os.environ.get('RUNNER_OS'), runner_arch=os.environ.get('RUNNER_ARCH'),
                image_os=os.environ.get('ImageOS'), image_version=os.environ.get('ImageVersion'),
                os_release_sha256=C.digest(release) if release.exists() else None, run_id=os.environ.get('GITHUB_RUN_ID'),
                attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), source_sha=os.environ.get('GITHUB_SHA'))


def audit(image, header, dynamic, out):
    """Production entry: header = parse_dynamic_header of the image. Returns dict for result.json."""
    libs = record_libraries(header['needed'], out)
    recorded = {k: v for k, v in libs.items() if v.get('path')}
    verify_recorded(recorded)
    rows, findings, pending = resolve_imports(dynamic['symbols'], dynamic['verneed'], header['needed'], libs, header['runpath'])
    record = dict(environment=environment(), image_sha256=C.digest(image), libraries=libs, imports=rows)
    C.save(Path(out) / 'system-libraries.json', record)
    counts = {}
    for row in rows:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    return dict(findings=findings, pending=pending, import_status_counts=counts, imports=rows,
                libraries={k: dict(path=v.get('path'), sha256=v.get('sha256'), package=v.get('package'), reason=v.get('reason'))
                           for k, v in libs.items()})
