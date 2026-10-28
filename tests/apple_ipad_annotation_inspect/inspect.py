#!/usr/bin/env python3
"""Read one existing failed XCTest log, entirely within Actions."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = ROOT / 'build/apple-ipad-annotation-inspection'; out.mkdir(parents=True, exist_ok=True)
    report = {'inspection_source': os.environ['GITHUB_SHA'], 'inspection_run': os.environ['GITHUB_RUN_ID'],
              'inspection_attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'original_run': 40653266726,
              'original_attempt': 1, 'original_source': 'd364d71e3ee6e38de0e3084015bf0896c62a71f6',
              'original_artifact': 12806868805, 'accepted': False, 'failure': None}
    try:
        meta = fetch('actions/artifacts/12806868805')
        assert meta['name'] == 'team24-apple-native-ipad-40653266726-1' and not meta['expired']
        assert meta['workflow_run']['id'] == 40653266726 and meta['workflow_run']['head_sha'] == report['original_source']
        raw = download_artifact_zip(meta['id']); digest = hashlib.sha256(raw).hexdigest()
        assert len(raw) == meta['size_in_bytes'] and meta['digest'] == 'sha256:' + digest
        assert digest == 'f6b67ece7985544048013ce9a8c3bb2acd82a03235f1719482313928eb8b3b6e'
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names))
            assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
            result = json.loads(archive.read('result.json'))
            assert (result['source_sha'], result['run_id'], result['attempt'], result['platform'], result['accepted']) == (report['original_source'], '40653266726', '1', 'ipad', False)
            log = archive.read('wave3-native-ui.log')
            expected = result['files']['wave3-native-ui.log']
            assert len(log) == expected['bytes'] and hashlib.sha256(log).hexdigest() == expected['sha256']
            (out / 'wave3-native-ui.log').write_bytes(log)
            lines = log.decode('utf-8', errors='replace').splitlines()
            matches = [i for i, line in enumerate(lines) if re.search(r'error:|XCTAssert|failed|Failure|Assertion|Picker cannot', line, re.I)]
            snippets = []
            for i in matches[:80]:
                snippets.append({'line': i + 1, 'context': [line[:4000] for line in lines[max(0, i-3):min(len(lines), i+4)]]})
            picker = next((i for i, line in enumerate(lines) if 'Picker cannot find EXReader-invalid.jsonl' in line), None)
            assert picker is not None, 'Expected original picker failure not present'
            hierarchy = lines[picker:min(len(lines), picker + 1000)]
            (out / 'picker-hierarchy.txt').write_text('\n'.join(hierarchy) + '\n')
            picker_elements = [line[:3000] for line in hierarchy if re.search(r'DOC\.|EXReader|jsonl|NavigationBar|CollectionView|No Items|empty|No Content|Browse View', line, re.I)]
            report.update(original_zip_sha256=digest, log_sha256=hashlib.sha256(log).hexdigest(),
                          match_count=len(matches), matches=snippets, picker_elements=picker_elements,
                          xcresult_present=any(n.startswith('wave3.xcresult/') for n in names), accepted=True)
    except Exception as error:
        report['failure'] = str(error)
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    assert report['accepted'], 'Existing artifact inspection failed'

if __name__ == '__main__': main()
