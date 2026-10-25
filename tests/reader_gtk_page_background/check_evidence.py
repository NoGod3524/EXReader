# SPDX-License-Identifier: MIT
"""Candidate-only scope authentication; frozen 3.40 reports/checkers stay intact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

SDK = 'b911815e26a10e7c45f50f56bf7c4e46cbca010b'
REPORTS = {
    'preferences-ui/result.json': (41, 'page_background_scope_passed'),
    'gtk-drop-ui/report.json': (20, 'drop_import_scope_passed'),
    'gtk-drop-backend/report.json': (23, 'ok'),
    'gtk-batch-evidence.json': (None, 'ok'),
    'records-ui/report.json': (30, 'reading_records_scope_passed'),
    'gtk-navigation-ui/result.json': (29, 'navigation_scope_passed'),
    'gtk-search-ui/result.json': (30, 'search_scope_passed'),
    'account-ui/result.json': (46, 'accepted'),
    'account-shelf/shelf-result.json': (14, 'accepted'),
    'account-original/report.json': (20, 'passed'),
    'account-atspi-fixes/result.json': (10, 'accepted'),
    'account-product-ui/product-result.json': (5, 'accepted'),
    'account-fixed-ui/fixed-ui.json': (24, 'accepted'),
    'account-metadata-ui/metadata-ui.json': (15, 'accepted'),
    'account-collections-ui/collections-ui.json': (27, 'accepted'),
    'account-regressions/regressions.json': (4, 'passed'),
}
LEGACY = {'account-original/report.json', 'account-regressions/regressions.json'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', required=True, type=Path)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    build = args.build
    binary = build / 'account-package/EXReader-Linux/bin/exreader-linux'
    program = hashlib.sha256(binary.read_bytes()).hexdigest()
    result = dict(accepted=False, ok=False, page_background_scope_passed=False, settings_whole_page_palette_accepted=False,
                  source_sha=source, run_id=run, attempt=attempt, program_sha256=program, sdk_candidate_source=SDK,
                  sdk_version='3.41.0', core_version='3.40.0', sdk_abi=1, complete_product=False,
                  six_platform_accepted=False, physical_device_execution=False, performance_accepted=False,
                  orca_accepted=False, verified={}, legacy_reports_external_identity={})

    def bind(path, count=None):
        result['verified'][path] = dict(sha256=hashlib.sha256((build / path).read_bytes()).hexdigest(), count=count)

    try:
        loaded = {}
        for path, (count, grant) in REPORTS.items():
            value = json.loads((build / path).read_text())
            assert value.get('source_sha', value.get('source')) == source, path
            if path in LEGACY:
                assert value['schema'] == 1 and 'attempt' not in value and 'program_sha256' not in value
                if 'run_id' in value:
                    assert str(value['run_id']) == run
                result['legacy_reports_external_identity'][path] = dict(
                    source_sha=source, run_id=run, attempt=attempt, program_sha256=program,
                    binding='completed same-attempt producer job and raw ZIP; original schema unchanged')
            else:
                assert str(value['run_id']) == run and str(value['attempt']) == attempt, path
            if 'program_sha256' in value:
                assert value['program_sha256'] == program, path
            assert value[grant] is True, path
            if count is not None:
                rows = value['checks']
                assert len(rows) == count, path
                if rows and isinstance(rows[0], dict):
                    assert all(row.get('passed', row.get('pass', row.get('ok'))) is True for row in rows), path
                    names = [row['name'] for row in rows]
                else:
                    names = rows
                assert all(isinstance(name, str) and name for name in names) and len(set(names)) == len(names), path
            loaded[path] = value
            bind(path, count)
        settings = loaded['preferences-ui/result.json']
        assert settings['original_settings_count'] == settings['original_settings_passed'] == 35
        assert settings['count'] == settings['passed'] == 41 and settings['failed'] == 0
        assert settings['sdk_candidate_source'] == SDK and settings['diagnostic_only'] is False
        assert settings['sdk_changed'] is True and settings['pending_fields'] == []
        assert settings['reflow_outer_margin']['whole_page_background_accepted'] is True
        required = {'light_foreground_and_background_change_page_pixels', 'dark_theme_and_palette_change_page_pixels',
                    'system_theme_tracks_real_portal_preference_changes', 'bounded_epub_uses_sdk_canvas_and_keeps_outer_margin',
                    'palette_change_preserves_same_book_part_anchor_and_font', 'original_image_quadrants_and_white_patch_are_not_recolored',
                    'authored_explicit_white_paint_survives_dark_canvas_outside_image',
                    'original_image_samples_stay_identical_after_native_palette_switch',
                    'next_bounded_chapter_uses_same_canvas_without_source_change'}
        assert required.issubset({row['name'] for row in settings['checks']})
        batch = loaded['gtk-batch-evidence.json']
        assert batch['batch_import_scope_passed'] is True and batch['diagnostic_only'] is True
        assert batch['backend_checks'] == 684 and batch['owner_fault_scenarios'] == 4
        assert loaded['account-ui/result.json']['credential_leak_hits'] == 0
        assert loaded['account-ui/result.json']['local_originals'] == 52
        shelf = loaded['account-shelf/shelf-result.json']
        assert shelf['originals'] == 2202 and shelf['page_size'] == 50 and shelf['cache_limit'] == 150 and shelf['problems'] == []
        manifest_path = 'account-package/build.json'
        manifest = json.loads((build / manifest_path).read_text())
        assert manifest['source_sha'] == source and manifest['sdk_version'] == '3.41.0' and manifest['abi'] == 1
        assert manifest['files']['bin/exreader-linux'] == program
        bind(manifest_path)
        for header in ('base.h', 'render.h'):
            path = 'reading-library/stage/include/exr/' + header
            expected = subprocess.check_output(['git', 'show', SDK + ':include/exr/' + header])
            assert (build / path).read_bytes() == expected
            bind(path)
        fixture_path = 'page-background-fixtures/manifest.json'
        fixture = json.loads((build / fixture_path).read_text())
        assert fixture['book'] == 'Authored white and original image.epub'
        book_path = 'page-background-fixtures/' + fixture['book']
        assert hashlib.sha256((build / book_path).read_bytes()).hexdigest() == fixture['sha256']
        bind(fixture_path);bind(book_path)
        for path, expected in (('gtk-drop-j03/portable.log', 52), ('gtk-drop-j03/gtk.log', 28)):
            rows = [json.loads(line) for line in (build / path).read_text().splitlines() if line.startswith('{')]
            summaries = [row for row in rows if row.get('case') == '__summary']
            assert len(summaries) == 1 and summaries[0]['total'] == summaries[0]['passed'] == expected
            assert summaries[0]['failed'] == summaries[0]['skipped'] == 0
            bind(path, expected)
        result['ok'] = result['page_background_scope_passed'] = result['settings_whole_page_palette_accepted'] = True
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        (build / 'gtk-page-background-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
