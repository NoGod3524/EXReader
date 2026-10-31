# SPDX-License-Identifier: MIT
"""H02: real packaged host, real credential worker, no credential-capable logon session.

--probe  : token / spawn feasibility only (no host). Decides whether the full run is meaningful.
full     : drive the real Win32 account dialog of EXReader.exe launched under a NETWORK-logon primary token.
Checks are independent: a failing expectation is recorded as RED evidence and never weakened or skipped.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'tests/reader_windows_account'))
sys.path.insert(0, str(ROOT / 'tests/windows_host'))
sys.path.insert(0, str(ROOT / 'tests/windows_host/worker_review'))
import token_host as T

REAL_1312 = 1312


def run_probe(output):
    notes = {'runner_session': T.current_session()}
    name, password = T.create_user()
    try:
        notes['desktop_acl'] = T.open_desktop_to_everyone()
        token = T.network_primary_token(name, password)
        notes['network_token'] = T._token_info(token)
        work = output / 'probe';work.mkdir(parents=True)
        T.grant(work, name, 'F');T.grant(HERE, name, 'RX')
        python_dir = Path(sys.executable).parent
        T.grant(python_dir, name, 'RX')
        result = work / 'cred.json'
        spawn_notes = {}
        handle, pid = T.spawn([sys.executable, str(HERE / 'probe_cred.py'), str(result), 'p' + name], token, spawn_notes)
        notes['spawn'] = spawn_notes
        proc = T.HostProcess(handle, pid)
        proc.wait(60)
        notes['helper_exit'] = proc.returncode
        notes['helper_result'] = json.loads(result.read_text()) if result.exists() else None
    except Exception as error:
        notes['error'] = repr(error)
    finally:
        T.delete_user(name)
    notes['credential_1312_observed_by_same_token_probe'] = bool(
        notes.get('helper_result') and REAL_1312 in (notes['helper_result'].get('CredWriteW'), notes['helper_result'].get('CredReadW')))
    (output / 'probe.json').write_text(json.dumps(notes, indent=2, default=str), encoding='utf-8')
    print(json.dumps(notes, indent=2, default=str), flush=True)
    return 0 if notes['credential_1312_observed_by_same_token_probe'] else 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    for name in ('candidate', 'package', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=(name == 'output'))
    args = parser.parse_args()
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    output = args.output.resolve();output.mkdir(parents=True, exist_ok=False)
    if args.probe:
        sys.exit(run_probe(output))
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')

    import base64
    import secrets
    import ssl
    import check_worker as W0
    import check_account_ui as X
    from check_worker import U, send, set_text
    from make_fixtures import epub  # noqa: F401

    marker = secrets.token_hex(6)
    user_a, pass_a = 'ua' + marker, 'pa' + secrets.token_hex(16)
    user_b, pass_b = 'ub' + marker, 'pb' + secrets.token_hex(16)
    auth_a = 'Basic ' + base64.b64encode((user_a + ':' + pass_a).encode()).decode()
    needles = [v.encode() for v in (user_a, pass_a, user_b, pass_b, auth_a)] + [
        base64.b64encode((user_a + ':' + pass_a).encode()), base64.b64encode((user_b + ':' + pass_b).encode())]

    certs = output / 'certificates';certs.mkdir()
    key, certificate = certs / 'server.key', certs / 'server.crt'
    openssl = shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe'
    subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key), '-out', str(certificate),
                    '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, capture_output=True)
    subprocess.run(['certutil', '-addstore', '-f', 'Root', str(certificate)], check=True, capture_output=True)
    dav = X.Dav(certificate, key, auth_a)
    root = dav.base + '/dav/'

    source = output / 'sources';source.mkdir()
    (source / 'Refusal Small.txt').write_bytes(('H02 refusal original marker. ' * 300 + '\n').encode())

    name, password = T.create_user()
    report = {'synthetic_user': name, 'checks': [], 'launches': [], 'thread_samples': {}, 'dav_requests': {}}
    checks = report['checks']

    def check(label, ok, **detail):
        checks.append({'check': label, 'pass': bool(ok), **detail})
        print(json.dumps(checks[-1], ensure_ascii=False, default=str), flush=True)

    shim = None
    devices = []
    try:
        report['desktop_acl'] = T.open_desktop_to_everyone()
        token = T.network_primary_token(name, password)
        T.grant(output, name, 'F');T.grant(args.package, name, 'RX');T.grant(args.candidate.parent, name, 'RX')
        report['token_logon'] = T._token_info(token)
        shim = T.SubprocessShim(token, report)
        W0.subprocess = shim  # the retained driver's own launch path, now with the network token

        def device(profile, existing=False):
            d = X.Device(args.candidate.resolve(), (args.package / 'Reader.otf').resolve(), output / profile, existing=existing)
            devices.append(d);return d

        def sql(query, values=()):
            with sqlite3.connect(output / 'dev' / 'library.sqlite.product.sqlite', timeout=10) as db:
                return db.execute(query, values).fetchall()

        def state():
            return {'books': sql('SELECT book_key,title,author,favorite FROM reader_books ORDER BY book_key'),
                    'revisions': sql('SELECT count(*) FROM reader_revisions')[0][0],
                    'outbox': sql('SELECT count(*) FROM reader_outbox')[0][0]}

        def dav_state():
            with dav.lock:
                return [(r['method'], r['authenticated']) for r in dav.requests]

        def revision_rows():
            return sql('SELECT revision_id,entity_kind,entity_key,body_sha256,body_json FROM reader_revisions ORDER BY revision_id')

        def snapshot():
            # Heads are computed independently from the retained wire parents, not from a host summary.
            rows = revision_rows()
            parents = {(kind, key, parent) for _, kind, key, _, body in rows for parent in json.loads(body)['parents']}
            return {'books': state()['books'],
                    'heads': sorted((kind, key, rid) for rid, kind, key, _, _ in rows if (kind, key, rid) not in parents),
                    'revisions': [(rid, kind, key, sha) for rid, kind, key, sha, _ in rows],
                    'outbox': state()['outbox']}

        def attempt(action):
            try:
                return action(), None
            except Exception as error:
                return False, repr(error)

        def interrupt(dialog, mode):
            """Interrupt a real A network session: 'cancel' while a PROPFIND is held open, 'fail' with a server error."""
            detail = {'mode': mode}
            if mode == 'cancel':
                dav.blocked.clear();dav.release.clear();dav.pause = True
                A.press(dialog, X.SYNC)
                detail['network_request_held'] = dav.blocked.wait(180)
                detail['cancel_enabled'], detail['cancel_error'] = attempt(
                    lambda: detail['network_request_held'] and A.wait(lambda: A.enabled(dialog, X.CANCEL), timeout=30))
                if detail['cancel_enabled']:
                    A.press(dialog, X.CANCEL)
                dav.pause = False;dav.release.set()
                expected = '同步已取消'
            else:
                dav.fail = 500
                A.press(dialog, X.SYNC)
                expected = '同步失败'
            _, detail['settle_error'] = attempt(lambda: A.wait(
                lambda: any(n in A.note(dialog) for n in ('同步已取消', '同步失败', '同步完成')), timeout=240))
            dav.fail = 0
            detail['note'] = A.note(dialog);detail['retry_enabled'] = A.enabled(dialog, X.RETRY)
            really = expected in detail['note'] and detail['retry_enabled'] and (
                mode != 'cancel' or (detail['network_request_held'] and detail['cancel_enabled']))
            return bool(really), detail

        def apply_a_session_only(dialog):
            A.wait(lambda: A.enabled(dialog, X.APPLY), timeout=240)
            A.fill(dialog, root, user_a, pass_a, False);A.press(dialog, X.APPLY)
            A.wait(lambda: '仅本次会话' in A.note(dialog), timeout=60)

        def sampled(action, host):
            sampler = T.ThreadSampler(host.process.pid);sampler.start()
            try:
                return action()
            finally:
                report['thread_samples'].setdefault('all', []).extend(sampler.finish())

        A = device('dev')
        report['process_token'] = shim.launches[-1]['process_token']
        # import one original through the retained path control
        sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
        import importlib.util
        spec = importlib.util.spec_from_file_location('compact_picker', ROOT / 'tests/reader_windows_compact/check_ui.py')
        compact_ui = importlib.util.module_from_spec(spec);spec.loader.exec_module(compact_ui)
        compact_ui.picker(A, source / 'Refusal Small.txt')
        A.wait(lambda: '已导入' in A.status() or '去重' in A.status(), timeout=180);A.wait_idle()
        before = state()
        check('host_runs_under_network_logon_primary_token', report['process_token']['logon_type'] == 'Network'
              and report['process_token']['token_type'] == 'primary', token=report['process_token'])

        # S1: no previous secret, remember on -> refusal, zero authenticated or unauthenticated requests
        dialog = A.open_account()
        A.fill(dialog, root, user_a, pass_a, True)
        sampled(lambda: (A.press(dialog, X.APPLY),
                         A.wait(lambda: 'UNAVAILABLE' in A.note(dialog) or '系统安全存储' in A.note(dialog) or '仅本次' in A.note(dialog), timeout=60)), A)
        note = A.note(dialog)
        check('s1_remember_on_without_old_secret_is_refused_as_UNAVAILABLE', 'UNAVAILABLE' in note, note=note)
        check('s1_sync_stays_disabled_and_no_request_reaches_server', not A.enabled(dialog, X.SYNC) and not dav_state(),
              sync_enabled=A.enabled(dialog, X.SYNC), requests=dav_state())
        check('s1_book_revision_outbox_unchanged', state() == before)

        # S2: remember off -> memory only
        A.fill(dialog, root, user_a, pass_a, False)
        sampled(lambda: (A.press(dialog, X.APPLY), A.wait(lambda: '仅本次会话' in A.note(dialog), timeout=60)), A)
        check('s2_remember_off_accepts_session_only_secret', A.enabled(dialog, X.SYNC), note=A.note(dialog))
        sampled(lambda: A.run_sync(dialog), A)
        after_sync = state()
        check('s2_sync_authenticates_with_session_secret', dav_state() and all(a for _, a in dav_state()), requests=len(dav_state()))

        # S3: A is live in memory; saving B (remember on) fails. A must not silently stand in for B.
        count_before_b = len(dav_state())
        A.fill(dialog, root, user_b, pass_b, True)
        sampled(lambda: (A.press(dialog, X.APPLY),
                         A.wait(lambda: 'UNAVAILABLE' in A.note(dialog) or '仅本次会话' in A.note(dialog), timeout=60)), A)
        note_b = A.note(dialog)
        sync_enabled = A.enabled(dialog, X.SYNC)
        check('s3_failed_B_save_is_reported_UNAVAILABLE', 'UNAVAILABLE' in note_b, note=note_b)
        used_a = False
        if sync_enabled:
            A.press(dialog, X.SYNC)
            time.sleep(8)
            used_a = len(dav_state()) > count_before_b
        check('s3_failed_B_save_does_not_let_stale_A_secret_sync_as_B', not sync_enabled or not used_a,
              sync_enabled_after_failed_B=sync_enabled, requests_with_A_after_B_failed=len(dav_state()) - count_before_b)
        check('s3_book_revision_head_unchanged_by_failed_B', state()['books'] == after_sync['books'], before=after_sync['books'], after=state()['books'])

        # S4: a real cancel of A's network session, then Retry, keeps books, revision heads and revision bytes
        try:
            apply_a_session_only(dialog)
            before = snapshot()
            really, detail = interrupt(dialog, 'cancel')
            check('s4_cancel_really_happened_during_network', really, **detail)
            if detail['retry_enabled']:
                A.press(dialog, X.RETRY)
            _, error = attempt(lambda: A.wait_note(dialog, '同步完成', 240))
            after = snapshot()
            check('s4_retry_after_cancel_completes', error is None, note=A.note(dialog), error=error)
            check('s4_cancel_retry_keeps_books', after['books'] == before['books'], before=before['books'], after=after['books'])
            check('s4_cancel_retry_keeps_revision_heads', bool(before['heads']) and after['heads'] == before['heads'], before=before['heads'], after=after['heads'])
            check('s4_cancel_retry_keeps_revision_bytes', after['revisions'] == before['revisions'],
                  before=len(before['revisions']), after=len(after['revisions']))
        except Exception as error:
            check('s4_completed_without_harness_error', False, error=repr(error))

        # S6: A's session is cancelled / failed, saving B fails, then Retry must send nothing at all
        for tag, mode in (('a', 'cancel'), ('b', 'fail')):
            try:
                apply_a_session_only(dialog)
                really, detail = interrupt(dialog, mode)
                check('s6%s_A_session_really_%s' % (tag, 'cancelled' if mode == 'cancel' else 'failed'), really, **detail)
                before, count_before = snapshot(), len(dav_state())
                A.fill(dialog, root, user_b, pass_b, True)
                A.press(dialog, X.APPLY)
                A.wait(lambda: 'UNAVAILABLE' in A.note(dialog) or '仅本次会话' in A.note(dialog), timeout=60)
                check('s6%s_B_save_refused_as_UNAVAILABLE' % tag, 'UNAVAILABLE' in A.note(dialog), note=A.note(dialog))
                retry_enabled = A.enabled(dialog, X.RETRY)
                A.press(dialog, X.RETRY)
                time.sleep(10)
                _, idle_error = attempt(lambda: A.wait(lambda: A.enabled(dialog, X.APPLY), timeout=240))
                new_requests = dav_state()[count_before:]
                check('s6%s_retry_after_failed_B_sends_zero_requests' % tag, not new_requests,
                      retry_enabled_after_failed_B=retry_enabled, new_requests=len(new_requests),
                      methods=sorted({m for m, _ in new_requests}), note=A.note(dialog), idle_error=idle_error)
                after = snapshot()
                check('s6%s_retry_after_failed_B_keeps_books_heads_revisions' % tag, after == before,
                      heads=(before['heads'], after['heads']), revisions=(len(before['revisions']), len(after['revisions'])),
                      outbox=(before['outbox'], after['outbox']))
            except Exception as error:
                check('s6%s_completed_without_harness_error' % tag, False, error=repr(error))
        A.close_account(dialog)
        A.close()

        # S5: restart -> in-memory secret is gone
        count_restart = len(dav_state())
        A2 = device('dev', existing=True)
        dialog = A2.open_account()
        check('s5_restart_has_no_secret_and_sync_disabled', not A2.enabled(dialog, X.SYNC), note=A2.note(dialog))
        check('s5_no_server_request_after_restart', len(dav_state()) == count_restart)
        A2.close_account(dialog);A2.close()

        # leak scan of this package's own files only, synthetic markers only
        leaks = []
        for path in output.rglob('*'):
            try:
                if path.is_file() and path.stat().st_size < 64 * 1024 * 1024 and path.name not in ('report.json',):
                    data = path.read_bytes()
                    if any(n in data for n in needles):
                        leaks.append(str(path.relative_to(output)))
            except PermissionError:
                pass
        check('no_plaintext_marker_in_package_temp_files', not leaks, files=leaks)
        samples = report['thread_samples'].get('all', [])
        check('worker_threads_observed_without_impersonation_token',
              bool(samples) and all(s.get('thread_token') == 'none' and s.get('open_thread_token_error') == 1008 for s in samples), n=len(samples))
    except BaseException as error:
        report['fatal'] = repr(error)
        raise
    finally:
        for d in devices:
            if d.process.poll() is None:
                d.process.kill()
        report['launches'] = shim.launches if shim else []
        report['raw_1312_in_worker'] = 'NOT OBSERVED: host does not expose the credential return code; evidence is UNAVAILABLE UI result + token identity (see doc)'
        T.delete_user(name)
        (output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        try:
            thumb = subprocess.run(['powershell', '-NoProfile', '-Command',
                                    "(New-Object Security.Cryptography.X509Certificates.X509Certificate2('%s')).Thumbprint" % certificate],
                                   capture_output=True, text=True).stdout.strip()
            if thumb:
                subprocess.run(['certutil', '-delstore', 'Root', thumb], capture_output=True)
        except Exception:
            pass
    failed = [c['check'] for c in checks if not c['pass']]
    print(json.dumps({'passed': len(checks) - len(failed), 'failed': failed}), flush=True)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
