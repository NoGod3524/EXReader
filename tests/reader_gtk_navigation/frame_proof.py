"""Actions-only exact draw observation pin and independent native pixel proof."""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE = '07ebe8786434ef384c97ccdb451242d3c6aee6cb'
OBSERVATION = '8325f9e1f80ef12193bee0b9eca4d4bac8c4c3be'
OLD_RUN = 40177143143
WORKFLOW = '.github/workflows/reader-gtk-navigation-frame-proof.yml'
JOB = 'Actual GTK new sensitive draw and unchanged 29 navigation conditions'
OUT = ROOT / 'build/frame-proof'
sys.path.insert(0, str(ROOT / 'tests/reader_hosts_integration'))
from final import Bundle, fetch, identity, pages, require


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def source(path, revision=BASE):
    return subprocess.check_output(['git', 'show', revision + ':' + path], text=True)


def records(text):
    return [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Call) and
            isinstance(node.func, ast.Name) and node.func.id == 'record']


def names():
    calls = records(source('tests/reader_gtk_navigation/check_ui.py'))
    result = [call.args[0].value for call in calls]
    require(len(result) == len(set(result)) == 29, 'original navigation names differ')
    return result


def guard(write=True):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    sha = os.environ['GITHUB_SHA'];require(git('rev-parse', 'HEAD') == sha, 'checkout differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, sha], check=True)
    reader = 'examples/linux/reader.c'
    require(git('rev-parse', sha + ':' + reader) == git('rev-parse', OBSERVATION + ':' + reader),
            'reader.c is not the exact reviewed observation blob')
    allowed = ('tests/reader_gtk_navigation/', 'tests/reader_hosts_integration/probe_navigation.py',
               WORKFLOW, 'docs/READER-GTK-NAVIGATION-FRAME-PROOF.md',
               'docs/validation/reader-gtk-navigation-frame-proof.json', reader)
    changed = git('diff', '--name-only', BASE, sha).splitlines()
    require(all(any(path.startswith(item) if item.endswith('/') else path == item for item in allowed)
                for path in changed), 'foreign production or test paths changed')
    for path in ('tests/reader_gtk_navigation/backend.c', 'tests/reader_gtk_navigation/make_inputs.py'):
        require(git('rev-parse', sha + ':' + path) == git('rev-parse', BASE + ':' + path), 'original backend/fixtures changed')
    original = ast.parse(source('tests/reader_gtk_navigation/check_ui.py'))
    current = ast.parse((ROOT / 'tests/reader_gtk_navigation/check_ui.py').read_text())
    require([ast.dump(call) for call in records(source('tests/reader_gtk_navigation/check_ui.py'))] ==
            [ast.dump(call) for call in records((ROOT / 'tests/reader_gtk_navigation/check_ui.py').read_text())],
            'any original 29 conditions or observations changed')
    for name in ('frame', 'storage'):
        old = next(node for node in ast.walk(original) if isinstance(node, ast.FunctionDef) and node.name == name)
        new = next(node for node in ast.walk(current) if isinstance(node, ast.FunctionDef) and node.name == name)
        require(ast.dump(old) == ast.dump(new), 'original selector/storage identity helper changed')
    def sleeps(tree):
        return [ast.dump(node) for node in ast.walk(tree) if isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and node.func.attr == 'sleep']
    require(sleeps(original) == sleeps(current), 'new fixed sleep added')
    report = dict(source_sha=sha, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  accepted=True, base=BASE, observation_commit=OBSERVATION,
                  reader_blob=git('rev-parse', sha + ':' + reader), changed=changed,
                  original_navigation_conditions_preserved=29, new_fixed_sleeps=0,
                  sdk_unchanged=True, other_production_unchanged=True)
    if write:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'source-guard.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)
    return report


def run(command):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / ('command-%03d.log' % len(list(OUT.glob('command-*.log'))))
    with path.open('w') as log:
        log.write(json.dumps(list(map(str, command))) + '\n');log.flush()
        result = subprocess.run(list(map(str, command)), stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        tail = path.read_text(errors='replace')[-5000:]
        print('::error::' + tail.replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D'), flush=True)
        raise RuntimeError('cloud command failed: ' + str(path))


def build():
    guard();prefix = ROOT / 'build/frame-stage';sdk = ROOT / 'build/reading-library/stage'
    def module(path, extra=()):
        folder = ROOT / 'build/frame-modules' / path.replace('/', '-')
        run(['cmake', '-S', path, '-B', folder, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_INSTALL_PREFIX=' + str(prefix), '-DCMAKE_PREFIX_PATH=' + str(prefix) + ';' + str(sdk),
             '-DEXR_SDK=' + str(sdk), *extra])
        run(['cmake', '--build', folder, '--parallel', '4']);run(['cmake', '--install', folder])
    run(['cmake', '--preset', 'reading-library']);run(['cmake', '--build', '--preset', 'reading-library'])
    run(['cmake', '--install', ROOT / 'build/reading-library'])
    module('apps/reader/store/native');module('extras/webdav')
    module('apps/reader/revisions', ['-DREADER_PRODUCT_PREFIX=' + str(prefix)])
    for name in ('commands', 'desktop-metadata', 'sync', 'session'):
        module('apps/reader/' + name)
    for path in ('extras/credentials', 'extras/sideload', 'extras/desktop-drop', 'apps/reader/reading-state',
                 'apps/reader/batch-import', 'apps/reader/reading-commands', 'apps/reader/annotation-view',
                 'apps/reader/preferences', 'apps/reader/search', 'apps/reader/navigation'):
        module(path)
    desktop = ROOT / 'build/frame-desktop'
    options = ['-D' + name + '=ON' for name in ('EXR_READER_GTK_BATCH_IMPORT', 'EXR_READER_GTK_DROP_IMPORT',
               'EXR_READER_GTK_ACCOUNT', 'EXR_READER_GTK_PREFERENCES', 'EXR_READER_GTK_SEARCH',
               'EXR_READER_GTK_READING_RECORDS', 'EXR_READER_GTK_NAVIGATION', 'EXR_READER_BUILD_GTK',
               'EXR_LINUX_REVIEW_TESTS', 'EXR_LINUX_FIXED_TESTS')]
    options += ['-D' + name + '=' + str(prefix) for name in ('READER_METADATA_PREFIX', 'READER_ACCOUNT_PREFIX',
                'READER_DESKTOP_DROP_PREFIX', 'READER_BATCH_IMPORT_PREFIX', 'READER_PREFERENCES_PREFIX',
                'READER_SEARCH_PREFIX', 'READER_READING_RECORDS_PREFIX', 'READER_NAVIGATION_PREFIX')]
    run(['cmake', '-S', 'apps/reader/desktop', '-B', desktop, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DEXR_SDK=' + str(sdk), '-DCMAKE_PREFIX_PATH=' + str(prefix) + ';' + str(sdk),
         '-DEXR_READER_FIXTURES=' + str(ROOT / 'tests/fixtures'), *options])
    run(['cmake', '--build', desktop, '--target', 'exreader-linux', 'reader-gtk-navigation-backend', '--parallel', '4'])
    run([sys.executable, 'tests/reader_gtk_receive/check_link.py', '--map', desktop / 'gtk-account-host.map',
         '--binary', desktop / 'gtk-host/exreader-linux', '--output', OUT / 'host-link.json'])
    (OUT / 'host.map').write_bytes((desktop / 'gtk-account-host.map').read_bytes())
    run([sys.executable, 'tools/build_linux_host.py', '--sdk', sdk, '--binary', desktop / 'gtk-host/exreader-linux', '--output', OUT / 'package'])
    run([sys.executable, 'tests/reader_navigation/make_navigation_fixtures.py', OUT / 'fixtures'])
    consumer = ROOT / 'build/frame-f2-consumer'
    run(['cmake', '-S', 'tests/reader_navigation/consumer', '-B', consumer, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_PREFIX_PATH=' + str(prefix) + ';' + str(sdk)])
    run(['cmake', '--build', consumer, '--parallel', '4'])
    run([sys.executable, 'tests/reader_navigation/check_navigation.py', '--probe', consumer / 'navigation-probe',
         '--c-consumer', consumer / 'navigation-c-consumer', '--fixtures', OUT / 'fixtures',
         '--installed', prefix, '--output', OUT / 'f2-installed'])
    run([sys.executable, 'tests/reader_gtk_navigation/make_inputs.py', OUT / 'fixtures'])
    run([sys.executable, 'tests/linux_host/generate_fixed.py', OUT / 'fixed-inputs'])
    run([desktop / 'reader-gtk-navigation-backend', OUT / 'backend.sqlite', OUT / 'package/EXReader-Linux/Reader.otf',
         OUT / 'fixtures', OUT / 'fixed-inputs'])


def validate(report, source_sha, run_id, attempt):
    identity(report, source_sha, run_id, attempt)
    require(report['accepted'] is False and report['diagnostic_only'] is False and
            report['navigation_scope_passed'] is True and report['complete_product'] is False and
            report['performance_accepted'] is False, 'wrong actual navigation scope')
    require(report['program_source_sha'] == source_sha and re.fullmatch('[0-9a-f]{64}', report['program_sha256']), 'wrong actual binary identity')
    require(report['count'] == report['passed'] == len(report['checks']) == 29 and report['failed'] == 0,
            'missing actual navigation checks')
    require([row['name'] for row in report['checks']] == names() and all(row['pass'] is True for row in report['checks']),
            'original named conditions failed or substituted')
    images = report['image_observations'];require([row['name'] for row in images] == ['before-directory', 'after-directory'], 'wrong actual captures')
    for image in images:
        host = image['host'];width,height=int(image['preferences']['bitmap_width']),int(image['preferences']['bitmap_height'])
        require(host['image_located'] == host['page_draw_sensitive'] == 1 and
                host['frame_generation'] == host['painted_generation'] == image['before_host']['frame_generation'], 'unpainted actual generation')
        x=host['image_x']+(host['image_width']-width)//2;y=host['image_y']+(host['image_height']-height)//2
        require(image['crop'] == [x,y,width,height] and width <= host['image_width'] and height <= host['image_height'], 'wrong actual image crop')
        require(host['page_x'] <= x and x+width <= host['page_x']+host['page_width'] and
                host['page_y'] <= y and y+height <= host['page_y']+host['page_height'], 'clipped actual bitmap')
    after=images[1];barrier=after['draw_barrier']
    require(type(barrier['after_draw']) is int and barrier['painted_serial'] > barrier['after_draw'] and
            barrier['sensitive'] == barrier['focused'] == 1 and barrier['frame_generation'] == barrier['painted_generation'], 'no actual new sensitive draw')
    require(images[0]['sha256'] == images[1]['sha256'], 'actual page pixels changed')
    composite=next(row['observed'] for row in report['checks'] if row['name'] == 'read_only_browsing_close_preserves_pixels_notes_progress_and_product')
    require(composite['before_frame'] == composite['after_frame'] and composite['before_storage'] == composite['after_storage'] and
            composite['before_pixels'] == composite['after_pixels'] == images[0]['sha256'], 'original exact composite differs')


def aggregate():
    guard(False);sha=os.environ['GITHUB_SHA'];run_id=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])
    metadata=fetch('actions/runs/%d'%run_id)
    require(metadata['head_sha']==sha and metadata['path']==WORKFLOW and metadata['run_attempt']==attempt, 'foreign workflow')
    producers=[row for row in pages('actions/runs/%d/attempts/%d/jobs'%(run_id,attempt),'jobs') if row['name']==JOB]
    require(len(producers)==1 and producers[0]['conclusion']=='success' and
            all(step['conclusion']=='success' for step in producers[0]['steps']), 'actual producer incomplete')
    artifacts=[row for row in pages('actions/runs/%d/artifacts'%run_id,'artifacts') if row['name']=='reader-gtk-navigation-frame-%d-%d'%(run_id,attempt)]
    require(len(artifacts)==1 and artifacts[0]['workflow_run']['head_sha']==sha, 'wrong actual artifact')
    bundle=Bundle(artifacts[0])
    try:
        report=bundle.report('frame-proof/ui/result.json');validate(report,sha,run_id,attempt)
        source_guard=bundle.report('frame-proof/source-guard.json');identity(source_guard,sha,run_id,attempt)
        require(source_guard==guard(False),'producer guard bytes differ')
        program=hashlib.sha256(bundle.bytes('frame-proof/package/EXReader-Linux/bin/exreader-linux',64*1024**2)).hexdigest()
        package=bundle.report('frame-proof/package/build.json')
        require(package['source_sha']==sha and package['sdk_version']=='3.40.0' and package['abi']==1 and
                package['files']['bin/exreader-linux']==program==report['program_sha256'],'actual package identity differs')
        link=bundle.report('frame-proof/host-link.json');identity(link,sha,run_id,attempt)
        require(link['accepted'] is True and link['program_sha256']==program and len(link['providers'])==1 and
                link['map_sha256']==hashlib.sha256(bundle.bytes('frame-proof/host.map',16*1024**2)).hexdigest(),'actual provider link map differs')
        f2=bundle.report('frame-proof/f2-installed/result.json');identity(f2,sha,run_id,attempt)
        require(f2['accepted'] is True and f2['checks']==130,'original installed F2 checks missing')
        image_hashes={}
        for item in report['image_observations']:
            png=bundle.bytes('frame-proof/ui/'+item['name']+'.png',16*1024**2);picture=Image.open(io.BytesIO(png)).convert('RGB')
            x,y,width,height=item['crop'];require(0<=x<x+width<=picture.width and 0<=y<y+height<=picture.height,'PNG crop out of window')
            require(hashlib.sha256(picture.crop((x,y,x+width,y+height)).tobytes()).hexdigest()==item['sha256'],'actual PNG contradicts report')
            image_hashes[item['name']]=hashlib.sha256(png).hexdigest()
        mutations=[('source_sha','foreign'),('run_id','0'),('attempt','0'),('diagnostic_only',True),
                   ('navigation_scope_passed',False),('count',28),('checks',[]),('program_sha256',''),
                   ('complete_product',True),('performance_accepted',True)]
        for key,value in mutations:
            changed=copy.deepcopy(report);changed[key]=value
            try:validate(changed,sha,run_id,attempt)
            except (ValueError,AssertionError,KeyError):continue
            raise ValueError('accepted protocol mutation '+key)
        for key in ('draw-serial','painted-generation','pixels'):
            changed=copy.deepcopy(report)
            if key=='draw-serial':changed['image_observations'][1]['draw_barrier']['painted_serial']=changed['image_observations'][1]['draw_barrier']['after_draw']
            elif key=='painted-generation':changed['image_observations'][1]['host']['painted_generation']=-1
            else:changed['image_observations'][1]['sha256']='0'*64
            try:validate(changed,sha,run_id,attempt)
            except (ValueError,AssertionError,KeyError):continue
            raise ValueError('accepted protocol mutation '+key)
        original=bundle.report('navigation-probe/input.json');pixels=bundle.report('navigation-probe/original-pixel-difference.json')
        require(original['original_run']==OLD_RUN and original['diagnostic_only'] is True and original['accepted'] is False and
                pixels['original_formula_roi_difference']['changed_pixels']==52033,'original failure was not retained')
        result=dict(accepted=True,scope='Linux GTK navigation 29 original conditions with exact actual new sensitive image draw',
                    source_sha=sha,run_id=run_id,attempt=attempt,observation_commit=OBSERVATION,
                    program_sha256=program,navigation_checks=29,installed_f2_checks=130,protocol_rejections=len(mutations)+3,
                    actual_screenshot_sha256=image_hashes,bitmap_rgb_sha256=report['image_observations'][0]['sha256'],
                    draw_barrier=report['image_observations'][1]['draw_barrier'],
                    original_failure_run=OLD_RUN,original_source_reaccepted=False,original_after_contained_directory_controls=True,
                    artifact={key:artifacts[0][key] for key in ('id','name','size_in_bytes','digest','expires_at')},
                    complete_product=False,other_hosts_accepted=False,performance_accepted=False)
        folder=ROOT/'build/frame-proof-summary';folder.mkdir(parents=True,exist_ok=True)
        (folder/'verified.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    finally:bundle.close()


if __name__=='__main__':
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    {'guard':guard,'build':build,'aggregate':aggregate}[sys.argv[1]]()
