"""Actions-only real host cancellation at the public F3 save boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import traceback

import check_ui as F


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    for name in ('candidate', 'control', 'font', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    result = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], accepted=False, checks=rows,
                  consumer_sha256=digest(args.candidate), control_sha256=digest(args.control),
                  complete_product=False, original_f3_suite_accepted=False)
    app = None
    try:
        for role, filename, title in [('empty', None, None),
                                      ('txt', 'Reading sample.txt', 'Reading sample'),
                                      ('epub', 'Picture book.epub', 'Picture book'),
                                      ('pdf', 'Fixed page.pdf', 'Fixed page')]:
            profile = output / role
            app = F.App(args.candidate.resolve(), args.font.resolve(), profile)
            app.settle()
            if filename:
                app.import_file(args.fixtures / filename)
                app.open(title)
                app.wait_idle()
            app.open_dialog()
            field = F.ZOOM if role == 'pdf' else F.MARGIN
            key = 'fixed_page_zoom' if role == 'pdf' else 'margin'
            initial, next_value = (100, 125) if role == 'pdf' else (36, 60)
            F.set_text(app.field(field), str(initial))
            app.apply()
            app.close_dialog()
            before = F.document(profile)[1]
            before_frame = app.page_shot(role + '-before.bmp', output) if filename else None

            for stage in (11, 12):
                app.open_dialog()
                F.set_text(app.field(field), str(next_value))
                assert app.q(stage + 100) == 1
                app.press(F.APPLY)
                app.wait(lambda: app.q(18) == stage, timeout=90)
                at_boundary = F.document(profile)[1]
                assert (at_boundary == before) == (stage == 11)
                # Deliver the real owner cancel command at a held worker
                # boundary. The hook never edits the flag or the save result.
                F.send(app.window, 0x111, 117, 0)
                app.release()
                app.wait_idle()
                app.close_dialog()
                value, after = F.document(profile)
                frame = app.page_shot(role + '-stage-' + str(stage) + '.bmp', output) if filename else None
                expected = initial if stage == 11 else next_value
                assert value[key] == expected
                assert (after == before) == (stage == 11)
                if filename:
                    assert (frame == before_frame) == (stage == 11)
                app.open_dialog()
                assert float(F.text(app.field(field))) == expected
                app.close_dialog()
                rows.append(dict(name=role + ('-before-save-cancel-retains' if stage == 11 else '-after-save-cancel-publishes'),
                                 passed=True, pid=app.process.pid, boundary_stage=stage,
                                 file_sha256=hashlib.sha256(after).hexdigest()))
                print(json.dumps(rows[-1]), flush=True)

            app.close_app()
            app = F.App(args.candidate.resolve(), args.font.resolve(), profile, existing=True)
            app.settle()
            if filename:
                app.open(title)
                app.wait_idle()
            app.open_dialog()
            assert float(F.text(app.field(field))) == next_value
            assert F.document(profile)[0][key] == next_value
            rows.append(dict(name=role + '-reopened-committed-choice', passed=True, pid=app.process.pid))
            app.close_dialog()
            app.close_app()
            app = None

        # Same actual save and worker, with only the old generic cancellation
        # veto restored. It must leave disk committed and UI stale.
        profile = output / 'old-veto-control'
        app = F.App(args.control.resolve(), args.font.resolve(), profile)
        app.open_dialog()
        F.set_text(app.field(F.MARGIN), '36')
        app.apply()
        F.set_text(app.field(F.MARGIN), '60')
        assert app.q(112) == 1
        app.press(F.APPLY)
        app.wait(lambda: app.q(18) == 12, timeout=90)
        F.send(app.window, 0x111, 117, 0)
        app.release()
        app.wait_idle()
        app.close_dialog()
        assert F.document(profile)[0]['margin'] == 60
        app.open_dialog()
        assert float(F.text(app.field(F.MARGIN))) == 36
        rows.append(dict(name='old-post-save-veto-control-rejected', passed=True, pid=app.process.pid))
        app.close_dialog()
        app.close_app()
        app = None
        assert len(rows) == 13
        result['accepted'] = True
    except Exception:
        result['failure'] = traceback.format_exc()
        raise
    finally:
        if app is not None:
            try:
                app.release()
                app.close_app()
            except Exception:
                app.process.kill()
                app.process.wait()
        result['count'] = len(rows)
        (output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
