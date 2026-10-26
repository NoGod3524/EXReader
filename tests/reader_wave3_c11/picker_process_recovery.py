"""Actions-only test: kill the host while the real system save picker is open."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
for name in ('fixtures', 'app', 'test-apk', 'output'):
    p.add_argument('--' + name, type=Path, required=True)
a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
package = 'org.exreader.host'
identity = {key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
result = {**identity, 'accepted': False, 'scenario': 'real system picker and explicit background process kill', 'physical_device': False}

def adb(*args, timeout=120):
    return subprocess.check_output(['adb', *map(str, args)], stderr=subprocess.STDOUT, timeout=timeout)

def snapshot():
    adb('shell', 'uiautomator', 'dump', '/sdcard/exr-picker-window.xml', timeout=45)
    raw = adb('exec-out', 'cat', '/sdcard/exr-picker-window.xml')
    (a.output / 'last-window.xml').write_bytes(raw)
    return list(ET.fromstring(raw).iter('node'))

def wait_for(predicate, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        nodes = snapshot()
        item = predicate(nodes)
        if item is not None: return item
        time.sleep(1)
    raise AssertionError('expected system or app UI did not appear; last-window.xml retained')

def text_is(node, value):
    return node.get('text', '').strip().casefold() == value.casefold()

def tap(node):
    match = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
    assert match, node.attrib
    x1, y1, x2, y2 = map(int, match.groups())
    assert x2 > x1 and y2 > y1
    adb('shell', 'input', 'tap', (x1 + x2) // 2, (y1 + y2) // 2)

def long_tap(node):
    match = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
    assert match, node.attrib
    x1, y1, x2, y2 = map(int, match.groups()); assert x2 > x1 and y2 > y1
    x, y = (x1 + x2) // 2, (y1 + y2) // 2
    adb('shell', 'input', 'swipe', x, y, x, y, 900)

def pid():
    value = subprocess.run(['adb', 'shell', 'pidof', package], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20).stdout.strip()
    return value if re.fullmatch(r'\d+', value) else ''

try:
    apk_hash = hashlib.sha256(a.app.read_bytes()).hexdigest()
    installed = adb('shell', 'pm', 'path', package).decode('utf-8').strip()
    assert installed.startswith('package:') and '\n' not in installed
    adb('pull', installed[len('package:'):], a.output / 'installed.apk')
    assert hashlib.sha256((a.output / 'installed.apk').read_bytes()).hexdigest() == apk_hash
    assert adb('shell', 'pm', 'clear', package).strip() == b'Success'
    adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')
    adb('shell', 'am', 'force-stop', package)
    adb('exec-out', 'run-as', package, 'mkdir', '-p', 'files/wave3-fixtures')
    manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
    rows = [row for row in manifest['books'] if row['role'] in ('txt', 'epub')]
    assert [row['role'] for row in rows] == ['txt', 'epub']
    for row in rows:
        assert re.fullmatch(r'[A-Za-z0-9_.-]+', row['file'])
        path = a.fixtures / row['file']; data = path.read_bytes()
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
        temporary = '/data/local/tmp/exr-picker-' + row['file']
        adb('push', path, temporary)
        adb('exec-out', 'run-as', package, 'cp', temporary, 'files/wave3-fixtures/' + row['file'])
    payload = json.dumps({'books': rows}, ensure_ascii=False).encode('utf-8')
    temp = a.output / 'input.json'; temp.write_bytes(payload)
    adb('push', temp, '/data/local/tmp/exr-picker-input.json')
    adb('exec-out', 'run-as', package, 'cp', '/data/local/tmp/exr-picker-input.json', 'files/wave3-input.json')
    adb('install', '-r', '-t', a.test_apk)
    destination = '/sdcard/Download/EXReaderRecovery.epub'
    adb('shell', 'rm', '-f', destination)
    command = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'phase', 'picker-seed']
    for key, value in identity.items(): command.extend(('-e', key, value))
    command.append(package + '.test/' + package + '.Wave3UiTest')
    seeded = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180, check=False)
    (a.output / 'instrumentation.txt').write_bytes(seeded.stdout)
    assert seeded.returncode == 0 and b'WAVE3_UI_PASS picker-seed' in seeded.stdout
    report = json.loads(adb('exec-out', 'run-as', package, 'cat', 'files/wave3-ui-picker-seed.json'))
    assert report['passed'] is True and all(report.get(key) == value for key, value in identity.items())
    seeded_books = json.loads(adb('exec-out', 'run-as', package, 'cat', 'files/wave3-books.json'))
    adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')
    epub = next(row for row in rows if row['role'] == 'epub'); title = seeded_books['epub']['title']
    assert seeded_books['epub']['sha256'] == epub['sha256']
    book = wait_for(lambda nodes: next((node for node in nodes if node.get('package') == package and (node.get('text') == title or node.get('text', '').startswith(title + '\n'))), None), 120)
    long_tap(book)
    tap(wait_for(lambda nodes: next((node for node in nodes if text_is(node, '导出原件') and node.get('package') == package), None), 30))
    wait_for(lambda nodes: next((node for node in nodes if node.get('content-desc') == '原件导出状态' and '✓' in node.get('text', '')), None), 120)
    tap(wait_for(lambda nodes: next((node for node in nodes if text_is(node, '保存到…') and node.get('package') == package), None), 30))
    wait_for(lambda nodes: next((node for node in nodes if 'documentsui' in node.get('package', '').lower()), None), 180)
    before = pid(); assert before, 'host was not alive while the real picker was visible'
    adb('shell', 'run-as', package, '/system/bin/kill', '-9', before)
    deadline = time.monotonic() + 30
    while pid() == before and time.monotonic() < deadline: time.sleep(.2)
    assert pid() != before, 'the original host process survived the kill'
    result['pid_before_kill'] = before
    nodes = snapshot()
    if not any(text_is(node, 'Downloads') for node in nodes):
        roots = next((node for node in nodes if 'show roots' in node.get('content-desc', '').lower()), None)
        assert roots is not None, 'cannot locate the system picker roots'
        tap(roots)
        tap(wait_for(lambda nodes: next((node for node in nodes if text_is(node, 'Downloads')), None), 30))
    editor = wait_for(lambda nodes: next((node for node in nodes if node.get('class') == 'android.widget.EditText' and 'documentsui' in node.get('package', '').lower()), None), 30)
    tap(editor); adb('shell', 'input', 'keycombination', 'KEYCODE_CTRL_LEFT', 'KEYCODE_A')
    adb('shell', 'input', 'text', 'EXReaderRecovery.epub')
    wait_for(lambda nodes: next((node for node in nodes if node.get('class') == 'android.widget.EditText' and node.get('text') == 'EXReaderRecovery.epub'), None), 30)
    tap(wait_for(lambda nodes: next((node for node in nodes if text_is(node, 'Save') and 'documentsui' in node.get('package', '').lower()), None), 30))
    wait_for(lambda nodes: next((node for node in nodes if '已保存' in node.get('text', '') and node.get('package') == package), None), 120)
    after = pid(); assert after and after != before, 'save did not resume a new host process'
    saved = adb('exec-out', 'cat', destination)
    assert len(saved) == epub['bytes'] and hashlib.sha256(saved).hexdigest() == epub['sha256']
    result.update({'accepted': True, 'pid_after_result': after, 'app_sha256': apk_hash,
                   'bytes': len(saved), 'sha256': hashlib.sha256(saved).hexdigest(),
                   'picker': 'real Android DocumentsUI', 'kill': 'SIGKILL of background host, not force-stop'})
except BaseException as error:
    result['failure'] = type(error).__name__ + ': ' + str(error)
    raise
finally:
    (a.output / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
