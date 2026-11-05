"""Read the completed diagnostic APK's original same-run evidence only in CI."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import urllib.error
import urllib.parse
import urllib.request
import zipfile

API = 'https://api.github.com/repos/NoGod3524/EXReader'
RUN = 39903068530
SOURCE = 'd78abd7911c3ceb7b723cb4605765e88f0dd6785'
HEADERS = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
           'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'EXReader-debug-bitmap-evidence-audit'}


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
require(run['head_sha'] == SOURCE and run['run_attempt'] == 1 and run['status'] == 'completed' and
        run['conclusion'] in ('success', 'failure'), 'debug execution is not complete or differs')
artifacts = api('/actions/runs/' + str(RUN) + '/artifacts?per_page=100')['artifacts']
matches = [item for item in artifacts if item['name'] == 'EXReader-WP13-Android']
require(len(matches) == 1, 'debug artifact missing or ambiguous')
meta = matches[0]
require(meta['workflow_run']['head_sha'] == SOURCE and meta['workflow_run']['id'] == RUN and not meta['expired'] and
        0 < meta['size_in_bytes'] < 256*1024**2 and meta.get('digest', '').startswith('sha256:'), 'debug artifact identity differs')
try:
    response = urllib.request.build_opener(NoRedirect).open(urllib.request.Request(API + '/actions/artifacts/' + str(meta['id']) + '/zip', headers=HEADERS), timeout=60)
except urllib.error.HTTPError as error:
    require(error.code == 302, 'signed redirect missing')
    location = error.headers.get('Location', '')
    target = urllib.parse.urlparse(location)
    require(target.scheme == 'https' and target.hostname and not target.username and not target.password, 'invalid redirect')
    response = urllib.request.urlopen(location, timeout=60)
with response:
    raw = response.read(meta['size_in_bytes'] + 1)
require(len(raw) == meta['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == meta['digest'], 'debug ZIP digest differs')
archive = zipfile.ZipFile(io.BytesIO(raw))
names = archive.namelist()
require(len(names) == len(set(names)) and sum(i.file_size for i in archive.infolist()) < 1024**3, 'invalid ZIP cardinality/budget')
for name in names:
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe ZIP entry')


def one(suffix):
    matches = [name for name in names if name.endswith(suffix)]
    require(len(matches) == 1, 'missing or ambiguous entry: ' + suffix)
    return json.loads(archive.read(matches[0]))


validations = {suite: one('/evidence/' + folder + '/validation.json') for suite, folder in
               [('walkthrough', 'device'), ('review', 'review'), ('bounded', 'bounded')]}
for validation in validations.values():
    require(validation['source_sha'] == SOURCE and validation['run_id'] == str(RUN) and validation['attempt'] == '1', 'suite identity differs')
case = next(c for c in validations['walkthrough']['cases'] if c['id'] == 'pdf_process_restart')
proofs = {p['role']: p for p in case['frame_observations']}
require('reference' in proofs and 'restored' in proofs, 'restart proof is incomplete')
roles = {}
for role in ('pretransition', 'reference', 'restored'):
    proof = proofs[role]
    roles[role] = {'status': proof['status'], 'elapsed_ms': proof['elapsed_ms'], 'pixel_sha256': proof.get('pixel_sha256'),
                  'final_pair': proof['samples'][-2:]}
ref = roles['reference']['final_pair'][-1]
rest = roles['restored']['final_pair'][-1]
require('bitmap_identity' in ref['observation'] and 'bitmap_identity' in rest['observation'], 'DEBUG bitmap identity absent')
fields = '''book index part path start end anchor_kind anchor_sha256 font zoom render_scale bitmap_width bitmap_height glyph_font_first viewport_width viewport_height fit offset_x offset_y selection_mode selection_start selection_end'''.split()
summary = {'diagnostic_only': True, 'accepted': False, 'debug_run': RUN, 'debug_source': SOURCE, 'attempt': 1,
           'host_conclusion': run['conclusion'], 'artifact_id': meta['id'], 'artifact_bytes': meta['size_in_bytes'],
           'artifact_digest': meta['digest'], 'artifact_expired': meta['expired'], 'artifact_expires': meta['expires_at'],
           'suites': {k: {'summary': v['summary'], 'sequence': v.get('sequence'),
                         'failed': [{f: c.get(f) for f in ('id', 'status', 'detail', 'error')} for c in v['cases'] if c['status'] != 'pass']}
                     for k, v in validations.items()},
           'pdf_restart': {k: case.get(k) for k in ('status', 'detail', 'duration_ms')}, 'roles': roles,
           'frame_fields_diff': {k: [ref['observation'].get(k), rest['observation'].get(k)] for k in fields
                                 if ref['observation'].get(k) != rest['observation'].get(k)},
           'bounds_equal': ref['bounds'] == rest['bounds'],
           'logical_argb_equal': ref['observation']['bitmap_identity']['logical_argb_sha256'] == rest['observation']['bitmap_identity']['logical_argb_sha256'],
           'raw_equal': ref['observation']['bitmap_identity']['raw_sha256'] == rest['observation']['bitmap_identity']['raw_sha256'],
           'screen_pixel_equal': ref['pixel_sha256'] == rest['pixel_sha256'], 'screen_png_equal': ref['png_sha256'] == rest['png_sha256']}
output = Path('build/debug-bitmap-evidence')
output.mkdir(parents=True, exist_ok=True)
(output/'diagnostic.json').write_text(json.dumps(summary, indent=2) + '\n')
print('DEBUG_BITMAP_EVIDENCE ' + json.dumps(summary, separators=(',', ':')))
