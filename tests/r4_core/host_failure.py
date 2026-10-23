"""CI-only byte/state/pixel comparison of the retained failing original run."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from PIL import Image, ImageChops, ImageDraw

API = 'https://api.github.com/repos/NoGod3524/EXReader'
RUN = 39899828858
SOURCE = 'da1c1833d89932612d8e4549fee5aec378555ad4'
ARTIFACT = 12478623224
SIZE = 156992804
DIGEST = 'sha256:7973d2aa1c32e9043f1f1f5b64e7c045762c4aa053ee008f4e0dbb2f0e7c80da'
HEADERS = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
           'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'EXReader-original-frame-diagnostic'}


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
request = urllib.request.Request(API + '/actions/artifacts/' + str(ARTIFACT) + '/zip', headers=HEADERS)
try:
    response = urllib.request.build_opener(NoRedirect).open(request, timeout=60)
except urllib.error.HTTPError as error:
    require(error.code == 302, 'signed artifact redirect missing')
    location = error.headers.get('Location', '')
    target = urllib.parse.urlparse(location)
    require(target.scheme == 'https' and target.hostname and not target.username and not target.password, 'invalid signed redirect')
    response = urllib.request.urlopen(location, timeout=60)
with response:
    raw = response.read(SIZE + 1)
require(len(raw) == SIZE and 'sha256:' + hashlib.sha256(raw).hexdigest() == DIGEST, 'downloaded original ZIP differs')
archive = zipfile.ZipFile(io.BytesIO(raw))
names = archive.namelist()
require(len(names) == len(set(names)) and sum(item.file_size for item in archive.infolist()) < 1024**3, 'invalid ZIP entries')
for name in names:
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe ZIP entry')


def one(suffix):
    found = [name for name in names if name.endswith(suffix)]
    require(len(found) == 1, 'ambiguous or missing entry: ' + suffix)
    return found[0], archive.read(found[0])


validation_path, payload = one('/evidence/device/validation.json')
validation = json.loads(payload)
require(validation['source_sha'] == SOURCE and validation['run_id'] == str(RUN) and validation['attempt'] == '1', 'validation identity mismatch')
case = next(c for c in validation['cases'] if c['id'] == 'pdf_process_restart')
require(case['status'] == 'fail', 'expected failure missing')
root = validation_path.rsplit('/', 1)[0] + '/'
output = Path('build/host-failure')
output.mkdir(parents=True, exist_ok=True)
roles = {}
proofs = case['frame_observations']
for proof in proofs:
    if not proof['samples']:
        continue
    last = proof['samples'][-1]
    path = root + last['png']
    png = archive.read(path)
    require(len(png) == last['png_bytes'] and hashlib.sha256(png).hexdigest() == last['png_sha256'], 'sample PNG identity differs')
    image = Image.open(io.BytesIO(png)).convert('RGB')
    image.save(output/(proof['role'] + '.png'))
    roles[proof['role']] = (proof, last, image)


def compare(left, right):
    if left.size != right.size:
        return {'left_size': left.size, 'right_size': right.size, 'same_size': False}
    diff = ImageChops.difference(left, right)
    changed = [i for i, value in enumerate(diff.getdata()) if value != (0, 0, 0)]
    return {'same_size': True, 'changed_pixels': len(changed), 'total_pixels': left.width*left.height,
            'bbox': diff.getbbox(), 'rows': sorted({i//left.width for i in changed}),
            'columns': sorted({i % left.width for i in changed})}


reference = roles['reference'][1]
restored = roles['restored'][1]
fields = '''book index part path start end anchor_kind anchor_sha256 font zoom render_scale bitmap_width bitmap_height glyph_font_first viewport_width viewport_height fit offset_x offset_y selection_mode selection_start selection_end'''.split()
state_diff = {k: [reference['observation'].get(k), restored['observation'].get(k)] for k in fields
              if reference['observation'].get(k) != restored['observation'].get(k)}
report = {'diagnostic_only': True, 'accepted': False, 'original_run': RUN, 'original_source': SOURCE,
          'artifact_id': ARTIFACT, 'artifact_digest': DIGEST, 'failure': {k: case.get(k) for k in ('id', 'status', 'detail')},
          'frame_fields_diff': state_diff, 'bounds': [reference['bounds'], restored['bounds']],
          'proofs': proofs, 'pixel_comparisons': {}, 'previous_pdf_comparisons': {}}
for a, b in [('pretransition', 'reference'), ('reference', 'restored'), ('pretransition', 'restored')]:
    report['pixel_comparisons'][a + '_vs_' + b] = compare(roles[a][2], roles[b][2])
for earlier in validation['cases']:
    if not earlier['id'].startswith(('pdf_', 'open_pdf')):
        continue
    for index, proof in enumerate(earlier.get('frame_observations', [])):
        if not proof.get('samples'):
            continue
        sample = proof['samples'][-1]
        image = Image.open(io.BytesIO(archive.read(root + sample['png']))).convert('RGB')
        for role in ('reference', 'restored'):
            result = compare(roles[role][2], image)
            result.pop('rows', None)
            result.pop('columns', None)
            report['previous_pdf_comparisons'][earlier['id'] + ':' + str(index) + ':' + proof['role'] + ':' + role] = result
diff = ImageChops.difference(roles['reference'][2], roles['restored'][2])
diff.save(output/'reference-restored-diff.png')
panels = [(key, roles[key][2]) for key in ('pretransition', 'reference', 'restored')] + [('difference x8', diff.point(lambda p: min(255, p*8)))]
sheet = Image.new('RGB', (360*len(panels), 580), 'white')
draw = ImageDraw.Draw(sheet)
for i, (name, picture) in enumerate(panels):
    picture = picture.copy()
    picture.thumbnail((350, 550))
    sheet.paste(picture, (i*360, 25))
    draw.text((i*360+4, 5), name, fill='black')
sheet.save(output/'contact.png')
(output/'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
compact = dict(report)
compact['pixel_comparisons'] = {k: {a: b for a, b in v.items() if a not in ('rows', 'columns')} for k, v in report['pixel_comparisons'].items()}
print('ORIGINAL_FRAME_DIAGNOSTIC ' + json.dumps(compact, separators=(',', ':')))
print('CONTACT_PNG_BASE64 ' + base64.b64encode((output/'contact.png').read_bytes()).decode())
