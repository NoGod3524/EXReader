"""Small strict report identity gate; no host behavior is manufactured here."""
import copy,hashlib
TARGETS={'windows':'eab342ef456be4a8a1811e5249e3c217d906ce8a','gtk':'57203a52aee439be5194ee0a4b13563a975e8daf','android':'4a04a9cc74dde67f755c87e87b278d63a254a3ac','macos':'15dab6b2270dc296ed6239db67ced2e22d255e65','iphone':'72c6bbdd14ebf3be453fa7f0da81119d52675eb5','ipad':'72c6bbdd14ebf3be453fa7f0da81119d52675eb5'}
def validate(e,host,sha,run,attempt):
 assert e['harness_sha']==sha and e['host']==host and e['target_sha']==TARGETS[host]
 assert e['run_id']==run and e['attempt']==attempt
 assert e['keyboard_accepted'] is False and e['complete_product'] is False and e['screen_reader_accepted'] is False
 assert e['executions'] and len({x['name'] for x in e['executions']})==len(e['executions'])
 if e['accepted']:assert e['programs'] and all(x['returncode']==0 for x in e['executions'])
def verify_bytes(data,identity):
 assert len(data)==identity['bytes'] and hashlib.sha256(data).hexdigest()==identity['sha256']
def selftest():
 good=dict(harness_sha='h',host='windows',target_sha=TARGETS['windows'],run_id='r',attempt='1',keyboard_accepted=False,complete_product=False,screen_reader_accepted=False,executions=[dict(name='actual',returncode=0)],programs={'actual':{'sha256':'a'*64}},accepted=True)
 validate(good,'windows','h','r','1')
 cases=[dict(harness_sha='other'),dict(target_sha='other'),dict(host='gtk'),dict(run_id='other'),dict(attempt='2'),dict(executions=[]),dict(executions=good['executions']*2),dict(programs={}),dict(complete_product=True),dict(keyboard_accepted=True),dict(executions=[dict(name='actual',returncode=1)])]
 for patch in cases:
  bad=copy.deepcopy(good);bad.update(patch)
  try:validate(bad,'windows','h','r','1')
  except (AssertionError,KeyError):continue
  raise AssertionError('admitted corrupted identity: '+repr(patch))
 identity={'bytes':4,'sha256':hashlib.sha256(b'good').hexdigest()};verify_bytes(b'good',identity)
 for data in (b'bad',b'evil'):
  try:verify_bytes(data,identity)
  except AssertionError:continue
  raise AssertionError('admitted tampered bytes')
 return len(cases)+2
if __name__=='__main__':print('D06 strict negative controls:',selftest())
