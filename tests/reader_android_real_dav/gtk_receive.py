"""Open actual Android-sent books in the actual GTK host over the live service."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import traceback

assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path.insert(0, 'tools')
from check_linux_host import Session, command

output = Path(os.environ['INTEROP_GTK_OUTPUT']).resolve(); output.mkdir(parents=True)
bundle = Path(os.environ['INTEROP_ANDROID_BUNDLE']).resolve()
manifest = json.loads((bundle / 'manifest.json').read_text())
payload = Path('build/interop-gtk-package/EXReader-Linux').resolve()
binary = payload / 'bin/exreader-linux'
host = Session(binary, payload / 'Reader.otf', output)
result = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
          'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'accepted': False,
          'actual_desktop_sync': False, 'actual_desktop_receive': False,
          'organization_accepted': False, 'bidirectional': False, 'books': []}

def account():
    parser = configparser.ConfigParser(interpolation=None); parser.read(host.observe)
    return dict(parser['account']) if parser.has_section('account') else {}

def ready(predicate, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if host.process.poll() is not None: raise RuntimeError('GTK process exited; see application.log')
        state = account()
        if state and not int(state['owner_busy']) and not int(state['preparing']) and predicate(state): return state
        time.sleep(.1)
    raise TimeoutError('GTK account state: ' + repr(account()))

def sql(query, params=()):
    db = sqlite3.connect('file:' + str(host.folder / 'profile/library.sqlite.product.sqlite') + '?mode=ro', uri=True)
    try: return db.execute(query, params).fetchall()
    finally: db.close()

def open_account():
    command('xdotool', 'windowactivate', '--sync', host.window)
    host.key('F2');host.wait(lambda s: not s.get('shelf_loading') and not s.get('shelf_restoring'), timeout=60)
    host.key('ctrl+shift+a');ready(lambda s: s['visible'] == '1')
    window = command('xdotool', 'search', '--onlyvisible', '--all', '--pid', host.process.pid, '--name', '^Account and Sync$').splitlines()[-1]
    command('xdotool', 'windowactivate', '--sync', window)

def field(key, value):
    host.key('alt+' + key, 'ctrl+a');host.paste(value)

try:
    end = time.monotonic() + 30
    while time.monotonic() < end:
        if 'window id #' in command('xprop', '-root', '_NET_SUPPORTING_WM_CHECK'): break
        time.sleep(.1)
    host.launch()
    running = Path('/proc/%d/exe' % host.process.pid).resolve()
    require_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert running == binary and hashlib.sha256(running.read_bytes()).hexdigest() == require_sha
    result['program_sha256'] = require_sha; result['pid'] = host.process.pid
    open_account()
    field('w', os.environ['INTEROP_ROOT']); field('u', os.environ['INTEROP_USER']);field('p', os.environ['INTEROP_PASSWORD'])
    host.key('alt+h', 'alt+a');ready(lambda s: s['bound'] == '1' and s['has_password'] == '1')
    host.key('alt+s'); synced = ready(lambda s: s['session_state'] in ('4', '5'), 300)
    assert synced['session_state'] == '4' and synced['completed_shards'] == '256', synced
    result['actual_desktop_sync'] = True
    for row in manifest['revisions']:
        got = sql('SELECT CAST(body_json AS BLOB) FROM reader_revisions WHERE revision_id=?', (row['id'],))
        assert len(got) == 1 and bytes(got[0][0]) == (bundle / row['file']).read_bytes(), row['id']
    host.key('alt+r'); projected = ready(lambda s: s['phase'] == '0' and int(s['receive_seen']) >= len(manifest['originals']), 180)
    assert projected['projection_status'] == '0', projected
    host.key('alt+F4'); ready(lambda s: s['visible'] == '0' and s['session_present'] == '0')
    expected = {r['revision_id']: r for r in manifest['reading_records']}
    for original in manifest['originals']:
        role = original['role']
        bookrow = next(row for row in manifest['revisions'] if row['entity_kind'] == 'book' and row['book_key'] == original['book_key'])
        title = json.loads((bundle / bookrow['file']).read_bytes())['payload']['title']
        command('xdotool', 'windowactivate', '--sync', host.window)
        queries = host.read()['shelf_queries'];host.key('ctrl+f', 'ctrl+a');host.paste(title)
        host.wait(lambda s: s['shelf_queries'] > queries and not s['shelf_loading'] and not s['shelf_restoring'] and s['books'] == 1, timeout=90)
        host.key('F2', 'Home', 'Return')
        def mapped():
            rows = sql('SELECT sdk_book_id FROM reader_local_books WHERE book_key=?', (original['book_key'],))
            return rows[0][0] if rows else 0
        opened = ready(lambda s: s['visible'] == '0' and mapped() > 0 and int(s['imported_book']) == mapped(), 180)
        host.wait(lambda s: s['book'] == mapped() and s['reader_visible'] == 1 and not s['saving'], timeout=90)
        found = {}
        for item in opened['resolutions'].split(';'):
            if not item: continue
            rid, status, state, part, page, start, end = item.split('|')
            record = expected[rid]; capture = record['capture']['numbers']
            assert record['role'] == role and int(status) == 0 and int(state) == 1
            assert int(start) == int(capture[2]) and int(end) == int(capture[3])
            if record['mode'] == 2: assert int(part) == int(capture[1])
            if record['mode'] == 3: assert int(page) == int(capture[1])
            found[rid] = {'status': int(status), 'state': int(state), 'start': int(start), 'end': int(end)}
        wanted = {key for key, row in expected.items() if row['role'] == role}
        assert set(found) == wanted and int(opened['reading_rows']) == len(wanted) and opened['reading_more'] == '0', opened
        result['books'].append({'role': role, 'book_key': original['book_key'], 'sdk_book_id': mapped(), 'resolutions': found})
    result['actual_desktop_receive'] = True; result['accepted'] = True
except Exception as error:
    result['failure'] = str(error);result['trace'] = traceback.format_exc()
finally:
    if host.process and host.process.poll() is None:
        host.process.send_signal(signal.SIGTERM);host.process.wait(timeout=20)
    if host.log: host.log.close()
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)
sys.exit(0 if result['accepted'] else 1)
