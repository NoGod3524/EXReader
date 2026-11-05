import copy,hashlib
def controls(cross,ui):
 from verify import cross_check
 results=[]
 for name,reason in (('signal','actual SIGKILL'),('target','published target preserved'),
  ('pending','C02 pending state'),('requests','cleanup only'),('early-release','asynchronous custody'),
  ('release','final join before release')):
  c=copy.deepcopy(cross);u=copy.deepcopy(ui);rows={r['name']:r for r in c['rows']}
  if name=='signal':rows['04-migrator-pending-survives-death']['returncode']=0
  elif name=='target':rows['02-reader-excludes-migrator']['target_after']['ino']+=1
  elif name=='pending':
   r=rows['04-migrator-pending-survives-death']
   for key in ('pending_before','pending_after_death'):
    row=r[key]['state'];raw=bytes.fromhex(row['bytes_hex'])[:-368]
    row.update(bytes_hex=raw.hex(),size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
  elif name=='requests':next(r for r in u['records'] if r['name']=='gtk-cleanup-only-retry')['request_count_after']+=1
  elif name=='early-release':rows['03-network-and-close-retain-lease']['active_refusal']['returncode']=0
  else:rows['03-network-and-close-retain-lease']['after_final_join']['returncode']=2
  try:cross_check(c,u)
  except AssertionError as e:
   assert str(e)==reason,(name,str(e))
   results.append(dict(name=name,rejected=True,reason=str(e)))
  else:raise AssertionError('negative accepted '+name)
 return results
