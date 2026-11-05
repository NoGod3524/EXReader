"""Record actual installed SDK headers/configs, binaries, maps and host options."""
import hashlib
import json
import os
from pathlib import Path
import re
import candidate

ROOT = Path(__file__).resolve().parents[2]
FLAGS = ('SEARCH', 'NAVIGATION', 'RECORDS', 'IMPORT_ORGANIZE', 'PREFERENCES')
FILES = {
    'production': 'ws-host/EXReaderProduct.exe',
    'packaged_production': 'ws-package/EXReader/EXReader.exe',
    'f3_production': 'wprefs-package/EXReader/EXReader.exe',
    'shelf_review': 'ws-host/EXReaderShelfReview.exe',
    'atomic_review': 'ws-host/EXReaderPreferencesCommitReview.exe',
    'old_veto_control': 'ws-host/EXReaderPreferencesCancelControl.exe',
    'baseline': 'baseline-package/EXReader/EXReader.exe',
    'production_map': 'ws-host/windows-host.map',
    'atomic_map': 'ws-host/EXReaderPreferencesCommitReview.map',
    'control_map': 'ws-host/EXReaderPreferencesCancelControl.map',
    'baseline_map': 'baseline-host/windows-host.map',
    'host_cache': 'ws-host/CMakeCache.txt',
    'baseline_cache': 'baseline-host/CMakeCache.txt',
    'sdk_header': 'reading-library/stage/include/exr/base.h',
    'sdk_config': 'reading-library/stage/lib/cmake/EXReader/EXReaderConfig.cmake',
    'sdk_version': 'reading-library/stage/lib/cmake/EXReader/EXReaderConfigVersion.cmake',
    'baseline_header': 'baseline-library/stage/include/exr/base.h',
    'baseline_config': 'baseline-library/stage/lib/cmake/EXReader/EXReaderConfig.cmake',
    'baseline_version': 'baseline-library/stage/lib/cmake/EXReader/EXReaderConfigVersion.cmake',
}
if candidate.active():
    FILES.update(revisions_cache='ws-revisions/CMakeCache.txt', baseline_revisions_cache='baseline-revisions/CMakeCache.txt')


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    files = {}
    for name, relative in FILES.items():
        raw = (ROOT / 'build' / relative).read_bytes()
        assert raw
        files[name] = dict(path=relative, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    cache = (ROOT / 'build' / FILES['host_cache']).read_text(encoding='utf-8')
    assert 'EXR_SDK_VERSION:STRING=3.41.0' in cache
    for flag in FLAGS:
        assert 'EXR_READER_WINDOWS_' + flag + ':BOOL=ON' in cache
    assert 'EXR_READER_PREFS_COMMIT_REVIEW_BUILD:BOOL=ON' in cache
    for name, version in [('sdk_header', '3.41.0'), ('baseline_header', '3.40.0')]:
        header = (ROOT / 'build' / FILES[name]).read_text(encoding='utf-8')
        assert '#define EXR_VERSION "' + version + '"' in header
        assert '#define EXR_ABI_VERSION 1u' in header
    for name, version in [('sdk_version', '3.41.0'), ('baseline_version', '3.40.0')]:
        assert 'set(PACKAGE_VERSION "' + version + '")' in (ROOT / 'build' / FILES[name]).read_text(encoding='utf-8')
    assert len({files[name]['sha256'] for name in ('production', 'shelf_review', 'atomic_review', 'old_veto_control', 'baseline')}) == 5
    assert files['production']['sha256'] == files['packaged_production']['sha256'] == files['f3_production']['sha256']
    raw3 = None
    if candidate.active():
        baseline = (ROOT / 'build' / FILES['baseline_cache']).read_text(encoding='utf-8')
        revisions = (ROOT / 'build' / FILES['revisions_cache']).read_text(encoding='utf-8')
        old_revisions = (ROOT / 'build' / FILES['baseline_revisions_cache']).read_text(encoding='utf-8')
        for contents in (cache, baseline):
            assert 'EXR_READER_WINDOWS_RAW3:BOOL=OFF' in contents
        for contents in (revisions, old_revisions):
            assert 'EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=OFF' in contents
        raw3 = dict(host=False, baseline_host=False, revisions=False, baseline_revisions=False)
    result = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
        sdk_version='3.41.0', sdk_abi=1, sdk_source=candidate.SDK if candidate.active() else 'edddc463c06ed5731195cdb8f06b2df6dff7699e',
        baseline_sdk_version='3.40.0', baseline_source='9854061be331fe603a1822d9b2b36ee357154927',
        full_host_options={flag: True for flag in FLAGS}, files=files, complete_product=False)
    if candidate.active(): result.update(sdk_checkout_source=os.environ['GITHUB_SHA'], raw3=raw3)
    (ROOT / 'build/windows-341-identity.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
