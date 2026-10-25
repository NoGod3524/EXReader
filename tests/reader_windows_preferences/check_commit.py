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


def content_pixels(image):
    # The actual page painter has a four-pixel gutter. DrawFocusRect paints
    # inside that gutter at inset one when keyboard focus enters the page.
    # Keep every content pixel, omitting only three gutter pixels and unused
    # DIB alpha. Full original BMP captures and raw edge differences remain.
    width, height, raw = image
    cropped = b''.join(raw[(y*width+3)*4:(y*width+width-3)*4] for y in range(3,height-3))
    return width,height,cropped[0::4],cropped[1::4],cropped[2::4]


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
            field = F.ZOOM if role == 'pdf' else F.MARGIN if role == 'empty' else F.FONT
            key = 'fixed_page_zoom' if role == 'pdf' else 'margin' if role == 'empty' else 'font_size'
            initial, next_value = (100, 125) if role == 'pdf' else (36, 60) if role == 'empty' else (24, 26)
            F.set_text(app.field(field), str(initial))
            app.apply()
            app.close_dialog()
            before = F.document(profile)[1]
            before_frame = app.page_shot(role + '-before.bmp', output) if filename else None

            for stage in (11, 12):
                if not filename:
                    app.open_dialog()
                    F.set_text(app.field(field), str(next_value))
                assert app.q(stage + 100) == 1
                if not filename:
                    app.press(F.APPLY)
                else:
                    # Persist through the real nonmodal font/zoom toolbar path;
                    # the modal settings owner correctly blocks other commands.
                    F.send(F.U.GetDlgItem(app.window, 116 if role == 'pdf' else 114), 0xF5)
                app.wait(lambda: app.q(18) == stage, timeout=90)
                at_boundary = F.document(profile)[1]
                assert (at_boundary == before) == (stage == 11)
                pid = app.process.pid
                if filename:
                    app.click('cancel')
                else:
                    # While modal, application close is the real owner cancel
                    # path. Check the resulting durable choice after restart.
                    F.send(app.window, F.WM_CLOSE)
                app.release()
                if filename:
                    app.wait_idle()
                else:
                    app.process.wait(timeout=90)
                    app.log.close()
                    app = F.App(args.candidate.resolve(), args.font.resolve(), profile, existing=True)
                    app.settle()
                value, after = F.document(profile)
                frame = app.page_shot(role + '-stage-' + str(stage) + '.bmp', output) if filename else None
                expected = initial if stage == 11 else next_value
                facts = dict(role=role,stage=stage,key=key,actual=value[key],expected=expected,status=app.status())
                if filename:
                    assert before_frame[:2] == frame[:2], 'viewport size changed'
                    width, height = frame[:2]
                    changed_rgb = [index // 4 for index in range(0, len(frame[2]), 4)
                                   if frame[2][index:index+3] != before_frame[2][index:index+3]]
                    facts.update(changed_rgb_pixels=len(changed_rgb),
                                 changed_alpha_bytes=sum(a != b for a,b in zip(frame[2][3::4],before_frame[2][3::4])),
                                 changed_bounds=([min(n%width for n in changed_rgb),min(n//width for n in changed_rgb),
                                                  max(n%width for n in changed_rgb),max(n//width for n in changed_rgb)] if changed_rgb else None),
                                 changed_interior_pixels=sum(3<=n%width<width-3 and 3<=n//width<height-3 for n in changed_rgb))
                result.setdefault('boundary_observations', []).append(facts)
                print('COMMIT_BOUNDARY ' + json.dumps(facts), flush=True)
                assert value[key] == expected, facts
                assert (after == before) == (stage == 11)
                if filename:
                    assert (content_pixels(frame) == content_pixels(before_frame)) == (stage == 11), facts
                app.open_dialog()
                assert float(F.text(app.field(field))) == expected
                app.close_dialog()
                rows.append(dict(name=role + ('-before-save-cancel-retains' if stage == 11 else '-after-save-cancel-publishes'),
                                 passed=True, pid=pid, boundary_stage=stage,
                                 cancellation='native-cancel-button' if filename else 'actual-close-and-reopen',
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
        app.settle()
        app.import_file(args.fixtures / 'Reading sample.txt')
        app.open('Reading sample')
        app.wait_idle()
        app.open_dialog()
        F.set_text(app.field(F.FONT), '24')
        app.apply()
        app.close_dialog()
        assert app.q(112) == 1
        F.send(F.U.GetDlgItem(app.window, 114), 0xF5)
        app.wait(lambda: app.q(18) == 12, timeout=90)
        app.click('cancel')
        app.release()
        app.wait_idle()
        assert F.document(profile)[0]['font_size'] == 26
        app.open_dialog()
        assert float(F.text(app.field(F.FONT))) == 24
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
