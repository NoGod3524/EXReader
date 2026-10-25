# SPDX-License-Identifier: MIT
"""Actions-only exact-source GTK drop/paste and retained-suite authentication."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    build = args.build
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    binary = build / 'account-package/EXReader-Linux/bin/exreader-linux'
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    report = dict(accepted=False, drop_import_scope_passed=False, ok=False, source_sha=source, run_id=run, attempt=attempt,
                  program_sha256=digest, complete_product=False, physical_device_execution=False,
                  six_platform_accepted=False, performance_accepted=False, orca_accepted=False,
                  settings_whole_page_palette_accepted=False, verified={})

    def load(relative, grant=None, count=None):
        path = build / relative
        value = json.loads(path.read_text())
        assert value.get('source_sha', value.get('source')) == source, relative
        assert str(value['run_id']) == run and str(value['attempt']) == attempt, relative
        if 'program_sha256' in value:
            assert value['program_sha256'] == digest, relative
        if grant:
            assert value[grant] is True, relative
        if count is not None:
            checks = value['checks']
            assert len(checks) == count, relative
            if checks and isinstance(checks[0], dict):
                assert all(row.get('passed', row.get('pass', row.get('ok'))) is True for row in checks), relative
                names = [row.get('name') for row in checks]
            else:
                names = checks
            assert len(set(names)) == len(names), relative
        report['verified'][relative] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), count=count)
        return value

    try:
        ui = load('gtk-drop-ui/report.json', 'drop_import_scope_passed', 20)
        required = {'real_pointer_drag_delivered_exact_native_uri_bytes', 'ordinary_text_ctrl_v_is_not_a_file_import_action',
                    'gtk_remains_responsive_during_real_delayed_clipboard_owner', 'escape_cancels_pending_clipboard_without_queuing_import',
                    'late_native_clipboard_response_cannot_restart_cancelled_import', 'gnome_cut_paste_owns_payload_after_clipboard_owner_dies',
                    'explicit_multi_file_input_keeps_only_32_visible_receipts', 'parent_close_finishes_without_waiting_for_clipboard_owner',
                    'reopen_keeps_real_sdk_ids_and_canonical_keys_stable', 'cut_drag_and_refused_items_never_mutate_original_files'}
        assert required.issubset({row['name'] for row in ui['checks']})
        assert ui['accepted'] is False and ui['complete_product'] is False
        load('gtk-drop-backend/report.json', 'ok', 23)
        batch = load('gtk-batch-evidence.json', 'ok')
        assert batch['batch_import_scope_passed'] is True and batch['backend_checks'] == 684 and batch['owner_fault_scenarios'] == 4
        assert batch['all_reading_navigation_search_and_non_palette_settings_retained'] is True
        assert set(batch['retained_sdk_failures']) == {'light_foreground_and_background_change_page_pixels', 'dark_theme_and_palette_change_page_pixels'}
        for relative, expected in [('gtk-drop-j03/portable.log', 52), ('gtk-drop-j03/gtk.log', 28)]:
            path = build / relative
            values = [json.loads(line) for line in path.read_text().splitlines() if line.startswith('{')]
            summaries = [value for value in values if value.get('case') == '__summary']
            assert len(summaries) == 1 and summaries[0]['total'] == expected and summaries[0]['passed'] == expected
            assert summaries[0]['failed'] == 0 and summaries[0]['skipped'] == 0
            report['verified'][relative] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), count=expected)
        account = load('account-ui/result.json', 'accepted', 46)
        assert account['credential_leak_hits'] == 0 and account['local_originals'] == 52
        shelf = load('account-shelf/shelf-result.json', 'accepted', 14)
        assert shelf['originals'] == 2202 and shelf['page_size'] == 50 and shelf['cache_limit'] == 150 and shelf['problems'] == []
        load('account-original/report.json', 'passed', 20)
        load('account-atspi-fixes/result.json', 'accepted', 10)
        report['retained_sdk_failures'] = batch['retained_sdk_failures']
        report['drop_import_scope_passed'] = True
        report['ok'] = True
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        (build / 'gtk-drop-evidence.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
