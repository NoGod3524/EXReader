#!/usr/bin/env python3
"""Inspect retained mobile failures in Actions without rerunning producers."""
import argparse, hashlib, io, json, os, re, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
PINS = {
    'ipad': (12934491128, 479945377, 'cc696e4d3060c7e2a2c6cf2f55e283bd5e7323ff082cfe949e39d1fb37e6d90a')}
def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    p = argparse.ArgumentParser(); p.add_argument('--platform', choices=PINS, required=True); args = p.parse_args()
    aid, size, sha = PINS[args.platform]
    out = ROOT / 'build/mobile-failure-inspection' / args.platform; out.mkdir(parents=True)
    meta = fetch('actions/artifacts/' + str(aid))
    assert meta['workflow_run']['id'] == 40946665738 and meta['workflow_run']['head_sha'] == 'fc336333cd67bf8871e2602777ec857312de06cb'
    assert meta['size_in_bytes'] == size and meta['digest'] == 'sha256:' + sha and not meta['expired']
    raw = download_artifact_zip(aid)
    assert len(raw) == size and hashlib.sha256(raw).hexdigest() == sha
    bundle = out / 'raw'
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\\\' not in n for n in names)
        result = json.loads(archive.read('result.json'))
        assert (result['source_sha'], result['run_id'], result['attempt'], result['platform'], result['accepted']) == ('fc336333cd67bf8871e2602777ec857312de06cb', '40946665738', '1', args.platform, False)
        log = archive.read('wave3-native-ui.log')
        expected = result['files']['wave3-native-ui.log']
        assert len(log) == expected['bytes'] and hashlib.sha256(log).hexdigest() == expected['sha256']
        (out / 'wave3-native-ui.log').write_bytes(log)
        for n in names:
            if sys.platform == 'darwin' and n.startswith('wave3.xcresult/'):
                data = archive.read(n)
                expected = result['files'].get(n)
                if not n.endswith('/'):
                    assert expected and len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256']
                    dest = bundle / n; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
    lines = log.decode('utf-8', 'replace').splitlines()
    indexes = [i for i, line in enumerate(lines) if re.search(r'error:|XCTAssert|failed|Failure|Picker cannot|Test Case', line, re.I)]
    snippets = [dict(line=i+1, context=lines[max(0,i-4):min(len(lines),i+12)]) for i in indexes]
    picker = [i for i, line in enumerate(lines) if re.search(r'Picker cannot|XCTAssert|error:', line)]
    blocks = ['\n'.join(lines[max(0,i-10):min(len(lines),i+700)]) for i in picker]
    start = next(i for i, line in enumerate(lines) if 'testNativeAnnotationPreviewConfirmCancelAndDuplicate' in line and 'started.' in line)
    end = next(i for i in range(start + 1, len(lines)) if "testNativeHistoryAfterFoundAndLargeRotationExit" in lines[i] and 'started.' in lines[i])
    blocks.append('\n'.join(lines[start:end]))
    (out / 'failure-context.txt').write_text('\n\n'.join(blocks))
    print('FAILURE CONTEXT\n' + '\n\n'.join(blocks)[-150000:], flush=True)
    report = dict(artifact_id=aid, artifact_bytes=size, artifact_sha256=sha, source=result['source_sha'], platform=args.platform,
                  inspection_source=os.environ['GITHUB_SHA'], phases=result['phases'], matches=snippets, inspected=True, accepted=False)
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print('RETAINED RESULT\n' + json.dumps(report), flush=True)
if __name__ == '__main__': main()
