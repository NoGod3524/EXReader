"""F07 authoritative symbol evidence (read-only).

Reads the six already-accepted peer artifacts of run 41306566948, and re-derives
the SQLite binding facts with the CI-preinstalled LLVM pair instead of a
hand-rolled parser:

  * ELF  : llvm-readobj --symbols --dyn-syms --version-info --needed-libs
  * MachO: llvm-readobj --macho-dsymtab --version-info --needed-libs
  * PE   : llvm-readobj --coff-imports --coff-exports
  * all  : llvm-nm --format=posix (defined / undefined / weak types)

Nothing is built, installed, linked or executed. Every payload read is bounded.
The summary always reports acceptance_assessed=false: this job produces
observations, not a verdict.
"""
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile

RUN_ID = '41306566948'
ARTIFACTS = {
    'windows': 13083193632,
    'android': 13083881725,
    'gtk': 13083892632,
    'macos': 13083986989,
    'iphone': 13084032549,
    'ipad': 13083873210,
}
REPO = os.environ.get('GITHUB_REPOSITORY', 'NoGod3524/EXReader')
TOKEN = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN', '')
OUT_DIR = 'f07-authoritative-symbols'
TOTAL_BUDGET = 300
READ_TIMEOUT = 30
MAX_IDENTIFIERS = 5000
RUNTIME_PRIMS = {'dlopen', 'dlmopen', 'dlsym', 'dlvsym', 'LoadLibraryA', 'LoadLibraryW',
                 'LoadLibraryExA', 'LoadLibraryExW', 'GetProcAddress'}

START = time.monotonic()


class StripAuthOnCrossHost(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            new.headers.pop('Authorization', None)
            new.unredirected_hdrs.pop('Authorization', None)
        return new


OPENER = urllib.request.build_opener(StripAuthOnCrossHost)


def remaining():
    return TOTAL_BUDGET - (time.monotonic() - START)


def download_artifact(aid):
    url = f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip'
    req = urllib.request.Request(url, headers={'User-Agent': 'f07-a11y', 'Authorization': 'Bearer ' + TOKEN})
    return OPENER.open(req, timeout=min(120, max(30, remaining()))).read()


def tool_version(path):
    try:
        p = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=READ_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        return None, f'launch-failed: {exc}'
    if p.returncode != 0:
        return None, f'rc={p.returncode}'
    text = (p.stdout or '') + (p.stderr or '')
    m = re.search(r'(\d+\.\d+\.\d+)', text)
    return (m.group(1) if m else None), text.strip().splitlines()[0][:120] if text.strip() else ''


def preflight():
    pairs = {}
    for name, cands in (('nm', ['llvm-nm-18', 'llvm-nm-19', 'llvm-nm-17', 'llvm-nm']),
                        ('readobj', ['llvm-readobj-18', 'llvm-readobj-19', 'llvm-readobj-17', 'llvm-readobj'])):
        for c in cands:
            from shutil import which
            p = which(c)
            if p:
                ver, note = tool_version(p)
                pairs[name] = {'path': p, 'version': ver, 'note': note}
                break
        else:
            pairs[name] = {'path': None, 'version': None, 'note': 'not found'}
    ok = bool(pairs['nm']['path'] and pairs['readobj']['path']
              and pairs['nm']['version'] and pairs['nm']['version'] == pairs['readobj']['version'])
    return pairs, ok


def run(cmd, cwd=None):
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=min(READ_TIMEOUT, max(5, remaining())))
    except subprocess.TimeoutExpired:
        return {'cmd': ' '.join(cmd), 'timeout': True, 'rc': None, 'stdout_bytes': 0}
    return {'cmd': ' '.join(cmd), 'rc': p.returncode, 'stdout_bytes': len(p.stdout or b''),
            'stderr': (p.stderr or b'').decode('utf-8', 'replace')[:400],
            'out': (p.stdout or b'').decode('utf-8', 'replace'),
            'seconds': round(time.monotonic() - t0, 3)}


SYM_LINE = re.compile(r'^\s*(?:[0-9A-Za-z]+:)?([0-9A-Fa-f]+)?\s*([A-Za-z_][^\s]*)\s*$')
NM_POSIX = re.compile(r'^(\S+)\s+([A-Za-z?])\s+(\S+)$')


def classify_nm(text):
    """Return counts and bounded identifier lists from `llvm-nm --format=posix`."""
    defined, undefined, weak_def, weak_ref = [], [], [], []
    for line in text.splitlines():
        m = NM_POSIX.match(line.strip())
        if not m:
            continue
        name = m.group(3).lstrip('_')
        t = m.group(2)
        if not name.startswith('sqlite3_'):
            continue
        if t in ('U', 'u'):
            undefined.append(name)
            if t == 'u':
                weak_ref.append(name)
        else:
            defined.append(name)
            if t in ('W', 'w', 'V', 'v', 'C'):
                weak_def.append(name)
    return {'defined': sorted(set(defined)), 'undefined': sorted(set(undefined)),
            'weak_defined': sorted(set(weak_def)), 'weak_undefined': sorted(set(weak_ref))}


