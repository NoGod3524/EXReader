"""Current-suite-only passive key/state and asynchronous X11 focus evidence.

No key retry, action wait, changed pacing, observation replacement or assertion.
Focus queries run on a separate observer thread and carry their own timestamps.
"""
import configparser
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import traceback

def install(Session):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    original = Session.key
    events = []
    errors = []
    pending = queue.Queue()
    identity = {k: os.environ[v] for k, v in (('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT'))}

    def snapshot(host):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(host.observe)
        return {name: dict(parser[name]) for name in ('host', 'collections') if parser.has_section(name)}

    def inspect_focus():
        while True:
            event = pending.get()
            try:
                if event is None:
                    return
                event['focus_query_started'] = time.monotonic()
                window = subprocess.check_output(['xdotool', 'getwindowfocus'], text=True, timeout=2).strip()
                title = subprocess.check_output(['xdotool', 'getwindowname', window], text=True, timeout=2).strip()
                event['x11_focus'] = {'window': window, 'title': title, 'observed_at': time.monotonic()}
            except Exception:
                event['observer_error'] = traceback.format_exc()
                errors.append(event['observer_error'])
            finally:
                pending.task_done()

    worker = threading.Thread(target=inspect_focus, daemon=True)
    worker.start()

    def observe(host, key, phase):
        # Evidence collection must not replace an original test failure.
        try:
            current = snapshot(host)
            if current.get('collections', {}).get('visible') != '1':
                return
            event = dict(identity, key=key, phase=phase, observed_at=time.monotonic(), pid=host.process.pid,
                         folder=str(host.folder), state=current)
            events.append(event)
            pending.put(event)
        except Exception:
            errors.append(traceback.format_exc())

    def key(host, *keys):
        for value in keys:
            observe(host, value, 'before')
            try:
                original(host, value)
            finally:
                observe(host, value, 'after')
    Session.key = key

    def finish(out):
        pending.put(None)
        worker.join(timeout=15)
        if worker.is_alive():
            errors.append('Focus evidence thread did not finish within 15 seconds after the suite ended')
        out.mkdir(parents=True, exist_ok=True)
        for folder in sorted({event['folder'] for event in events}):
            rows = [event for event in events if event['folder'] == folder]
            (Path(folder) / 'native-collections-keys.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
            for event in rows:
                print('GTK_COLLECTIONS_KEY ' + json.dumps(event), flush=True)
        record = dict(identity, observer_only=True, current_suite_only=True,
                      module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      original_driver_sha256=hashlib.sha256((Path(__file__).resolve().parents[2] / 'tools/check_linux_host.py').read_bytes()).hexdigest(),
                      event_count=len(events), errors=errors, complete=not errors and not worker.is_alive(),
                      scope='Passive state snapshots and asynchronous X11 window-level focus, not widget-level focus; original keys, sleeps and waits unchanged')
        (out / 'collections-observer-identity.json').write_text(json.dumps(record, indent=2))
        print('GTK_COLLECTIONS_OBSERVER ' + json.dumps(record), flush=True)
    return finish
