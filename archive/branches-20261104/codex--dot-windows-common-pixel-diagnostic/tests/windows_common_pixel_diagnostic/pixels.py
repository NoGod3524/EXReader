"""Actions-only read-only diagnosis of an authenticated failed F3 capture."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip, require

assert os.environ.get('GITHUB_ACTIONS') == 'true'
SOURCE = 'e330a415b733db18dea5aa6010d13cf3063587fd'
ARTIFACT = 12795210910
DIGEST = 'e7d1c566f1c1e5379d2a05f52009d76ef506528bdfb083a8c9ff066f0d29c7e2'
out = ROOT / 'build/windows-f3-pixel-diagnostic'; out.mkdir(parents=True)
report = dict(diagnostic_source_sha=os.environ['GITHUB_SHA'], diagnostic_run_id=os.environ['GITHUB_RUN_ID'],
              diagnostic_attempt=os.environ['GITHUB_RUN_ATTEMPT'], original_source_sha=SOURCE,
              original_run_id=40638398225, original_attempt=1, artifact_id=ARTIFACT,
              diagnostic_complete=False, original_F3_accepted=False, problems=[])
try:
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == os.environ['GITHUB_SHA'], 'Checkout differs')
    require(not subprocess.check_output(['git', 'diff', '--name-only', SOURCE, 'HEAD', '--', 'apps', 'src', 'include', 'tests/reader_windows_preferences']), 'Source/judge modified')
    meta = fetch('actions/artifacts/' + str(ARTIFACT))
    require(meta['workflow_run']['head_sha'] == SOURCE and meta['workflow_run']['id'] == 40638398225 and not meta['expired'], 'Foreign artifact')
    require(meta['name'] == 'reader-windows-search-initial-40638398225-1' and meta['digest'] == 'sha256:' + DIGEST, 'Artifact identity differs')
    with tempfile.TemporaryFile() as stream:
        download_artifact_zip(ARTIFACT, stream); stream.seek(0); raw = stream.read()
    require(len(raw) == meta['size_in_bytes'] and hashlib.sha256(raw).hexdigest() == DIGEST, 'Artifact bytes differ')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), 'Duplicate member')
        failed = json.loads(archive.read('wprefs-ui/preferences-ui.json'))
        require(failed['source_sha'] == SOURCE and str(failed['run_id']) == '40638398225' and str(failed['attempt']) == '1' and failed['accepted'] is False, 'Failure report differs')
        bmp = archive.read('wprefs-ui/captures/light.bmp')
        header = struct.unpack_from('<IiiHHIIiiII', bmp, 14)
        width, height = header[1], header[2]
        require(bmp[:2] == b'BM' and header[0] == 40 and header[3:6] == (1,32,0) and width > 0 and height > 0, 'Unexpected original BMP format')
        offset = struct.unpack_from('<I', bmp, 10)[0]
        body = bmp[offset:]
        require(len(body) == width * height * 4, 'Truncated BMP')
        image = (width, height, b''.join(body[y*width*4:(y+1)*width*4] for y in reversed(range(height))))
    # Compile only the unchanged pure sampling helpers, directly from old judge.
    judge = ROOT / 'tests/reader_windows_preferences/check_ui.py'
    syntax = ast.parse(judge.read_text(encoding='utf-8'))
    helpers = [node for node in syntax.body if isinstance(node, ast.FunctionDef) and node.name in ('at','near','layout')]
    require(len(helpers) == 3, 'Original helpers changed')
    namespace = {}; exec(compile(ast.Module(body=helpers, type_ignores=[]), str(judge), 'exec'), namespace)
    at, near, layout = (namespace[name] for name in ('at','near','layout'))
    dx, dy, page_width, page_height = layout((width,height), (720,1040))
    corner = at(image, dx+6, dy+6)
    surround = at(image, max(dx-4,1), max(dy-4,1))
    ink = [at(image,x,y) for x in range(dx+40,dx+page_width-40,7) for y in range(dy+40,dy+min(page_height,500)-10,5)]
    ink = [pixel for pixel in ink if not near(pixel,corner,16)]
    conditions = dict(corner_white=near(corner,(255,255,255),2), surround_white=near(surround,(255,255,255),2),
                      ink_present=bool(ink), ink_dark_enough=bool(ink) and min(sum(p) for p in ink)<260)
    required = next(ast.literal_eval(node.value) for node in syntax.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REQUIRED' for t in node.targets))
    report.update(diagnostic_complete=True, bmp_sha256=hashlib.sha256(bmp).hexdigest(), client=[width,height],
        sampled_layout=[dx,dy,page_width,page_height], corner=corner, surround=surround, ink_count=len(ink),
        minimum_ink_rgb_sum=min(map(sum,ink)) if ink else None, darkest_ink=min(ink,key=sum) if ink else None,
        predicates=conditions, exact_original_predicate_result=all(conditions.values()),
        original_passed=failed['checks'], failed_check=required[len(failed['checks'])], not_executed=required[len(failed['checks'])+1:],
        original_judge_sha256=hashlib.sha256(judge.read_bytes()).hexdigest(), source_or_assertion_changed=False)
except Exception as error:
    report['problems'].append(repr(error))
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
require(report['diagnostic_complete'], 'Diagnostic incomplete')
