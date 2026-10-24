# SPDX-License-Identifier: MIT
"""Cloud-only real process interruption and source-bound consumer evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import sqlite3
import subprocess
import threading

EXPECTED = {
    'joint_sqlite_version_and_compile_limits', 'original_sha256_and_nfc_title',
    'duplicate_preserves_user_metadata', 'oldest_duplicate_keeps_real_legacy_mode',
    'bounded_epub_mode_from_public_api', 'pdf_fixed_page_mapping',
    'multichunk_cancel_retains_committed_sdk_source',
    'postcommit_product_failure_repaired_after_restart',
    'cancel_at_publication_reports_cancel_retains_commit',
}
NATIVE_EXPECTED = {
    'migration_matches_source_and_reopens', 'foreign_identity_preserved',
    'atomic_attach_rollback', 'verified_identity_and_mode_refusals',
    'oldest_duplicate_keeps_true_mode', 'existing_metadata_and_history_retained',
    'local_removal_retains_global_records', 'bounded_keyset_no_duplicates',
    'rejects_bad_inputs', 'owner_queue_and_no_reentry', 'busy_writer_retries',
    'shelf_triggers_still_enforced',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('build', type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    binary = build / ('reader-desktop-catalog-check.exe' if os.name == 'nt' else 'reader-desktop-catalog-check')
    sdk = json.loads((build / 'sdk-check/sdk-result.json').read_text())
    native = json.loads((build / 'native-check/result.json').read_text())
    for report, expected_count in ((sdk, 9), (native, 12)):
        assert report['accepted'] is True and report['problems'] == []
        for field, environment in (('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')):
            assert report[field] == os.environ[environment]
        assert report['sqlite_version'] == '3.54.0'
        assert len(report['checks']) == expected_count
        assert len({row['id'] for row in report['checks']}) == expected_count
        assert all(row['passed'] is True for row in report['checks'])
    assert {row['id'] for row in sdk['checks']} == EXPECTED
    assert {row['id'] for row in native['checks']} == NATIVE_EXPECTED
    # Independent digest over the exact fixture content, not the adapter's hash.
    with sqlite3.connect(build / 'sdk-check/product.sqlite') as db:
        key, size = db.execute("SELECT book_key,source_bytes FROM reader_books WHERE title='Large source'").fetchone()
        original = bytes(ord('a') + (offset * 17 + offset // 65536) % 26 for offset in range(196609))
        assert key == 'txt:' + hashlib.sha256(original).hexdigest() and size == 196609
    kills = []
    for stage in ('sdk', 'transaction'):
        folder = build / ('kill-' + stage)
        folder.mkdir()
        process = subprocess.Popen([str(binary), str(folder), 'seed', stage], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1)
        lines = []
        messages = queue.Queue()

        def read_output():
            for line in process.stdout:
                lines.append(line)
                if line.strip() == 'READY_TO_KILL':
                    messages.put(True)
            messages.put(False)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            assert messages.get(timeout=90) is True, ''.join(lines)
            assert process.poll() is None
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=20)
            reader.join(timeout=10)
            (folder / 'seed.log').write_text(''.join(lines))
        assert process.returncode != 0
        result = subprocess.run([str(binary), str(folder), 'recover'], capture_output=True, text=True, timeout=90)
        (folder / 'recover.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0 and 'RECOVERED' in result.stdout, result.stdout + result.stderr
        kills.append({'stage': stage, 'killed_returncode': process.returncode, 'recovered': True})
    link_map = (build / 'sdk-link.map').read_text(errors='replace')
    # Require an actual map entry identifying the selected SQLite archive object.
    if os.name == 'nt':
        providers = [line.strip() for line in link_map.splitlines()
                     if re.search(r'^\s*[0-9a-fA-F]+:[0-9a-fA-F]+\s+sqlite3_open\s+', line)]
        assert len(providers) == 1
        assert re.search(r'(reader_catalog_sqlite|exr_vendor_exr_sqlite)[^\s]*:sqlite3\.', providers[0]), providers
    else:
        build_log = (build.parent / 'desktop-evidence/build.log').read_text(errors='replace')
        providers = re.findall(r'(\S+\.a\([^)]+\)): definition of sqlite3_open\b', build_log)
        assert len(providers) == 1, providers
        assert re.search(r'lib(reader_catalog_sqlite|exr_vendor_exr_sqlite)\.a\(sqlite3\.c\.o\)$', providers[0]), providers
    artifact = {
        'accepted': True, 'scope': 'installed public SDK and product catalog consumer; no desktop UI credit',
        'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'sdk_checks': sdk['checks'],
        'native_checks': native['checks'], 'process_kills': kills,
        'sqlite_source_id': sdk['sqlite_source_id'], 'sqlite_link_map_entries': providers,
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'complete_product': False,
    }
    (build / 'verified.json').write_text(json.dumps(artifact, indent=2) + '\n')
    print(json.dumps(artifact))


if __name__ == '__main__':
    main()
