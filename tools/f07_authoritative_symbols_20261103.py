"""F07 authoritative symbol evidence (read-only).

Reads the six already-accepted peer artifacts of run 41306566948, and re-derives
the SQLite binding facts with the CI-preinstalled LLVM pair instead of a
hand-rolled parser:

  * ELF  : llvm-readobj --symbols --dyn-syms --version-info --needed-libs
  * MachO: llvm-readobj --symbols --needed-libs
  * PE   : llvm-readobj --coff-imports --coff-exports
  * all  : llvm-nm --format=posix (defined / undefined / weak types)

Nothing is built, installed, linked or executed. Every payload read is bounded.
The summary always reports acceptance_assessed=false: this job produces
observations, not a verdict.
"""
import io
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

RUN_ID = '41306566948'
SOURCE_SHA = 'ec11cf862ca3b44483d7e8c4726ae748ab438337'
REPOSITORY_ID = 1421442522
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
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_ERROR_BYTES = 128 * 1024
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


def timeout():
    left = remaining()
    if left <= 0:
        raise TimeoutError('total budget exhausted')
    return min(READ_TIMEOUT, left)


def read_bounded(response, limit):
    chunks, size = [], 0
    while True:
        timeout()
        chunk = response.read(min(1024 * 1024, limit + 1 - size))
        if not chunk:
            return b''.join(chunks)
        size += len(chunk)
        if size > limit:
            raise ValueError('response byte limit exceeded')
        chunks.append(chunk)


def api_json(path):
    req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/{path}',
        headers={'User-Agent': 'f07-audit', 'Authorization': 'Bearer ' + TOKEN})
    with OPENER.open(req, timeout=timeout()) as response:
        return json.loads(read_bounded(response, 2 * 1024 * 1024))


def validate_artifact(metadata, aid, blob):
    run = metadata.get('workflow_run') or {}
    if (metadata.get('id') != aid or metadata.get('expired') is not False
            or run.get('id') != int(RUN_ID) or run.get('head_sha') != SOURCE_SHA
            or run.get('repository_id') != REPOSITORY_ID
            or run.get('head_repository_id') != REPOSITORY_ID):
        raise ValueError('artifact identity does not match fixed producer')
    digest = 'sha256:' + hashlib.sha256(blob).hexdigest()
    if metadata.get('digest') != digest or metadata.get('size_in_bytes') != len(blob):
        raise ValueError('artifact size/digest mismatch or missing digest')
    return digest


def download_artifact(aid):
    metadata = api_json(f'actions/artifacts/{aid}')
    url = f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip'
    req = urllib.request.Request(url, headers={'User-Agent': 'f07-a11y', 'Authorization': 'Bearer ' + TOKEN})
    with OPENER.open(req, timeout=timeout()) as response:
        blob = read_bounded(response, MAX_ARCHIVE_BYTES)
    validate_artifact(metadata, aid, blob)
    return blob, metadata


def tool_version(path):
    result = run([path, '--version'])
    if not operation_ok(result):
        return None, f"tool version failed: rc={result.get('rc')}"
    text = (result.get('out') or '') + (result.get('stderr') or '')
    m = re.search(r'(\d+\.\d+\.\d+)', text)
    return (m.group(1) if m else None), text.strip().splitlines()[0][:120] if text.strip() else ''


def _candidates(base):
    """PATH entries (highest version first), then the plain name, then distro trees."""
    from shutil import which
    found = []
    for v in range(21, 13, -1):
        p = which('%s-%d' % (base, v))
        if p:
            found.append(p)
    p = which(base)
    if p:
        found.append(p)
    import glob
    found.extend(sorted(glob.glob('/usr/lib/llvm-*/bin/' + base), reverse=True))
    return found


NM_BIN = None
RO_BIN = None


