"""Collect real XCUI outcomes without converting an incomplete audit to acceptance."""
import hashlib,json,os,plistlib,shutil,subprocess,sys
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
sys.path.insert(0,str(Path('tests/reader_a11y_apple').resolve()))
from audit_collect import parse_records, element_map, evaluate_geometry
sys.path.insert(0,str(Path('tests/apple_host').resolve()))
from collect_evidence import load_results
p=sys.argv[1]; root=Path('build/d04'); out=Path('build/evidence');out.mkdir(parents=True,exist_ok=True)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def command(*a): return subprocess.run(a,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
checks=[];records={};findings=[];files=[];problems=[]
labels=['import','normal','original-compact'] if p=='macos' else ['import','normal','original-large','large']
policy=json.loads(Path('tests/reader_a11y_apple/a11y_contract.json').read_text())['policy']
for label in labels:
    log=root/'results'/f'{label}.log'; bundle=root/'results'/f'{label}.xcresult'
    exitfile=root/'results'/f'{label}.exit'
    entry={'label':label,'exit':int(exitfile.read_text()) if exitfile.exists() else None,'cases':[]}
    if bundle.exists():
        shutil.copytree(bundle,out/bundle.name,dirs_exist_ok=True)
        try: entry['cases']=load_results(bundle)
        except BaseException as e: problems.append(label+': '+str(e))
        exported=command('xcrun','xcresulttool','export','attachments','--path',str(bundle),'--output-path',str(out/(label+'-attachments')))
        (out/(label+'-export.log')).write_text(exported.stdout)
        if exported.returncode: problems.append(label+': attachment export failed')
    else: problems.append(label+': no xcresult')
    if log.exists():
        shutil.copy2(log,out/log.name)
        records[label]=parse_records(log.read_text(errors='replace'))
        for step,state in records[label]['states'].items():
            elements=element_map(state)
            interactive=[id for id,e in elements.items() if e['role'] in ('Button','TextField','TextView','Toggle','MenuButton','PopUpButton')]
            evaluate_geometry(p,label+'/'+step,{'interactive':interactive},elements,state['window'],policy,findings,state['screenshot'])
            for id in interactive:
                if not elements[id]['label'].strip(): findings.append({'criterion':'name','verdict':'fail','state':step,'element':id,'blocking':True})
    expected=2 if label in ('normal','large') else 1
    entry['passed']=entry['exit']==0 and len(entry['cases'])==expected and all(c['result']=='Passed' for c in entry['cases'])
    checks.append(entry)
for name in ('destination.txt','normal-content-size.txt','large-content-size.txt','keyboard-ui-mode.txt'):
    if (root/name).exists(): shutil.copy2(root/name,out/name)
project=root/'project/EXReaderHost.xcodeproj/project.pbxproj'
if project.exists(): shutil.copy2(project,out/'project.pbxproj')
products=root/'DerivedData/Build/Products'/('Debug' if p=='macos' else 'Debug-iphonesimulator')
app=products/'EXReaderHost.app'; info=app/('Contents/Info.plist' if p=='macos' else 'Info.plist'); exe=app/('Contents/MacOS/EXReaderHost' if p=='macos' else 'EXReaderHost')
identity={}
if info.exists() and exe.exists():
    plist=plistlib.loads(info.read_bytes())
    identity={'executable_sha256':sha(exe),'info_sha256':sha(info),'source':plist.get('EXRSourceSHA'),'sdk_version':plist.get('EXRSDKVersion'),'page_theme':plist.get('EXRPageThemeEnabled')}
    if identity['source']!=os.environ['TARGET_SHA'] or identity['sdk_version']!='3.41.0' or identity['page_theme'] is not False: problems.append('program plist identity mismatch')
    shutil.copy2(exe,out/'EXReaderHost-executable')
    ent=command('codesign','-d','--entitlements',':-',str(app)); (out/'entitlements.txt').write_text(ent.stdout)
else: problems.append('actual program missing')
libs={str(f):sha(f) for f in Path('stage/lib').glob('*') if f.is_file()}
manifest=Path('build/apple-resources/manifest.json')
if manifest.exists(): shutil.copy2(manifest,out/'fixture-manifest.json')
completed=all(x['passed'] for x in checks) and not problems
for label in ('normal',) if p=='macos' else ('normal','large'):
    states=records.get(label,{}).get('states',{})
    if not states or not any('returned-shelf' in x for x in states): completed=False;problems.append(label+': default journey incomplete')
# Geometry is a conservative screen-level finding, not proof that scrolling cannot recover it.
report={'schema':1,'package':'D04','platform':p,'harness_sha':os.environ['GITHUB_SHA'],'target_sha':os.environ['TARGET_SHA'],'sdk_sha':os.environ['SDK_SHA'],
 'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'job':os.environ['GITHUB_JOB'],
 'program':identity,'installed_libraries':libs,'review_macros':[],'page_theme':'OFF','launch_scope':'default [] and separately labelled unchanged fixture regression',
 'checks':checks,'records':records,'geometry_and_name_findings':findings,'problems':problems,
 'audit_completed':completed,'default_ui_accepted':False,'ax_semantics_accepted':False,'dynamic_type_accepted':False,
 'voiceover_accepted':False,'physical_device_execution':False,'complete_product':False,
 'unverified':['VoiceOver speech/rotor','physical iPhone/iPad','focus owner and restoration order','mobile hardware keyboard','macOS system large-font setting','system picker import (existing app fixture button used separately)','actual search query/result navigation (dialog reachability only)','text clipping inside labels requires visual review','full settings/theme: default page-theme OFF']}
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
for f in sorted(out.rglob('*')):
    if f.is_file():files.append({'path':str(f.relative_to(out)),'bytes':f.stat().st_size,'sha256':sha(f)})
(out/'files.json').write_text(json.dumps(files,indent=2)+'\n')
print('D04_TARGET_REPORT '+json.dumps({k:v for k,v in report.items() if k not in ('records','geometry_and_name_findings','installed_libraries')},ensure_ascii=False))
print('D04_FINDINGS '+json.dumps([f for f in findings if f.get('verdict')=='fail'],ensure_ascii=False))
sys.exit(0 if completed else 1)
