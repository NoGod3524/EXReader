"""Actions-only observation around immutable retained GTK tests; not a test replacement."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import select
import runpy
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = ROOT / 'build/f05-gtk/import-dialog-diagnostics.json'
IDENTITY = {k: os.environ.get(e, '') for k, e in
            [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
BLOBS = {'tests/linux_host/check_account_ui.py': '56ae329b91597bd0fd0f51e871f6a5a458ea1f32',
         'tools/check_linux_host.py': 'a71f0761a00e5bbef39b2c2718d809f7fec1a065'}
LIMIT = 2 * 1024 * 1024
STATE_KEYS = ('sequence', 'book', 'error', 'busy', 'visible')
REPORT = dict(IDENTITY, schema=2, complete=False, original_finished=False,
              original_exception=None, original_sources={}, calls=[], errors=[],
              timing_perturbation_possible=True, extra_queries_only_after_failure=False,
              input_targeting='exact_import_window_only',
              report_limit_bytes=LIMIT, call_limit=1024, event_limit_per_call=512,
              failure_query_total_seconds=5, accepted=False)
ACTIVE = None
USED = 0

def targeted_return(window,pid,index,send,probe,record):
    def owner():
        result=probe(['xdotool','getwindowpid',window],capture_output=True,text=True,timeout=5)
        if result.returncode==1:return None
        result.check_returncode()
        if result.stdout.strip()!=str(pid):raise AssertionError('Import window belongs to another process')
        return pid
    def finished(dispatched,closed_during_dispatch=False):
        record('targeted_import_return',window_id=window,host_pid=pid,return_index=index,
               dispatched=dispatched,ignored_after_close=not dispatched,closed_during_dispatch=closed_during_dispatch)
        return ''
    if owner() is None:
        if index>1:return finished(False)
        raise RuntimeError('Import window vanished before its first Return')
    try:
        result=send('xdotool','key','--window',window,'--clearmodifiers','Return')
    except subprocess.CalledProcessError:
        # Accept may destroy the chooser before the matching key-up. The
        # original case's book/error/database assertions still decide success.
        if owner() is None:return finished(True,True)
        raise
    finished(True)
    return result

def issue(label):
    if len(REPORT['errors']) < 32:
        REPORT['errors'].append(label)
    REPORT['complete'] = False

def observe(action):
    try:
        return action()
    except Exception as error:
        issue('observer:' + type(error).__name__)
        return None

def event(kind, **values):
    global USED
    if ACTIVE is None:
        return
    item = {'kind': kind, 'monotonic': time.monotonic(), **values}
    data = json.dumps(item, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
    if len(ACTIVE['events']) >= 512 or USED + len(data) > LIMIT - 131072:
        issue('observation_limit')
        ACTIVE['truncated'] = True
        return
    USED += len(data)
    ACTIVE['events'].append(item)

def state_values(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in STATE_KEYS
            if type(value.get(key)) is int and -(2**63) <= value[key] < 2**63}

def window_id(value):
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,20}', value) and int(value)>0:
        return value
    issue('non_numeric_window_id')
    return None

def fixture_name(value, host):
    if value is None:
        return {'kind': 'cancel'}
    # Do not resolve or inspect arbitrary input files or expose absolute paths.
    path = Path(value)
    root = ROOT / 'build/f05-gtk-retained'
    try:
        relative = path.relative_to(root)
    except ValueError:
        return {'kind': 'outside_fixture'}
    if '..' in relative.parts or len(str(relative)) > 240:
        return {'kind': 'unmapped_fixture'}
    # Original generated corpus paths only; no profile, credential or arbitrary title.
    if any(p in ('profile', 'home', 'run') for p in relative.parts):
        return {'kind': 'excluded_fixture'}
    if not re.fullmatch(r'[A-Za-z0-9_./ -]+', str(relative)):
        return {'kind': 'non_ascii_fixture'}
    return {'kind': 'fixture', 'relative': str(relative)}

def save_report():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT['complete'] = not REPORT['errors'] and all(not c.get('truncated') for c in REPORT['calls'])
    body = json.dumps(REPORT, ensure_ascii=True, allow_nan=False, indent=2).encode()
    if len(body) > LIMIT:
        issue('encoded_report_limit')
        REPORT['calls'] = [{'ordinal': c['ordinal'], 'outcome': c.get('outcome', 'unknown'),
                            'truncated': True} for c in REPORT['calls']]
        body = json.dumps(REPORT, ensure_ascii=True, allow_nan=False, indent=2).encode()
    if len(body) > LIMIT:
        raise RuntimeError('diagnostic output limit')
    OUTPUT.write_bytes(body)
    print('F05 retained diagnostic: ' + json.dumps(
        {'complete': REPORT['complete'], 'calls': len(REPORT['calls']),
         'original_finished': REPORT['original_finished'],
         'original_exception': REPORT['original_exception'], 'errors': REPORT['errors']},
        allow_nan=False), flush=True)
    failed = next((c for c in reversed(REPORT['calls']) if c.get('outcome') == 'raised'), None)
    if failed:
        events = failed.get('events', [])
        states = [e for e in events if e.get('kind') == 'original_state_read']
        searches = [e for e in events if e.get('kind') == 'original_visible_search_return']
        detail = {k: failed.get(k) for k in ('ordinal','fixture','host_pid','host_window','selected_window','exception_type','truncated')}
        detail['first_original_state'] = states[0] if states else None
        detail['last_original_state'] = states[-1] if states else None
        detail['search_returncodes'] = {str(rc): sum(e['returncode'] == rc for e in searches) for rc in sorted({e['returncode'] for e in searches})}
        detail['post_failure'] = [e for e in events if e.get('kind', '').startswith('post_failure')][-12:]
        text = json.dumps(detail, ensure_ascii=True, allow_nan=False)
        print('F05 original dialog failure evidence: ' + text[:10000], flush=True)

def main():
    global ACTIVE
    if os.environ.get('GITHUB_ACTIONS') != 'true' or IDENTITY['attempt'] != '1':
        raise RuntimeError('Actions attempt 1 only')
    if OUTPUT.exists():
        raise RuntimeError('diagnostic output already exists')
    for relative, expected in BLOBS.items():
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeError('immutable original source absent')
        actual = subprocess.check_output(['git', 'hash-object', str(path)], text=True).strip()
        if actual != expected:
            raise RuntimeError('immutable original source changed')
        REPORT['original_sources'][relative] = {'blob': actual, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    old_path = list(sys.path)
    old_argv = list(sys.argv)
    sys.path.insert(0, str(ROOT / 'tools'))
    sys.path.insert(0, str(ROOT / 'tests/linux_host'))
    host_module = importlib.import_module('check_linux_host')
    if Path(host_module.__file__).resolve() != ROOT / 'tools/check_linux_host.py':
        raise RuntimeError('wrong original Session module')
    old_dialog, old_read = host_module.Session.dialog, host_module.Session.read
    old_command, old_subprocess = host_module.command, host_module.subprocess

    def observed_read(host):
        result = old_read(host)
        observe(lambda: event('original_state_read', state=state_values(result)))
        return result

    def observed_command(*args, **kwargs):
        if ACTIVE is not None and tuple(map(str,args))==('xdotool','key','--clearmodifiers','Return'):
            ACTIVE['return_count']=ACTIVE.get('return_count',0)+1
            return targeted_return(ACTIVE['selected_window'],ACTIVE['host_pid'],ACTIVE['return_count'],
                old_command,old_subprocess.run,event)
        result = old_command(*args, **kwargs)
        if ACTIVE is not None and tuple(map(str, args)) == (
                'xdotool', 'search', '--sync', '--onlyvisible', '--name', '^Import book$'):
            def record():
                ids = result.splitlines()
                if len(ids) > 64 or any(not re.fullmatch(r'[0-9]{1,20}', x) or int(x)<=0 for x in ids):
                    issue('unexpected_original_window_ids')
                    return
                ACTIVE['selected_window'] = ids[-1] if ids else None
                event('original_sync_search_return', window_ids=ids)
            observe(record)
        return result

    class LocalProcessProxy:
        def __getattr__(self, name):
            return getattr(old_subprocess, name)
        def run(self, *args, **kwargs):
            result = old_subprocess.run(*args, **kwargs)
            if ACTIVE is not None and args and list(args[0]) == [
                    'xdotool', 'search', '--onlyvisible', '--name', '^Import book$']:
                observe(lambda: event('original_visible_search_return', returncode=result.returncode,
                                      stdout_discarded=True, stderr_discarded=True))
            return result

    def failure_queries(host):
        deadline = time.monotonic() + 5
        original_states = [e for e in ACTIVE['events'] if e.get('kind') == 'original_state_read']
        event('post_failure_begin', last_original_observation=original_states[-1] if original_states else None,
              state_is_new_sample=False,
              process_returncode=host.process.poll() if host.process is not None else None)
        def query(label, argv):
            remaining = deadline - time.monotonic()
            if remaining <= .1:
                issue('post_failure_deadline')
                return []
            process = None
            data = bytearray()
            try:
                process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                           start_new_session=True)
                local_deadline = min(deadline - .05, time.monotonic() + .8)
                eof = False
                while time.monotonic() < local_deadline:
                    ready, _, _ = select.select([process.stdout], [], [], max(0, local_deadline-time.monotonic()))
                    if not ready:
                        break
                    block = os.read(process.stdout.fileno(), min(1024, 4097-len(data)))
                    if not block:
                        eof = True
                        break
                    data.extend(block)
                    if len(data)>4096:
                        issue('post_failure_output_limit')
                        return []
                if not eof:
                    issue('post_failure_query_timeout')
                    event('post_failure_query_error', label=label, error_type='Timeout')
                    return []
                remaining = deadline-time.monotonic()
                if remaining<=0:
                    raise subprocess.TimeoutExpired(argv, 5)
                process.wait(timeout=min(.05, remaining))
                values = data.decode('ascii', 'strict').splitlines()
                if len(values)>32 or any(not re.fullmatch(r'[0-9]{1,20}', x) or int(x)<=0 for x in values):
                    values=[]
                    issue('post_failure_non_numeric')
                event('post_failure_query', label=label, returncode=process.returncode, values=values)
                return values
            except Exception as error:
                event('post_failure_query_error', label=label, error_type=type(error).__name__)
                issue('post_failure_query_error')
                return []
            finally:
                if process is not None:
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        try:
                            remaining = deadline-time.monotonic()
                            if remaining>0:
                                process.wait(timeout=remaining)
                            else:
                                process.poll()
                        except subprocess.TimeoutExpired:
                            pass
                        if process.poll() is None:
                            issue('post_failure_query_cleanup_incomplete')
                    if process.stdout is not None:
                        process.stdout.close()
        ids = query('visible_import_windows', ['xdotool', 'search', '--onlyvisible', '--name', '^Import book$'])
        focus = query('focus_window', ['xdotool', 'getwindowfocus'])
        selected = ACTIVE.get('selected_window')
        windows = list(dict.fromkeys(([selected] if selected else []) + ids + focus))
        for window in windows[:4]:
            query('pid_of_window_' + window, ['xdotool', 'getwindowpid', window])
        exhausted=time.monotonic() > deadline
        if exhausted:
            issue('post_failure_deadline')
        event('post_failure_end', deadline_exhausted=exhausted)

    def observed_dialog(host, path=None):
        global ACTIVE
        previous = ACTIVE
        if previous is not None:
            issue('nested_dialog')
            return old_dialog(host, path)
        if len(REPORT['calls']) >= 1024:
            issue('call_limit')
            return old_dialog(host, path)
        item = {'ordinal': len(REPORT['calls']) + 1, 'started_monotonic': time.monotonic(),
                'fixture': observe(lambda: fixture_name(path, host)), 'events': [],
                'host_pid': host.process.pid if host.process is not None else None,
                'host_window': window_id(getattr(host, 'window', None)), 'truncated': False}
        REPORT['calls'].append(item)
        ACTIVE = item
        saved_command, saved_subprocess = host_module.command, host_module.subprocess
        host_module.command = observed_command
        host_module.subprocess = LocalProcessProxy()
        try:
            result = old_dialog(host, path)
            item['outcome'] = 'returned'
            return result
        except BaseException as error:
            item['outcome'] = 'raised'
            item['exception_type'] = type(error).__name__
            # The original failure is authoritative; diagnostics never replace it.
            try:
                failure_queries(host)
            except BaseException as diagnostic_error:
                issue('failure_observer:' + type(diagnostic_error).__name__)
            raise
        finally:
            host_module.command, host_module.subprocess = saved_command, saved_subprocess
            item['finished_monotonic'] = time.monotonic()
            ACTIVE = previous
            try:
                save_report()
            except BaseException as diagnostic_error:
                issue('save_observer:' + type(diagnostic_error).__name__)

    host_module.Session.dialog = observed_dialog
    host_module.Session.read = observed_read
    try:
        sys.argv = [str(ROOT / 'tests/linux_host/check_account_ui.py'), *old_argv[1:]]
        runpy.run_path(str(ROOT / 'tests/linux_host/check_account_ui.py'), run_name='__main__')
        REPORT['original_finished'] = True
    except BaseException as error:
        REPORT['original_exception'] = type(error).__name__
        raise
    finally:
        host_module.Session.dialog, host_module.Session.read = old_dialog, old_read
        host_module.command, host_module.subprocess = old_command, old_subprocess
        sys.path[:] = old_path
        sys.argv = old_argv
        try:
            save_report()
        except BaseException as diagnostic_error:
            issue('final_save:' + type(diagnostic_error).__name__)
    if not REPORT['complete']:
        raise RuntimeError('original checks returned but diagnostic evidence incomplete')

if __name__ == '__main__':
    main()
