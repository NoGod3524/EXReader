"""Replay the full native suite against authenticated producer bytes and original assertions.

This checks functional coverage, not a complete native UI frame census. Output
must be outside the sealed raw run. All percentages use the retained samples.
"""
import argparse,ast,csv,hashlib,importlib.util,json,math,time,zipfile
from collections import Counter
from pathlib import Path,PurePosixPath

COHORTS=('cold_shelf','warm_shelf','reading','import','import_epub')
TXT_REJECTIONS=('import_rejected','rejected_but_sdk_orphan','imported_not_in_catalog','catalog_identity_mismatch')
BISECT_MIB=(.25,.5,1,2,4,5,6,6.5,7,8,12,16)
REQUIRED_CHECKS=(
 'thirty_or_more_independent_process_starts','at_least_ten_launches_per_named_cohort','every_measured_launch_complete',
 'cold_and_warm_strategies_recorded','window_appeared_each_launch','first_screen_interactive_observed_each_shelf_launch',
 'shelf_pagination_observed','search_result_observed','eight_in_book_page_turns_per_reading_launch','continue_reading_observed',
 'continue_reading_page_verified','import_input_responsiveness_observed','original_txt_input_identity_recorded',
 'original_txt_path_facts_separated','original_txt_path_accounted_for','working_set_peak_observed','artifact_identity_recorded',
 'corpus_identity_recorded','frame_time_not_measured','numeric_budget_not_enforced')
PROPOSED_METRICS=('first_screen_interactive_ms','shelf_next_page_ms','search_result_ms','book_page_turn_ms','resume_ms','input_during_import_p50_ms','peak_working_set_bytes')

def need(value,reason):
 if not value:raise ValueError(reason)
def sha(path):
 digest=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for block in iter(lambda:stream.read(1<<20),b''):digest.update(block)
 return digest.hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def rows(path):return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
