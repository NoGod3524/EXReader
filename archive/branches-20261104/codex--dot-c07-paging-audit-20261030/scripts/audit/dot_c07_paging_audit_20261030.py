#!/usr/bin/env python3
"""Actions-only C07 additive evidence audit; not independent API execution."""
import copy, hashlib, importlib.util, io, json, os, pathlib, re, sqlite3
import subprocess, tempfile, urllib.request, zipfile
from pathlib import Path, PurePosixPath

SOURCE='7f15fe49374cd9389e2106837351d4bbd5e56113'
RUN='41134343005'
ATTEMPT='1'
ART='13016305109'
DIGEST='0c926a7cdc47e6a870d0ee237c6c3de4b3e794713f9d8f7d0c2db03f4b76ba38'
SIZE=1011359
BASE='2b5222ad2af4c92e7f239d6ab4d355fba6859974'
ROOT='f05-paging-evidence/'
FILES=('calls.jsonl','setup.jsonl','catalog.sqlite','result.json')
LIMIT=256*1024*1024
EXPECT={'sha':SOURCE,'run_id':RUN,'attempt':ATTEMPT,'artifact_id':ART}
def sha(b): return hashlib.sha256(b).hexdigest()
class Reject(Exception): pass
def need(ok,rule):
    if not ok: raise Reject(rule)
