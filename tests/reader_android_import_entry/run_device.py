#!/usr/bin/env python3
"""Drives the installed probe importer and the self-built DocumentsProvider app through real intents on an
emulator and judges each named scenario from the importer's own evidence log. Exit status is non-zero if any
check fails; results.json lists every check with the observation it was judged on."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

IMP = 'org.exreader.importprobe'
SRC = 'org.exreader.importprobe.source'
DOC_URI = 'content://' + SRC + '.docs/document/'
PATTERN = b'0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ \n'
checks, observations = [], {}
cursor = 0


def adb(*args, check=True, timeout=120):
    p = subprocess.run(['adb', *map(str, args)], capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise SystemExit('adb failed: %s\n%s' % (args, p.stdout + p.stderr))
    return p.stdout


def run_as(pkg, *cmd):
    return subprocess.run(['adb', 'shell', 'run-as', pkg, *cmd], capture_output=True, text=True, timeout=60).stdout


def events():
    out = run_as(IMP, 'cat', 'files/evidence.jsonl')
    result = []
    for line in out.splitlines():
        try:
            result.append(json.loads(line))
        except ValueError:
            pass
    return result


def mark():
    return len(events())


def wait(pred, since, timeout=60, what=''):
    end = time.time() + timeout
    while time.time() < end:
        for e in events()[since:]:
            if pred(e):
                return e
        time.sleep(0.4)
    raise Failure('timeout waiting for ' + what)


class Failure(Exception):
    pass


def check(name, ok, detail=''):
    checks.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + str(detail) if not ok else ''), flush=True)


def scenario(fn):
    def wrapper(*a):
        try:
            fn(*a)
        except Failure as e:
            check(fn.__name__, False, e)
    wrapper.__name__ = fn.__name__
    return wrapper


def ctl(cmd, **extra):
    args = ['shell', 'am', 'broadcast', '-f', '32', '-n', IMP + '/.CommandReceiver', '--es', 'cmd', cmd]
    for k, v in extra.items():
        args += ['--es', k, str(v)]
    adb(*args)


def src(cmd, **extra):
    args = ['shell', 'am', 'broadcast', '-f', '32', '-n', SRC + '/.ControlReceiver', '--es', 'cmd', cmd]
    for k, v in extra.items():
        args += ['--es', k, str(v)]
    adb(*args)


def send(mode, *docs):
    adb('shell', 'am', 'start', '-n', SRC + '/.SenderActivity', '--es', 'mode', mode, '--es', 'docs', ','.join(docs))


def listing(sub):
    out = run_as(IMP, 'ls', '-l', 'files/exr-import/' + sub)
    files = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[0][0] == '-':
            files.append((parts[-1], int(parts[4])))
    return files


def wait_part(minimum, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        parts = [n for n, s in listing('tmp') if s >= minimum]
        if parts:
            return parts
        time.sleep(0.3)
    raise Failure('no .part reached %d bytes' % minimum)


def text_sha(length):
    data = (PATTERN * (length // 64 + 1))[:length]
    return hashlib.sha256(data).hexdigest()


def settle(since, uri_doc, timeout=60):
    """Wait for ready -> commit -> readback -> released of one document; return the events."""
    uri = DOC_URI + uri_doc
    ready = wait(lambda e: e['ev'] == 'ready' and e.get('uri') == uri, since, timeout, 'ready ' + uri_doc)
    commit = wait(lambda e: e['ev'] == 'commit' and e.get('id') == ready['id'], since, timeout, 'commit ' + uri_doc)
    readback = readback_of(since, ready['id'], timeout) if commit['status'] == 0 else None
    return ready, commit, readback


def readback_of(since, id_, timeout):
    return wait(lambda e: e['ev'] == 'readback' and e.get('id') == id_, since, timeout, 'readback')


def clean_staging(name):
    time.sleep(0.5)
    check(name + ': tmp empty', listing('tmp') == [], listing('tmp'))
    check(name + ': ready empty', [n for n, _ in listing('ready')] == [], listing('ready'))


@scenario
def s_setup(output):
    adb('shell', 'getprop', 'ro.build.version.sdk')
    ctl('status')
    e = wait(lambda e: e['ev'] == 'entry-created', 0, 90, 'entry-created')
    check('setup: native library opened on the sdk-owner thread', e['handle'] is True, e)
    since = mark()
    ctl('wrong-thread')
    w = wait(lambda e: e['ev'] == 'wrong-thread', since, 30, 'wrong-thread')
    check('thread rule: native commit from the main thread is refused (EXR_ARGUMENT)', w['status'] == 1 and w['thread'] == 'main', w)


@scenario
def s_view_epub_and_dedupe(output):
    since = mark()
    send('view', 'epub')
    ready, commit, rb = settle(since, 'epub')
    check('VIEW epub: staged as EPUB by content, title from display name',
          ready['format'] == 'EPUB' and ready['title'] == 'Fixture Book' and not ready['already'], ready)
    check('VIEW epub: ready and commit ran on the sdk-owner thread', ready['thread'] == 'sdk-owner' and commit['thread'] == 'sdk-owner', [ready, commit])
    check('VIEW epub: installed SDK import ok, created, original read back byte-equal',
          commit['status'] == 0 and commit['created'] == 1 and rb['equal'] is True, [commit, rb])
    book = commit['bookId']
    since = mark()
    send('view', 'epub')
    ready2, commit2, rb2 = settle(since, 'epub')
    check('re-delivery: same content id, SDK exact duplicate keeps the book (created=0)',
          ready2['id'] == ready['id'] and commit2['created'] == 0 and commit2['bookId'] == book and rb2['equal'], [ready2, commit2])
    clean_staging('VIEW epub')
    observations['epub'] = {'id': ready['id'], 'bookId': book}


@scenario
def s_send_pdf(output):
    since = mark()
    send('send', 'pdf')
    ready, commit, rb = settle(since, 'pdf')
    check('SEND pdf: staged as PDF, SDK file import ok, read back', ready['format'] == 'PDF' and commit['status'] == 0 and rb['equal'], [ready, commit])


@scenario
def s_multi_short_unknown(output):
    since = mark()
    send('multi', 'txt-short', 'txt-seekable', 'txt-short-b')
    r1, c1, b1 = settle(since, 'txt-short')
    r2, c2, b2 = settle(since, 'txt-seekable')
    r3, c3, b3 = settle(since, 'txt-short-b')
    check('SEND_MULTIPLE: unknown-length pipe with 1..37 byte writes staged with the exact bytes',
          r1['id'] == text_sha(300000) + '.txt' and r1['size'] == 300000, r1)
    check('SEND_MULTIPLE: seekable declared-length document staged with the exact bytes',
          r2['id'] == text_sha(70000) + '.txt' and r2['size'] == 70000, r2)
    check('SEND_MULTIPLE: identical bytes under another provider name share one content id',
          r3['id'] == r1['id'], [r3, c3])
    observations['txt_sdk_duplicate'] = {'first': [c1['bookId'], c1['created']], 'second': [c3['bookId'], c3['created']]}
    check('SEND_MULTIPLE: every book imported and read back', all(c['status'] == 0 for c in (c1, c2, c3)) and b1['equal'] and b2['equal'] and b3['equal'])
    since = mark()
    ctl('status')
    st = wait(lambda e: e['ev'] == 'status', since, 30, 'status')
    check('copy buffer: no provider read request exceeded 64 KiB', 0 < st['maxChunk'] <= 65536, st)
    clean_staging('SEND_MULTIPLE')


@scenario
def s_staged_dedupe(output):
    ctl('hold', arg='on')
    since = mark()
    send('send', 'txt-short')
    r1 = wait(lambda e: e['ev'] == 'ready' and e.get('uri', '').endswith('txt-short'), since, 60, 'first ready')
    send('send', 'txt-short-b')
    r2 = wait(lambda e: e['ev'] == 'ready' and e.get('uri', '').endswith('txt-short-b'), since, 60, 'second ready')
    check('re-post while unreleased: second ticket reports alreadyStaged and the same id', r2['already'] is True and r2['id'] == r1['id'], [r1, r2])
    staged = [n for n, _ in listing('ready') if not n.endswith('.title')]
    check('re-post while unreleased: exactly one staged file', staged == [r1['id']], staged)
    ctl('hold', arg='off')
    ctl('commit-pending')
    wait(lambda e: e['ev'] == 'released' and e.get('id') == r1['id'], since, 60, 'released')
    clean_staging('staged dedupe')


@scenario
def s_picker(output):
    since = mark()
    adb('shell', 'am', 'start', '-n', IMP + '/.ShareActivity', '--ez', 'pick', 'true')
    wait(lambda e: e['ev'] == 'picker-result', since, 30, 'picker-result')
    got = {}
    for d in ('txt-seekable', 'epub', 'pdf'):
        got[d] = settle(since, d)
    check('picker result (ClipData of three grants): all imported and read back',
          all(c['status'] == 0 and b['equal'] for _, c, b in got.values()), got)
    clean_staging('picker')


@scenario
def s_hostile_name(output):
    since = mark()
    send('view', 'evil-name')
    ready, commit, rb = settle(since, 'evil-name')
    names = run_as(IMP, 'find', 'files', '-name', '*evil*')
    check('provider name is only a hint: no separators in title, no file named after it',
          '/' not in ready['title'] and '\\' not in ready['title'] and names.strip() == '', [ready['title'], names])
    check('provider name: staged under its content hash', ready['id'] == text_sha(1000) + '.txt', ready['id'])


@scenario
def s_failures(output):
    cases = [('txt-error', 'IO'), ('txt-truncated', 'IO'), ('txt-overlong', 'IO'), ('txt-33m', 'LIMIT'), ('epub-129m', 'LIMIT'),
             ('epub-declared-big', 'LIMIT'), ('zip-unknown', 'UNSUPPORTED_FORMAT'), ('pdf-lie', 'UNSUPPORTED_FORMAT'),
             ('empty', 'EMPTY')]
    src('reset-log')
    for doc, code in cases:
        since = mark()
        send('send', doc)
        f = wait(lambda e: e['ev'] == 'failed' and e.get('uri', '').endswith('/' + doc), since, 180, 'failed ' + doc)
        check('failure %s -> %s, no file left' % (doc, code), f['code'] == code and f['thread'] == 'sdk-owner', f)
        clean_staging(doc)
    opens = run_as(SRC, 'cat', 'files/opens.log')
    check('declared 128 MiB + 1: refused before the provider stream was opened', 'epub-declared-big' not in opens, opens)
    since = mark()
    send('send', 'txt-32m')
    ready = wait(lambda e: e['ev'] == 'ready' and e.get('uri', '').endswith('txt-32m'), since, 300, 'ready 32m')
    commit = wait(lambda e: e['ev'] == 'commit' and e.get('id') == ready['id'], since, 300, 'commit 32m')
    check('exactly 32 MiB unknown-length text is accepted and staged; the SDK verdict is recorded',
          ready['size'] == 32 * 1024 * 1024 and commit['status'] in (0, 6), [ready, commit])
    observations['txt_32m_sdk_status'] = commit['status']
    ctl('release-pending')
    time.sleep(1)


@scenario
def s_permission(output):
    src('close-gate')
    since = mark()
    send('view', 'txt-gated')
    time.sleep(2.5)
    src('revoke', doc='txt-gated')
    src('open-gate')
    f = wait(lambda e: e['ev'] == 'failed' and e.get('uri', '').endswith('txt-gated'), since, 60, 'failed txt-gated')
    check('grant revoked before the stream opened -> PERMISSION', f['code'] == 'PERMISSION', f)
    since = mark()
    ctl('submit-uri', arg=DOC_URI + 'never-granted')
    f = wait(lambda e: e['ev'] == 'failed' and e.get('uri') == DOC_URI + 'never-granted', since, 60, 'failed ungranted')
    check('URI never granted -> PERMISSION', f['code'] == 'PERMISSION', f)
    since = mark()
    ctl('submit-uri', arg='file:///data/local/tmp/x.epub')
    f = wait(lambda e: e['ev'] == 'failed' and e.get('uri', '').startswith('file:'), since, 30, 'failed file uri')
    check('file:// URI refused as ARGUMENT', f['code'] == 'ARGUMENT', f)
    clean_staging('permission')


@scenario
def s_cancel(output):
    src('close-gate')
    since = mark()
    send('view', 'txt-slow')
    wait_part(1024 * 1024)
    t0 = time.time()
    ctl('cancel-last')
    f = wait(lambda e: e['ev'] == 'failed' and e.get('uri', '').endswith('txt-slow'), since, 30, 'cancel')
    check('ticket.cancel() on a stalled provider -> CANCELLED within 3 s', f['code'] == 'CANCELLED' and time.time() - t0 < 3 + 1.5, [f, time.time() - t0])
    src('open-gate')
    clean_staging('cancel')


@scenario
def s_close_entry(output):
    src('close-gate')
    since = mark()
    send('view', 'txt-slow')
    wait_part(1024 * 1024)
    ctl('cancel-all')
    f = wait(lambda e: e['ev'] == 'failed' and e.get('uri', '').endswith('txt-slow'), since, 30, 'close failure')
    rec = wait(lambda e: e['ev'] == 'entry-recreated', since, 30, 'entry-recreated')
    check('entry.close() mid-copy -> CANCELLED, staging lock released for a new entry', f['code'] == 'CANCELLED', [f, rec])
    src('open-gate')
    clean_staging('close')
    since = mark()
    send('view', 'txt-seekable')
    ready, commit, rb = settle(since, 'txt-seekable')
    check('after close the new entry imports normally', commit['status'] == 0 and rb['equal'])


@scenario
def s_ui_close_keeps_copy(output):
    src('close-gate')
    since = mark()
    send('view', 'txt-slow')
    wait_part(1024 * 1024)
    adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
    d = wait(lambda e: e['ev'] == 'activity-destroy', since, 30, 'activity-destroy')
    src('open-gate')
    ready, commit, rb = settle(since, 'txt-slow', timeout=90)
    check('Activity closed mid-copy: copy completes and is delivered once',
          d['changingConfig'] is False and commit['status'] == 0 and rb['equal'], [d, ready])
    n = len([e for e in events()[since:] if e['ev'] == 'ready' and e.get('uri', '').endswith('txt-slow')])
    check('Activity closed mid-copy: exactly one ready event', n == 1, n)
    clean_staging('ui close')


@scenario
def s_rotation(output):
    adb('shell', 'settings', 'put', 'system', 'accelerometer_rotation', '0')
    adb('shell', 'settings', 'put', 'system', 'user_rotation', '0')
    src('close-gate')
    since = mark()
    send('view', 'txt-slow')
    wait_part(1024 * 1024)
    adb('shell', 'settings', 'put', 'system', 'user_rotation', '1')
    try:
        c = wait(lambda e: e['ev'] == 'activity-create' and e['restored'] is True, since, 30, 'recreated activity')
    finally:
        pass
    src('open-gate')
    ready, commit, rb = settle(since, 'txt-slow', timeout=90)
    n = len([e for e in events()[since:] if e['ev'] == 'ready' and e.get('uri', '').endswith('txt-slow')])
    check('rotation mid-copy: Activity recreated from saved state, copy delivered exactly once',
          c['orientation'] == 2 and n == 1 and commit['status'] == 0 and rb['equal'], [c, n])
    adb('shell', 'settings', 'put', 'system', 'user_rotation', '0')
    clean_staging('rotation')


@scenario
def s_kill_during_copy(output):
    src('close-gate')
    since = mark()
    send('view', 'txt-slow')
    parts = wait_part(1024 * 1024)
    adb('shell', 'am', 'force-stop', IMP)
    left = listing('tmp')
    check('force-stop mid-copy leaves the partial temporary on disk', len(left) >= 1, left)
    since = mark()
    ctl('status')
    e = wait(lambda e: e['ev'] == 'entry-created', since, 60, 'entry-created after kill')
    check('restart removes the orphaned temporary and finds nothing ready', listing('tmp') == [] and e['pending'] == '', [e, listing('tmp')])
    src('open-gate')
    time.sleep(1)
    clean_staging('kill during copy')


@scenario
def s_kill_after_publish(output):
    ctl('hold', arg='on')
    since = mark()
    send('view', 'txt-short')
    ready = wait(lambda e: e['ev'] == 'ready' and e.get('uri', '').endswith('txt-short'), since, 60, 'ready')
    adb('shell', 'am', 'force-stop', IMP)
    check('force-stop after publish keeps the staged file', ready['id'] in [n for n, _ in listing('ready')], listing('ready'))
    since = mark()
    ctl('status')
    e = wait(lambda e: e['ev'] == 'entry-created', since, 60, 'entry-created')
    commit = wait(lambda e: e['ev'] == 'commit' and e.get('id') == ready['id'], since, 60, 'recovered commit')
    rb = readback_of(since, ready['id'], 60)
    check('restart lists the published file and the host imports it (SDK dedupe keeps the earlier book)',
          ready['id'] in e['pending'] and commit['status'] == 0 and rb['equal'], [e, commit])
    clean_staging('kill after publish')


@scenario
def s_review_ticket_races(output):
    since = mark(); ctl('review-ticket-races')
    event = wait(lambda e: e['ev'] == 'review-ticket-races', since, 120, 'actual ticket races')
    result = event.get('result', {})
    check('review: 20000 concurrent cancel/commit calls have exactly one winner and no accepted cancel publishes',
          result.get('ok') is True and result.get('iterations') == 20000 and result.get('cancel_wins', 0) + result.get('commit_wins', 0) == 20000, event)


@scenario
def s_review_ready_leases(output):
    ctl('hold', arg='on'); since = mark()
    send('send', 'txt-short')
    wait(lambda e: e['ev'] == 'ready' and e.get('uri', '').endswith('txt-short'), since, 60, 'lease first ready')
    send('send', 'txt-short-b')
    wait(lambda e: e['ev'] == 'ready' and e.get('uri', '').endswith('txt-short-b'), since, 60, 'lease duplicate ready')
    since = mark(); ctl('review-release-first')
    event = wait(lambda e: e['ev'] == 'review-release-first', since, 30, 'first lease release')
    check('review: releasing first duplicate lease preserves the second queued ready file', event.get('ok') is True, event)
    since = mark(); ctl('review-release-last')
    event = wait(lambda e: e['ev'] == 'review-release-last', since, 60, 'last lease import/release')
    readback = wait(lambda e: e['ev'] == 'readback', since, 30, 'last lease SDK readback')
    check('review: last duplicate lease imports through SDK with exact original readback then deletes once', event.get('ok') is True and readback['equal'] is True, [event, readback])
    since = mark(); send('send', 'txt-short')
    wait(lambda e: e['ev'] == 'ready' and e.get('uri', '').endswith('txt-short'), since, 60, 'new lease generation')
    since = mark(); ctl('review-stale-release')
    event = wait(lambda e: e['ev'] == 'review-stale-release', since, 30, 'stale release')
    check('review: stale repeated release cannot delete a restaged same-content file', event.get('ok') is True, event)
    since = mark(); ctl('review-foreign-release')
    event = wait(lambda e: e['ev'] == 'review-foreign-release', since, 60, 'cross-entry foreign release')
    check('review: foreign entry leases cannot remove either entry original', event.get('ok') is True, event)
    since = mark(); ctl('review-close-generation')
    event = wait(lambda e: e['ev'] == 'review-close-generation', since, 60, 'closed entry lease recovery')
    readback = wait(lambda e: e['ev'] == 'readback', since, 30, 'recovered lease SDK readback')
    check('review: closed-entry stale lease cannot delete recovered file and new owner imports exact bytes', event.get('ok') is True and readback['equal'] is True, [event, readback])
    ctl('hold', arg='off'); clean_staging('review ready leases')


@scenario
def s_review_reliable_pipe_fds(output):
    # Obtain the real grant and finish one error before measuring; launching 32
    # Activities would mix window/Intent descriptor lifetimes into the pipe test.
    since = mark(); send('send', 'txt-error')
    warmup = wait(lambda e: e['ev'] == 'failed' and e.get('uri', '').endswith('txt-error'), since, 60, 'reliable pipe warmup')
    check('review: real share grants the pipe URI and warmup reports IO', warmup['code'] == 'IO', warmup)
    time.sleep(0.5)
    since = mark(); ctl('review-fd-count')
    before = wait(lambda e: e['ev'] == 'review-fd-count', since, 30, 'initial fd count')
    failures = []
    for iteration in range(32):
        since = mark(); ctl('submit-uri', arg=DOC_URI + 'txt-error')
        failures.append(wait(lambda e: e['ev'] == 'failed' and e.get('uri', '').endswith('txt-error'), since, 60, 'reliable pipe error'))
    since = mark(); ctl('review-fd-count')
    after = wait(lambda e: e['ev'] == 'review-fd-count', since, 30, 'final fd count')
    check('review: 32 real reliable-pipe provider errors remain IO with no committed request', len(failures) == 32 and all(e['code'] == 'IO' and e['state'] == 'FAILED' for e in failures), failures)
    check('review: repeated reliable-pipe failure descriptors close within baseline plus four framework FDs', before['count'] > 0 and after['count'] <= before['count'] + 4, {'before': before, 'after': after, 'repetitions': 32})
    clean_staging('review reliable pipe errors')


def main():
    global cursor
    parser = argparse.ArgumentParser()
    parser.add_argument('--importer', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    api = adb('shell', 'getprop', 'ro.build.version.sdk').strip()
    abi = adb('shell', 'getprop', 'ro.product.cpu.abi').strip()
    for apk in (args.importer, args.source):
        adb('install', '-r', '-t', apk)
    run_as(IMP, 'rm', '-rf', 'files')
    adb('shell', 'pm', 'grant', IMP, 'android.permission.POST_NOTIFICATIONS', check=False)
    for fn in (s_setup, s_view_epub_and_dedupe, s_send_pdf, s_multi_short_unknown, s_staged_dedupe, s_picker,
               s_hostile_name, s_failures, s_permission, s_cancel, s_close_entry, s_ui_close_keeps_copy,
               s_rotation, s_kill_during_copy, s_kill_after_publish,
               s_review_ticket_races, s_review_ready_leases, s_review_reliable_pipe_fds):
        fn(args.output)
    (args.output / 'evidence.jsonl').write_text('\n'.join(json.dumps(e) for e in events()))
    (args.output / 'revoke.log').write_text(run_as(SRC, 'cat', 'files/revoke.log'))
    (args.output / 'opens.log').write_text(run_as(SRC, 'cat', 'files/opens.log'))
    (args.output / 'logcat.txt').write_text(adb('logcat', '-d', '-v', 'threadtime', check=False))
    result = {**{key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]},
              'device_api': api, 'device_abi': abi, 'checks': checks, 'observations': observations,
              'passed': sum(c['ok'] for c in checks), 'failed': sum(not c['ok'] for c in checks)}
    (args.output / 'results.json').write_text(json.dumps(result, indent=2))
    print('%d passed, %d failed' % (result['passed'], result['failed']))
    sys.exit(1 if result['failed'] or not checks else 0)


if __name__ == '__main__':
    main()