def bounded(s):
    return s[:MAX_IDENTIFIERS]


def analyse_payload(target, kind, path):
    ops = []
    if kind == 'macho':
        ops.append(run(['llvm-readobj', '--macho-dsymtab', path]))
        ops.append(run(['llvm-readobj', '--version-info', path]))
        ops.append(run(['llvm-readobj', '--needed-libs', path]))
        ops.append(run(['llvm-nm', '--format=posix', '-m', path]))
    elif kind == 'elf':
        ops.append(run(['llvm-readobj', '--symbols', '--dyn-syms', '--version-info', '--needed-libs', path]))
        ops.append(run(['llvm-nm', '--format=posix', path]))
    else:
        ops.append(run(['llvm-readobj', '--coff-imports', '--coff-exports', path]))
    merged = {'defined': [], 'undefined': [], 'weak_defined': [], 'weak_undefined': []}
    for r in ops:
        if r.get('out'):
            c = classify_nm(r['out'])
            for k in merged:
                merged[k].extend(c[k])
    entry = {'target': target, 'kind': kind, 'member': os.path.basename(path),
             'bytes': os.path.getsize(path),
             'operations': [{k: v for k, v in r.items() if k != 'out'} for r in ops],
             'sqlite': {k: bounded(sorted(set(v))) for k, v in merged.items()},
             'sqlite_counts': {k: len(set(v)) for k, v in merged.items()},
             'version_info_present': any('version' in (r.get('out') or '').lower()
                                         and 'version' in ' '.join(r.get('cmd', '')) for r in ops),
             'runtime_prim_hits': sorted({p for r in ops for p in RUNTIME_PRIMS
                                          if p in (r.get('out') or '')}),
             }
    return entry


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pairs, tools_ok = preflight()
    summary = {'run_id': RUN_ID, 'repo': REPO, 'acceptance_assessed': False,
               'scope': 'authoritative symbol observations for F07',
               'tool_preflight': pairs, 'tools_ok': tools_ok,
               'binaries': [], 'errors': [], 'budget_seconds': TOTAL_BUDGET,
               'a4_partial': True, 'a4_reason': 'literal dataflow to dlsym/GetProcAddress not attempted in the bounded run'}
    if not tools_ok:
        summary['errors'].append('llvm pair missing or version mismatch; fail closed before any payload read')
        json.dump(summary, open(os.path.join(OUT_DIR, 'summary.json'), 'w'), indent=1)
        print('FAIL-CLOSED: llvm preflight')
        return 1

    tmp = '/tmp/f07'
    os.makedirs(tmp, exist_ok=True)
    for target, aid in ARTIFACTS.items():
        if remaining() < 60:
            summary['errors'].append(f'budget exhausted before {target}')
            continue
        try:
            blob = download_artifact(aid)
        except Exception as exc:  # noqa: BLE001
            summary['errors'].append(f'{target}: download failed {exc}')
            continue
        z = zipfile.ZipFile(io.BytesIO(blob))
        if 'program.bin' not in z.namelist():
            summary['errors'].append(f'{target}: program.bin missing')
            continue
        payload = z.read('program.bin')
        if payload[:2] == b'PK':
            apk = zipfile.ZipFile(io.BytesIO(payload))
            members = [n for n in apk.namelist() if n.startswith('lib/') and n.endswith('.so')][:64]
            for i, n in enumerate(members):
                p = os.path.join(tmp, f'{target}-{i}.so')
                open(p, 'wb').write(apk.read(n))
                e = analyse_payload(target, 'elf', p)
                e['member'] = n
                summary['binaries'].append(e)
        else:
            kind = 'pe' if payload[:2] == b'MZ' else ('macho' if payload[:4] in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe') else 'elf')
            p = os.path.join(tmp, f'{target}-program.bin')
            open(p, 'wb').write(payload)
            summary['binaries'].append(analyse_payload(target, kind, p))

    weak_total = sum(len(b['sqlite']['weak_defined']) + len(b['sqlite']['weak_undefined'])
                     for b in summary['binaries'])
    summary['weak_version_assessed'] = tools_ok and not summary['errors']
    summary['weak_sqlite_identifiers_total'] = weak_total
    summary['elapsed_seconds'] = round(time.monotonic() - START, 2)
    json.dump(summary, open(os.path.join(OUT_DIR, 'summary.json'), 'w'), indent=1)
    for b in summary['binaries']:
        print(b['target'], b['member'], b['kind'], b['sqlite_counts'],
              'weak=', len(b['sqlite']['weak_defined']) + len(b['sqlite']['weak_undefined']),
              'prims=', b['runtime_prim_hits'])
    print('weak_version_assessed=', summary['weak_version_assessed'],
          'errors=', summary['errors'], 'elapsed=', summary['elapsed_seconds'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