def strict_json(data):
    def pairs(values):
        d={}
        for k,v in values:
            need(k not in d,'json.duplicate_key')
            d[k]=v
        return d
    def constant(value): raise Reject('json.nonfinite')
    try: return json.loads(data.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
    except Reject: raise
    except Exception: raise Reject('json.parse')
def lines(data):
    need(len(data)<=1048576,'json.size')
    chunks=data.splitlines()
    need(all(chunks),'json.parse')
    return [strict_json(x) for x in chunks]
def strict_zip(raw):
    out={}; names=set(); canonical=set(); total=0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        need(len(infos)<=500,'zip.members')
        for info in infos:
            name=info.filename
            need(name not in names,'zip.duplicate_raw'); names.add(name)
            normalized=str(PurePosixPath(name.replace('\\','/')))
            need(normalized not in canonical,'zip.canonical_collision')
            canonical.add(normalized)
            p=PurePosixPath(normalized)
            need(not p.is_absolute() and '..' not in p.parts and ':' not in p.parts[0]
                 and '\x00' not in name and '\\' not in name,'zip.path')
            need((info.external_attr>>16)&0o170000!=0o120000,'zip.symlink')
            if info.is_dir(): continue
            total+=info.file_size
            need(total<=LIMIT,'zip.bytes')
            out[normalized]=z.read(info)
    return out
def pick(files,name):
    matches=[v for k,v in files.items() if k==ROOT+name or k.endswith('/'+ROOT+name)]
    need(len(matches)==1,'files.unique')
    return matches[0]
def key(i): return 'txt:'+format(i,'064x')
def db_check(raw,setup):
    need(len(raw)<=LIMIT,'db.size')
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'catalog.sqlite'; path.write_bytes(raw)
        con=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            con.enable_load_extension(False)
            con.execute('PRAGMA trusted_schema=OFF')
            need(con.execute('PRAGMA application_id').fetchone()==(1163416144,),'db.identity')
            need(con.execute('PRAGMA user_version').fetchone()==(3,),'db.identity')
            for name in ('reader_books','reader_local_books','reader_revisions','reader_outbox'):
                need(con.execute('SELECT type FROM sqlite_master WHERE name=?',(name,)).fetchall()==[('table',)],'db.tables')
            need(con.execute('PRAGMA quick_check').fetchall()==[('ok',)],'db.integrity')
            need(not con.execute('PRAGMA foreign_key_check').fetchall(),'db.integrity')
            books=con.execute('SELECT book_key,format,source_sha256,source_bytes,title,author,sort_title,favorite,deleted FROM reader_books ORDER BY book_key').fetchmany(52)
            expected=[(key(i),'txt',format(i,'064x'),123,'Synthetic paging row','Author','Sort',0,1) for i in range(1,52)]
            need(books==expected,'db.books')
            need(not con.execute('SELECT book_key FROM reader_local_books LIMIT 1').fetchall(),'db.no_sdk_mapping')
            revisions=con.execute('SELECT revision_id,entity_kind,entity_key,operation,CAST(body_json AS BLOB),body_sha256 FROM reader_revisions').fetchmany(103)
            need(len(revisions)==102,'db.revision_count')
            by_id={r[0]:r for r in revisions}
            need(len(by_id)==102,'db.revision_ids')
            for record in setup:
                rid=record['revision_id']
                need(rid in by_id,'db.setup_identity')
                _,kind,k,op,wire,digest=by_id[rid]
                need(sha(wire)==digest,'db.wire_hash')
                obj=strict_json(wire)
                operation=record['operation'].lower()
                need((kind,k,op)==('book',record['book_key'],operation),'db.wire_identity')
                need(obj.get('id')==rid and obj.get('entity_kind')==kind and obj.get('entity_key')==k
                     and obj.get('operation')==op and type(obj.get('version')) is int and obj['version']==1
                     and obj.get('location_kind')=='none','db.wire_identity')
                need(obj.get('parents')==record['expected_heads'],'db.parents')
                if op=='delete':
                    need(obj.get('payload') is None,'db.payload')
                else:
                    payload={'format':'txt','source_sha256':k[4:],'source_bytes':123,
                             'title':'Synthetic paging row','author':'Author','favorite':False}
                    need(obj.get('payload')==payload and obj['payload']['favorite'] is False,'db.payload')
            outbox=con.execute('SELECT revision_id,attempts,last_error FROM reader_outbox').fetchmany(103)
            need(len(outbox)==102 and {r[0] for r in outbox}==set(by_id)
                 and all(r[1:]==(0,'') for r in outbox),'db.outbox')
        finally: con.close()


def paging(files):
    manifest=strict_json(pick(files,'paging-manifest.json'))
    need(type(manifest.get('schema')) is int and manifest['schema']==1,'manifest.schema')
    need(manifest.get('source_sha')==SOURCE,'manifest.source')
    need(str(manifest.get('run_id'))==RUN,'manifest.run')
    need(type(manifest.get('attempt')) is int and manifest['attempt']==1,'manifest.attempt')
    need(manifest.get('complete') is True and manifest.get('paging_outcome')=='success'
         and manifest.get('claim_scope')=='installed_synthetic_api'
         and manifest.get('gtk_claim') is False and manifest.get('sdk_original_claim') is False,'manifest.scope')
    data={}
    for name in FILES:
        data[name]=pick(files,name)
        item=manifest.get('files',{}).get(name,{})
        need(item.get('bytes')==len(data[name]) and item.get('sha256')==sha(data[name]),'manifest.file_hash')
    setup=lines(data['setup.jsonl'])
    need(len(setup)==102,'setup.count')
    ids=set()
    for index,item in enumerate(setup):
        need(type(item.get('schema')) is int and item['schema']==1 and item.get('type')=='typed_command','setup.schema')
        need(type(item.get('seq')) is int,'json.integer_type')
        need(item['seq']==index+1,'setup.sequence')
        op='PUT' if index%2==0 else 'DELETE'
        need(item.get('operation')==op,'setup.operation')
        need(item.get('book_key')==key(index//2+1),'setup.key')
        parent=[] if op=='PUT' else [setup[index-1]['revision_id']]
        need(item.get('expected_heads')==parent,'setup.parents')
        rid=item.get('revision_id')
        need(isinstance(rid,str) and re.fullmatch('[0-9a-f]{32}',rid) is not None and rid not in ids,'setup.revision_id')
        ids.add(rid)
        need(type(item.get('return_code')) is int and item['return_code']==0
             and item.get('created') is True and item.get('applied') is True,'setup.success')
    calls=lines(data['calls.jsonl'])
    need(len(calls)==9,'calls.count')
    names=['removed_first','removed_second','removed_end','visible_find_deleted','retained_find_deleted',
           'reject_zero_limit','reject_over_limit','reject_empty_cursor','owner_gate_reentry']
    after=[None,key(50),key(51),None,None,None,None,'',None]
    limits=[50,50,50,None,None,0,101,50,50]
    keys=[[key(i) for i in range(1,51)],[key(51)],[],[],[key(1)],[],[],[],[key(i) for i in range(1,51)]]
    for i,item in enumerate(calls):
        seq=i+1
        need(type(item.get('schema')) is int and item['schema']==1 and item.get('type')=='catalog_call','calls.schema')
        need(type(item.get('seq')) is int,'json.integer_type')
        need(item['seq']==seq and item.get('id')==names[i],'calls.sequence')
        api='reader_catalog_find' if seq==4 else ('reader_catalog_retained_find' if seq==5 else 'reader_catalog_removed_page')
        need(item.get('api')==api,'calls.api')
        expected_input={'after_key':after[i],'limit':limits[i],'book_key':key(1) if seq in (4,5) else None,'query':None}
        need(item.get('input')==expected_input,'calls.input')
        actual_limit=item['input'].get('limit')
        need(actual_limit is None if limits[i] is None else type(actual_limit) is int,'json.integer_type')
        need(type(item.get('return_code')) is int,'json.integer_type')
        need(item['return_code']==(21 if seq in (6,7,8) else 0),'calls.return_code')
        err=item.get('error',{})
        need(type(err.get('code')) is int,'json.integer_type')
        need(err.get('code')==(21 if seq in (6,7,8) else 0)
             and err.get('message')==('Invalid bounded removed-book cursor' if seq in (6,7,8) else ''),'calls.error')
        rows=item.get('rows')
        need(isinstance(rows,list) and type(item.get('callback_count')) is int
             and item['callback_count']==len(rows),'calls.callback_count')
        need(len(rows)==len(keys[i]),'calls.rows')
        for j,row in enumerate(rows):
            need(type(row.get('callback_index')) is int and row['callback_index']==j
                 and row.get('book_key')==keys[i][j],'calls.keys')
            need(type(row.get('deleted')) is int and row['deleted']==1,'calls.deleted')
        before,found=(7,0) if seq==4 else ((0,1) if seq==5 else (None,None))
        need(item.get('found_before')==before and item.get('found_after')==found,'calls.found')
        for field,expected in (('found_before',before),('found_after',found)):
            need(item.get(field) is None if expected is None else type(item.get(field)) is int,'json.integer_type')
        need(item.get('gtk_claim') is False and item.get('sdk_original_claim') is False
             and item.get('claim_scope')=='installed_synthetic_api','calls.scope')
    need(type(calls[8].get('compare_with_seq')) is int,'json.integer_type')
    need(calls[8].get('compare_with_seq')==1 and calls[8].get('follows')==names[5:8]
         and calls[8]['rows']==calls[0]['rows'],'calls.gate')
    result=strict_json(data['result.json'])
    need(result.get('accepted') is True and result.get('checks')==9 and result.get('rows')==51
         and result.get('page_sizes')==[50,1,0] and result.get('gtk_claim') is False
         and result.get('sdk_original_claim') is False,'calls.summary')
    db_check(data['catalog.sqlite'],setup)
    return {'api_calls':9,'typed_commands':102,'books':51,'revisions':102,'outbox':102,
            'scope':'installed synthetic API producer observations plus independent DB consistency'}

def dump(obj): return json.dumps(obj,separators=(',',':')).encode()
def reseal(files):
    m=strict_json(files[ROOT+'paging-manifest.json'])
    m['files']={n:{'bytes':len(files[ROOT+n]),'sha256':sha(files[ROOT+n])} for n in FILES if ROOT+n in files}
    files[ROOT+'paging-manifest.json']=dump(m)
    return files
def mutate_records(files,name,fn):
    records=lines(files[ROOT+name]);fn(records)
    files[ROOT+name]=b'\n'.join(dump(r) for r in records)+b'\n'
    return reseal(files)


def fixture(db_fault=None):
    setup=[]; books=[]; revisions=[]
    for i in range(1,52):
        k=key(i); put=format(2*i-1,'032x'); delete=format(2*i,'032x')
        books.append((k,'txt',format(i,'064x'),123,'Synthetic paging row','Author','Sort',0,1))
        for op,rid,parents in [('PUT',put,[]),('DELETE',delete,[put])]:
            setup.append({'schema':1,'type':'typed_command','seq':len(setup)+1,'operation':op,
                'book_key':k,'expected_heads':parents,'return_code':0,'created':True,'applied':True,'revision_id':rid})
            payload=None if op=='DELETE' else {'format':'txt','source_sha256':format(i,'064x'),'source_bytes':123,
                'title':'Synthetic paging row','author':'Author','favorite':False}
            wire=dump({'version':1,'id':rid,'entity_kind':'book','entity_key':k,'operation':op.lower(),
                       'location_kind':'none','parents':parents,'payload':payload})
            revisions.append((rid,'book',k,op.lower(),wire.decode(),sha(wire)))
    # Construct separate negative fixtures before INSERT; never disable immutable triggers.
    if db_fault=='wrong_deleted':
        books[0]=books[0][:-1]+(0,)
    elif db_fault=='foreign_parent':
        row=list(revisions[1]); obj=strict_json(row[4].encode())
        obj['parents']=[setup[2]['revision_id']]
        wire=dump(obj); row[4]=wire.decode(); row[5]=sha(wire); revisions[1]=tuple(row)
    elif db_fault=='raw_body_hash':
        row=list(revisions[0]); row[5]='0'*64; revisions[0]=tuple(row)
    elif db_fault is not None:
        raise ValueError('unknown fixture mutation')
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'synthetic.sqlite'; c=sqlite3.connect(path)
        for migration in ('001_catalog.sql','002_originals.sql','003_original_staging.sql'):
            sql=subprocess.check_output(['git','show',SOURCE+':apps/reader/store/'+migration],text=True)
            c.executescript(sql)
        c.executemany('INSERT INTO reader_books VALUES(?,?,?,?,?,?,?,?,?)',books)
        c.executemany('INSERT INTO reader_revisions VALUES(?,?,?,?,?,?)',revisions)
        c.executemany('INSERT INTO reader_outbox(revision_id,attempts,last_error) VALUES(?,0,?)',[(r[0],'') for r in revisions])
        c.commit();c.close();db=path.read_bytes()
    names=['removed_first','removed_second','removed_end','visible_find_deleted','retained_find_deleted',
           'reject_zero_limit','reject_over_limit','reject_empty_cursor','owner_gate_reentry']
    after=[None,key(50),key(51),None,None,None,None,'',None]
    limits=[50,50,50,None,None,0,101,50,50]
    resultkeys=[[key(i) for i in range(1,51)],[key(51)],[],[],[key(1)],[],[],[],[key(i) for i in range(1,51)]]
    calls=[]
    for i in range(9):
        seq=i+1;bad=seq in (6,7,8)
        before,found=(7,0) if seq==4 else ((0,1) if seq==5 else (None,None))
        rows=[{'callback_index':j,'book_key':k,'deleted':1} for j,k in enumerate(resultkeys[i])]
        item={'schema':1,'type':'catalog_call','seq':seq,'id':names[i],
          'api':'reader_catalog_find' if seq==4 else ('reader_catalog_retained_find' if seq==5 else 'reader_catalog_removed_page'),
          'input':{'after_key':after[i],'limit':limits[i],'book_key':key(1) if seq in (4,5) else None,'query':None},
          'return_code':21 if bad else 0,'error':{'code':21 if bad else 0,'message':'Invalid bounded removed-book cursor' if bad else ''},
          'found_before':before,'found_after':found,'callback_count':len(rows),'rows':rows,
          'claim_scope':'installed_synthetic_api','gtk_claim':False,'sdk_original_claim':False}
        if seq==9:item.update(follows=names[5:8],compare_with_seq=1)
        calls.append(item)
    files={ROOT+'setup.jsonl':b'\n'.join(dump(x) for x in setup)+b'\n',
           ROOT+'calls.jsonl':b'\n'.join(dump(x) for x in calls)+b'\n',ROOT+'catalog.sqlite':db,
           ROOT+'result.json':dump({'accepted':True,'checks':9,'rows':51,'page_sizes':[50,1,0],
                'gtk_claim':False,'sdk_original_claim':False}),
           ROOT+'paging-manifest.json':dump({'schema':1,'source_sha':SOURCE,'run_id':RUN,'attempt':1,
                'claim_scope':'installed_synthetic_api','gtk_claim':False,'sdk_original_claim':False,
                'paging_outcome':'success','complete':True})}
    return reseal(files)

def new_controls():
    base=fixture();paging(base)
    cases=[]
    def record(label,rule,fn):
        try:fn(); actual='accepted'
        except Reject as e:actual=str(e)
        except Exception as e:actual='unexpected:'+type(e).__name__+':'+str(e)
        cases.append({'control':label,'expected':rule,'actual':actual,'ok':actual==rule})
    def raw(label,rule,fn):
        f=dict(base);fn(f);reseal(f)
        record(label,rule,lambda:paging(f))
    raw('json_duplicate','json.duplicate_key',lambda f:f.__setitem__(ROOT+'calls.jsonl',f[ROOT+'calls.jsonl'].replace(b'{"schema":1',b'{"schema":1,"schema":1',1)))
    raw('json_bool_integer','json.integer_type',lambda f:mutate_records(f,'calls.jsonl',lambda r:r[0].update(seq=True)))
    raw('json_nonfinite','json.nonfinite',lambda f:f.__setitem__(ROOT+'calls.jsonl',f[ROOT+'calls.jsonl'].replace(b'{"schema":1',b'{"extra":NaN,"schema":1',1)))
    raw('json_truncated','json.parse',lambda f:f.__setitem__(ROOT+'calls.jsonl',f[ROOT+'calls.jsonl'][:-4]))
    for label,rule,names in [('zip_duplicate','zip.duplicate_raw',['a','a']),
         ('zip_canonical_collision','zip.canonical_collision',['a/b','a//b']),
         ('zip_traversal','zip.path',['../x'])]:
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:
            for name in names:z.writestr(name,b'x')
        record(label,rule,lambda data=buffer.getvalue():strict_zip(data))
    for field,value,rule in [('source_sha','0'*40,'manifest.source'),('run_id','0','manifest.run'),('attempt',2,'manifest.attempt')]:
        f=dict(base);m=strict_json(f[ROOT+'paging-manifest.json']);m[field]=value;f[ROOT+'paging-manifest.json']=dump(m)
        record('wrong_'+field,rule,lambda f=f:paging(f))
    f=dict(base);del f[ROOT+'calls.jsonl']
    record('missing_calls','files.unique',lambda:paging(f))
    def rec(label,name,rule,fn):
        f=dict(base);mutate_records(f,name,fn);record(label,rule,lambda:paging(f))
    rec('setup_short','setup.jsonl','setup.count',lambda r:r.pop())
    rec('setup_seq','setup.jsonl','setup.sequence',lambda r:r[1].update(seq=1))
    rec('setup_operation','setup.jsonl','setup.operation',lambda r:r[0].update(operation='DELETE'))
    rec('setup_key','setup.jsonl','setup.key',lambda r:r[2].update(book_key=key(1)))
    rec('setup_parent','setup.jsonl','setup.parents',lambda r:r[1].update(expected_heads=[r[2]['revision_id']]))
    rec('setup_reused_id','setup.jsonl','setup.revision_id',lambda r:r[1].update(revision_id=r[0]['revision_id']))
    rec('setup_unsuccessful','setup.jsonl','setup.success',lambda r:r[0].update(return_code=1))
    rec('call_short','calls.jsonl','calls.count',lambda r:r.pop())
    rec('cursor_wrong','calls.jsonl','calls.input',lambda r:r[1]['input'].update(after_key=key(49)))
    rec('empty_as_null','calls.jsonl','calls.input',lambda r:r[7]['input'].update(after_key=None))
    rec('duplicate_interior_key','calls.jsonl','calls.keys',lambda r:r[0]['rows'][24].update(book_key=key(24)))
    rec('second_page_repeats_cursor','calls.jsonl','calls.keys',lambda r:r[1]['rows'][0].update(book_key=key(50)))
    rec('active_removed_row','calls.jsonl','calls.deleted',lambda r:r[0]['rows'][0].update(deleted=0))
    rec('callback_count','calls.jsonl','calls.callback_count',lambda r:r[0].update(callback_count=49))
    rec('invalid_rc_zero','calls.jsonl','calls.return_code',lambda r:r[5].update(return_code=0))
    def callback_on_error(r):
        r[5]['rows']=[{'callback_index':0,'book_key':key(1),'deleted':1}];r[5]['callback_count']=1
    rec('invalid_callback','calls.jsonl','calls.rows',callback_on_error)
    rec('visible_found','calls.jsonl','calls.found',lambda r:r[3].update(found_after=1))
    rec('retained_wrong_key','calls.jsonl','calls.keys',lambda r:r[4]['rows'][0].update(book_key=key(2)))
    rec('gate_changed','calls.jsonl','calls.keys',lambda r:r[8]['rows'][0].update(book_key=key(2)))
    need(len(cases)==30,'controls.count')
    return cases



def db_controls():
    cases=[]
    for label,rule in [('wrong_deleted','db.books'),('foreign_parent','db.parents'),('raw_body_hash','db.wire_hash')]:
        try: paging(fixture(label)); actual='accepted'
        except Reject as error: actual=str(error)
        except Exception as error: actual='unexpected:'+type(error).__name__+':'+str(error)
        cases.append({'control':label,'expected':rule,'actual':actual,'ok':actual==rule})
    need(len(cases)==3,'db_controls.count')
    return cases

class NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        need(newurl.startswith('https://'),'download.https')
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if redirected is not None: redirected.remove_header('Authorization')
        return redirected

def main():
    need(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    out=Path('build/dot-c07-audit');out.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('legacy',Path(__file__).with_name('claude_c07_conflict_audit_20261030.py'))
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    report={'accepted':False,'audit_source_sha':os.environ['GITHUB_SHA'],
            'audit_run_id':os.environ['GITHUB_RUN_ID'],'audit_attempt':int(os.environ['GITHUB_RUN_ATTEMPT']),
            'producer':EXPECT,'formal_count':95,'formal_total':108,
            'limitations':['producer API observations are not independent API re-execution',
              'synthetic paging is not GTK behavior or SDK-original proof',
              'SQLite consistency does not prove execution chronology',
              'not complete F05, six-platform acceptance or production P0 acceptance',
              'legacy restore8 restart/sort observations retain their documented limitations']}
    try:
        legacy=old.selftest(EXPECT)
        report['legacy_controls']=legacy
        need(len(legacy)==97 and all(c['ok'] for c in legacy),'legacy.controls')
        controls=new_controls();report['paging_controls']=controls
        need(all(c['ok'] for c in controls),'paging.controls')
        database_controls=db_controls();report['database_controls']=database_controls
        need(all(c['ok'] for c in database_controls),'database.controls')
        base='repos/NoGod3524/EXReader/actions'
        meta={'run':old.gh_api(base+'/runs/'+RUN+'/attempts/'+ATTEMPT),
              'jobs':old.gh_api(base+'/runs/'+RUN+'/attempts/'+ATTEMPT+'/jobs?per_page=100'),
              'artifact':old.gh_api(base+'/artifacts/'+ART)}
        (out/'producer-metadata.json').write_text(json.dumps(meta,sort_keys=True))
        run,art=meta['run'],meta['artifact']
        need(str(run['id'])==RUN and run['head_sha']==SOURCE and str(run['run_attempt'])==ATTEMPT
             and run['status']=='completed' and run['conclusion']=='success','producer.identity')
        need(str(art['id'])==ART and art['name']=='f05-remaining-'+RUN+'-'+ATTEMPT
             and str(art['workflow_run']['id'])==RUN and art['workflow_run']['head_sha']==SOURCE
             and art['size_in_bytes']==SIZE and art['digest']=='sha256:'+DIGEST
             and not art['expired'],'producer.artifact_identity')
        request=urllib.request.Request('https://api.github.com/'+base+'/artifacts/'+ART+'/zip',
                 headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
        with urllib.request.build_opener(NoAuthRedirect()).open(request,timeout=180) as response:
            raw=response.read(LIMIT+1)
        need(len(raw)==SIZE and sha(raw)==DIGEST,'producer.zip_digest')
        (out/'original.zip').write_bytes(raw)
        report['retained_original_zip']={'path':'original.zip','bytes':len(raw),'sha256':sha(raw)}
        files=strict_zip(raw)
        authentication=old.authenticate(meta,raw,EXPECT,'restore8')
        report['legacy_authentication']=authentication.rows
        need(not authentication.failed(),'legacy.authentication')
        prior=old.audit(old.build_evidence(files,'restore8'),EXPECT,'restore8')
        report['legacy_restore8']=prior.rows
        need(not prior.failed(),'legacy.restore8')
        report['paging']=paging(files)
        report['accepted']=True
    except Exception as error:
        report['error']=type(error).__name__+':'+str(error)
    finally:
        (out/'receipt.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
        print(json.dumps({'accepted':report['accepted'],'producer':EXPECT,
             'legacy_controls':len(report.get('legacy_controls',[])),
             'paging_controls':len(report.get('paging_controls',[])),
             'database_controls':len(report.get('database_controls',[])),
             'error':report.get('error'),'paging':report.get('paging')},sort_keys=True))
    return 0 if report['accepted'] else 1

if __name__=='__main__':
    raise SystemExit(main())
