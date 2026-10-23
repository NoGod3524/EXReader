"""CI-only review of retained iPhone import screenshots, snapshots and video."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from PIL import Image, ImageDraw

API = 'https://api.github.com/repos/NoGod3524/EXReader'
RUN = 39899825998
SOURCE = 'da1c1833d89932612d8e4549fee5aec378555ad4'
ARTIFACT = 12478729543
SIZE = 141911749
DIGEST = 'sha256:df06a4d70c139e1b2f1b3148b9a25c6215da844e640cf2800445d4e84d92aa8a'
HEADERS = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
           'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'EXReader-original-import-diagnostic'}


def require(value, message):
    if not value:
        raise ValueError(message)


def api(path):
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=HEADERS), timeout=60) as response:
        return json.load(response)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, stream, code, message, headers, url):
        return None


run = api('/actions/runs/' + str(RUN))
require(run['head_sha'] == SOURCE and run['run_attempt'] == 1 and run['conclusion'] == 'failure', 'original failure identity differs')
metadata = api('/actions/artifacts/' + str(ARTIFACT))
require(metadata['workflow_run']['id'] == RUN and metadata['workflow_run']['head_sha'] == SOURCE and
        not metadata['expired'] and metadata['size_in_bytes'] == SIZE and metadata['digest'] == DIGEST, 'original artifact differs')
try:
    response = urllib.request.build_opener(NoRedirect).open(urllib.request.Request(API + '/actions/artifacts/' + str(ARTIFACT) + '/zip', headers=HEADERS), timeout=60)
except urllib.error.HTTPError as error:
    require(error.code == 302, 'signed redirect missing')
    location = error.headers.get('Location', '')
    target = urllib.parse.urlparse(location)
    require(target.scheme == 'https' and target.hostname and not target.username and not target.password, 'invalid signed redirect')
    response = urllib.request.urlopen(location, timeout=60)
with response:
    raw = response.read(SIZE + 1)
require(len(raw) == SIZE and 'sha256:' + hashlib.sha256(raw).hexdigest() == DIGEST, 'original ZIP differs')
archive = zipfile.ZipFile(io.BytesIO(raw))
names = archive.namelist()
require(len(names) == len(set(names)) and sum(item.file_size for item in archive.infolist()) < 1024**3, 'invalid ZIP entries')
for name in names:
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe ZIP entry')
manifest_path = next(name for name in names if name.endswith('evidence/iphone/attachments/manifest.json'))
prefix = manifest_path[:-len('manifest.json')]
manifest = json.loads(archive.read(manifest_path))
output = Path('build/apple-original-failure')
output.mkdir(parents=True, exist_ok=True)
report = {'diagnostic_only': True, 'accepted': False, 'source': SOURCE, 'run': RUN, 'artifact': ARTIFACT, 'attachments': []}
pictures = []


def scalars(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (str, int, float, bool)):
                yield str(k), str(v)
            else:
                yield from scalars(v)
    elif isinstance(value, list):
        for v in value:
            yield from scalars(v)


for group in manifest:
    owner = str(group.get('testIdentifier') or group.get('testName', ''))
    if 'test01ImportDeduplicateAndErrors' not in owner:
        continue
    for item in group.get('attachments', []):
        filename = item.get('exportedFileName', '')
        require(PurePosixPath(filename).name == filename, 'attachment path escapes')
        path = prefix + filename
        if path not in names:
            continue
        label = item.get('suggestedHumanReadableName', '')
        payload = archive.read(path)
        entry = {'label': label, 'file': filename, 'bytes': len(payload), 'type': item.get('uniformTypeIdentifier')}
        report['attachments'].append(entry)
        if payload.startswith(b'\x89PNG') and len(pictures) < 7:
            image = Image.open(io.BytesIO(payload)).convert('RGB')
            pictures.append((label[:60], image))
            image.save(output/(str(len(pictures)) + '.png'))
        elif filename.endswith(('.txt', '.json')) and len(payload) < 8*1024**2:
            text = payload.decode('utf-8', errors='replace')
            entry['relevant_lines'] = [line[:1200] for line in text.splitlines() if re.search(r'library\.|import|token|scene|status|failed|hittable|frame|Button', line, re.I)][:70]
        elif payload.startswith(b'bplist00') and 'snapshot' in label.lower():
            value = plistlib.loads(payload)
            objects = value.get('$objects', [])
            def resolve(node, depth=0, seen=frozenset()):
                if depth > 15:
                    return '<depth-bound>'
                if isinstance(node, plistlib.UID):
                    if node.data >= len(objects) or node.data in seen:
                        return '<reference>'
                    return resolve(objects[node.data], depth+1, seen | {node.data})
                if isinstance(node, dict):
                    return {str(k): resolve(v, depth+1, seen) for k, v in node.items()}
                if isinstance(node, list):
                    return [resolve(v, depth+1, seen) for v in node[:1000]]
                return '<bytes>' if isinstance(node, bytes) else node
            decoded = resolve(value)
            (output/(filename + '.json')).write_text(json.dumps(decoded, indent=2, default=str))
            entry['matching_snapshot_scalars'] = [[k, v[:1200]] for k, v in scalars(decoded) if re.search(r'library\.|import|就绪|导入|frame|hittable|enabled', k+' '+v, re.I)][:90]
        elif filename.endswith('.mp4') and 'Screen Recording' in label:
            video = output/'original.mp4'
            video.write_bytes(payload)
            swift = output/'frames.swift'
            swift.write_text('''import Foundation
import AVFoundation
import ImageIO
let asset = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.requestedTimeToleranceBefore = .zero
generator.requestedTimeToleranceAfter = .zero
let duration = CMTimeGetSeconds(asset.duration)
print("video duration=\\(duration)")
for second in [0.0, 4, 8, 12, 16, 24, max(0, duration-5)] {
  let image = try generator.copyCGImage(at: CMTime(seconds: second, preferredTimescale: 600), actualTime: nil)
  let url = URL(fileURLWithPath: CommandLine.arguments[2]+"/video-\\(Int(second)).png")
  let dst = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil)!
  CGImageDestinationAddImage(dst, image, nil)
  CGImageDestinationFinalize(dst)
}
''')
            proc = subprocess.run(['swift', str(swift), str(video), str(output)], capture_output=True, text=True, timeout=120)
            entry['video_export'] = {'returncode': proc.returncode, 'stdout': proc.stdout[-2000:], 'stderr': proc.stderr[-1500:]}
            for frame in sorted(output.glob('video-*.png')):
                pictures.append((frame.stem, Image.open(frame).convert('RGB')))

(output/'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
print('APPLE_ORIGINAL_IMPORT_DIAGNOSTIC ' + json.dumps(report, separators=(',', ':')))
for offset in range(0, len(pictures), 5):
    batch = pictures[offset:offset+5]
    sheet = Image.new('RGB', (300*len(batch), 580), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, (label, picture) in enumerate(batch):
        image = picture.copy()
        image.thumbnail((290, 550))
        sheet.paste(image, (i*300, 25))
        draw.text((i*300+2, 3), label[:43], fill='black')
    name = output/('contact-' + str(offset) + '.png')
    sheet.save(name)
    print('APPLE_CONTACT_PNG_BASE64 ' + base64.b64encode(name.read_bytes()).decode())
