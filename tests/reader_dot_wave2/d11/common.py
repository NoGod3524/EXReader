"""Actions-only semantic observations. Unknown is never a behavioral pass."""
import hashlib,json,os,pathlib,sqlite3,subprocess
TARGETS={'windows':'9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08','gtk':'803098e9df1a365a9b8e206805c2d179aca8501f','android':'4a04a9cc74dde67f755c87e87b278d63a254a3ac','macos':'15dab6b2270dc296ed6239db67ced2e22d255e65','iphone':'5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a','ipad':'5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a'}
ACTIONS=('back','resume','import','cancel','next','previous','search','directory','records','settings','close.search','close.directory','close.records','close.settings','disabled_noop','continue_after_return','no_unexpected_revision')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def identity(host):
 assert os.environ.get('GITHUB_ACTIONS')=='true'
 target=subprocess.check_output(['git','-C','target','rev-parse','HEAD'],text=True).strip();assert target==TARGETS[host]
 return dict(host=host,target_sha=target,harness_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])
def pending(host):return {k:dict(action=k,exposed=None,enabled=None,executed=False,result='pending',input=None,focus=None,reason='not reached') for k in ACTIONS}
def database_inventory(root):
 result={}
 for p in pathlib.Path(root).rglob('*.sqlite*'):
  if not p.is_file() or p.name.endswith(('-wal','-shm','-journal')):continue
  try:
   db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
   tables=[r[0] for r in db.execute("select name from sqlite_master where type='table'") if 'revision' in r[0] or 'outbox' in r[0]]
   result[p.name]={t:repr(db.execute('select * from "'+t.replace('"','""')+'" order by rowid').fetchall()) for t in tables};db.close()
  except sqlite3.Error as e:result[p.name]={'error':str(e)}
 return result
