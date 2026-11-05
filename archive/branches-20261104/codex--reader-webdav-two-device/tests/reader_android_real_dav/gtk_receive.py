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
sys.path.insert(0, 'tests/reader_a11y_gtk')
import atspi_client as bus

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

def records_state():
    parser = configparser.ConfigParser(interpolation=None);parser.read(host.observe)
    return dict(parser['reading_records']) if parser.has_section('reading_records') else {}

def wait_records(predicate):
    end = time.monotonic() + 60
    while time.monotonic() < end:
        state = records_state()
        if state and state['running'] == '0' and predicate(state): return state
        time.sleep(.05)
    raise TimeoutError('GTK record controls: ' + repr(records_state()))

def edit_record(shortcut, body):
    actions = int(records_state()['actions']);host.key(shortcut)
    end = time.monotonic() + 30
    while time.monotonic() < end:
        entry = next((node for node in bus.walk(app) if bus.name(node) == 'Reading record text' and
                      bus.role(node) == 'text' and bus.states(node).get('showing')), None)
        if entry: break
        time.sleep(.05)
    else: raise TimeoutError('GTK record text input missing')
    rect = bus.extents(entry);assert rect and rect['width'] > 4 and rect['height'] > 4
    command('xdotool', 'mousemove', '--sync', rect['x'] + rect['width'] // 2, rect['y'] + rect['height'] // 2)
    command('xdotool', 'click', '1');host.paste(body);host.key('alt+s')
    wait_records(lambda s: int(s['actions']) >= actions + 2)

def create_reverse(original):
    role = original['role']
    before = {r[0] for r in sql('SELECT revision_id FROM reader_revisions')}
    command('xdotool', 'windowactivate', '--sync', host.window)
    if role != 'cbz':
        host.key('F7', 'ctrl+Home', 'ctrl+shift+Right')
        selection = host.wait(lambda s: s['selected'] > 0, timeout=60)
        assert selection['reader_visible'] == 1
    host.key('ctrl+shift+r')
    state = wait_records(lambda s: s['visible'] == '1')
    if role != 'cbz':
        assert state['has_range'] == '1' and int(state['range_end']) > int(state['range_start']), state
    else:
        assert state['has_range'] == '0', state
    window = command('xdotool', 'search', '--onlyvisible', '--name', '^Reading records$').splitlines()[-1]
    command('xdotool', 'windowactivate', '--sync', window)
    actions = int(state['actions']);host.key('alt+s')
    wait_records(lambda s: int(s['actions']) > actions and s['progress_state'] == '4')
    edit_record('alt+a', 'GTK reverse bookmark ' + role)
    if role != 'cbz':
        edit_record('alt+h', 'GTK reverse highlight ' + role)
    rows = sql("SELECT revision_id,CAST(body_json AS BLOB) FROM reader_revisions WHERE entity_kind IN ('progress','annotation')")
    created = [(rid, bytes(wire)) for rid, wire in rows if rid not in before]
    assert len(created) == (2 if role == 'cbz' else 3), (role, len(created))
    records = []
    for rid, wire in created:
        envelope = json.loads(wire); location = envelope['payload']['location']
        assert envelope['payload']['book_key'] == original['book_key']
        assert location['parser_version'] == '3.41.0'
        start, end = location['selector']['start'], location['selector']['end']
        kind = 'progress' if envelope['entity_kind'] == 'progress' else ('highlight' if end > start else 'bookmark')
        if kind != 'progress': assert envelope['payload']['text'] == 'GTK reverse ' + kind + ' ' + role
        if kind == 'highlight': assert end > start
        target = output / (rid + '.json');target.write_bytes(wire)
        records.append({'id': rid, 'file': target.name, 'sha256': hashlib.sha256(wire).hexdigest(),
                        'role': role, 'kind': kind, 'book_key': original['book_key'],
                        'mode': location['mode'], 'part': location.get('part'), 'part_path': location.get('part_path'),
                        'page': location.get('page'), 'page_id': location.get('page_id'),
                        'annotation_id': envelope['payload'].get('annotation_id', ''), 'start': start, 'end': end})
    assert {row['kind'] for row in records} == ({'progress', 'bookmark'} if role == 'cbz' else {'progress', 'bookmark', 'highlight'})
    host.key('alt+F4');wait_records(lambda s: s['visible'] == '0')
    return records

try:
    end = time.monotonic() + 30
    while time.monotonic() < end:
        if 'window id #' in command('xprop', '-root', '_NET_SUPPORTING_WM_CHECK'): break
        time.sleep(.1)
    assert bus.init()[0]
    host.launch()
    app = bus.wait_application('exreader-linux')
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
    reverse = []
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
        reverse.extend(create_reverse(original))
    result['actual_desktop_receive'] = True
    open_account();field('u', os.environ['INTEROP_USER']);field('p', os.environ['INTEROP_PASSWORD'])
    host.key('alt+h', 'alt+a');ready(lambda s: s['bound'] == '1' and s['has_password'] == '1')
    generation = int(account()['session_generation']);host.key('alt+s')
    sent = ready(lambda s: int(s['session_generation']) > generation and s['session_state'] in ('4','5'), 300)
    assert sent['session_state'] == '4' and int(sent['pushed']) >= len(reverse), sent
    result['reverse_records'] = reverse
    result['gtk_reverse_uploaded'] = True
    result['accepted'] = True
except Exception as error:
    result['failure'] = str(error);result['trace'] = traceback.format_exc()
finally:
    if host.process and host.process.poll() is None:
        host.process.send_signal(signal.SIGTERM);host.process.wait(timeout=20)
    if host.log: host.log.close()
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)
sys.exit(0 if result['accepted'] else 1)
