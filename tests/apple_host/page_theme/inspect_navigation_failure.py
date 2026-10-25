# SPDX-License-Identifier: MIT
"""Inspect the actual preserved navigation import failure in Actions only."""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch

SOURCE = 'f4aa876c4e077201ade122c6a558a90731327daa'
RUN, JOB, ARTIFACT = 40174363253, 121113533530, 12591639142
SIZE = 114518763
DIGEST = 'sha256:13b6281deef8460d852e28e27457753ddfc7029444b26a7ecfb0a4169efcdc02'
TARGET = 'testAuthorCfiEntryUsesReaderLabel'
OUT = Path('build/apple-theme-diagnostic')


def require(value, message):
    if not value:
        raise ValueError(message)


def nested(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested(child)


def snapshot(payload):
    value = plistlib.loads(payload)
    objects = value.get('$objects', []) if isinstance(value, dict) else []

    def resolve(item, depth=0, seen=frozenset()):
        if depth > 14:
            return '<depth-bound>'
        if isinstance(item, plistlib.UID):
            if item.data in seen or item.data >= len(objects):
                return '<object-reference>'
            return resolve(objects[item.data], depth + 1, seen | {item.data})
        if isinstance(item, dict):
            return {str(key): resolve(child, depth + 1, seen) for key, child in item.items()}
        if isinstance(item, list):
            return [resolve(child, depth + 1, seen) for child in item[:2000]]
        if isinstance(item, bytes):
            return '<binary:%d>' % len(item)
        return item

    decoded = resolve(value)
    rows = []
    for node in nested(decoded):
        fields = {key: child for key, child in node.items() if isinstance(child, (str, int, float, bool))}
        if any(re.search(r'library\.|uiTest|导入|取消|失败|书架|初始化|token=', str(child)) for child in fields.values()):
            rows.append({key: str(child)[:1800] for key, child in fields.items()})
    return rows[:120]


def media(path):
    script = OUT / 'read-preserved-pixels.swift'
    script.write_text('''import Foundation
import Vision
import ImageIO
import AVFoundation
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let image: CGImage
if url.pathExtension == "mp4" {
    let asset = AVURLAsset(url: url)
    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    let second = max(0, CMTimeGetSeconds(asset.duration) - 4)
    image = try generator.copyCGImage(at: CMTime(seconds: second, preferredTimescale: 600), actualTime: nil)
} else {
    image = CGImageSourceCreateImageAtIndex(CGImageSourceCreateWithURL(url as CFURL, nil)!, 0, nil)!
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
try VNImageRequestHandler(cgImage: image).perform([request])
let words = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
let data = try JSONSerialization.data(withJSONObject: ["width": image.width, "height": image.height, "ocr": words], options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
''')
    result = subprocess.run(['swift', str(script), str(path)], capture_output=True, text=True, timeout=120)
    return json.loads(result.stdout) if result.returncode == 0 else {'ocr_error': result.stderr[-2000:]}


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'Actions repository differs')
    OUT.mkdir(parents=True, exist_ok=True)
    run = fetch('actions/runs/' + str(RUN) + '/attempts/1')
    job = fetch('actions/jobs/' + str(JOB))
    require(run['head_sha'] == SOURCE and run['run_attempt'] == 1 and job['run_id'] == RUN and
            job['head_sha'] == SOURCE and job['conclusion'] == 'failure' and job['name'] == 'Navigation UI ipad', 'failed producer identity differs')
    artifact = fetch('actions/artifacts/' + str(ARTIFACT))
    require(artifact['id'] == ARTIFACT and artifact['name'] == 'apple-navigation-ui-ipad-' + str(RUN) + '-1' and
            artifact['workflow_run']['head_sha'] == SOURCE and artifact['workflow_run']['id'] == RUN and not artifact['expired'] and
            artifact['size_in_bytes'] == SIZE and artifact['digest'] == DIGEST and
            datetime.datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.datetime.now(datetime.timezone.utc), 'retained artifact identity differs')
    raw = download_artifact_zip(ARTIFACT)
    require(len(raw) == SIZE and 'sha256:' + hashlib.sha256(raw).hexdigest() == DIGEST, 'original ZIP differs')
    report = {'accepted': False, 'diagnostic_only': True, 'target_source': SOURCE, 'target_run': RUN, 'target_attempt': 1,
              'target_job': JOB, 'artifact': {key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
              'observations': [], 'exports': []}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and sum(row.file_size for row in archive.infolist()) <= 1024**3, 'invalid/big ZIP')
        for name in names:
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe ZIP path')
        entries = [name for name in names if name.startswith('ipad.xcresult/') and not name.endswith('/')]
        require(entries, 'retained raw xcresult missing')
        for name in entries:
            path = OUT / 'retained' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name))
        bundle = OUT / 'retained/ipad.xcresult'
        for section in ('summary', 'tests'):
            result = subprocess.run(['xcrun', 'xcresulttool', 'get', 'test-results', section, '--path', str(bundle), '--format', 'json'],
                                    capture_output=True, text=True, timeout=90)
            require(result.returncode == 0, 'xcresult export failed: ' + result.stderr)
            payload = json.loads(result.stdout)
            (OUT / (section + '.json')).write_text(json.dumps(payload, indent=2, sort_keys=True))
            report['exports'].append(section)
            if section == 'summary':
                report['failures'] = [{key: row[key] for key in ('testName', 'message', 'issueType', 'fileName', 'lineNumber') if key in row}
                                      for row in nested(payload) if 'message' in row]
        attachments = OUT / 'attachments'
        subprocess.run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(bundle), '--output-path', str(attachments)], check=True, timeout=120)
        manifest = json.loads((attachments / 'manifest.json').read_text())
        for group in manifest:
            if TARGET not in str(group.get('testIdentifier') or group.get('testName', '')):
                continue
            for item in group['attachments']:
                filename = item['exportedFileName']; require(Path(filename).name == filename, 'unsafe exported attachment')
                path = attachments / filename
                size = path.stat().st_size
                row = {'name': item['suggestedHumanReadableName'], 'file': filename, 'bytes': size}
                if size <= 8 * 1024**2:
                    data = path.read_bytes()
                    if data.startswith((b'bplist00', b'<?xml')):
                        row['snapshot_fields'] = snapshot(data)
                    elif data.startswith(b'\x89PNG'):
                        row['actual_preserved_pixel_ocr'] = media(path)
                    elif path.suffix in ('.json', '.txt') and b'\x00' not in data[:200]:
                        row['text'] = data.decode('utf-8', errors='replace')[:16000]
                elif path.suffix == '.mp4' and size <= 40 * 1024**2:
                    row['actual_preserved_last_frame_ocr'] = media(path)
                report['observations'].append(row)
    (OUT / 'diagnostic.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