def preflight():
    """Pick one llvm-nm / llvm-readobj pair whose parsed versions are identical."""
    global NM_BIN, RO_BIN
    pairs = {'nm': {'path': None, 'version': None, 'note': 'not found'},
             'readobj': {'path': None, 'version': None, 'note': 'not found'}}
    nm_all, ro_all = _candidates('llvm-nm'), _candidates('llvm-readobj')
    pairs['nm']['note'] = 'searched %d candidate(s): %s' % (len(nm_all), nm_all)
    pairs['readobj']['note'] = 'searched %d candidate(s): %s' % (len(ro_all), ro_all)
    for n in nm_all:
        vn, note_n = tool_version(n)
        if not vn:
            continue
        for r in ro_all:
            vr, note_r = tool_version(r)
            if vr and vr == vn:
                NM_BIN, RO_BIN = n, r
                pairs['nm'] = {'path': n, 'version': vn, 'note': note_n}
                pairs['readobj'] = {'path': r, 'version': vr, 'note': note_r}
                return pairs, True
    if nm_all:
        vn, note_n = tool_version(nm_all[0])
        pairs['nm'] = {'path': nm_all[0], 'version': vn, 'note': note_n}
    if ro_all:
        vr, note_r = tool_version(ro_all[0])
        pairs['readobj'] = {'path': ro_all[0], 'version': vr, 'note': note_r}
    return pairs, False


def run(cmd, cwd=None):
    t0 = time.monotonic()
    # resolve the bare tool names chosen by preflight (the runner only ships
    # versioned or /usr/lib/llvm-*/bin paths, so the bare name may not exist)
    cmd = [NM_BIN if c == 'llvm-nm' else RO_BIN if c == 'llvm-readobj' else c for c in cmd]
    if any(c is None for c in cmd):
        return {'cmd': ' '.join(str(c) for c in cmd), 'rc': None, 'stdout_bytes': 0,
                'stderr': 'tool path unresolved', 'out': ''}
    result = {'cmd': ' '.join(cmd), 'argv': cmd, 'rc': None, 'stdout_bytes': 0}
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            deadline = time.monotonic() + timeout()
            p = subprocess.Popen(cmd, cwd=cwd, stdout=stdout, stderr=stderr)
            while p.poll() is None:
                if time.monotonic() >= deadline:
                    result['timeout'] = True
                    p.kill()
                    break
                if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT_BYTES or os.fstat(stderr.fileno()).st_size > MAX_ERROR_BYTES:
                    result['output_limit_exceeded'] = True
                    p.kill()
                    break
                time.sleep(0.02)
            result['rc'] = p.wait()
        except (OSError, TimeoutError) as exc:
            result['error'] = str(exc)
        result['stdout_bytes'] = os.fstat(stdout.fileno()).st_size
        result['stderr_bytes'] = os.fstat(stderr.fileno()).st_size
        if result['stdout_bytes'] > MAX_OUTPUT_BYTES or result['stderr_bytes'] > MAX_ERROR_BYTES:
            result['output_limit_exceeded'] = True
        stdout.seek(0)
        stderr.seek(0)
        result['stderr'] = stderr.read(MAX_ERROR_BYTES).decode('utf-8', 'replace')
        result['out'] = (stdout.read(MAX_OUTPUT_BYTES).decode('utf-8', 'replace')
                         if result['rc'] == 0 and not result.get('timeout')
                         and not result.get('output_limit_exceeded') else '')
    result['seconds'] = round(time.monotonic() - t0, 3)
    return result


RO_NAME = re.compile(r'^\s*Name:\s+([^\s(]*)', re.MULTILINE)


def classify_readobj(text):
    """Parse Symbol blocks only; section/import names are not symbols."""
    defined, undefined, weak_def, weak_ref = [], [], [], []
    cur = None

    def finish(rec):
        if not rec:
            return
        nm = rec['name'].removeprefix('_')
        if not nm.startswith('sqlite3_'):
            return
        if rec['undef'] is None:
            raise ValueError('SQLite symbol has no recognized definition state')
        if rec['undef']:
            undefined.append(nm)
            if rec['weak']:
                weak_ref.append(nm)
        else:
            defined.append(nm)
            if rec['weak']:
                weak_def.append(nm)

    depth = 0
    in_symbols = False
    for line in text.splitlines():
        if not depth:
            if line.strip() in ('Symbols [', 'DynamicSymbols ['):
                in_symbols = True
            elif line.strip() == ']':
                in_symbols = False
            elif in_symbols and line.strip() == 'Symbol {':
                depth = 1
            continue
        depth += line.count('{') - line.count('}')
        if depth == 0:
            if cur is None:
                raise ValueError('symbol block has no name')
            finish(cur)
            cur = None
            continue
        m = RO_NAME.match(line)
        if m:
            cur = {'name': m.group(1), 'undef': None, 'weak': False}
            continue
        if cur is None:
            continue
        # Mach-O prints RefType: UndefinedNonLazy even on defined symbols.
        # Only the symbol Type/Section fields determine whether it is undefined.
        if re.match(r'^\s*(?:Type|Section):\s+(?:Undef|Undefined)\b', line):
            cur['undef'] = True
        elif re.match(r'^\s*(?:Section:\s+|Type:\s+Absolute\b)', line):
            cur['undef'] = False
        if re.match(r'^\s*(?:Binding:\s+Weak\b|Weak(?:Def|Ref)\b)', line):
            cur['weak'] = True
    if depth:
        raise ValueError('unterminated symbol block')
    return {'defined': sorted(set(defined)), 'undefined': sorted(set(undefined)),
            'weak_defined': sorted(set(weak_def)), 'weak_undefined': sorted(set(weak_ref))}


