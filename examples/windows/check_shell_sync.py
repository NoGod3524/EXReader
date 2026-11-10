# SPDX-License-Identifier: MIT
"""Real-host cloud-sync acceptance: two profiles, one mock WebDAV process.

python -X utf8 examples/windows/check_shell_sync.py EXE MOCK_EXE FONT OUTPUT

Everything the user touches is the real EXReader.exe (settings -> 云同步 page,
edit boxes, buttons, worker thread, DPAPI file). Only annotation/progress data
is seeded as files, in the same format the host writes. The mock server runs in
its own process and is really killed to produce an outage.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_shell_search import run, setup  # noqa: E402

USER, PASSWORD = 'alice', 's3cret-Pw!-密码'


def epub(path):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip')
        z.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr('OEBPS/book.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">sync-book</dc:identifier><dc:title>Sync Book</dc:title><dc:language>en</dc:language></metadata><manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c"/></spine></package>')
        z.writestr('OEBPS/chapter.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title></head><body>' + ''.join(f'<p>Paragraph {i} of the synchronisation fixture.</p>' for i in range(40)) + '</body></html>')


def endpoint(at):
    return {'part_id': 'p1', 'part_path': 'OEBPS/chapter.xhtml', 'text_revision': '00000000deadbeef', 'text_size': 100000,
            'selector': {'start': at, 'end': at, 'exact': '', 'prefix': f'before {at}', 'suffix': 'after', 'chapter': None}}


def write_annotations(directory, sha, items):
    directory.mkdir(parents=True, exist_ok=True)
    doc = {'version': 1, 'book_sha256': sha, 'annotations': [
        {'color': 0, 'created_ms': ms, 'updated_ms': ms, 'text': text, 'anchor': {'start': endpoint(at), 'end': endpoint(at)}}
        for at, text, ms in items]}
    (directory / f'{sha}.json').write_text(json.dumps(doc, ensure_ascii=False), encoding='utf8')


def read_annotations(directory, sha):
    return [a['text'] for a in json.loads((directory / f'{sha}.json').read_text('utf8'))['annotations']]


class Mock:
    def __init__(self, exe, port=0):
        self.exe, self.port = exe, port
        self.p = None

    def start(self):
        self.p = subprocess.Popen([str(self.exe), str(self.port), USER, PASSWORD], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        line = self.p.stdout.readline().decode().strip()
        assert line.startswith('listening '), line
        self.port = int(line.split()[1])
        return self.port

    def kill(self):  # a real outage: the process is gone and the port refuses connections
        self.p.kill()
        self.p.wait()


def remote_state(mock, sha):
    import urllib.request, base64
    req = urllib.request.Request(f'http://127.0.0.1:{mock.port}/dav/{sha}/state.json')
    req.add_header('Authorization', 'Basic ' + base64.b64encode(f'{USER}:{PASSWORD}'.encode()).decode())
    return json.loads(urllib.request.urlopen(req, timeout=5).read().decode('utf8'))


def profile_run(exe, font, out, name, annot_dir, script, captures=()):
    phase = out / name
    old = os.environ.get('EXREADER_ANNOTATIONS_DIR')
    os.environ['EXREADER_ANNOTATIONS_DIR'] = str(annot_dir)
    try:
        return run(exe, font, phase, script, captures)
    finally:
        if old is None:
            os.environ.pop('EXREADER_ANNOTATIONS_DIR', None)
        else:
            os.environ['EXREADER_ANNOTATIONS_DIR'] = old


def main():
    exe, mock_exe, font, out = [Path(x).resolve() for x in sys.argv[1:5]]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    book = out / 'sync-book.epub'
    epub(book)
    sha = hashlib.sha256(book.read_bytes()).hexdigest()
    mock = Mock(mock_exe)
    port = mock.start()
    url = f'http://127.0.0.1:{port}/dav/'
    results = {}
    try:
        pa, pb = out / 'A', out / 'B'
        aa, ab = out / 'A-annotations', out / 'B-annotations'
        write_annotations(aa, sha, [(100, 'from device A', 1762600001000)])
        write_annotations(ab, sha, [(200, 'from device B', 1762600002000)])
        open_book = ['import|' + str(book), 'open|Sync Book'] + setup()

        # 1. device A: type server + credentials into the page, save, sync now
        script = open_book + ['sync_open', 'wait_idle', f'sync_fill|{url}|{USER}|{PASSWORD}', 'sync_click|save', 'sync_pass_empty', 'sync_click|now',
                              'sync_wait|20000', 'sync_check|0|同步完成|0']
        caps = [(f'STEP\t{len(script)}\tsync_check\tPASS', 'sync-ok')]
        script += ['probe_wait|3000', 'quit']
        results['A-first'] = profile_run(exe, font, out, 'A', aa, script, caps)
        st = remote_state(mock, sha)
        assert st['revision'] == 1 and len(st['annotations']) == 1, st['revision']

        # 2. device B (different profile + annotations) adds its own annotation -> merge on upload
        script = open_book + ['sync_open', f'sync_fill|{url}|{USER}|{PASSWORD}', 'sync_click|save', 'sync_click|now', 'sync_wait|20000',
                              'sync_check|0|同步完成|0', 'quit']
        results['B-merge'] = profile_run(exe, font, out, 'B', ab, script)
        st = remote_state(mock, sha)
        assert st['revision'] == 2 and len(st['annotations']) == 2
        assert sorted(read_annotations(ab, sha)) == ['from device A', 'from device B']

        # 3. device A restarts (credentials come back from the DPAPI file, nothing is typed) and receives B's annotation
        script = open_book + ['sync_open', 'sync_click|now', 'sync_wait|20000', 'sync_check|0|同步完成|0']
        caps = [(f'STEP\t{len(script)}\tsync_check\tPASS', 'sync-restart')]
        script += ['probe_wait|3000', 'quit']
        results['A-restart'] = profile_run(exe, font, out, 'A', aa, script, caps)
        assert sorted(read_annotations(aa, sha)) == ['from device A', 'from device B']

        # 4. outage: kill the server process, edit three things on A, sync -> readable error + drafts
        mock.kill()
        write_annotations(aa, sha, [(100, 'from device A', 1762600001000), (200, 'from device B', 1762600002000),
                                    (300, 'offline edit 1', 1762600100000)])
        script = open_book + ['sync_open', 'sync_click|now', 'sync_wait|40000', 'sync_check|4|无法连接服务器|1']
        caps = [(f'STEP\t{len(script)}\tsync_check\tPASS', 'sync-offline')]
        script += ['probe_wait|3000', 'quit']
        results['A-offline'] = profile_run(exe, font, out, 'A', aa, script, caps)
        queue = json.loads((pa / 'sync.json').read_text('utf8'))['queue']
        assert [q['sha256'] for q in queue] == [sha]

        # 5. server comes back on the same port: the queued draft is pushed
        mock2 = Mock(mock_exe, port)
        mock2.start()
        mock = mock2
        # the new process starts empty, so this is a first upload of the merged state
        script = open_book + ['sync_open', 'sync_click|now', 'sync_wait|20000', 'sync_check|0|同步完成|0']
        caps = [(f'STEP\t{len(script)}\tsync_check\tPASS', 'sync-reconnected')]
        script += ['probe_wait|3000', 'quit']
        results['A-reconnect'] = profile_run(exe, font, out, 'A', aa, script, caps)
        st = remote_state(mock, sha)
        assert len(st['annotations']) == 3
        assert json.loads((pa / 'sync.json').read_text('utf8'))['queue'] == []

        # 6. wrong password on a fresh profile: explicit 401 text, nothing saved as success
        pc = out / 'C'
        script = open_book + ['sync_open', f'sync_fill|{url}|{USER}|wrong-password', 'sync_click|now', 'sync_wait|20000', 'sync_check|1|HTTP 401|-1']
        caps = [(f'STEP\t{len(script)}\tsync_check\tPASS', 'sync-401')]
        script += ['probe_wait|3000', 'quit']
        results['C-401'] = profile_run(exe, font, out, 'C', out / 'C-annotations', script, caps)

        # 7. credentials are not in plain text anywhere the app writes
        scan = {}
        for label, folder in [('profile-A', pa), ('profile-B', pb), ('profile-C', pc), ('annotations-A', aa), ('annotations-B', ab)]:
            args = [sys.executable, '-I', str(ROOT / 'tools/check_sync_credentials.py'), str(folder), PASSWORD, USER]
            proc = subprocess.run(args, capture_output=True, text=True, encoding='utf8')
            scan[label] = proc.stdout.strip().splitlines()[-2:]
            if label.startswith('profile-') and label != 'profile-C':
                assert proc.returncode == 0, proc.stdout
            else:
                assert 'hits=0' in proc.stdout, proc.stdout
    finally:
        try:
            mock.kill()
        except Exception:
            pass
    report = {'exe_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(), 'book_sha256': sha, 'credential_scan': scan,
              'runs': {k: {'exit': v['exit'], 'elapsed_seconds': v['elapsed_seconds']} for k, v in results.items()}}
    (out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
