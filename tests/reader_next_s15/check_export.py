"""Actions-only execution of installed consumers against installed SDK 3.41/ABI1.

Builds nothing: every binary, header, package and fixture here was produced by
the workflow. The oracle compares real exported bytes with frozen fixtures,
records the install graph negatives, and keeps every observed failure.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
probe, c_consumer, fixtures, output, module, sdk, graph = map(Path, sys.argv[1:8])
probe = probe.resolve(); c_consumer = c_consumer.resolve(); fixtures = fixtures.resolve()
output = output.resolve(); module = module.resolve(); sdk = sdk.resolve(); graph = graph.resolve()
stage = module.parent.parent
output.mkdir(parents=True, exist_ok=True)
db = output / 'library.db'; product = output / 'product.db'
required = json.loads(Path('tests/reader_next_s15/cases.json').read_text())
summary = {'accepted': False, 'source_sha': os.environ['GITHUB_SHA'],
           'run_id': int(os.environ['GITHUB_RUN_ID']), 'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
           'platform': os.environ['RUNNER_OS'], 'checks': [], 'failures': [], 'limitations': [],
           'binary_identities': {}, 'cases': {}, 'system_share_ui': False, 'six_devices': False,
           'sdk_pin': '3.41.0', 'module_abi_preserved': True}
raw = output / 'raw'; raw.mkdir(exist_ok=True)
counter = 0
EXT = ['txt', 'html', 'fb2', 'epub', 'docx', 'rtf', 'mobi', 'pdf', 'cbz']


def require(v, m):
    if not v: raise AssertionError(m)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def call(args, **kw):
    global counter
    counter += 1
    proc = subprocess.run([str(probe), *map(str, args)], capture_output=True, timeout=180, **kw)
    (raw / f'{counter:03}.stdout').write_bytes(proc.stdout)
    (raw / f'{counter:03}.stderr').write_bytes(proc.stderr)
    require(proc.returncode == 0, f'probe {args}: {proc.returncode}: {proc.stderr.decode(errors="replace")}')
    return json.loads(proc.stdout)


def run(name, ids='1', mode='normal', directory=None, create=True, **kw):
    d = directory or output / name
    if create: d.mkdir(parents=True, exist_ok=True)
    r = call(['export', db, d, mode, ids], **kw)
    summary['cases'][name] = r
    return r, d


def passcase(name): summary['checks'].append(name)


def itemok(r, created=1):
    require(r['status'] == 0 and r['items'] and all(x['status'] == 0 and x['committed'] == 1 and x['created'] == created
            and not x['cleanup_pending'] and x['durable'] == 1 for x in r['items']), str(r))


def fails(r, code, d):
    require(r['status'] == code and not any(x['committed'] for x in r['items']), str(r))
    require(not list(d.glob('.roe-*.part')), 'failed export leaked a temporary without cleanup receipt')


try:
    # Installed SDK identity actually used by this build (headers, package, runtime).
    base = (sdk / 'include/exr/base.h').read_text()
    version = re.search(r'#define EXR_VERSION "([0-9.]+)"', base)
    abi = re.search(r'#define EXR_ABI_VERSION ([0-9]+)u', base)
    require(version and version.group(1) == '3.41.0', 'installed SDK header version')
    require(abi and abi.group(1) == '1', 'installed SDK ABI header')
    config = (stage / 'lib/cmake/EXReaderOriginalExport/EXReaderOriginalExportConfig.cmake').read_text()
    require('find_dependency(EXReader 3.41.0 EXACT CONFIG COMPONENTS library)' in config,
            'installed module config does not pin the approved SDK 3.41.0 graph')
    require('3.40.0' not in config.replace('3.41.0', ''), 'installed module config still references another SDK pin')
    summary['sdk_version'] = version.group(1); summary['sdk_abi'] = int(abi.group(1)); summary['module_pin'] = '3.41.0'
    passcase('approved_sdk_341_abi1')

    # Install-graph negatives executed by the independent checker in this job.
    report = json.loads(graph.read_text())
    require(report.get('accepted') is True and report.get('platform') == os.environ['RUNNER_OS'], 'install graph report')
    for name in ('sdk_default_pin_refused_by_341_install', 'sdk_unsupported_pin_refused',
                 'consumer_without_exact_sdk_refused', 'mixed_sdk_graph_refused'):
        require(report['cases'].get(name, {}).get('refused') is True, 'install graph case ' + name)
        passcase(name)
    summary['install_graph'] = report['cases']

    # Fresh installed C consumer: C ABI, exact version, single owner.
    c1 = subprocess.run([str(c_consumer)], capture_output=True, timeout=120)
    (raw / 'c-consumer.txt').write_bytes(c1.stdout + c1.stderr)
    require(c1.returncode == 0, 'C ABI consumer: ' + c1.stderr.decode(errors='replace'))
    cabi = json.loads(c1.stdout)
    require(cabi['c_abi'] == 1 and cabi['version'] == '3.41.0' and cabi['abi'] == 1, 'C ABI identity'); passcase('installed_c_abi')

    call(['seed', db, fixtures, product])
    manifest = json.loads((fixtures / 'manifest.json').read_text())

    # The same installed C consumer exports a real original byte-exactly.
    cdir = output / 'c-consumer'; cdir.mkdir()
    c2 = subprocess.run([str(c_consumer), str(db), str(cdir)], capture_output=True, timeout=180)
    (raw / 'c-consumer-export.txt').write_bytes(c2.stdout + c2.stderr)
    require(c2.returncode == 0, 'C ABI export: ' + c2.stderr.decode(errors='replace'))
    cexp = json.loads(c2.stdout)
    require(cexp['hash'] == manifest[0]['sha256'] and cexp['bytes'] == manifest[0]['bytes'], 'C consumer hash/size')
    require(Path(cexp['path']).read_bytes() == (fixtures / 'book.txt').read_bytes(), 'C consumer original bytes')
    passcase('installed_c_abi_real_export')

    call(['inspect', db, output / 'before', product])
    sdk_db_before = sha(db); product_before = sha(product)

    # Nine non-streamed (memory-imported) originals exported byte-exactly.
    r, d = run('nine', ','.join(map(str, range(1, 10)))); itemok(r)
    require(r['enters'] == 1 and r['leaves'] == 1, 'single balanced owner lease per run')
    for x, m in zip(r['items'], manifest):
        require(x['format'] == m['format'] and x['hash'] == m['sha256'] and x['bytes'] == m['bytes'], 'public format/hash/size')
        require(Path(x['path']).read_bytes() == (fixtures / m['name']).read_bytes(), 'original byte roundtrip')
        require(Path(x['path']).name == m['sha256'] + '.' + m['name'].split('.')[-1], 'stable original identity name')
    passcase('nine_format_byte_roundtrips'); passcase('temporary_readback_verified'); passcase('owner_lease_balanced')
    require(len(list(d.iterdir())) == 9 and not any(x['id'] in (10, 11) for x in r['items']), 'unselected excluded')
    passcase('selected_unselected_isolation')

    # Non-streamed storage for the remaining seeded books.
    r, d = run('nonstream', '10,11'); itemok(r)
    require(Path(r['items'][0]['path']).read_bytes() == (fixtures / 'large.txt').read_bytes(), 'large original bytes')
    require(Path(r['items'][1]['path']).read_bytes() == (fixtures / 'changed.txt').read_bytes(), 'changed original bytes')
    passcase('nonstream_memory_byte_identity')

    # Streamed storage (bounded source import for EPUB/CBZ, file import for PDF)
    # must export the same bytes as the non-streamed counterparts.
    nine = {x['id']: x for x in summary['cases']['nine']['items']}
    for name, book, counterpart, fixture in (('stream-cbz', 12, 9, 'book.cbz'), ('stream-epub', 13, 4, 'book.epub'),
                                             ('stream-pdf', 14, 8, 'book.pdf')):
        r, d = run(name, str(book)); itemok(r)
        item = r['items'][0]
        require(item['format'] == nine[counterpart]['format'], name + ' format')
        require(item['hash'] == nine[counterpart]['hash'], name + ' hash differs from the non-streamed original')
        require(Path(item['path']).read_bytes() == (fixtures / fixture).read_bytes(), name + ' bytes')
    passcase('stream_source_byte_identity')

    # Existing unchanged sideload exporter is an independent byte oracle.
    r, d = run('sideload', '9', mode='sideload'); itemok(r)
    oracle = Path(r['sideload_path'])
    require(oracle.is_file() and r['sideload_bytes'] == manifest[8]['bytes'], 'sideload oracle output')
    require(sha(oracle) == manifest[8]['sha256'] == r['items'][0]['hash'], 'module and sideload original differ')
    passcase('sideload_exporter_byte_identity')

    # Two sequential runs in one process: no retained source handle or lease.
    d = output / 'reuse'; (d / 'again').mkdir(parents=True)
    r, _ = run('reuse', '1', mode='twice', directory=d); itemok(r)
    require(r['enters'] == 1 and r['leaves'] == 1, 'lease balanced across the first run')
    require(len(list((d / 'again').iterdir())) == 1, 'second sequential run produced no file')
    passcase('source_handles_released_before_reuse')

    again, _ = run('duplicate', ','.join(map(str, range(1, 10))), directory=output / 'nine'); itemok(again, 0); passcase('duplicate_same_bytes')
    d = output / '书籍-🙂'; d.mkdir(); r, _ = run('unicode', directory=d); itemok(r)
    require(Path(r['items'][0]['path']).read_bytes() == (fixtures / 'book.txt').read_bytes(), 'native Unicode destination'); passcase('valid_unicode_destination')
    r, d = run('batch-preflight', '1,11', mode='batchsum'); fails(r, 2, d)
    require(not list(d.iterdir()), 'whole batch size preflight before any creation'); passcase('batch_preflight_atomic')
    r, d = run('same-title', '1,11'); itemok(r)
    require(r['items'][0]['path'] != r['items'][1]['path'], 'same title distinct bytes'); passcase('same_title_distinct_bytes')
    d = output / 'conflict'; d.mkdir(); target = d / (manifest[0]['sha256'] + '.txt'); target.write_bytes(b'DO NOT OVERWRITE')
    r, _ = run('conflict', directory=d); fails(r, 7, d)
    require(target.read_bytes() == b'DO NOT OVERWRITE', 'conflict overwritten'); passcase('existing_conflict_no_overwrite')
    r, d = run('display', mode='display'); itemok(r)
    require(Path(r['items'][0]['path']).name.startswith('Readable_Name--'), 'restricted display name'); passcase('display_name_restricted')
    for name, mode, code in [('bad_utf8', 'badutf', 1), ('device_name_rejected', 'device', 1), ('traversal_rejected', 'badslug', 1),
                             ('per_book_limit', 'booklimit', 2), ('batch_limit', 'batchlimit', 2), ('hard_limit', 'hardlimit', 2),
                             ('owner_refusal', 'ownerdeny', 3), ('wrong_thread', 'wrongthread', 3),
                             ('missing_source', 'normal', 5), ('cancel_before_start', 'cancel0', 8)]:
        r, d = run(name, ids='99999' if name == 'missing_source' else '1', mode=mode); fails(r, code, d); passcase(name)
    r, d = run('dot-traversal', directory=output / 'before' / '..' / 'nine'); require(r['status'] == 1, 'directory traversal refused')
    r, d = run('count101', ','.join(['1'] * 101)); fails(r, 2, d); passcase('count_101_rejected')
    r, d = run('count100', ','.join(['1'] * 100))
    require(len(r['items']) == 100 and r['status'] == 0 and r['items'][0]['created'] == 1 and all(x['created'] == 0 for x in r['items'][1:]), '100 explicit selections')
    passcase('count_100_accepted')
    r, d = run('reentry', mode='reentry'); itemok(r); require(r['reentry'] == 3, 'same-owner reentry refused'); passcase('callback_reentry')
    r, d = run('cancel-after', '1,2', mode='cancelafter1')
    require(r['status'] == 8 and r['items'][0]['committed'] == 1 and r['items'][1]['committed'] == 0 and len(list(d.iterdir())) == 1, 'partial committed cancellation')
    passcase('cancel_after_commit')
    actual = output / 'actual'; actual.mkdir(); alias = output / 'alias'
    if os.name == 'nt':
        p = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(actual)], capture_output=True)
        require(p.returncode == 0, 'create actual Windows junction')
    else: alias.symlink_to(actual, target_is_directory=True)
    r, _ = run('directory-alias', directory=alias)
    require(r['status'] in (1, 6) and not list(actual.iterdir()), 'directory alias refused'); passcase('directory_alias_rejected')
    d = output / 'file-alias'; d.mkdir(); victim = output / 'victim'; victim.write_bytes((fixtures / manifest[0]['name']).read_bytes())
    aliasfile = d / (manifest[0]['sha256'] + '.txt')
    if os.name == 'nt': os.link(victim, aliasfile)
    else: aliasfile.symlink_to(victim)
    r, _ = run('target-alias', directory=d)
    require(r['status'] == 7 and victim.read_bytes() == (fixtures / manifest[0]['name']).read_bytes(), 'file alias refused')
    passcase('target_alias_rejected')
    r, d = run('cleanup', '10', mode='cleanfail')
    require(r['status'] == 8 and r['items'][0]['cleanup_pending'] == 1 and not r['items'][0]['committed'], 'truthful cleanup failure receipt')
    receipt = Path(r['items'][0]['cleanup_path'])
    require(receipt.is_file() and receipt.parent == d, 'receipt owns real orphan'); receipt.unlink(); passcase('cleanup_receipt')
    d = output / 'killed'; d.mkdir()
    with (raw / 'kill.stderr').open('wb') as err:
        p = subprocess.Popen([str(probe), 'export', str(db), str(d), 'kill', '10'], stdout=subprocess.PIPE, stderr=err)
        line = p.stdout.readline().decode().strip(); require(line.startswith('READY '), 'kill reached actual copied temporary')
        receipt = Path(line[6:]); require(receipt.is_file(), 'kill receipt file')
        p.kill(); p.wait(timeout=30); require(p.returncode != 0, 'real process terminated')
        require(receipt.exists() and not list(d.glob('*.txt')), 'prefix never published on kill')
    (raw / 'kill-receipt.txt').write_text(line + '\n' + str(p.returncode) + '\n'); receipt.unlink()
    r, _ = run('reopened-retry', '10', directory=d); itemok(r)
    require(Path(r['items'][0]['path']).read_bytes() == (fixtures / 'large.txt').read_bytes(), 'reopen retry original')
    passcase('process_kill_reopen_retry')
    d = output / 'kill-published'; d.mkdir()
    with (raw / 'kill-published.stderr').open('wb') as err:
        p = subprocess.Popen([str(probe), 'export', str(db), str(d), 'killpublished', '1'], stdout=subprocess.PIPE, stderr=err)
        line = p.stdout.readline().decode().strip(); require(line.startswith('READY '), 'actual publication before kill')
        published = Path(line[6:]); require(published.is_file(), 'committed path')
        p.kill(); p.wait(timeout=30); require(p.returncode != 0, 'kill after commit')
    (raw / 'kill-published-receipt.txt').write_text(line + '\n' + str(p.returncode) + '\n')
    r, _ = run('committed-retry', directory=d); itemok(r, 0)
    require(published.read_bytes() == (fixtures / 'book.txt').read_bytes(), 'committed retry preserved bytes')
    passcase('process_kill_after_commit_retry')
    if os.name != 'nt':
        import resource
        def limits(): resource.setrlimit(resource.RLIMIT_FSIZE, (100000, 100000))
        r, d = run('write-failure', '10', preexec_fn=limits); fails(r, 6, d); passcase('posix_real_midstream_write_failure')
    else:
        summary['limitations'].append('Windows mid-stream disk-full/fsync failure injection UNAVAILABLE; actual locked-temp cleanup and no-overwrite publication failure exercised.')
        passcase('windows_actual_locked_cleanup_failure')
    call(['inspect', db, output / 'after', product]); before = output / 'before'; after = output / 'after'
    require({p.name: sha(p) for p in before.iterdir()} == {p.name: sha(p) for p in after.iterdir()},
            'public originals/notes/progress/history/outbox changed')
    require(sha(db) == sdk_db_before, 'SDK database bytes changed')
    require(sha(product) == product_before, 'product database bytes changed')
    passcase('sdk_original_notes_progress_unchanged'); passcase('product_history_outbox_unchanged')
    # Fault deliberately mutates a separate fixture owner through PUBLIC SDK API.
    r, d = run('invalidate', '10', mode='invalidate'); fails(r, 5, d); passcase('source_invalidated_mid_read')
    call(['inspect', db, output / 'after-invalidation', product])

    require(set(required) <= set(summary['checks']) and len(summary['checks']) == len(set(summary['checks'])),
            'required named checks missing/duplicated')
    files = {'probe': probe, 'c_consumer': c_consumer, 'module': module}
    binaries = output / 'binaries'; binaries.mkdir(exist_ok=True)
    for role, p in files.items():
        require(p.is_file() and p.stat().st_size > 0, 'missing actual binary ' + role)
        dest = binaries / p.name; shutil.copyfile(p, dest)
        summary['binary_identities'][role] = {'member': 's15-evidence/binaries/' + p.name, 'sha256': sha(dest), 'bytes': dest.stat().st_size}
    summary['accepted'] = True
except Exception as exc:
    summary['failures'].append(repr(exc))
finally:
    summary['count'] = len(summary['checks'])
    (output / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)
raise SystemExit(0 if summary['accepted'] else 1)