def classify_nm(text):
    """Parse typed POSIX/BSD output; untyped SQLite lines cannot be assessed."""
    defined, undefined, weak_def, weak_ref = [], [], [], []
    hexish = re.compile(r'^(0x)?[0-9A-Fa-f]+$')
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            if line.strip().startswith(('sqlite3_', '_sqlite3_')):
                raise ValueError('untyped SQLite symbol')
            continue
        name = t = None
        if len(parts) >= 3 and hexish.match(parts[0]) and len(parts[1]) == 1 and parts[1].isalpha():
            name, t = parts[2], parts[1]                 # bsd: value type name
        elif len(parts[1]) == 1 and parts[1].isalpha():
            name, t = parts[0], parts[1]                 # posix: name type [value]
        elif len(parts[0]) == 1 and parts[0].isalpha():
            t, name = parts[0], parts[1]                 # bsd undefined: U name
        if not name:
            if any(p.startswith(('sqlite3_', '_sqlite3_')) for p in parts):
                raise ValueError('unrecognized SQLite symbol type/format')
            continue
        base = name.removeprefix('_')
        if not base.startswith('sqlite3_'):
            continue
        if t in ('U', 'w', 'v'):
            undefined.append(base)
            if t in ('w', 'v'):
                weak_ref.append(base)
        else:
            defined.append(base)
            if t in ('W', 'V'):
                weak_def.append(base)
    return {'defined': sorted(set(defined)), 'undefined': sorted(set(undefined)),
            'weak_defined': sorted(set(weak_def)), 'weak_undefined': sorted(set(weak_ref))}


def bounded(s):
    return s[:MAX_IDENTIFIERS]


def classify_coff(text):
    result = {'defined': [], 'undefined': [], 'weak_defined': [], 'weak_undefined': []}
    for match in re.finditer(r'(?m)^\s*(Import|DelayImport|Export) \{([^}]+)\}', text):
        exported = match[1] == 'Export'
        field = 'Name' if exported else 'Symbol'
        for name in re.findall(r'(?m)^\s*' + field + r':\s+(\S+)', match[2]):
            if name.startswith('sqlite3_'):
                result['defined' if exported else 'undefined'].append(name)
    return {k: sorted(set(v)) for k, v in result.items()}


def classify_elf_versions(text):
    """GNU version index 0/1 is unversioned; the high bit records hiddenness."""
    start = re.search(r'(?m)^VersionSymbols \[\r?\n', text)
    if not start:
        raise ValueError('GNU version-symbol table was not returned')
    end = re.search(r'(?m)^\]', text[start.end():])
    if not end:
        raise ValueError('unterminated GNU version-symbol table')
    records = []
    for block in re.findall(r'Symbol \{([^}]+)\}', text[start.end():start.end() + end.start()]):
        name = RO_NAME.search(block)
        if not name or not name[1].startswith('sqlite3_'):
            continue
        version = re.search(r'(?m)^\s*Version:\s+(0x[0-9A-Fa-f]+|\d+)\b', block)
        if not version:
            raise ValueError('SQLite GNU version index is missing')
        raw = int(version[1], 16 if version[1].startswith('0x') else 10)
        if raw > 0xffff:
            raise ValueError('SQLite GNU version index exceeds the 16-bit field')
        records.append({'name': name[1], 'index': raw & 0x7fff, 'hidden': bool(raw & 0x8000)})
    return records


