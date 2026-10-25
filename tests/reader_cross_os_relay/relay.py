# SPDX-License-Identifier: MIT
"""Actions-only cross-OS relay stages: plan, send, receive, confirm. Never run locally.

Each stage runs on its own runner OS. Only the immutable service directory
(original books + revision wires), the transport records and the identity cross
between them; no SDK or product database is ever copied."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relaylib import (DIRECTIONS, HERE, ROLES, Refused, Service, canonical_inventory, clone_tree, current_os, exe, inventory_files, load_expected,
                      make_certificate, native_inventory, need, pinned, read_transport, run_identity, run_probe, same_identity, scan_for_secret,
                      sha256_bytes, sha256_path, temp_dir, tool, verify_originals, verify_tree, write_plan)

sys.path.insert(0, str(HERE.parent / 'reader_reading_state'))


def stage_result(out, stage, direction, checks, extra):
    value = dict(run_identity(), stage=stage, direction=direction, os=current_os(), checks=checks, accepted=all(c['pass'] for c in checks),
                 sdk_changed=False, schema_changed=False, host_ui_accepted=False, real_device_accepted=False, live_six_device_cloud=False,
                 scope='artifact-relayed cross-OS compatibility of native HTTPS service bytes; not a live multi-device user cloud')
    value.update(extra)
    (out / 'result.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(value)[:4000], flush=True)
    return value


class Checks:
    def __init__(self):
        self.items = []

    def run(self, name, function):
        try:
            function()
            self.items.append({'name': name, 'pass': True, 'detail': ''})
        except Exception as error:  # a failed check is retained, later independent checks still run
            self.items.append({'name': name, 'pass': False, 'detail': '%s: %s' % (type(error).__name__, error)})
            print('FAIL', name, error, flush=True)

    def ok(self):
        return all(c['pass'] for c in self.items)


def parse_common(parser):
    parser.add_argument('--direction', required=True, choices=sorted(DIRECTIONS))
    parser.add_argument('--bin', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)


def guard_direction(direction, stage):
    sender, receiver = DIRECTIONS[direction]
    expected_os = receiver if stage == 'receive' else sender
    need(current_os() == expected_os, 'stage %s of %s must run on %s, not %s' % (stage, direction, expected_os, current_os()))


# ---------- plan ----------
def plan(args):
    import make_fixtures
    expected = load_expected()
    out = args.output.resolve()
    out.mkdir(parents=True)
    fixtures = out / 'fixtures'
    make_fixtures.main(fixtures)
    manifest = json.loads((fixtures / 'manifest.json').read_text(encoding='utf-8'))
    table = {}
    for role in ROLES:
        entry = manifest[role]
        data = (fixtures / entry['file']).read_bytes()
        table[role] = {'file': entry['file'], 'bytes': len(data), 'sha256': sha256_bytes(data)}
    problems = []
    for role in ROLES:
        pin = expected['originals'][role]
        if pin['sha256'] != table[role]['sha256'] or pin['bytes'] != table[role]['bytes']:
            problems.append('%s generated %s/%d but expected.json pins %s/%s' % (role, table[role]['sha256'], table[role]['bytes'], pin['sha256'], pin['bytes']))
    value = dict(run_identity(), stage='plan', originals=table, pinned=not problems, problems=problems,
                 expected_sha256=sha256_path(HERE / 'expected.json'), cases=[c['id'] for c in expected['cases']], accepted=not problems)
    (out / 'result.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(value, indent=2))
    raise SystemExit(0 if not problems else 1)


# ---------- shared serving / probe ----------
def serve_and_probe(service_tree, probe_args, work, out, probe, label):
    key, cert = make_certificate(work / 'certs')
    shutil.copy(cert, out / 'server.crt')
    with Service(service_tree, key, cert) as service:
        done = run_probe(probe, probe_args + ['--webdav-root', service.root_url], service.auth, out / (label + '.log'))
        (out / (label + '-requests.json')).write_text(json.dumps(service.requests, indent=2) + '\n', encoding='utf-8')
        need(done.returncode == 0, label + ' probe refused (exit %d)' % done.returncode)
        service.assert_hygiene()
        return service


def check_probe_report(path, expect_cases=18):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    need(report['failures'] == 0 and report['checks'] and all(c['pass'] is True for c in report['checks']), 'probe checks failed')
    return report


def check_cases(report, expected):
    need([c['id'] for c in report['cases']] == [c['id'] for c in expected['cases']], 'receiver case ids/order differ from the pin')
    for c, pin in zip(report['cases'], expected['cases']):
        need(c['state'] == pin['state'], 'case %s state %s' % (c['id'], c['state']))
    need(report['receiver_found'] == 17 and report['receiver_ambiguous'] == 1 and report['receiver_mislocated'] == 0, '17 FOUND / 1 ambiguity / 0 mislocated')


def common_setup(args, stage):
    guard_direction(args.direction, stage)
    expected = load_expected()
    pins = pinned(expected)
    out = args.output.resolve()
    out.mkdir(parents=True)
    work = temp_dir('relay-%s-' % stage)
    plan_path = out / 'plan.tsv'
    write_plan(expected, plan_path, args.font)
    sha_args = []
    for role in ROLES:
        sha_args += ['--sha', '%s=%s' % (role, pins[role])]
    return expected, pins, out, work, plan_path, sha_args


def load_package(path, identity, direction, stage, native_tool, checks):
    path = Path(path)
    ident = json.loads((path / 'identity.json').read_text(encoding='utf-8'))
    need(same_identity(ident, identity) and ident['direction'] == direction and ident['stage'] == stage, 'relay identity differs from this run/direction')
    need(ident['os'] == DIRECTIONS[direction][0 if stage == 'send' else 1], 'relay peer OS differs')
    need(ident['expected_sha256'] == sha256_path(HERE / 'expected.json'), 'relay plan differs from the pin')
    for filename in ('transport.tsv',) + (('return.tsv',) if stage == 'receive' else ()):
        need(sha256_path(path / filename) == ident[filename.replace('.tsv', '_sha256')], 'relay transport bytes differ: ' + filename)
    inv = (path / 'inventory.json').read_bytes()
    need(sha256_bytes(inv) == ident['inventory_sha256'], 'inventory bytes differ from the identity')
    holder = {}

    def verify_native():
        done = tool(native_tool, 'verify', path / 'tree', path / 'inventory.json')
        need(done.returncode == 0, 'native verify refused the relayed tree: ' + done.stderr)
    checks.run('relayed tree matches its native inventory', verify_native)
    checks.run('native verify agrees with the independent Python inventory', lambda: need(canonical_inventory(path / 'tree') == inv, 'independent inventory differs'))

    def tamper():
        copy = temp_dir('relay-tamper-') / 'tree'
        clone_tree(path / 'tree', copy)
        victim = sorted((copy / 'exreader-sync-v1' / 'revisions').rglob('*.json'))[0]
        data = bytearray(victim.read_bytes())
        data[len(data) // 2] ^= 1
        victim.write_bytes(bytes(data))
        done = tool(native_tool, 'verify', copy, path / 'inventory.json')
        need(done.returncode != 0 and 'MISMATCH' in done.stdout, 'a one-bit change in a revision was NOT refused')
        victim.unlink()
        done = tool(native_tool, 'verify', copy, path / 'inventory.json')
        need(done.returncode != 0, 'a missing revision was NOT refused')
    checks.run('negative: altered or missing revision byte is refused before serving', tamper)
    need(checks.ok(), 'refusing to serve an unauthenticated relay tree')
    return ident, inv, holder


def write_identity(out, identity, direction, stage, extra):
    value = dict(identity, direction=direction, stage=stage, os=current_os())
    for filename in ('transport.tsv',) + (('return.tsv',) if stage == 'receive' else ()):
        value[filename.replace('.tsv', '_sha256')] = sha256_path(out / filename)
    value.update(extra)
    (out / 'identity.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


# ---------- send ----------
def send(args):
    expected, pins, out, work, plan_path, sha_args = common_setup(args, 'send')
    identity = run_identity()
    checks = Checks()
    tree = out / 'tree'
    tree.mkdir()
    probe, native_tool = args.bin / exe('relay-probe'), args.bin / exe('relay-tool')
    transport = out / 'transport.tsv'
    state = {}

    def fixtures_pinned():
        verify_manifest = json.loads((args.fixtures / 'manifest.json').read_text(encoding='utf-8'))
        for role in ROLES:
            data = (args.fixtures / verify_manifest[role]['file']).read_bytes()
            need(sha256_bytes(data) == pins[role] and len(data) == expected['originals'][role]['bytes'], 'fixture %s differs from the pin' % role)
    checks.run('downloaded originals equal the digests pinned before any consumer ran', fixtures_pinned)

    def produce():
        command = ['--mode', 'send', '--fixtures', args.fixtures.resolve(), '--font', args.font.resolve(), '--work', work / 'send', '--report', out / 'probe.json',
                   '--plan', plan_path, '--transport', transport] + sha_args
        state['service'] = serve_and_probe(tree, command, work, out, probe, 'send')
    checks.run('sender publishes originals, metadata, organization and 18 captures over native HTTPS', produce)
    report = {}

    def report_ok():
        report.update(check_probe_report(out / 'probe.json'))
        need(report['originals_exported'] == 4 and report['network_pushed'] == 31 and report['cancelled_attempts'] >= 1 and report['reopens'] >= 1, 'sender counters')
    checks.run('sender probe report is clean (retry after cancel, reopen, 31 revisions)', report_ok)
    rows = []

    def tree_ok():
        rows.extend(read_transport(transport))
        verify_tree(tree, expected, rows, False)
    checks.run('independent check of the service tree: SHA, Unicode, 18 captures, conflict, tombstone, pending parent', tree_ok)

    def inventory():
        native = native_inventory(native_tool, tree, out / 'inventory.json')
        state['digest'] = json.loads(native)['digest']
    checks.run('native inventory of the service tree equals the independent inventory', inventory)
    checks.run('no secret in the relay package', lambda: scan_for_secret(out, state['service'].secret, state['service'].auth))
    write_identity(out, identity, args.direction, 'send', {
        'inventory_sha256': sha256_path(out / 'inventory.json') if (out / 'inventory.json').exists() else '', 'inventory_digest': state.get('digest', ''),
        'expected_sha256': sha256_path(HERE / 'expected.json'), 'probe_sha256': sha256_path(probe), 'tool_sha256': sha256_path(native_tool)})
    stage_result(out, 'send', args.direction, checks.items, {'probe_sha256': sha256_path(probe), 'originals': {r: pins[r] for r in ROLES},
                                                           'requests': len(state['service'].requests) if 'service' in state else 0})
    raise SystemExit(0 if checks.ok() else 1)


# ---------- receive ----------
def receive(args):
    expected, pins, out, work, plan_path, sha_args = common_setup(args, 'receive')
    identity = run_identity()
    checks = Checks()
    probe, native_tool = args.bin / exe('relay-probe'), args.bin / exe('relay-tool')
    ident, inv, _ = load_package(args.input, identity, args.direction, 'send', native_tool, checks)
    sender_os = DIRECTIONS[args.direction][0]
    checks.run('package was produced on the other operating system', lambda: need(ident['os'] == sender_os and ident['os'] != current_os(), 'package os %s' % ident['os']))
    checks.run('package plan is the pinned expected.json', lambda: need(ident['expected_sha256'] == sha256_path(HERE / 'expected.json'), 'expected.json differs'))
    checks.run('originals in the relayed tree equal the pins', lambda: verify_originals(args.input / 'tree', expected))
    tree = out / 'tree'
    clone_tree(args.input / 'tree', tree)
    shutil.copy(args.input / 'transport.tsv', out / 'transport.tsv')
    state = {}
    returned = out / 'return.tsv'

    def consume():
        command = ['--mode', 'receive', '--font', args.font.resolve(), '--work', work / 'recv', '--report', out / 'probe.json', '--plan', plan_path,
                   '--transport', out / 'transport.tsv', '--return', returned, '--return-edit', '1'] + sha_args
        state['service'] = serve_and_probe(tree, command, work, out, probe, 'receive')
    checks.run('receiver with an empty store pulls only the relayed bytes over its own native HTTPS service', consume)
    report = {}

    def report_ok():
        report.update(check_probe_report(out / 'probe.json'))
        check_cases(report, expected)
        need(report['network_pulled'] >= 31 and report['metadata_projected'] == 4 and report['cancelled_attempts'] >= 1 and report['reopens'] >= 3, 'receiver counters')
    checks.run('receiver SDK read-back: 17 FOUND, 1 planted ambiguity, 0 mislocated, retry and reopen', report_ok)
    rows = []

    def tree_ok():
        rows.extend(read_transport(out / 'transport.tsv') + read_transport(returned))
        verify_tree(tree, expected, rows, True)
    checks.run('returned tree: merge, edit, tombstone and new capture are present and exact', tree_ok)

    def original_bytes_unchanged():
        old, _ = inventory_files(inv)
        new, _ = inventory_files(native_inventory(native_tool, tree, out / 'inventory.json'))
        for path, value in old.items():
            need(new.get(path) == value, 'relayed immutable file changed: ' + path)
        need(len(new) == len(old) + 4, 'receiver added exactly its four return revisions')
    checks.run('every relayed file is byte-identical after the return leg; only 4 revisions were added', original_bytes_unchanged)

    def db_ok():
        import sqlite3
        with sqlite3.connect('file:%s?mode=ro' % (work / 'recv' / 'B-product.sqlite').as_posix(), uri=True) as db:
            need(db.execute('SELECT count(*) FROM reader_revisions').fetchone() == (35,), 'receiver revision count')
            need(db.execute('SELECT count(*) FROM reader_outbox').fetchone() == (0,), 'receiver outbox not empty')
            rows_ = db.execute('SELECT format,title,author,favorite FROM reader_books ORDER BY format').fetchall()
        s = expected['strings']
        want = sorted([(r, s['title_' + r] if r != 'epub' else s['return_title_epub'], s['author_' + r], 0 if r == 'epub' else 1) for r in ROLES])
        need(rows_ == want, 'received product metadata is not byte exact: %r' % rows_)
        for r in ROLES:
            cached = work / 'recv' / 'B-cache' / ('%s.%s' % (pins[r], r))
            need(cached.is_file() and sha256_path(cached) == pins[r], 'receiver original cache differs from the pin: ' + r)
    checks.run('independent read of the receiver product store and original cache', db_ok)
    checks.run('no secret in the relay package', lambda: scan_for_secret(out, state['service'].secret, state['service'].auth))
    native = (out / 'inventory.json').read_bytes() if (out / 'inventory.json').exists() else b''
    write_identity(out, identity, args.direction, 'receive', {
        'inventory_sha256': sha256_bytes(native), 'inventory_digest': json.loads(native)['digest'] if native else '', 'parent_inventory_digest': ident['inventory_digest'],
        'expected_sha256': sha256_path(HERE / 'expected.json'), 'probe_sha256': sha256_path(probe), 'tool_sha256': sha256_path(native_tool)})
    stage_result(out, 'receive', args.direction, checks.items, {'probe_sha256': sha256_path(probe), 'parent_inventory_digest': ident['inventory_digest'], 'requests': len(state['service'].requests) if 'service' in state else 0,
                                                              'cases': report.get('cases', [])})
    raise SystemExit(0 if checks.ok() else 1)


# ---------- confirm ----------
def confirm(args):
    expected, pins, out, work, plan_path, sha_args = common_setup(args, 'confirm')
    identity = run_identity()
    checks = Checks()
    probe, native_tool = args.bin / exe('relay-probe'), args.bin / exe('relay-tool')
    ident, inv, _ = load_package(args.input, identity, args.direction, 'receive', native_tool, checks)
    checks.run('returned package was produced on the other operating system', lambda: need(ident['os'] == DIRECTIONS[args.direction][1] and ident['os'] != current_os(), 'package os'))
    checks.run('originals in the returned tree equal the pins', lambda: verify_originals(args.input / 'tree', expected))
    tree = temp_dir('relay-confirm-') / 'tree'
    clone_tree(args.input / 'tree', tree)
    shutil.copy(args.input / 'transport.tsv', out / 'transport.tsv')
    shutil.copy(args.input / 'return.tsv', out / 'return.tsv')
    state = {}

    def consume():
        command = ['--mode', 'confirm', '--font', args.font.resolve(), '--work', work / 'confirm', '--report', out / 'probe.json', '--plan', plan_path,
                   '--transport', out / 'transport.tsv', '--return', out / 'return.tsv'] + sha_args
        state['service'] = serve_and_probe(tree, command, work, out, probe, 'confirm')
    checks.run('original sender OS reads the returned tree with a fresh empty store', consume)

    def report_ok():
        report = check_probe_report(out / 'probe.json')
        check_cases(report, expected)
    checks.run('confirmation SDK read-back: 17 FOUND, 1 ambiguity, 0 mislocated, merge, edit, tombstone, returned capture', report_ok)

    def read_only():
        done = tool(native_tool, 'verify', tree, args.input / 'inventory.json')
        need(done.returncode == 0, 'confirmation changed the served tree: ' + done.stdout)
        need(not any(r['method'] in ('PUT', 'MKCOL') and r['status'] in (200, 201) for r in state['service'].requests), 'confirmation wrote to the service')
    checks.run('confirmation is read-only: the tree still matches the returned inventory', read_only)
    checks.run('no secret in the confirmation evidence', lambda: scan_for_secret(out, state['service'].secret, state['service'].auth))
    stage_result(out, 'confirm', args.direction, checks.items, {'probe_sha256': sha256_path(probe), 'parent_inventory_digest': ident['inventory_digest'],
                                                              'requests': len(state['service'].requests) if 'service' in state else 0})
    raise SystemExit(0 if checks.ok() else 1)


def build_report(args):
    """Binds the installed component, its consumers and the relay executables to this source/run/attempt."""
    consumer = json.loads(args.consumer_json.read_text(encoding='utf-8'))
    installed = []
    for path in sorted(p for p in args.prefix.rglob('*') if p.is_file()):
        installed.append({'path': path.relative_to(args.prefix).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha256_path(path)})
    probe, native_tool = args.bin / exe('relay-probe'), args.bin / exe('relay-tool')
    value = dict(run_identity(), stage='build', os=current_os(), c_consumer_exit=args.c_exit, probe_sha256=sha256_path(probe), tool_sha256=sha256_path(native_tool),
                 cpp_consumer_sha256=sha256_path(args.bin / exe('relay-consumer')), c_consumer_sha256=sha256_path(args.bin / exe('relay-c-consumer')),
                 component_failures=consumer['failures'], component_skips=consumer['skips'], component_checks_count=len(consumer['checks']), installed_files=installed,
                 python=platform.python_version(), accepted=consumer['failures'] == 0 and args.c_exit == 0,
                 scope='installed relay component, installed C and C++ consumers and relay executables on this OS only')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'result.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(value)[:3000])
    raise SystemExit(0 if value['accepted'] else 1)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build-report')
    p.add_argument('--bin', type=Path, required=True)
    p.add_argument('--prefix', type=Path, required=True)
    p.add_argument('--consumer-json', type=Path, required=True)
    p.add_argument('--c-exit', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('plan')
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('send')
    parse_common(p)
    p.add_argument('--fixtures', type=Path, required=True)
    for name in ('receive', 'confirm'):
        p = sub.add_parser(name)
        parse_common(p)
        p.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    try:
        {'plan': plan, 'send': send, 'receive': receive, 'confirm': confirm, 'build-report': build_report}[args.command](args)
    except Refused as error:
        print('REFUSED', error, file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
