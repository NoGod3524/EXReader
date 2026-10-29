#!/usr/bin/env python3
"""Inspect retained mobile failures in Actions without rerunning producers."""
import argparse, hashlib, io, json, os, re, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
PINS = {
    'iphone': (12928097306, 436248547, 'b7f3125fb508ecc417e59ca083f7ba89aa9e5308971c2aa483a1aab30adad7bb'),
    'ipad': (12928855897, 485229238, '6f576fe25c63e1ce2571c6672430d809da32eb269332143a9b24bcc483f86d02')}
def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    p = argparse.ArgumentParser(); p.add_argument('--platform', choices=PINS, required=True); args = p.parse_args()
    aid, size, sha = PINS[args.platform]
    out = ROOT / 'build/mobile-failure-inspection' / args.platform; out.mkdir(parents=True)
    meta = fetch('actions/artifacts/' + str(aid))
    assert meta['workflow_run']['id'] == 40935165396 and meta['workflow_run']['head_sha'] == '55ec49020383ef5073f47502b300ab0b5d0a7cae'
    assert meta['size_in_bytes'] == size and meta['digest'] == 'sha256:' + sha and not meta['expired']
    raw = download_artifact_zip(aid)
    assert len(raw) == size and hashlib.sha256(raw).hexdigest() == sha
    bundle = out / 'raw'
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\\\' not in n for n in names)
        result = json.loads(archive.read('result.json'))
        assert (result['source_sha'], result['run_id'], result['attempt'], result['platform'], result['accepted']) == ('55ec49020383ef5073f47502b300ab0b5d0a7cae', '40935165396', '1', args.platform, False)
        log = archive.read('wave3-native-ui.log')
        expected = result['files']['wave3-native-ui.log']
        assert len(log) == expected['bytes'] and hashlib.sha256(log).hexdigest() == expected['sha256']
        (out / 'wave3-native-ui.log').write_bytes(log)
        for n in names:
            if n.startswith('wave3.xcresult/'):
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
    (out / 'failure-context.txt').write_text('\n\n'.join(blocks))
    print('FAILURE CONTEXT\n' + '\n\n'.join(blocks)[-150000:], flush=True)
    xcresult = bundle / 'wave3.xcresult'
    tests = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'tests', '--path', str(xcresult), '--format', 'json'], text=True)
    (out / 'tests.json').write_text(tests)
    print('RAW XCRESULT TESTS\n' + tests, flush=True)
    attachments = out / 'attachments'
    subprocess.run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(xcresult), '--output-path', str(attachments)], check=True)
    report = dict(artifact_id=aid, artifact_bytes=size, artifact_sha256=sha, source=result['source_sha'], platform=args.platform,
                  inspection_source=os.environ['GITHUB_SHA'], phases=result['phases'], matches=snippets, inspected=True, accepted=False)
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print('RETAINED RESULT\n' + json.dumps(report), flush=True)
if __name__ == '__main__': main()
