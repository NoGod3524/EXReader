#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only actual worker completion after the UI metadata cache is evicted."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'worker_review'))
sys.path.insert(0, str(HERE))
from check_worker import App, U, set_text
from make_fixtures import epub


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.name == 'nt'
    output = args.output.resolve();output.mkdir(parents=True, exist_ok=False)
    first, second = output / 'First.epub', output / 'Second.epub'
    epub(first, 'Shelf Worker First', 'First original. ' * 100)
    epub(second, 'Shelf Worker Second', 'Second original. ' * 100)
    app = App(args.candidate.resolve(), (args.package / 'Reader.otf').resolve(), output / 'profile', bounded=True)
    checks = []
    try:
        app.import_file(first);app.import_file(second);app.open('Shelf Worker First')
        original = app.q(10)
        assert original > 0 and app.q(13) == 2
        app.gate(4);app.open('Shelf Worker Second', wait=False);app.stage(4)
        assert app.q(303) == 1 and app.q(13) == 0
        app.release();app.wait_idle()
        accepted = app.q(10)
        assert accepted > 0 and accepted != original and app.q(19) == accepted and app.q(13) == 0
        assert app.scalar('SELECT count(*) FROM books') == 2
        assert app.scalar('SELECT count(*) FROM epub_progress WHERE book_id=?', (accepted,)) == 1
        checks.append('completed_frame_and_owned_metadata_survive_real_ui_cache_eviction')
        assert app.q(304) == 1 and app.q(13) == 2
        app.gate(4);app.open('Shelf Worker First', wait=False);app.stage(4)
        assert app.q(303) == 1
        app.click('cancel');app.release();app.wait_idle()
        assert app.q(10) == accepted and app.q(19) == accepted and app.q(13) == 0
        checks.append('cancelled_owned_candidate_keeps_current_book_after_cache_eviction')
        assert app.q(304) == 1
        app.open('Shelf Worker First')
        assert app.q(10) == original and app.q(19) == original and app.q(13) == 2
        checks.append('reloaded_native_shelf_opens_correct_original_after_cancel')
        app.close()
        assert app.process.returncode == 0
        checks.append('normal_close_releases_worker_owned_metadata_and_handles')
        app=App(args.candidate.resolve(),(args.package/'Reader.otf').resolve(),output/'profile',bounded=True,existing=True)
        app.gate(5);set_text(U.GetDlgItem(app.window,126),'Shelf Worker First');app.stage(5)
        app.open('Shelf Worker Second',wait=False);app.release();app.wait_idle()
        assert app.q(10)==accepted and app.q(19)==accepted and app.q(13)==1 and app.q(305)==0
        assert app.row('Shelf Worker First')==0
        checks.append('interrupted_filter_retries_after_reading_without_replacing_active_book')
        app.close()
    finally:
        if app.process.poll() is None:
            app.close()
    assert len(checks) == 5
    report = {'accepted': True, 'complete_product': False, 'windows_bounded_shelf_ui_accepted': False,
              'scope': 'worker result ownership before Windows bounded UI integration',
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'problems': [],
              'binary_sha256': hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
              'files': {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted(output.rglob('*')) if path.is_file()}}
    (output / 'worker-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