def constants(path,names):
 def literal(node):
  if isinstance(node,ast.Dict):return {ast.literal_eval(k):literal(v) for k,v in zip(node.keys,node.values)}
  if isinstance(node,ast.BinOp) and isinstance(node.op,ast.LShift):
   left,right=ast.literal_eval(node.left),ast.literal_eval(node.right);need(type(left) is int and type(right) is int and 0<=right<=63,'fixed integer-size expression');return left<<right
  return ast.literal_eval(node)
 tree=ast.parse(Path(path).read_text(encoding='utf-8'))
 return {n.targets[0].id:literal(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in names}
def imported(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def launch_assertions(records,minimum_resumes):
 resumes=[]
 for record in records:
  need(record.get('ok') is True and record.get('window_ms') is not None and not record.get('faults'),'all original launches complete')
  ops=record['ops'];kind=record['cohort']
  if kind!='reading':need(ops['first_screen'].get('first_screen_interactive_ms') is not None,'original interactive first screen')
  if kind in ('cold_shelf','warm_shelf'):
   need(ops['shelf_next_page']['rows_after']>=100 and ops['search']['rows']==50 and ops['search_clear']['rows']==50 and ops['reset_top'] is True,'original shelf pagination/search/clear/reset assertions')
   need(not ops.get('page_turns'),'shelf must not substitute reader turns')
  if kind=='reading':
   need(len(ops.get('page_turns',[]))>=8,'eight original reader turns')
   if ops.get('resume'):resumes.append(ops['resume'])
  if kind in ('import','import_epub'):
   value=ops['import'];need(value.get('visible') is True and value.get('fixture_sha256') and value.get('busy_input_samples',0)>=1,'real fixed import and busy-window input')
  need(record.get('peak') and record['peak']['peak_working_set_bytes']>0,'working-set peak per process')
 need(len(resumes)>=minimum_resumes and all(v.get('verified') is True and v.get('ms') is not None for v in resumes),'original resume page verification')
 expected={'fresh-sdk-library-copy' if r['cohort'] in ('cold_shelf','import','import_epub') else 'shared-profile' for r in records}
 need({r['profile_strategy'] for r in records}==expected,'original cold/warm strategies')

def coverage(main,interactions,diagnosis):
 records=main['records'];summary=main['summary'];counts=Counter(r['cohort'] for r in records);skipped=summary.get('skipped_cohorts') or {}
 need(not (set(skipped)-{'import'}),'no new skipped cohort')
 skip=diagnosis.get('verdict') in TXT_REJECTIONS and bool(skipped.get('import'))
 need(bool(skipped.get('import'))==(diagnosis.get('verdict') in TXT_REJECTIONS),'TXT conditional follows the unchanged original rejection rule')
 expected=set(COHORTS)-({'import'} if skip else set())
 need(set(counts)==expected and all(counts[k]==12 for k in expected),'original five-by-twelve matrix or documented TXT conditional')
 need(summary['cohorts']==dict(counts) and len(records)>=30 and all(n>=10 for n in counts.values()),'original verifier cohort and 30/10 minimum')
 need(summary['measured_process_starts']==len(records) and summary['preparation_process_starts']==2 and summary['process_starts_total']==len(records)+2,'main launch accounting')
 need(summary['schema']==1 and summary['complete'] is True and not summary['problems'],'original main completion')
 need(all(summary['checks'].get(k) is True for k in REQUIRED_CHECKS) and summary['checks_passed']==summary['checks_total']==len(summary['checks']) and all(v is True for v in summary['checks'].values()),'all original named assertions')
 need(summary['performance_accepted'] is False and summary['budget_enforced'] is False and summary['frame_time']['measured'] is False and bool(summary['frame_time']['reason']),'original non-frame channel statements')
 need(summary['txt_path']['diagnosis']==diagnosis and summary['txt_path']['verdict']==diagnosis['verdict'],'same-run separated TXT diagnosis')
 fixture=summary['txt_path']['fixture'];need(bool(fixture.get('sha256')) and type(fixture.get('bytes')) is int and fixture['bytes']>0 and fixture.get('parameters') is not None,'original TXT fixture/generator identity')
 need(len(diagnosis.get('runs',[]))==3 and bool(diagnosis.get('verdict')),'three original TXT diagnoses')
 for run in diagnosis['runs']:
  facts=run.get('facts',{});need(facts.get('fixture') and facts.get('import') and 'catalog' in facts and facts.get('probes'),'separated original TXT facts')
 bisect=diagnosis.get('bisect',{}).get('imports',[])
 need(tuple(v['declared_mib'] for v in bisect)==BISECT_MIB,'all twelve original size-bisect imports')
 need(all(v.get('sha256') and v.get('bytes',0)>0 and 'catalog' in v and isinstance(v.get('completed'),bool) and isinstance(v.get('status_indicates_failure'),bool) for v in bisect),'separated bisect input/import/catalog facts')
 launch_assertions(records,8)
 result=interactions['result'];inter=interactions['records'];isummary=interactions['summary']
 need(not result['faults'] and len(result['font_order'])==5 and all(v in ('bigger-first','smaller-first') for v in result['font_order']),'original interaction faults/order')
 for key,n in {'shelf_scroll_down':15,'shelf_scroll_up':15,'font_bigger':10,'font_smaller':10}.items():
  values=result[key];need(len(values)==n and all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in values),'original interaction count/value '+key)
 need(Counter(r['cohort'] for r in inter)=={'warm_shelf':5,'reading':5},'two-by-five original interaction launches')
 need(isummary['schema']==1 and isummary['measured_process_starts']==10 and isummary['preparation_process_starts']==2 and isummary['process_starts_total']==12,'interaction launch accounting')
 launch_assertions(inter,4)
 return {'main_launches':len(records),'interaction_launches':10,'diagnostic_launches':3,'diagnostic_bisect_launches':1,'preparation_launches':4,'product_starts':len(records)+18,'default_product_starts':78,'original_txt_conditional_skip':skip,'default_txt_main_launches_missing':12 if skip else 0,'default_78_start_scope_complete':not skip}

def reader_body(expected,locator,nonuniform):
 need(type(nonuniform) is int and nonuniform>=0,'reader content count')
 if not expected:return 'not_applicable'
 return 'present' if locator and locator.get('valid') is True and nonuniform>0 else 'missing'

def artifact(root,archive,metadata,expected_source):
 meta=load(metadata);data=Path(archive)
 need(data.stat().st_size==meta['size_in_bytes'] and 'sha256:'+sha(data)==meta['digest'],'authenticated build ZIP bytes')
 need(meta['workflow_run']['head_sha']==expected_source,'authenticated build source')
 with zipfile.ZipFile(data) as z:
  names=[n for n in z.namelist() if not n.endswith('/')]
  need(len(names)==len(set(n.casefold() for n in names)),'unique producer inventory')
  for n in names:
   v=PurePosixPath(n);need(not v.is_absolute() and '..' not in v.parts and '\\' not in n and ':' not in n,'safe producer member')
  manifest=json.loads(z.read('manifest.json'));build=json.loads(z.read('build-identity.json'))
  need(manifest['source_sha']==build['source_sha']==expected_source and str(manifest['run_id'])==str(meta['workflow_run']['id']),'producer run/source manifest binding')
  need(set(names)==set(manifest['files'])|{'manifest.json'},'complete producer manifest')
  actual={p.relative_to(root/'product').as_posix() for p in (root/'product').rglob('*') if p.is_file()};need(actual==set(names),'exact retained producer inventory')
  for n in names:
   payload=z.read(n);path=root/'product'/n;need(len(payload)==path.stat().st_size and hashlib.sha256(payload).hexdigest()==sha(path),'retained producer bytes '+n)
   if n!='manifest.json':need(manifest['files'][n]=={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()},'producer payload manifest '+n)
 return meta,build

def environment_assertions(root,summary,origin,build,observations):
 env=summary['environment'];package=root/'product/program';art=env['artifacts']
 need(summary['source_sha']==env['source_sha']==origin['source_sha'] and summary['run_id']==env['run_id']==origin['run_id'] and summary['attempt']==env['attempt']=='local-native','native summary/environment source and execution identity')
 need(env['execution']=='local-native' and env['producer']['id']==origin['producer']['id'] and env['native_display']==origin['display_before'],'native producer and display provenance')
 need(load(observations/'environment.json')==env and load(observations/'preparation.json')==summary['preparation'],'original separate environment/preparation documents')
 need(env['cpu'].get('model') and env['os'].get('version') and env['memory_total_bytes']>0,'original CPU/OS/system-memory identity')
 need(env['display']['screen_width_px']>0 and env['display']['screen_height_px']>0,'original display geometry')
 measurement=env['measurement'];need(measurement['frame_time_measured'] is False and measurement['disk_cache_controlled'] is False and 'SendMessageTimeoutW' in measurement['input_delivery'],'original measurement provenance')
 files={p.relative_to(package).as_posix():p.stat().st_size for p in package.rglob('*') if p.is_file()}
 need(art['files']==files and art['package_total_bytes']==sum(files.values()),'complete package size inventory')
 need(art['exe_bytes']==files['EXReader.exe'] and art['exe_sha256']==build['program_sha256']==sha(package/'EXReader.exe') and art['font_sha256']==sha(package/'Reader.otf'),'measured EXE/font identity')
 need(art['seed_exe_sha256']==build['seed_sha256']==sha(root/'product/seed.exe') and art['seed_source_sha256']==sha(root/'product/native-source/seed_shelf.c'),'producer seed program/source identity')
 corpus=summary['preparation']['corpus'];need(corpus['originals_in_catalog']==2202 and corpus['titles_and_bytes_exact'] is True,'original 2202 corpus assertion')
 need('"public_sdk_originals":2202' in summary['preparation']['seed']['seed_stdout'],'public SDK corpus seed')
 need(env['corpus']['originals']==2202 and env['corpus']['reading_fixture_sha256']==sha(package/'Sample-positive.epub'),'fixed packaged reading input')


def audit(a):
 begun=time.monotonic();root=Path(a.run).resolve();output=Path(a.output).resolve()
 need(not output.is_relative_to(root) and not output.exists(),'fresh independent audit output outside sealed raw');output.mkdir(parents=True)
 try:
  def bounded():need(time.monotonic()-begun<1200,'20-minute independent audit cap')
  need(sha(root/'manifest.json')==a.manifest_sha256,'externally pinned native raw manifest')
  origin=load(root/'result.json');manifest=load(root/'manifest.json');producer,build=artifact(root,a.zip,a.metadata,a.expected_source)
  need(origin['execution']=='local-native' and origin['attempt']=='local-native' and origin['actions_environment_value']!='true','explicit native execution identity')
  need(origin['source_sha']==manifest['source_sha']==a.expected_source and origin['producer']==producer,'independently authenticated source/artifact metadata')
  need(origin['collection_complete'] is True and not origin['problems'] and not origin['collection_cap_expired'] and not origin['controller_stop_requested'],'complete uncancelled original suite')
  need(origin['display_unchanged'] is True and origin['display_before']==origin['display_after'] and len(origin['display_before'])==3 and all(v>0 for v in origin['display_before']),'actual display mode unchanged')
  actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()};need(actual==set(manifest['files'])|{'manifest.json'},'complete native raw inventory')
  for n,v in manifest['files'].items():
   bounded();name=PurePosixPath(n);need(not name.is_absolute() and '..' not in name.parts and '\\' not in n and ':' not in n,'bounded raw member');p=root/n;need(sha(p)==v['sha256'] and p.stat().st_size==v['bytes'],'raw bytes '+n)
  for n,v in build['unchanged_helpers'].items():need(sha(Path(a.helper_root)/n)==v,'unchanged original functional body '+n)
  need(load(root/'observer-limit-controls.log')=={'capture_limit_checks':8,'passed':True},'bounded observer protocol controls')
  need(origin['harness_sha256']==sha(root/'product/native-source/native_full.py'),'executed native entry source')
  need(origin['observer_source_sha']==a.observer_source and origin['observer_sha256']==a.observer_sha256==sha(a.observer),'separately pinned observer executable/source')
  original=constants(Path(a.helper_root)/'tests/reader_perf_windows/verify_composition.py',{'REQUIRED_CHECKS','PROPOSED_METRICS'})
  need(original=={'REQUIRED_CHECKS':REQUIRED_CHECKS,'PROPOSED_METRICS':PROPOSED_METRICS},'unchanged full original verifier assertion inventory')
  diagnosis_contract=constants(Path(a.helper_root)/'tests/reader_perf_windows/diagnose_txt_import.py',{'BISECT_MIB','ORIGINAL'})
  need(diagnosis_contract['BISECT_MIB']==BISECT_MIB,'unchanged original bisect sizes')
  main={'records':load(root/'observations/per-launch.json'),'summary':load(root/'observations/summary.json')}
  inter={'records':load(root/'interactions/per-launch.json'),'summary':load(root/'interactions/summary.json'),'result':load(root/'interactions/interactions.json')}
  diag=load(root/'txt/diagnosis.json');result=coverage(main,inter,diag);summary=main['summary']
  need(diag['input']['parameters']==diagnosis_contract['ORIGINAL'],'unchanged TXT generator and wait parameters')
  proposals=summary['proposed_budgets'];need(proposals,'original budget proposals retained')
  for v in proposals:
   number=v.get('proposal_ms',v.get('proposal_bytes'));need(v['metric'] in PROPOSED_METRICS and v.get('basis') and type(number) is int and number>0,'original proposal schema')
  for name,document in [('observations',main),('interactions',inter)]:
   evidence=root/name;environment_assertions(root,document['summary'],origin,build,evidence)
   for n in ('per-launch.csv','samples.csv','memory.csv','environment.json','preparation.json'):need((evidence/n).stat().st_size>0,'original evidence file '+name+'/'+n)
   need(rows(evidence/'per-launch.jsonl')==document['records'],'all original launch JSONL rows')
   with (evidence/'memory.csv').open(encoding='utf-8') as f:mem=list(csv.DictReader(f))
   need(len(mem)>=len(document['records'])*10,'original memory sample coverage '+name)
  with (root/'observations/samples.csv').open(encoding='utf-8') as f:samples=list(csv.DictReader(f))
  need(len(samples)>=104 and {'book_page_turn','input_during_import'}<={r['op'] for r in samples},'original raw sample operation coverage')
  captures=origin['captures'];need(len(captures)==result['product_starts'] and Counter(e['stage'] for e in captures)=={'txt-diagnosis':4,'original-main':result['main_launches']+2,'original-interactions':12},'all original 78 (or conditional 66) native process starts')
  lifetimes=[rows(root/e['folder']/'driver.jsonl') for e in captures]
  need(all(v[0]['kind']=='process' and v[-1]['kind']=='close' for v in lifetimes) and all(a[-1]['qpc']<b[0]['qpc'] for a,b in zip(lifetimes,lifetimes[1:])),'independent non-overlapping product lifetimes, allowing OS PID reuse')
  need(len(origin['steps'])==3 and [s['name'] for s in origin['steps']]==['txt-diagnosis','original-main','original-interactions'] and all(s['exit']==0 for s in origin['steps']),'all original stage bodies completed')
  for stage,document in [('original-main',main),('original-interactions',inter)]:
   entries={Path(e['log']).name:e for e in captures if e['stage']==stage};need(len(entries)==len(document['records'])+2,'unique native launch log binding')
   for r in document['records']:need(entries[r['launch_id']+'.log']['pid']==r['pid'],'every measured launch native PID binding')
   need({'prep-catalog.log','prep-reading.log'}<=set(entries),'both original preparations captured')
  need({Path(e['log']).name for e in captures if e['stage']=='txt-diagnosis'}=={'txt-00.log','txt-01.log','txt-02.log','bisect.log'},'all TXT and bisect launch bindings')
  pixels=imported('native_full_pixels',root/'product/native-source/pixels.py');replay=imported('native_full_replay',root/'product/native-source/replay.py');marker_check=imported('native_full_markers',root/'product/native-source/native_full.py').validate_picker_marker;body=[];ui=[];problems=[]
  for e in captures:
   bounded();folder=root/e['folder'];need(e['complete'] and e['process_exit']==0 and e['observer_exit']==0,'normal native launch/observer completion')
   native_rows=rows(folder/'native.jsonl');ready=[v for v in native_rows if v['kind']=='ready']
   need(len(ready)==1 and ready[0]['capture_limit_ms']==e['observer_limit_ms'] and 1<=e['observer_limit_ms']<=5400000,'explicit bounded observer interval')
   driver=rows(folder/'driver.jsonl')
   for req in [v for v in driver if v['kind']=='picker_request']:
    bound={kind:[v for v in driver if v['kind']==kind and v.get('request')==req['request']] for kind in ('picker_dialog','picker_closed','picker_cua_complete')}
    need(all(len(v)==1 for v in bound.values()) and req['qpc']<=bound['picker_dialog'][0]['qpc']<=bound['picker_closed'][0]['qpc']<=bound['picker_cua_complete'][0]['qpc'],'real owned picker and completion chronology')
    complete=bound['picker_cua_complete'][0];marker_check(req,complete['marker'],e['pid'],complete['qpc'])
    need(load(req['complete_file'])==complete['marker'] and Path(req['path']).resolve().is_relative_to(root) and sha(req['path'])==req['sha256'] and Path(req['path']).stat().st_size==req['bytes'],'original input and retained real CUA marker bytes')
   document=load(folder/'product-native-trace.json');need(document['pid']==e['pid'] and document['frequency']==e['frequency'],'native trace process/QPC binding')
   native=json.loads(json.dumps(replay.replay(document)));need(native==e['native_analysis']==load(folder/'native-analysis.json'),'all retained native candidate/tail rows replayed')
   value=pixels.analyze(folder,{**e,'program_sha256':build['program_sha256']},type('Checks',(),{'rows':staticmethod(rows),'need':staticmethod(need),'sha':staticmethod(sha),'save':staticmethod(lambda path,v:None)}))
   save(output/(e['folder']+'-pixels.json'),value)
   expected=e['expected_reader'] or native['reader_produced']>0;available=value['distinct_content_frames'].get(123,0);status=reader_body(expected,e.get('reader_locator'),available)
   body.append({'capture':e['index'],'stage':e['stage'],'log':Path(e['log']).name,'expected_reader':expected,'reader_locator':e.get('reader_locator'),'reader_nonuniform_frames':available,'reader_body':status,'uniform_reader_observations':value['uniform_regions'][123]})
   if status=='missing':problems.append(e['folder']+': applicable reader body missing')
   ui.append({'capture':e['index'],'all_generation_candidates':native['reader_native_ui_frame_candidates'],'all_paints_retained':native['reader_paints'],'reader_missing':native['reader_missing'],'ui_start_missing':native['reader_native_ui_start_missing'],'shelf_full_census_proven':False})
  result.update(execution='local-native',analyzer_sha256=sha(__file__),source_sha=origin['source_sha'],producer_artifact=producer['id'],raw_manifest_sha256=a.manifest_sha256,raw_files=len(manifest['files']),body=body,native_ui=ui,all_original_content_checks_passed=not problems,problems=problems,original_ci_identity_layer_impersonated=False,all_ui_frame_census_complete=False,f08_accepted=False)
  save(output/'audit.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('body','native_ui')}));return not problems
 except BaseException as error:
  save(output/'audit-failure.json',{'all_original_content_checks_passed':False,'f08_accepted':False,'error':repr(error)});raise

def self_test():
 import copy
 def launch(kind,index):
  ops={'first_screen':{'first_screen_interactive_ms':1}}
  if kind in ('cold_shelf','warm_shelf'):ops.update(shelf_next_page={'rows_after':100},search={'rows':50},search_clear={'rows':50},reset_top=True)
  elif kind=='reading':
   ops['page_turns']=[{} for _ in range(8)]
   if index:ops['resume']={'verified':True,'ms':1}
  else:ops['import']={'visible':True,'fixture_sha256':'fixed','busy_input_samples':1}
  return {'cohort':kind,'ok':True,'faults':[],'window_ms':1,'ops':ops,'peak':{'peak_working_set_bytes':1},'profile_strategy':'fresh-sdk-library-copy' if kind in ('cold_shelf','import','import_epub') else 'shared-profile'}
 diag={'verdict':'consistent','runs':[{'facts':{'fixture':{'id':1},'import':{'seen':True},'catalog':{},'probes':{'x':1}}} for _ in range(3)],'bisect':{'imports':[{'declared_mib':m,'sha256':'fixed','bytes':1,'catalog':{},'completed':True,'status_indicates_failure':False} for m in BISECT_MIB]}}
 records=[launch(kind,i) for kind in COHORTS for i in range(12)]
 summary={'schema':1,'cohorts':dict(Counter(r['cohort'] for r in records)),'measured_process_starts':60,'preparation_process_starts':2,'process_starts_total':62,'complete':True,'problems':[],'checks':{k:True for k in REQUIRED_CHECKS},'checks_passed':20,'checks_total':20,'performance_accepted':False,'budget_enforced':False,'frame_time':{'measured':False,'reason':'original non-frame channel'},'txt_path':{'diagnosis':diag,'verdict':diag['verdict'],'fixture':{'sha256':'fixed','bytes':1,'parameters':{}}}}
 main={'records':records,'summary':summary}
 inter={'records':[launch(c,i) for c in ('warm_shelf','reading') for i in range(5)],'summary':{'schema':1,'measured_process_starts':10,'preparation_process_starts':2,'process_starts_total':12},'result':{'faults':[],'font_order':['bigger-first']*5,**{k:[1]*n for k,n in {'shelf_scroll_down':15,'shelf_scroll_up':15,'font_bigger':10,'font_smaller':10}.items()}}}
 need(coverage(main,inter,diag)['product_starts']==78,'positive complete original 78-start plan')
 conditional=copy.deepcopy(main);rejected=copy.deepcopy(diag);rejected['verdict']='import_rejected';conditional['records']=[r for r in conditional['records'] if r['cohort']!='import'];cs=conditional['summary'];cs.update(measured_process_starts=48,process_starts_total=50,cohorts=dict(Counter(r['cohort'] for r in conditional['records'])),skipped_cohorts={'import':'original rejection'});cs['txt_path'].update(diagnosis=rejected,verdict='import_rejected')
 need(coverage(conditional,inter,rejected)['product_starts']==66,'positive original conditional 66-start plan')
 controls=[('missing launch',lambda m,i,d:m['records'].pop()),('missing page',lambda m,i,d:m['records'][24]['ops']['page_turns'].pop()),('wrong resume',lambda m,i,d:m['records'][25]['ops']['resume'].update(verified=False)),('missing busy import',lambda m,i,d:m['records'][36]['ops']['import'].update(busy_input_samples=0)),('missing bisect input',lambda m,i,d:d['bisect']['imports'].pop()),('missing original check',lambda m,i,d:m['summary']['checks'].pop(REQUIRED_CHECKS[0])),('false TXT skip',lambda m,i,d:m['summary'].update(skipped_cohorts={'import':'requested'})),('missing interaction turn',lambda m,i,d:i['records'][5]['ops']['page_turns'].pop()),('missing interaction launch',lambda m,i,d:i['records'].pop()),('interaction fault',lambda m,i,d:i['result']['faults'].append('real failure')),('nonfinite interaction',lambda m,i,d:i['result']['font_bigger'].__setitem__(0,float('nan')))]
 for label,mutate in controls:
  m,i,d=copy.deepcopy((main,inter,diag));mutate(m,i,d)
  try:coverage(m,i,d)
  except (ValueError,KeyError):continue
  raise AssertionError(label+' accepted')
 need(reader_body(False,None,0)=='not_applicable' and reader_body(True,{'valid':True},1)=='present' and reader_body(True,None,10)=='missing' and reader_body(True,{'valid':True},0)=='missing','reader applicability and missing/unknown pixels')
 from native_full import validate_picker_marker
 request={'request':0,'qpc':10};marker={'request':0,'pid':7,'qpc':20,'computer_use_returned':True,'post_action_refresh_returned':True}
 validate_picker_marker(request,marker,7,30)
 for change in ({'pid':8},{'request':1},{'qpc':9},{'qpc':31},{'computer_use_returned':False},{'post_action_refresh_returned':False}):
  try:validate_picker_marker(request,{**marker,**change},7,30)
  except ValueError:continue
  raise AssertionError('false CUA marker accepted')
 import tempfile
 with tempfile.TemporaryDirectory(prefix='f08-native-audit-controls-') as temporary:
  root=Path(temporary);product=root/'product';product.mkdir();expected='1'*40
  payloads={'build-identity.json':json.dumps({'source_sha':expected}).encode(),'program/EXReader.exe':b'explicit test-only payload'}
  manifest={'source_sha':expected,'run_id':'12','files':{n:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for n,v in payloads.items()}}
  payloads['manifest.json']=json.dumps(manifest).encode();archive=root/'build.zip';metadata=root/'metadata.json'
  with zipfile.ZipFile(archive,'w') as z:
   for name,value in payloads.items():
    z.writestr(name,value);path=product/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
  meta={'size_in_bytes':archive.stat().st_size,'digest':'sha256:'+sha(archive),'workflow_run':{'head_sha':expected,'id':12}};save(metadata,meta)
  artifact(root,archive,metadata,expected)
  def rejected(label):
   try:artifact(root,archive,metadata,expected)
   except ValueError:return
   raise AssertionError(label+' accepted')
  save(metadata,{**meta,'digest':'sha256:'+'0'*64});rejected('wrong archive digest');save(metadata,meta)
  save(metadata,{**meta,'workflow_run':{'head_sha':'2'*40,'id':12}});rejected('wrong source');save(metadata,meta)
  (product/'program/EXReader.exe').write_bytes(b'changed');rejected('changed retained binary');(product/'program/EXReader.exe').write_bytes(payloads['program/EXReader.exe'])
  extra=product/'extra';extra.write_bytes(b'extra');rejected('unlisted producer payload');extra.unlink()
  original=archive.read_bytes();archive.write_bytes(original+b'changed');rejected('changed ZIP bytes');archive.write_bytes(original)
 print(json.dumps({'artifact_negative_controls':5,'picker_barrier_negative_controls':6,'coverage_controls_passed':True,'positive_default_product_starts':78,'positive_original_conditional_product_starts':66,'negative_controls':len(controls),'reader_body_controls':4,'f08_accepted':False}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true')
 for n in ('run','helper-root','output','zip','metadata','expected-source','manifest-sha256','observer','observer-source','observer-sha256'):p.add_argument('--'+n)
 a=p.parse_args()
 if a.self_test:self_test()
 else:
  need(all(getattr(a,n.replace('-','_')) for n in ('run','helper-root','output','zip','metadata','expected-source','manifest-sha256','observer','observer-source','observer-sha256')),'independently pinned audit inputs')
  raise SystemExit(0 if audit(a) else 1)
