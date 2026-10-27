"""Real account status name events and keyboard close; no screen-reader claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_a11y_gtk'))
import atspi_client as bus
from driver import Host, wait_until


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True)
    host = Host((args.payload / 'bin/exreader-linux').resolve(),
                (args.payload / 'Reader.otf').resolve(), folder)
    recorder = bus.Recorder()
    report = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  program_sha256=hashlib.sha256(host.binary.read_bytes()).hexdigest(),
                  orca_accepted=False, physical_device_accepted=False, checks=[])
    app = None
    def check(name, passed, details):
        report['checks'].append(dict(name=name, passed=bool(passed), details=details))
        assert passed, report['checks'][-1]
    def control(description):
        return next((n for n in bus.walk(app) if n.get_description() == description), None)
    try:
        assert bus.init()[0] and recorder.start()
        host.launch()
        app = bus.wait_application('exreader-linux')
        host.key('ctrl+shift+a')
        dialog = wait_until(lambda: bus.find_one(app, roles=('dialog',), text='Account and Sync'), 30)
        host.activate(host.window_named('Account and Sync'))
        notice = wait_until(lambda: control('Account operation status'), 30)
        progress = wait_until(lambda: control('Account sync progress'), 30)
        wait_until(lambda: host.section('account').get('owner_busy') == '0', 30)
        before = bus.name(notice)
        mark = recorder.mark()
        # Invalid HTTP root is rejected locally; no external account or secret.
        root = bus.find_one(dialog, text='HTTPS WebDAV root')
        assert root is not None
        for _ in range(30):
            if any(bus.same(root, n) for n in bus.focused_all(app)):
                break
            host.key('Tab')
        else:
            raise AssertionError('root entry unreachable by keyboard')
        host.key('ctrl+a')
        host.type_text('http://invalid.example/no-network')
        host.key('alt+a')
        wait_until(lambda: bus.name(notice) != before and bool(bus.name(notice)), 30)
        after = bus.name(notice)
        events = wait_until(lambda: [e for e in recorder.since(mark)
            if e['type'] == 'object:property-change:accessible-name'
            and e.get('source_name') == after], 30)
        # The status label can be resized after its name changes. Compare the
        # same two live nodes once the native layout has settled.
        deadline = time.monotonic() + 6
        peer = None
        same_notice = False
        while time.monotonic() < deadline:
            peer = control('Account operation status')
            same_notice = bus.same(notice, peer)
            if same_notice:
                break
            time.sleep(.08)
        check('account_status_exposes_changed_name_event', same_notice,
              dict(before=before, after=after, events=events, path=bus.path_of(notice),
                   peer_path=bus.path_of(peer), notice_extents=bus.extents(notice),
                   peer_extents=bus.extents(peer)))
        check('progress_has_stable_semantic_description', progress.get_description() == 'Account sync progress',
              dict(name=bus.name(progress), path=bus.path_of(progress)))
        (folder / 'tree.json').write_text(json.dumps(bus.dump(app), indent=2))
        host.screenshot(folder / 'account.png', window='root')
        host.key('Escape')
        wait_until(lambda: not bus.find_one(app, roles=('dialog',), text='Account and Sync'), 30)
        frame = bus.find_one(app, roles=('frame',), text='EXReader Linux')
        focused = wait_until(lambda: [n for n in bus.focused_all(app) if bus.is_ancestor(frame, n)], 30)
        check('error_dialog_closes_and_restores_focus', bool(focused), [bus.path_of(n) for n in focused])
        report['accepted'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        recorder.stop()
        (folder / 'events.json').write_text(json.dumps(recorder.items, indent=2))
        if app is not None:
            (folder / 'final-tree.json').write_text(json.dumps(bus.dump(app), indent=2))
        host.close()
        bus.exit_bus()
        (folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)
    assert report['accepted'], report.get('error')

if __name__ == '__main__':
    main()
