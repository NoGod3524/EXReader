# SPDX-License-Identifier: MIT
"""Cloud-only real GTK/X11 fixed-page acceptance, after unchanged 20+5 cases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_linux_host import Session, command
from generate_fixed import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--original-evidence', type=Path, required=True)
    parser.add_argument('--product-evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    original = json.loads((args.original_evidence / 'report.json').read_text())
    product = json.loads((args.product_evidence / 'product-result.json').read_text())
    assert original['passed'] is True and len(original['checks']) == 20 and all(x['pass'] for x in original['checks'])
    assert product['accepted'] is True and len(product['checks']) == 5
    assert original['source_sha'] == product['source_sha'] == source
    assert original['run_id'] == product['run_id'] == run and product['attempt'] == attempt
    folder = args.output.resolve()
    folder.mkdir()
    inputs = folder / 'inputs'
    generate(inputs)
    pdf, cbz = inputs / 'Pages.pdf', inputs / 'Pages.cbz'
    pdf_bytes = pdf.read_bytes()
    cbz_bytes = cbz.read_bytes()
    host = Session((args.payload / 'bin/exreader-linux').resolve(), (args.payload / 'Reader.otf').resolve(), folder)
    package = json.loads((args.payload.parent / 'build.json').read_text())
    assert package['source_sha'] == source and package['sdk_version'] == '3.40.0' and package['abi'] == 1
    assert package['files']['bin/exreader-linux'] == hashlib.sha256(host.binary.read_bytes()).hexdigest()
    assert package['files']['Reader.otf'] == hashlib.sha256(host.font.read_bytes()).hexdigest()
    checks = []
    report = {'accepted': False, 'source_sha': source, 'run_id': run, 'attempt': attempt,
              'original_ui_cases': 20, 'original_product_cases': 5, 'checks': checks,
              'package_manifest_sha256': hashlib.sha256((args.payload.parent / 'build.json').read_bytes()).hexdigest(),
              'scope': 'Linux native PDF/CBZ page reading, text panel and fixed annotations',
              'complete_product': False, 'performance_budget_accepted': False}

    def require(name, condition, observation=None):
        checks.append({'name': name, 'passed': bool(condition), 'observed': observation or host.read()})
        assert condition, name + ': ' + repr(host.read())
        print('FIXED UI PASS ' + name, flush=True)

    def settled():
        return host.wait(lambda state: not state['saving'] and not state['save_failed'])

    def copy():
        host.key('F7', 'ctrl+a', 'ctrl+c')
        return subprocess.check_output(['xclip', '-selection', 'clipboard', '-o'], text=True, timeout=30)

    def screenshot(name):
        path = folder / name
        command('import', '-window', host.window, path)
        image = Image.open(path).convert('RGB')
        assert image.width >= 1000 and image.height >= 700
        # Capture the actual rendered page region, not just toolbar text.
        crop = image.crop((40, 120, 570, 650))
        assert sum(1 for pixel in crop.getdata() if min(pixel) < 180) > 300

    try:
        host.launch()
        require('01 independent empty GTK profile', settled()['books'] == 0)
        host.dialog(pdf)
        initial = settled()
        pdf_id = initial['book']
        require('02 native chooser imports and renders three-page PDF', initial['fixed'] == 1 and initial['pages'] == 3
                and initial['page'] == 0 and initial['books'] == 1 and initial['error'] == 0)
        screenshot('pdf.png')
        require('03 mapped PDF bitmap has actual page ink', True)
        require('04 PDF selection and native clipboard', 'Fixed page 1.' in copy())
        host.dialog(pdf)
        require('05 exact PDF duplicate keeps one SDK book', settled()['books'] == 1 and host.read()['book'] == pdf_id)
        host.key('F4')
        assert settled()['page'] == 1 and 'Fixed page 2.' in copy()
        host.key('F3', 'F3')
        require('06 PDF next previous and first boundary keep accepted frame', host.read()['page'] == 0 and host.read()['error'] == 1)
        host.key('F5')
        require('07 fixed F5 changes zoom without repagination or font change', settled()['zoom'] == 125
                and host.read()['font'] == initial['font'] and host.read()['page'] == 0)
        for _ in range(6):
            host.key('F5')
        require('08 oversized zoom refused without changing page or accepted zoom', host.read()['error'] == 6
                and host.read()['zoom'] == 250 and host.read()['page'] == 0)
        for _ in range(5):
            host.key('F6')
        assert settled()['zoom'] == 125 and host.read()['error'] == 0
        host.key('F11')
        host.paste('Fixed note: 中文 café')
        selected = copy()
        host.key('F8')
        state = settled()
        with sqlite3.connect(folder / 'profile/library.sqlite') as db:
            note = db.execute('SELECT page,start,end,text,exact,page_id FROM fixed_notes').fetchone()
        require('09 native selected PDF byte range captures stored-source selector', state['notes'] == 1
                and note[:4] == (0, 0, len(selected.encode()), 'Fixed note: 中文 café')
                and bytes(note[4]).decode() == selected and bool(note[5]))
        host.key('F4', 'F4', 'F4')
        assert host.read()['page'] == 2 and host.read()['error'] == 1
        host.key('F9', 'Home', 'Return')
        require('10 unique fixed note activation navigates and selects actual quote', settled()['page'] == 0
                and host.read()['selected'] > 0 and copy() == selected)
        host.key('F4')
        saved = settled()
        pdf.unlink()
        pid = host.process.pid
        host.close()
        host.launch()
        restored = settled()
        require('11 fresh process restores PDF from stored bytes with page zoom and note', host.process.pid != pid
                and all(restored[k] == saved[k] for k in ('book', 'page', 'zoom', 'font', 'notes', 'fixed'))
                and 'Fixed page 2.' in copy())
        killed = host.process.pid
        host.process.send_signal(signal.SIGKILL)
        host.process.wait(timeout=20)
        host.log.close()
        host.launch()
        recovered = settled()
        require('12 process kill after committed page restores PDF state', host.process.pid != killed
                and all(recovered[k] == saved[k] for k in ('book', 'page', 'zoom', 'notes')))
        host.dialog()
        require('13 cancelling native import keeps fixed page', host.read()['book'] == pdf_id and host.read()['page'] == 1)
        for name in ('Broken.pdf', 'Broken.cbz'):
            host.dialog(inputs / name)
            assert host.read()['error'] != 0 and host.read()['book'] == pdf_id and host.read()['page'] == 1
        require('14 malformed PDF and CBZ retain reader and library', host.read()['books'] == 1)
        host.dialog(inputs / 'Too-large.pdf')
        require('15 32 MiB PDF import ceiling preserves accepted page', host.read()['error'] == 6
                and host.read()['book'] == pdf_id and host.read()['page'] == 1 and host.read()['books'] == 1)
        host.key('F9', 'Home', 'F10')
        assert settled()['notes'] == 0
        host.close()
        host.launch()
        require('16 fixed note deletion persists across restart', settled()['notes'] == 0 and host.read()['page'] == 1)
        host.dialog(inputs / 'Rotated.pdf')
        assert settled()['fixed'] == 1 and host.read()['pages'] == 3 and 'Fixed page 1.' in copy()
        # At the retained 125% zoom the rotated page is wider than the native
        # viewport. Zoom out through the real controls to expose its right edge.
        host.key('F6', 'F6')
        assert settled()['zoom'] == 75
        screenshot('rotated.png')
        require('17 rotated PDF remains renderable and selectable', host.read()['error'] == 0)
        host.dialog(inputs / 'Repeated.pdf')
        text = copy()
        assert text.count('selection target') == 3
        # Select the first target through real native keyboard input; the exact
        # 16 characters have identical 32-scalar context on all three lines.
        offset = text.index('selection target')
        host.key('ctrl+Home')
        command('xdotool', 'key', '--clearmodifiers', '--repeat', str(offset), '--delay', '1', 'Right')
        command('xdotool', 'key', '--clearmodifiers', '--repeat', '16', '--delay', '1', 'shift+Right')
        host.key('F8', 'F4', 'F9', 'Home', 'Return')
        require('18 ambiguous fixed quote refuses jump instead of guessing stored offset', host.read()['error'] == 1
                and host.read()['page'] == 1 and host.read()['notes'] == 1)
        host.dialog(cbz)
        cbz_state = settled()
        cbz_id = cbz_state['book']
        screenshot('cbz.png')
        require('19 CBZ imports original archive and renders native bitmap', cbz_state['fixed'] == 1
                and cbz_state['pages'] == 3 and cbz_state['error'] == 0 and cbz_state['end'] == 0)
        host.key('F7', 'ctrl+a', 'F8')
        require('20 image-only CBZ cannot create fabricated text note', host.read()['error'] == 1 and host.read()['notes'] == 0)
        host.key('F4', 'F4', 'F4')
        require('21 CBZ last boundary retains last page', host.read()['page'] == 2 and host.read()['error'] == 1)
        before = host.read()['books']
        host.dialog(cbz)
        require('22 duplicate CBZ retains committed page and row', settled()['book'] == cbz_id
                and host.read()['page'] == 2 and host.read()['books'] == before)
        pdf.write_bytes(pdf_bytes)
        with sqlite3.connect(folder / 'profile/library.sqlite.product.sqlite') as db:
            expected = {'pdf:' + hashlib.sha256(pdf_bytes).hexdigest(), 'cbz:' + hashlib.sha256(cbz_bytes).hexdigest()}
            rows = db.execute('SELECT b.book_key,l.location_kind FROM reader_books b JOIN reader_local_books l USING(book_key)').fetchall()
        require('23 real PDF and CBZ catalog source digests use fixed-page mode', expected <= {key for key, mode in rows if mode == 'fixed_page'})
        txt = inputs / 'Reflow.txt'
        txt.write_text('Native reflow retains font actions after fixed-page reading.\n' * 80)
        host.dialog(txt)
        assert settled()['fixed'] == 0
        host.key('F5')
        require('24 fixed-to-reflow switch restores original font actions', settled()['font'] == initial['font'] + 2
                and host.read()['fixed'] == 0 and host.read()['error'] == 0)
        host.close()
        assert len(checks) == 24 and all(case['passed'] is True for case in checks)
        report['accepted'] = True
    finally:
        if host.process and host.process.poll() is None:
            host.process.terminate()
            host.process.wait(timeout=20)
        if host.log:
            host.log.close()
        report['files'] = {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in sorted(folder.rglob('*')) if path.is_file() and path.name != 'fixed-ui.json'}
        (folder / 'fixed-ui.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'accepted': report['accepted'], 'fixed_ui_checks': len(checks),
                      'source_sha': source, 'run_id': run, 'attempt': attempt}))


if __name__ == '__main__':
    main()
