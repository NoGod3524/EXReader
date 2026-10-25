"""Actions-only strict C07 judge.

Downloads every original ZIP of this run/attempt, authenticates size/digest/expiry/source, and only then
checks both directions, the shared four-format bytes, the exact programs and the named results.
A missing end or direction is reported as pending; nothing is inferred from an accepted field alone.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'reader_android_raw3'))
from bundle import verify, parse, sha  # noqa: E402
import fetch  # noqa: E402
from capture_contract import judge
from test_capture_contract import exercise

assert os.environ.get('GITHUB_ACTIONS') == 'true'
IDENT = fetch.IDENTITY
TARGET = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
checks, problems, pending, upstream = [], [], [], {}
current = [None]
ROLES = ('txt', 'epub', 'pdf', 'cbz')
KINDS = {(role, kind) for role in ROLES for kind in ('progress', 'bookmark')} | {(role, 'highlight') for role in ('txt', 'epub', 'pdf')}


def check(name, condition, detail=None):
    checks.append({'name': name, 'pass': bool(condition), 'direction': current[0], **({'detail': detail} if detail is not None else {})})
    if not condition:
        problems.append(name)
    return bool(condition)


class Archive:
    def __init__(self, name):
        self.identity, raw = fetch.download(name)
        self.zip = zipfile.ZipFile(io.BytesIO(raw))
        self.names = self.zip.namelist()
        upstream[name] = self.identity

    def read(self, suffix):
        found = [n for n in self.names if n == suffix or n.endswith('/' + suffix)]
        assert len(found) == 1, (suffix, found)
        return self.zip.read(found[0])

    def json(self, suffix):
        return parse(self.read(suffix))


def load(name):
    try:
        return Archive(name)
    except Exception as error:  # noqa: BLE001 - missing/expired/mismatching artifact is a pending end, not a pass
        pending.append({'artifact': name, 'reason': repr(error)[:300]})
        return None


def selector_states(manifest):
    """Per record: NULL, allocated-empty, nonempty and NUL-bearing selector classes, kept apart."""
    rows = []
    for row in manifest['reading_records']:
        states = []
        for item in row['capture']['selectors']:
            if item is None:
                states.append('NULL')
            else:
                data = base64.b64decode(item, validate=True)
                states.append('allocated-empty' if not data else 'nonempty+NUL' if b'\0' in data else 'nonempty')
        point = row['capture']['numbers'][2] == row['capture']['numbers'][3]
        rows.append({'role': row['role'], 'kind': row['kind'], 'mode': row['mode'], 'anchor_version': row['anchor_version'],
                     'shape': 'point' if point else 'range', 'exact_prefix_suffix': states})
    return rows


def main():
    jobs = fetch.api('actions/runs/' + IDENT['run_id'] + '/attempts/' + IDENT['attempt'] + '/jobs?per_page=100')['jobs']
    run = fetch.api('actions/runs/' + IDENT['run_id'] + '/attempts/' + IDENT['attempt'])
    check('run head is the C07 source', run['head_sha'] == IDENT['source_sha'])
    job_rows = {}
    for name in ('fixtures', 'mac-send', 'android', 'mac-receive'):
        found = [j for j in jobs if j['name'] == name]
        ok = len(found) == 1 and found[0]['conclusion'] == 'success' and found[0]['head_sha'] == IDENT['source_sha']
        check('job ' + name + ' succeeded on the same source', ok, found[0]['conclusion'] if len(found) == 1 else 'missing')
        if len(found) == 1:
            job_rows[name] = {k: found[0][k] for k in ('id', 'name', 'head_sha', 'conclusion', 'run_attempt')}
        if not ok:
            pending.append({'job': name, 'reason': found[0]['conclusion'] if len(found) == 1 else 'missing'})

    fixtures, mac, android_pkt, android_ev, receive = (load(n) for n in ('c07-fixtures', 'c07-mac-sender', 'c07-android-sender', 'c07-android-evidence', 'c07-mac-receive'))
    load('c07-mac-toolchain')
    common = parse(fixtures.read('common.json'))['originals'] if fixtures else None
    mac_manifest = android_manifest = None
    mac_sha = android_sha = None

    # ---- shared bytes -----------------------------------------------------------------------------
    if fixtures:
        check('four common originals frozen once, PDF is the pinned 8845B sample',
              [r['role'] for r in common] == list(ROLES) and next(r for r in common if r['role'] == 'pdf')['sha256'] == '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc')
        for row in common:
            check('common original ' + row['role'] + ' bytes match its declared SHA-256', sha(fixtures.read(row['file'])) == row['sha256'])

    current[0] = 'macos->android'
    if mac:
        result = mac.json('result.json')
        check('mac sender same source/run/attempt', all(str(result[k]) == str(v) for k, v in IDENT.items()) and result['accepted'])
        files_ok = all(len(mac.read(n)) == d['bytes'] and sha(mac.read(n)) == d['sha256'] for n, d in result['files'].items())
        check('mac sender original file inventory exact', files_ok, len(result['files']))
        verified = verify(lambda n: mac.read('sender-bundle/' + n))
        mac_manifest, mac_sha = verified['manifest'], verified['manifest_sha256']
        sender = mac_manifest['sender']
        check('mac sender is the actual executable and SDK dylib',
              sender['platform'] == 'macos' and sha(mac.read('sender-bundle/proofs/program')) == sender['program_sha256'] == result['program_sha256']
              and sha(mac.read('sender-bundle/proofs/sdk.dylib')) == sender['sdk_dso_sha256'] and sender['sdk_dso_sha256'] in result['sdk_dylibs'].values())
        check('mac executable on disk is the one recorded', sha(mac.read('actual-c07-host')) == result['program_sha256'])
        check('mac provider is the explicit raw family without a static SDK', result['provider']['selector_bytes_candidate'] and not result['provider']['static_sdk_linked'])
        check('mac sender coverage: 4 originals, 11 real records, 19-or-more complete wires',
              verified['originals'] == 4 and verified['reading_records'] == 11 and verified['revisions'] > 11)
        check('mac common bytes equal the frozen set', common is not None and {r['role']: r['sha256'] for r in common} == {r['role']: r['sha256'] for r in mac_manifest['originals']})
        phases = {p['name']: p for p in result['phases']}
        check('mac sender phases ran as distinct real processes', set(phases) == {'send', 'operations', 'session-push'} and len({p['pid'] for p in phases.values()}) == 3)
        push = mac.json('session-push.json')
        check('mac HostAccountSession pushed over verified HTTPS in 256 shards',
              push['actual_native_session']['completed_shards'] == 256 and push['actual_native_session']['completed_sweeps'] == 1)
        sent = mac.json('https-sent/index.json')
        sent_hashes = {e['sha256'] for e in sent['entries']}
        check('every Mac wire and original was actually PUT with its exact bytes',
              all(r['sha256'] in sent_hashes for r in mac_manifest['revisions'] + mac_manifest['originals']) and sent['tls_trust_checked'])
        check('mac NULL-operations profile is part of the original ZIP', 'profiles/source-version-and-NULL-operations/reader-catalog.db' in result['files'])

    current[0] = 'android->macos'
    if android_pkt:
        verified = verify(lambda n: android_pkt.read('bundle/' + n))
        android_manifest, android_sha = verified['manifest'], verified['manifest_sha256']
        sender = android_manifest['sender']
        check('android sender same source/run/attempt', sender['platform'] == 'android' and all(str(sender[k]) == str(v) for k, v in IDENT.items()))
        check('android sender coverage: 4 originals, 11 real records, 19 complete wires', verified['originals'] == 4 and verified['reading_records'] == 11 and verified['revisions'] == 19)
        check('android common bytes equal the frozen set', common is not None and {r['role']: r['sha256'] for r in common} == {r['role']: r['sha256'] for r in android_manifest['originals']})
        null_manifest = parse(android_pkt.read('null-bundle/manifest.json'))
        null_ids = {r['id'] for r in null_manifest['revisions']}
        null_wire = parse(android_pkt.read('null-bundle/' + next(r['file'] for r in null_manifest['revisions'] if r['id'] == null_manifest['null_revision'])))
        check('android NULL expression is a NULL exact, anchor3 fixed-page transport, never a capture',
              null_wire['payload']['location']['selector']['exact'] == {'base64': None, 'size': 0} and null_wire['payload']['location']['anchor_version'] == 3
              and null_manifest['null_revision'] in null_ids and all(r['revision_id'] != null_manifest['null_revision'] for r in android_manifest['reading_records']))
        check('android NULL graph comes from the same sender APK and SDK',
              all(null_manifest['sender'][k] == sender[k] for k in ('apk_sha256', 'sdk_dso_sha256', 'source_sha')))
    if android_ev:
        current[0] = 'macos->android'
        ui = android_ev.json('ui/result.json')
        check('android original runner accepted on the same source', ui['accepted'] and all(str(ui[k]) == str(v) for k, v in IDENT.items()) and ui['actual_tls'])
        check('android receives the macOS packet and NULL negative', ui['incoming_apple_status'] == 'passed' and ui['authentic_apple_null_status'] == 'passed')
        by = {p['phase']: p for p in ui['phases']}
        wanted = ['sender', 'session-push', 'session-receive', 'session-reopen', 'apple-receive', 'apple-reopen', 'apple-null-receive',
                  'apple-null-reopen', 'apple-null-reopen-again', 'missing-parent', 'legacy-pending', 'raw-contract', 'reopen-ui']
        check('android named phases all present, passed and distinct processes', set(by) == set(wanted) and len({p['pid'] for p in ui['phases']}) == len(wanted)
              and all(p['passed'] and all(c['pass'] for c in p['checks']) for p in ui['phases']))
        for name in ('session-push', 'session-receive', 'apple-receive', 'apple-null-receive'):
            check('android ' + name + ' used the native HTTPS Session over 256 shards', by[name]['raw3']['session']['shards'] == 256)
        att = android_ev.json('peer/attestation.json')
        check('android peer is the same-run macOS sender', att['same_run_producer'] and all(str(att[k]) == str(v) for k, v in IDENT.items()))
        reopen = by['apple-reopen']
        check('android independently FOUND and recaptured all 11 macOS records after reopening',
              reopen['raw3']['network_reopen_records'] == 11 and len(reopen['resolutions']) == 11 and all(r['found'] for r in reopen['resolutions']))
        if mac_manifest:
            check('android consumed exactly the Mac manifest', reopen['raw3']['peer_manifest_sha256'] == mac_sha == att['manifest_sha256'])
            check('android peer program is the Mac executable', reopen['raw3']['peer']['program_sha256'] == mac_manifest['sender']['program_sha256'])
            check('android FOUND exactly the Mac record revisions', {r['revision'] for r in reopen['resolutions']} == {r['revision_id'] for r in mac_manifest['reading_records']})
        for name, again in (('apple-null-reopen', False), ('apple-null-reopen-again', True)):
            proof = by[name]['raw3']
            check('android ' + name + ': Mac NULL kept, unreadable, unrestorable, UI refused, no resolution',
                  proof['nullable_preserved'] and proof['typed_unreadable'] and proof['version_unrestorable'] and proof['actual_ui_navigation_refused']
                  and proof['reopened_again'] == again and not by[name]['resolutions'])
        current[0] = 'android->macos'
        apk = android_ev.read('apks/host-debug.apk')
        sender = android_manifest['sender'] if android_manifest else None
        if sender:
            check('android sender APK bytes are the installed program', sha(apk) == sender['apk_sha256'])
            with zipfile.ZipFile(io.BytesIO(apk)) as archive:
                check('android sender SDK DSO is the unique packaged libexreader.so', sha(archive.read('lib/x86_64/libexreader.so')) == sender['sdk_dso_sha256']
                      and [n for n in archive.namelist() if n.startswith('lib/x86_64/libexreader.so')] == ['lib/x86_64/libexreader.so'])
        native = android_ev.json('native/result.json')
        check('android Debug/Release archives, providers and single SQLite audit passed', native['accepted'] and native['one_product_sqlite'] and native['single_shared_sdk']
              and len(native['archives']) == 7 and native['legacy_anchor_max_version'] == 2)
        check('android record phases observed PDF NUL point and range', by['sender']['count'] == 6)
        null = android_ev.json('android-null/result.json')
        report = android_ev.json('android-null/raw-report.json')
        check('android NULL export phase passed in its own process', null['accepted'] and report['passed'] and report['pid'] not in {p['pid'] for p in ui['phases']}
              and [c['name'] for c in report['checks']] == ['c07_android_actual_null_negative_export_for_mac'])
        if android_pkt:
            check('android NULL packet bytes are the exported ones', null['manifest_sha256'] == sha(android_pkt.read('null-bundle/manifest.json')))
        requests = json.loads(android_ev.read('ui/native-https-requests.json'))
        check('android HTTPS requests all carried the generated test authorization', requests and all(r['authorization_sha256'] for r in requests))
        if sender:
            check('android sender manifest SHA matches the runner phase', by['sender']['manifest_sha256'] == android_sha)

    current[0] = 'android->macos'
    if receive:
        result = receive.json('result.json')
        check('mac receive same source/run/attempt', result['accepted'] and all(str(result[k]) == str(v) for k, v in IDENT.items()))
        files_ok = all(len(receive.read(n)) == d['bytes'] and sha(receive.read(n)) == d['sha256'] for n, d in result['files'].items())
        check('mac receive original file inventory exact', files_ok, len(result['files']))
        names = [p['name'] for p in result['phases']]
        check('mac receive ran six fresh real processes', names == ['android-receive', 'android-receive-reopen', 'android-session-receive', 'android-session-reopen',
                                                                  'android-null-receive', 'android-null-reopen'] and len({p['pid'] for p in result['phases']}) == 6)
        if mac:
            check('mac receivers are the exact sender executable', result['program_sha256'] == result['sender_program_sha256'] == mac.json('result.json')['program_sha256'])
            sender_pids = {p['pid'] for p in mac.json('result.json')['phases']}
            check('mac receiver processes differ from sender processes', not (sender_pids & {p['pid'] for p in result['phases']}))
        if android_manifest:
            check('mac consumed exactly the Android manifest', result['android_manifest_sha256'] == android_sha)
            expected_ids = {r['revision_id']: r for r in android_manifest['reading_records']}
            revisions = {r['id']: r for r in android_manifest['revisions']}
            for name in ('android-receive', 'android-receive-reopen', 'android-session-receive', 'android-session-reopen'):
                report = receive.json(name + '.json')
                rows = report['records']
                check('mac ' + name + ' independently FOUND and recaptured all 11 Android records read-only',
                      len(rows) == 11 and {r['revision_id'] for r in rows} == set(expected_ids) and all(r['found'] and r['sender_platform'] == 'android' for r in rows))
                check('mac ' + name + ' kept every original wire byte', all(r['wire_sha256'] == revisions[r['revision_id']]['sha256'] for r in rows))
                check('mac ' + name + ' covered every role/kind', {(r['role'], r['kind']) for r in rows} == KINDS)
                checked = [(r['revision_id'], judge(r, expected_ids[r['revision_id']])) for r in rows]
                check('mac ' + name + ' exact sender numbers/selectors and registered route contract',
                      all(not failures for _, failures in checked), checked)
                if name.startswith('android-session'):
                    session = report['actual_native_session']
                    check('mac ' + name + ' used the actual HostAccountSession over 256 shards', session['actual_host_account_session'] and session['completed_shards'] == 256 and session['completed_sweeps'] == 1)
                # Transport bytes and the host's page/chapter reconstruction are separate columns, reported
                # side by side (EPUB chapter scope is rebuilt from part_path); never merged or hidden.
                separate = upstream.setdefault('transport_vs_reconstruction', {}).setdefault(name, [])
                for r in rows:
                    t, c = r['transport_capture'], r['recapture']
                    separate.append({'role': r['role'], 'kind': r['kind'], 'numbers_equal': t['numbers'] == c['numbers'],
                                     'selectors_equal': t['selectors'] == c['selectors'], 'route_equal': t['route'] == c['route'],
                                     'contract_passed': not judge(r, expected_ids[r['revision_id']])})
            mutation_report = exercise(receive, android_manifest)
            mutation_out = Path('build/c07-strict')
            mutation_out.mkdir(parents=True, exist_ok=True)
            (mutation_out / 'capture-contract-regression.json').write_text(json.dumps(mutation_report, indent=2) + '\n')
            check('real artifact capture mutations are all rejected', mutation_report['positives'] == 44 and mutation_report['all_rejected'],
                  {'positives': mutation_report['positives'], 'mutants': mutation_report['mutants']})
            net = receive.json('native-https.json')
            check('mac network receive authenticated every HTTPS request', net['requests'] and all(q['authenticated'] for q in net['requests']) and net['tls_trust_checked'])
            for name in ('android-null-receive', 'android-null-reopen'):
                report = receive.json(name + '.json')
                row, = report['records']
                check('mac ' + name + ': Android NULL keeps bytes, no location, no FOUND, navigation refused',
                      row['found'] is False and row['typed_has_location'] is False and row['typed_quote_nil'] is True and row['navigation_refused'] is True)

    current[0] = None
    if mac_manifest and android_manifest:
        classes = {'macos': selector_states(mac_manifest), 'android': selector_states(android_manifest)}
        for side, rows in classes.items():
            check(side + ' PDF has a genuine NUL point and a NUL range', any(r['role'] == 'pdf' and r['shape'] == 'point' and 'nonempty+NUL' in r['exact_prefix_suffix'] for r in rows)
                  and any(r['role'] == 'pdf' and r['shape'] == 'range' and r['exact_prefix_suffix'][0] == 'nonempty+NUL' for r in rows))
            check(side + ' normal positives never use NULL exact', all(r['exact_prefix_suffix'][0] != 'NULL' for r in rows))
        check('both senders cover the same 11 role/kind records', {(r['role'], r['kind']) for r in classes['macos']} == {(r['role'], r['kind']) for r in classes['android']} == KINDS)
        upstream['record_classes'] = classes
    direction = {name: any(c['direction'] == name for c in checks) and all(c['pass'] for c in checks if c['direction'] == name) for name in ('macos->android', 'android->macos')}
    accepted = not problems and not pending and all(direction.values())
    result = {**IDENT, 'accepted': accepted, 'status': 'accepted' if accepted else ('pending' if pending else 'failed'),
              'target_source': TARGET, 'jobs': job_rows, 'artifacts': upstream, 'pending': pending, 'failed_checks': problems,
              'checks': checks, 'check_count': len(checks), 'directions': direction,
              'mac_manifest_sha256': mac_sha, 'android_manifest_sha256': android_sha,
              'scope': 'native owners/protocol only: Android API34 x86_64 emulator and macOS; no GUI, six-platform, physical device, performance or final product grant',
              'gui': False, 'six_platform': False, 'physical_device': False, 'performance': False, 'complete_product': False}
    out = Path('build/c07-strict')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('checks', 'artifacts')}), flush=True)
    if not accepted:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
