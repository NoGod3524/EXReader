"""Actions-only raw3 actual-host bundle identity, original bytes and complete graph."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

assert os.environ.get('GITHUB_ACTIONS') == 'true'
def sha(data):return hashlib.sha256(data).hexdigest()
def pairs(items):
 out={}
 for key,value in items:
  assert key not in out;out[key]=value
 return out
def parse(data):return json.loads(data.decode('utf-8'),object_pairs_hook=pairs)
def safe(name):
 path=PurePosixPath(name);assert isinstance(name,str) and name and not path.is_absolute() and '\\' not in name and ':' not in name and all(part not in ('','.','..') for part in name.split('/'));return name
def verify(read):
 raw=read('manifest.json');manifest=parse(raw);assert manifest['schema']==1
 peer=manifest['sender'];assert peer['platform'] in ('android','macos') and peer['exr_version']=='3.41.0'
 assert len(peer['source_sha'])==40 and str(peer['run_id']).isdigit() and str(peer['attempt']).isdigit()
 assert len(peer['sdk_dso_sha256'])==64
 assert len(peer['apk_sha256'] if peer['platform']=='android' else peer['program_sha256'])==64
 assert peer['parser_version']==('exreader-sdk-3.41.0' if peer['platform']=='android' else '3.41.0')
 originals={};files={'manifest.json'}
 for row in manifest['originals']:
  assert row['role'] not in originals and row['format']==row['role'] and row['role'] in ('txt','epub','pdf','cbz')
  name=safe(row['file']);assert name.startswith('originals/') and name not in files;files.add(name);data=read(name)
  assert 0<len(data)<=32*1024**2 and len(data)==row['bytes'] and sha(data)==row['sha256'] and row['book_key']==row['format']+':'+sha(data);originals[row['role']]=row
 assert set(originals)=={'txt','epub','pdf','cbz'}
 revisions={};wire_objects={};book_keys={row['book_key'] for row in originals.values()}
 for row in manifest['revisions']:
  name=safe(row['file']);assert name.startswith('revisions/') and name not in files;files.add(name);data=read(name);wire=parse(data)
  assert 0<len(data)<=1048576 and len(data)==row['bytes'] and sha(data)==row['sha256'] and row['id'] not in revisions
  assert row['id']==wire['id'] and row['entity_kind']==wire['entity_kind'] and row['entity_key']==wire['entity_key'] and row['parents']==wire['parents']
  assert len(row['id'])==32 and all(c in '0123456789abcdef' for c in row['id']) and row['book_key'] in book_keys
  if row['entity_kind']=='book':assert row['entity_key']==row['book_key']
  else:assert row['entity_kind'] in ('progress','annotation') and wire['payload']['book_key']==row['book_key']
  revisions[row['id']]=row;wire_objects[row['id']]=wire
 assert 4<=len(revisions)<=100
 visiting=set();visited=set()
 def walk(key):
  assert key not in visiting
  if key in visited:return
  visiting.add(key);row=revisions[key]
  for parent in row['parents']:
   assert parent in revisions and revisions[parent]['entity_kind']==row['entity_kind'] and revisions[parent]['entity_key']==row['entity_key'];walk(parent)
  visiting.remove(key);visited.add(key)
 for key in revisions:walk(key)
 assert {row['book_key'] for row in revisions.values() if row['entity_kind']=='book'}==book_keys
 coverage=set()
 for row in manifest['reading_records']:
  wire=wire_objects[row['revision_id']];capture=row['capture'];location=wire['payload']['location'];selector=location['selector'];mode={'reflow_global':1,'epub_chapter':2,'fixed_page':3}[location['mode']]
  assert row['role'] in originals and row['kind'] in ('progress','bookmark','highlight')
  assert wire['entity_kind']==('progress' if row['kind']=='progress' else 'annotation')
  assert row['mode']==mode==int(capture['numbers'][0]) and row['anchor_version']==location['anchor_version']
  assert capture['route'][0]==wire['payload']['book_key']==originals[row['role']]['book_key'] and capture['route'][1]==location['parser_version']==peer['parser_version']
  assert int(capture['numbers'][2])==selector['start'] and int(capture['numbers'][3])==selector['end']
  assert selector['end']>=selector['start'] and (row['kind']=='highlight')==(selector['end']>selector['start'])
  for index,key in enumerate(('exact','prefix','suffix')):
   copied=None if capture['selectors'][index] is None else base64.b64decode(capture['selectors'][index],validate=True)
   if location['anchor_version']==3:
    assert mode==3 and set(selector[key])=={'base64','size'}
    item=selector[key];assert type(item['size']) is int and 0<=item['size']<=(65536 if index==0 else 128)
    declared=None if item['base64'] is None else base64.b64decode(item['base64'],validate=True)
    assert item['size']==(0 if declared is None else len(declared))
    if declared is not None:assert base64.b64encode(declared).decode()==item['base64'];declared.decode('utf-8')
   else:
    assert location['anchor_version'] in (1,2)
    declared=None if selector[key] is None else selector[key].encode('utf-8')
   assert copied==declared
  if mode==2:assert capture['route'][2]==location['part_path'] and int(capture['numbers'][1])==location['part']
  if mode==3:assert capture['route'][3]==location['page_id'] and int(capture['numbers'][1])==location['page']
  coverage.add((row['role'],row['kind']))
 required={(role,kind) for role in originals for kind in ('progress','bookmark')}|{(role,'highlight') for role in ('txt','epub','pdf')}
 assert required<=coverage
 return {'manifest':manifest,'manifest_sha256':sha(raw),'files':sorted(files),'originals':len(originals),'revisions':len(revisions),'reading_records':len(manifest['reading_records']),'complete_graph':True}
def folder(path):
 root=Path(path)
 def read(name):
  file=root/safe(name);assert file.is_file() and not file.is_symlink();return file.read_bytes()
 return verify(read)

def verify_null(read):
 raw=read('manifest.json');manifest=parse(raw)
 assert manifest['schema']==1 and manifest['purpose']=='authentic-apple-null-negative'
 original,=manifest['originals'];assert original['role']==original['format']=='pdf'
 data=read(safe(original['file']));assert len(data)==original['bytes']==8845 and sha(data)==original['sha256']=='5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
 assert original['book_key']=='pdf:'+original['sha256']
 files={'manifest.json',original['file']};wires={}
 for row in manifest['revisions']:
  name=safe(row['file']);assert name not in files;files.add(name);body=read(name);wire=parse(body)
  assert len(body)==row['bytes'] and sha(body)==row['sha256'] and wire['id']==row['id'] and row['id'] not in wires
  assert all(row[k]==wire[k] for k in ('entity_kind','entity_key','parents')) and row['book_key']==original['book_key']
  assert wire['entity_kind'] in ('annotation','book') and (wire['entity_key']==original['book_key'] if wire['entity_kind']=='book' else wire['payload']['book_key']==original['book_key'])
  wires[row['id']]=wire
 assert 3<=len(wires)<=100
 visiting=set();visited=set()
 def walk(key):
  assert key not in visiting
  if key in visited:return
  visiting.add(key);wire=wires[key]
  for parent in wire['parents']:
   assert parent in wires and all(wires[parent][k]==wire[k] for k in ('entity_kind','entity_key'));walk(parent)
  visiting.remove(key);visited.add(key)
 for key in wires:walk(key)
 selected=wires[manifest['null_revision']];assert selected['entity_kind']=='annotation' and selected['payload']['annotation_id']==manifest['annotation_id']
 location=selected['payload']['location'];assert location['anchor_version']==3 and location['mode']=='fixed_page' and location['selector']['exact']=={'base64':None,'size':0}
 assert selected['parents'] and any(w['entity_kind']=='book' for w in wires.values())
 assert not any(manifest['null_revision'] in w['parents'] for w in wires.values())
 return {'manifest':manifest,'manifest_sha256':sha(raw),'files':sorted(files),'revisions':len(wires),'null_revision':manifest['null_revision'],'complete_graph':True}

def null_folder(path):
 root=Path(path)
 def read(name):
  file=root/safe(name);assert file.is_file() and not file.is_symlink();return file.read_bytes()
 return verify_null(read)
