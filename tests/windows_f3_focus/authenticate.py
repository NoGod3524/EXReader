"""Authenticate scoped F3 acceptance without laundering unrelated failed gates."""
import hashlib, importlib.util, io, json, os, sys, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from check_parallel_integration import fetch, download_artifact_zip, require

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    source,run,attempt=os.environ['GITHUB_SHA'],int(os.environ['GITHUB_RUN_ID']),int(os.environ['GITHUB_RUN_ATTEMPT'])
    out=ROOT/'build/f3-focus-summary';out.mkdir(parents=True,exist_ok=True)
    result=dict(accepted=False,source_sha=source,run_id=run,attempt=attempt,artifacts={},problems=[],complete_product=False)
    def archive(key,name):
        meta=fetch('actions/artifacts/'+os.environ[key+'_ID'])
        require(meta['name']==name+f'-{run}-{attempt}' and meta['workflow_run']['id']==run and meta['workflow_run']['head_sha']==source and not meta['expired'],'artifact identity')
        require(datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'artifact expiry')
        with tempfile.TemporaryFile() as f:
            download_artifact_zip(meta['id'],f);f.seek(0);raw=f.read()
        digest=hashlib.sha256(raw).hexdigest()
        require(len(raw)==meta['size_in_bytes'] and meta['digest']=='sha256:'+digest and os.environ[key+'_DIGEST'].removeprefix('sha256:')==digest,'artifact bytes/digest')
        z=zipfile.ZipFile(io.BytesIO(raw));names=z.namelist()
        require(len(names)==len(set(names)) and all(not n.startswith(('/','\\')) and '..' not in n.replace('\\','/').split('/') for n in names),'unsafe archive')
        result['artifacts'][key]={k:meta[k] for k in ('id','name','size_in_bytes','digest')}
        return z
    def identity(r):
        require(r['source_sha']==source and str(r['run_id'])==str(run) and str(r['attempt'])==str(attempt),'foreign report')
    try:
        info=fetch(f'actions/runs/{run}')
        require(info['head_sha']==source and info['run_attempt']==attempt and info['head_branch']=='codex/dot-windows-f3-focus-fix' and info['path']=='.github/workflows/windows-f3-focus.yml','workflow identity')
        jobs=fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
        result['jobs']=[dict(id=j['id'],name=j['name'],conclusion=j['conclusion'],steps=j['steps']) for j in jobs if j['name']!='authenticate']
        producer,=[j for j in jobs if j['name']=='installed F1 and native Windows search controls and lifecycle']
        require(producer['head_sha']==source and producer['run_attempt']==attempt and producer['status']=='completed','producer identity')
        steps={s['name']:s['conclusion'] for s in producer['steps']}
        result['unrelated_failed_steps']=[s['name'] for s in producer['steps'] if s['conclusion']=='failure']
        for name in ('Execute real native F3 settings, page theme and persistence','All thirteen actual atomic commit checks and old-veto negative control on SDK3.41','Verify focus policy and real keyboard cue accessibility','Execute real keyboard and UI Automation search controls','Independent original native keyboard and accessibility regression'):
            require(steps.get(name)=='success','affected step failed: '+name)
        z=archive('ORIGINAL','reader-windows-search-initial')
        def load(path):return json.loads(z.read(path))
        def sha(path):return hashlib.sha256(z.read(path)).hexdigest()
        origin=load('f3-focus-source/source.json');identity(origin)
        require(origin['base']=='e330a415b733db18dea5aa6010d13cf3063587fd','wrong base')
        f3=module('original_f3','tests/reader_windows_preferences/verify.py')
        report=load('wprefs-ui/preferences-ui.json')
        count=f3.validate(report,source,run,attempt,sha('wprefs-package/EXReader/EXReader.exe'),sha('baseline-package/EXReader/EXReader.exe'))
        require(count==25,'original full F3 coverage')
        for name in report['captures']:require(z.read('wprefs-ui/captures/'+name).startswith(b'BM'),'missing capture')
        require(f3.bmp_inner(z.read('wprefs-ui/captures/default-on.bmp'))==f3.bmp_inner(z.read('wprefs-ui/captures/default-off.bmp')),'default pixels drift')
        require(f3.bmp_inner(z.read('wprefs-ui/captures/fixed-light.bmp'))==f3.bmp_inner(z.read('wprefs-ui/captures/fixed-dark.bmp')),'fixed page changed')
        atomic=module('original_atomic','tests/reader_windows_preferences/verify_commit.py')
        atomic.validate(load('wprefs-commit-ui/report.json'),source,run,attempt,sha('ws-host/EXReaderPreferencesCommitReview.exe'),sha('ws-host/EXReaderPreferencesCancelControl.exe'))
        focus=load('f3-focus-contrast/observations.json');identity(focus)
        obs={r['label']:r for r in focus['observations']}
        require(obs['focus-away']['focused'] is False and obs['focus-away']['edge_dark']==0,'focus-away pixels')
        require(obs['hide-focus-cue']['focused'] is True and obs['hide-focus-cue']['ui_state']&1 and obs['hide-focus-cue']['edge_dark']==0,'hidden native cue not respected')
        for label in ('show-focus-cue','keyboard-tab-page'):
            r=obs[label];require(r['focused'] is True and not r['ui_state']&1 and r['edge_dark']==0 and sum(sum(p)<260 for p in r['canvas_edge'])>100,'visible keyboard cue missing: '+label)
            require(r['surround']==[255,255,255],'focus cue painted into the surrounding gutter')
        require(obs['hide-focus-cue']['interior_sha256']==obs['show-focus-cue']['interior_sha256'],'focus obscured light content')
        dark_off,dark_on=obs['dark-hide-focus-cue'],obs['dark-show-focus-cue']
        require(dark_off['focused'] and dark_on['focused'] and dark_off['ui_state']&1 and not dark_on['ui_state']&1,'dark focus state')
        require(dark_off['interior_sha256']==dark_on['interior_sha256'],'focus obscured dark content')
        require(sum(abs(sum(a)-sum(b))>300 for a,b in zip(dark_off['canvas_edge'],dark_on['canvas_edge']))>100,'dark focus cue insufficient contrast')
        a11y=load('f3-focus-a11y/a11y-ui.json');identity(a11y)
        require(a11y['accepted'] is True and not a11y['failures'] and a11y['count']==len(a11y['checks']) and a11y['count']>10,'original a11y failed')
        keyboard=load('ws-search-keyboard/keyboard-uia.json')
        f3.search.bound(keyboard,f3.search.names_from_source(ROOT/'tests/reader_windows_search/check_keyboard.py','REQUIRED'),source,run,attempt)
        require(keyboard['consumer_sha256']==sha('ws-package/EXReader/EXReader.exe'),'keyboard used different host')
        result.update(original_f3_checks=count,atomic_checks=13,keyboard_checks=keyboard['count'],a11y_checks=a11y['count'],focus=focus,consumer_sha256=sha('ws-package/EXReader/EXReader.exe'))
        for jobname in ('current_native','current_fonts'):
            j,=[j for j in jobs if j['name']==jobname]
            require(j['head_sha']==source and j['run_attempt']==attempt and j['conclusion']=='success','affected current job failed: '+jobname)
        native=archive('NATIVE','windows-txt-forward-scan')
        c09=json.loads(native.read('c09/report.json'));identity(c09)
        require(c09['accepted'] is True and not c09['failures'] and all(s['passed'] for s in c09['steps']),'C09 failed')
        forward=json.loads(native.read('txt-forward-scan/report.json'));identity(forward)
        require(forward['accepted'] is True and not forward['failures'],'forward failed')
        require(hashlib.sha256(native.read('c09/package/EXReader/EXReader.exe')).hexdigest()==forward['candidate_sha256'],'forward binary mismatch')
        fonts=archive('FONTS','windows-font-lifecycle')
        binding=json.loads(fonts.read('evidence/same-source.json'));identity(binding)
        require(binding['accepted'] is True and binding['case_counts']==[8,5] and binding['program_sha256']==hashlib.sha256(fonts.read('host/EXReaderWave3.exe')).hexdigest(),'font binding')
        for path,count in [('report.json',8),('txt/report.json',5)]:
            r=json.loads(fonts.read('evidence/'+path));identity(r)
            require(r['accepted'] is True and not r['problems'] and len(r['checks'])==count and all(c['passed'] for c in r['checks']),'font report')
        result.update(accepted=True,scope='F3 original 25, atomic 13, focus cues and keyboard accessibility, current C09/TXT/SDK/font regressions; unrelated legacy failures retained',full_legacy_suite_accepted=not result['unrelated_failed_steps'],font_checks=[8,5])
    except Exception as e:
        result['problems'].append(type(e).__name__+': '+str(e))
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    require(result['accepted'],'F3 scoped acceptance refused')
if __name__=='__main__':main()