def operation_ok(result):
    return (result.get('rc') == 0 and not any(result.get(k) for k in
            ('timeout', 'error', 'parse_error', 'output_limit_exceeded')))


def payload_members(target, blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        if archive.namelist().count('program.bin') != 1:
            raise ValueError('program.bin must occur exactly once')
        info = archive.getinfo('program.bin')
        if info.file_size > MAX_MEMBER_BYTES:
            raise ValueError('program.bin byte limit exceeded')
        payload = archive.read(info)
    program_sha256 = hashlib.sha256(payload).hexdigest()
    if target == 'android':
        with zipfile.ZipFile(io.BytesIO(payload)) as apk:
            members = [i for i in apk.infolist() if i.filename.startswith('lib/') and i.filename.endswith('.so')]
            if not 0 < len(members) <= 64 or len({i.filename for i in members}) != len(members):
                raise ValueError('APK library list is empty, duplicate or exceeds 64')
            if sum(i.file_size for i in members) > MAX_MEMBER_BYTES:
                raise ValueError('APK library byte limit exceeded')
            binaries = [(i.filename, 'elf', apk.read(i)) for i in members]
    else:
        kind = {'windows': 'pe', 'gtk': 'elf', 'macos': 'macho', 'iphone': 'macho', 'ipad': 'macho'}[target]
        binaries = [('program.bin', kind, payload)]
    for name, kind, binary in binaries:
        valid = (binary.startswith(b'\x7fELF') if kind == 'elf' else binary.startswith(b'MZ') if kind == 'pe'
                 else binary[:4] in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
                                     b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                                     b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'))
        if not valid:
            raise ValueError(f'{target}/{name}: unexpected binary format')
    return binaries, program_sha256


def analyse_payload(target, kind, path):
    ops = []
    if kind == 'macho':
        ops.append(run(['llvm-readobj', '--symbols', path]))
        ops.append(run(['llvm-readobj', '--needed-libs', path]))
        ops.append(run(['llvm-nm', '--format=posix', path]))
    elif kind == 'elf':
        ops.append(run(['llvm-readobj', '--symbols', '--dyn-syms', '--sections', '--version-info', '--needed-libs', path]))
        ops.append(run(['llvm-nm', '--format=posix', path]))
    else:
        ops.append(run(['llvm-readobj', '--coff-imports', '--coff-exports', path]))
    merged = {'defined': [], 'undefined': [], 'weak_defined': [], 'weak_undefined': []}
    version_records = []
    for r in ops:
        if operation_ok(r) and r.get('out'):
            parser = (classify_coff if kind == 'pe' else classify_readobj) if 'llvm-readobj' in r.get('cmd', '') else classify_nm
            try:
                c = parser(r['out'])
                if kind == 'elf' and parser is classify_readobj:
                    version_records = classify_elf_versions(r['out'])
            except ValueError as exc:
                r['parse_error'] = str(exc)
                continue
            for k in merged:
                merged[k].extend(c[k])
    complete = bool(ops) and all(operation_ok(r) for r in ops)
    full_symbols = any(re.search(r'(?m)^Symbols \[\s*\n\s*Symbol \{', r.get('out') or '')
                       for r in ops if r.get('rc') == 0)
    identifiers_bounded = any(len(set(names)) > MAX_IDENTIFIERS for names in merged.values()) or len(version_records) > MAX_IDENTIFIERS
    version_assessed = complete and not identifiers_bounded and kind == 'elf' and any(
        all(re.search(r'(?m)^' + section + r' \[', r.get('out') or '') for section in
            ('Sections', 'VersionSymbols', 'VersionDefinitions', 'VersionRequirements')) for r in ops)
    entry = {'target': target, 'kind': kind, 'member': os.path.basename(path),
             'bytes': os.path.getsize(path),
             'operations': ops,
             'operations_complete': complete,
             'full_symbol_table_present': full_symbols,
             'weak_assessed': complete and full_symbols and not identifiers_bounded and kind in ('elf', 'macho'),
             'identifiers_bounded': identifiers_bounded,
             'sqlite_scope': 'imports_and_exports_only' if kind == 'pe' else 'symbols_and_dynamic_symbols' if kind == 'elf' else 'full_symbols',
             'version_assessed': version_assessed,
             'sqlite_version_table_entries': bounded(version_records),
             'sqlite': {k: bounded(sorted(set(v))) for k, v in merged.items()},
             'sqlite_counts': {k: len(set(v)) for k, v in merged.items()},
             'version_info_present': (any(re.search(r'Name:\s+\.gnu\.version(?:_d|_r)?(?:\s|\()',
                                                   r.get('out') or '') for r in ops)
                                      if version_assessed else None),
             'sqlite_versioned_symbols': bounded(sorted(
                 {name for names in merged.values() for name in names if '@' in name}
                 | {record['name'] for record in version_records if record['index'] > 1})),
             'runtime_prim_hits': sorted({p for r in ops for p in RUNTIME_PRIMS
                                          if p in (r.get('out') or '')}),
             }
    return entry


def main():
    global START
    START = time.monotonic()
    os.makedirs(OUT_DIR, exist_ok=True)
    pairs, tools_ok = preflight()
    summary = {'run_id': RUN_ID, 'repo': REPO, 'acceptance_assessed': False,
               'scope': 'authoritative symbol observations for F07',
               'tool_preflight': pairs, 'tools_ok': tools_ok,
               'binaries': [], 'errors': [], 'budget_seconds': TOTAL_BUDGET,
               'inputs': [], 'input_identity_assessed': False,
               'weak_version_assessed': False,
               'a4_partial': True, 'a4_reason': 'literal dataflow to dlsym/GetProcAddress not attempted in the bounded run'}
    if not tools_ok:
        summary['errors'].append('llvm pair missing or version mismatch; fail closed before any payload read')
        write_summary(summary)
        print('FAIL-CLOSED: llvm preflight')
        return 1

    try:
        if REPO != 'NoGod3524/EXReader':
            raise ValueError('repository differs from fixed producer')
        producer = api_json(f'actions/runs/{RUN_ID}/attempts/1')
        if (producer.get('id') != int(RUN_ID) or producer.get('head_sha') != SOURCE_SHA
                or producer.get('run_attempt') != 1
                or (producer.get('repository') or {}).get('id') != REPOSITORY_ID):
            raise ValueError('producer run/source/attempt mismatch')
        summary['producer'] = {k: producer.get(k) for k in ('id', 'head_sha', 'run_attempt')}
    except Exception as exc:
        summary['errors'].append(f'producer identity failed: {exc}')
        write_summary(summary)
        return 1
    for target, aid in ARTIFACTS.items():
        if remaining() < 60:
            summary['errors'].append(f'budget exhausted before {target}')
            continue
        try:
            blob, metadata = download_artifact(aid)
            binaries, program_sha256 = payload_members(target, blob)
            summary['inputs'].append({'target': target, 'artifact': metadata,
                                      'program_sha256': program_sha256})
            with tempfile.TemporaryDirectory(prefix='f07-') as tmp:
                for i, (member, kind, binary) in enumerate(binaries):
                    p = os.path.join(tmp, f'{target}-{i}.bin')
                    with open(p, 'wb') as stream:
                        stream.write(binary)
                    e = analyse_payload(target, kind, p)
                    e.update(member=member, sha256=hashlib.sha256(binary).hexdigest(), artifact_id=aid)
                    summary['binaries'].append(e)
        except Exception as exc:  # noqa: BLE001
            summary['errors'].append(f'{target}: input or analysis failed: {exc}')
            continue

    weak_total = sum(b['sqlite_counts']['weak_defined'] + b['sqlite_counts']['weak_undefined']
                     for b in summary['binaries'])
    for b in summary['binaries']:
        if not b['operations_complete']:
            summary['errors'].append(f"{b['target']}/{b['member']}: tool operation failed or timed out")
    summary['input_identity_assessed'] = set(i['target'] for i in summary['inputs']) == set(ARTIFACTS)
    summary['weak_version_assessed'] = (tools_ok and summary['input_identity_assessed'] and not summary['errors']
        and set(b['target'] for b in summary['binaries']) == set(ARTIFACTS)
        and all(b['weak_assessed'] and b['version_assessed'] for b in summary['binaries']))
    summary['weak_sqlite_identifiers_total'] = weak_total
    summary['elapsed_seconds'] = round(time.monotonic() - START, 2)
    write_summary(summary)
    for b in summary['binaries']:
        print(b['target'], b['member'], b['kind'], b['sqlite_counts'],
              'weak=', len(b['sqlite']['weak_defined']) + len(b['sqlite']['weak_undefined']),
              'prims=', b['runtime_prim_hits'])
    print('weak_version_assessed=', summary['weak_version_assessed'],
          'errors=', summary['errors'], 'elapsed=', summary['elapsed_seconds'])
    return 1 if summary['errors'] else 0


def write_summary(summary):
    with open(os.path.join(OUT_DIR, 'summary.json'), 'w', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=1)


def self_test():
    from unittest.mock import patch
    f07 = sys.modules[__name__]
    blob = b'fixed artifact bytes'
    metadata = {'id': 123, 'expired': False, 'size_in_bytes': len(blob),
        'digest': 'sha256:' + hashlib.sha256(blob).hexdigest(),
        'workflow_run': {'id': int(f07.RUN_ID), 'head_sha': f07.SOURCE_SHA,
            'repository_id': f07.REPOSITORY_ID, 'head_repository_id': f07.REPOSITORY_ID}}
    assert f07.validate_artifact(metadata, 123, blob) == metadata['digest']
    for bad, data in ((dict(metadata, id=124), blob),
                      (dict(metadata, digest=None), blob), (metadata, blob + b'x'),
                      (dict(metadata, workflow_run=dict(metadata['workflow_run'], head_sha='bad')), blob)):
        try:
            f07.validate_artifact(bad, 123, data)
        except ValueError:
            pass
        else:
            raise AssertionError('unbound input accepted')
    c = f07.classify_nm('sqlite3_a T 10 4\n00000020 T _sqlite3_b\n'
                        '         U _sqlite3_c\nsqlite3_d w 0 0\n'
                        'sqlite3_e W 20 4\nsqlite3_f u 30 4\nsqlite3_g C 40 4\n')
    assert c['defined'] == ['sqlite3_a', 'sqlite3_b', 'sqlite3_e', 'sqlite3_f', 'sqlite3_g']
    assert c['undefined'] == ['sqlite3_c', 'sqlite3_d']
    assert c['weak_defined'] == ['sqlite3_e']
    assert c['weak_undefined'] == ['sqlite3_d']
    c = f07.classify_coff('Import {\n Name: sqlite3.dll\n Symbol: sqlite3_open_v2 (1)\n}\n'
                          'Export {\n Ordinal: 1\n Name: sqlite3_close\n}\n')
    assert c['undefined'] == ['sqlite3_open_v2'] and c['defined'] == ['sqlite3_close']
    versions = f07.classify_elf_versions('VersionSymbols [\n Symbol {\n Version: 1\n Name: sqlite3_plain\n }\n'
        ' Symbol {\n Version: 32770\n Name: sqlite3_hidden\n }\n]\n')
    assert versions == [{'name': 'sqlite3_plain', 'index': 1, 'hidden': False},
                        {'name': 'sqlite3_hidden', 'index': 2, 'hidden': True}]
    assert f07.classify_elf_versions('VersionSymbols [\r\n Symbol {\r\n Version: 1\r\n Name: sqlite3_crlf\r\n }\r\n]\r\n')[0]['index'] == 1
    try:
        f07.classify_elf_versions('VersionSymbols [\n Symbol {\n Name: sqlite3_bad\n }\n]\n')
    except ValueError:
        pass
    else:
        raise AssertionError('missing SQLite version index accepted')
    c = f07.classify_readobj('''Symbols [
  Symbol {
    Name: _sqlite3_a (1)
    Section: __text (0x1)
    RefType: UndefinedNonLazy (0x0)
    Flags [
      WeakDef (0x80)
    ]
  }
  Symbol {
    Name: _sqlite3_b (2)
    Section: Undefined (0x0)
    Binding: Weak (0x2)
  }
]
Section {
 Name: sqlite3_not_a_symbol
 Undefined Weak
}
''')
    assert c['defined'] == c['weak_defined'] == ['sqlite3_a']
    assert c['undefined'] == c['weak_undefined'] == ['sqlite3_b']
    c = f07.classify_readobj('Symbols [\n Symbol {\n Name: (0)\n Section: Undefined (0x0)\n }\n]\n'
        'VersionSymbols [\n Symbol {\n Name: sqlite3_only_a_version_row\n }\n]\n')
    assert not any(c.values())
    with tempfile.NamedTemporaryFile() as payload:
        def success(cmd):
            return {'cmd': ' '.join(cmd), 'rc': 0,
                    'out': 'Sections [\n]\nVersionSymbols [\n]\nVersionDefinitions [\n]\nVersionRequirements [\n]', 'stderr': ''}
        with patch.object(f07, 'run', side_effect=success):
            e = f07.analyse_payload('gtk', 'elf', payload.name)
            assert e['operations_complete'] and e['version_assessed']
            assert e['version_info_present'] is False
            e = f07.analyse_payload('macos', 'macho', payload.name)
            assert e['version_info_present'] is None
            assert not any('-m' in op['cmd'].split() for op in e['operations'])
            assert any('--symbols' in op['cmd'] for op in e['operations'])
        def versioned(cmd):
            return {'cmd': ' '.join(cmd), 'rc': 0,
                    'out': success(cmd)['out'] + '\nName: .gnu.version_r (12)\n', 'stderr': ''}
        with patch.object(f07, 'run', side_effect=versioned):
            assert f07.analyse_payload('gtk', 'elf', payload.name)['version_info_present'] is True
        for result in ({'rc': 1, 'out': 'sqlite3_false T 0 0'},
                       {'rc': None, 'timeout': True},
                       {'rc': 0, 'out': 'sqlite3_false T 0 0', 'output_limit_exceeded': True}):
            with patch.object(f07, 'run', return_value=result):
                e = f07.analyse_payload('macos', 'macho', payload.name)
                assert not e['operations_complete'] and not e['weak_assessed']
                assert e['sqlite_counts']['defined'] == 0
        with patch.object(f07, 'run', return_value={'rc': 0, 'out': ''}):
            e = f07.analyse_payload('gtk', 'elf', payload.name)
            assert not e['version_assessed'] and e['version_info_present'] is None
    for text in ('Symbols [\n Symbol {\n Name: sqlite3_bad (0)', 'Symbols [\n Symbol {\n}\n'):
        try:
            f07.classify_readobj(text)
        except ValueError:
            pass
        else:
            raise AssertionError('malformed symbol block accepted')
    with patch.object(f07, 'MAX_OUTPUT_BYTES', 100):
        result = f07.run([sys.executable, '-c', 'print("x" * 200)'])
        assert result['output_limit_exceeded'] and not f07.operation_ok(result)
    with patch.object(f07, 'remaining', return_value=0):
        result = f07.run([sys.executable, '-c', 'raise Exception("must not run")'])
        assert not f07.operation_ok(result) and result['rc'] is None
    def zipped(entries):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, contents in entries:
                archive.writestr(name, contents)
        return stream.getvalue()
    good = zipped([('program.bin', b'\x7fELFdummy')])
    assert f07.payload_members('gtk', good)[0][0][1] == 'elf'
    for target, blob in [('gtk', b'bad zip'), ('gtk', zipped([])),
                         ('gtk', zipped([('program.bin', b'MZwrong format')])),
                         ('android', zipped([('program.bin', zipped([]))]))]:
        try:
            f07.payload_members(target, blob)
        except (ValueError, zipfile.BadZipFile):
            pass
        else:
            raise AssertionError('invalid payload accepted')
    with tempfile.TemporaryDirectory() as outdir, patch.object(f07, 'OUT_DIR', outdir), \
            patch.object(f07, 'preflight', return_value=({}, True)), \
            patch.object(f07, 'api_json', return_value={'id': int(RUN_ID), 'head_sha': SOURCE_SHA,
                'run_attempt': 1, 'repository': {'id': REPOSITORY_ID}}), \
            patch.object(f07, 'ARTIFACTS', {'gtk': 1}), \
            patch.object(f07, 'download_artifact', return_value=(good, {})), \
            patch.object(f07, 'run', return_value={'rc': 1, 'stderr': 'intentional failure'}):
        assert f07.main() == 1
        with open(os.path.join(outdir, 'summary.json')) as stream:
            summary = json.load(stream)
        assert not summary['weak_version_assessed'] and summary['errors']
        assert not summary['acceptance_assessed']
    print('F07 offline regression checks passed')


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        self_test()
    elif sys.argv[1:]:
        raise SystemExit('usage: f07_authoritative_symbols_20261103.py [--self-test]')
    else:
        sys.exit(main())
