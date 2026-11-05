"""No partial, source-only, wrong-program or false-focus six-platform grants."""
import copy,hashlib
from common import TARGETS,ACTIONS

def validate(e,host,sha,run,attempt):
 assert e['harness_sha']==sha and e['host']==host and e['target_sha']==TARGETS[host]
 assert e['run_id']==run and e['attempt']==attempt
 assert e['keyboard_accepted'] is False and e['complete_product'] is False and e['screen_reader_accepted'] is False
 assert e['executions'] and len({x['name'] for x in e['executions']})==len(e['executions'])
 if e['accepted']:assert e['programs'] and all(x['returncode']==0 for x in e['executions'])

def grant(matrix):
 assert set(matrix)==set(TARGETS),'missing or extra target'
 for host,e in matrix.items():
  assert e['target_sha']==TARGETS[host] and e['program_verified'] is True
  rows=e['actions'];assert len(rows)==len(ACTIONS) and {r['action'] for r in rows}==set(ACTIONS),'partial or duplicated action list'
  for row in rows:
   assert row['result']=='passed' and row['exposed'] is True and row['executed'] is True
   assert row['input']!='source-only'
   if row['action'] in ('search','directory','records','settings'):assert row.get('focused_inside') is True and row.get('focus_visible') is True and row.get('focus_enabled') is True
  assert e.get('physical_keyboard_accepted',False) is False,'pointer/emulator input cannot grant physical keyboard'
 return True

def verify_bytes(raw,value):assert len(raw)==value['bytes'] and hashlib.sha256(raw).hexdigest()==value['sha256']
def selftest():
 good={host:dict(target_sha=sha,program_verified=True,actions=[dict(action=k,result='passed',exposed=True,executed=True,input='native',focused_inside=True,focus_visible=True,focus_enabled=True) for k in ACTIONS]) for host,sha in TARGETS.items()};assert grant(good)
 cases=[]
 def corrupt(name,change):
  bad=copy.deepcopy(good);change(bad)
  try:grant(bad)
  except (AssertionError,KeyError):cases.append(dict(name=name,rejected=True));return
  raise AssertionError('corrupt complete matrix accepted: '+name)
 corrupt('missing-target',lambda x:x.pop('ipad'))
 corrupt('source-declaration-only',lambda x:x['gtk']['actions'][0].update(input='source-only',executed=False))
 corrupt('touch-as-keyboard',lambda x:x['iphone'].update(physical_keyboard_accepted=True))
 corrupt('main-window-focus-as-modal',lambda x:x['windows']['actions'][6].update(focused_inside=False))
 corrupt('duplicate-action',lambda x:x['android']['actions'].__setitem__(1,x['android']['actions'][0]))
 corrupt('wrong-program',lambda x:x['macos'].update(program_verified=False))
 corrupt('partial-report',lambda x:x['gtk']['actions'].pop())
 corrupt('failed-action',lambda x:x['windows']['actions'][0].update(result='failed'))
 corrupt('invisible-focus',lambda x:x['gtk']['actions'][6].update(focus_visible=False))
 corrupt('wrong-source',lambda x:x['ipad'].update(target_sha='0'*40))
 return cases
if __name__=='__main__':print(selftest())
