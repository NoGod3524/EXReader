import hashlib, json, os, sqlite3, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_sync'))
from check_sync import revision, raw
assert os.environ.get('GITHUB_ACTIONS') == 'true'
exe, folder = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
folder.mkdir(parents=True, exist_ok=True)
db = folder / 'product.sqlite'
def call(*args):
    p = subprocess.run([str(exe),str(db),*map(str,args)],check=True,capture_output=True,text=True)
    value=json.loads(p.stdout)
    assert value['status']==0, (args,value,p.stderr)
    return value
def receive(v):
    body=raw(v); path=folder/(hashlib.sha256(body).hexdigest()+'.json');path.write_bytes(body);call('receive',path)
def sql(q):
    with sqlite3.connect(db) as c: return c.execute(q).fetchall()
def scan(kind,limit=2):
    cursor='-'; result=[]
    while True:
        rows=call('page',kind,cursor,limit)['rows'];result.extend(rows)
        if len(rows)<limit: return result
        cursor=rows[-1]['key']
def rev(n,kind,key,payload=None,parents=(),operation='put'):
    return revision(n,kind=kind,key=key,payload=payload,parents=parents,operation=operation)
bookkey='txt:'+'a'*64
book=rev(1,'book',bookkey,{'format':'txt','source_sha256':'a'*64,'source_bytes':123,'title':'Book','author':'A','favorite':False})
receive(book);call('book',bookkey,book['id'],'Book')
parent='f'*32; child='1'*32
p=rev(2,'shelf',parent,{'name':'Parent','parent_id':None,'ordinal':0})
c=rev(3,'shelf',child,{'name':'Child','parent_id':parent,'ordinal':1})
t=rev(4,'tag','2'*32,{'name':'Tag'});s=rev(5,'series','3'*32,{'name':'Series'})
m=[]
for n,kind,ident in [(6,'shelf',child),(7,'tag',t['entity_key']),(8,'series',s['entity_key'])]:
    m.append(rev(n,'membership',kind+':'+ident+':'+bookkey,{'collection_kind':kind,'collection_id':ident,'book_key':bookkey,'ordinal':n}))
for v in [c,p,t,s,*m]:receive(v)
first=scan('shelf',1);assert [r['result'] for r in first]==[2,0],first
assert [r['result'] for r in scan('shelf',1)]==[0,0]
assert sql('select name,parent_id from reader_shelves order by name')==[('Child',parent),('Parent',None)]
assert all(r['result']==0 for kind in ('tag','series','membership') for r in scan(kind,1))
assert sql('select count(*) from reader_local_books')==[(0,)]
assert all(sql('select count(*) from '+table)==[(1,)] for table in ('reader_book_shelves','reader_book_tags','reader_book_series'))
assert all(r['result']==0 for kind in ('shelf','tag','series','membership') for r in scan(kind,1))
delete=rev(9,'membership',m[0]['entity_key'],parents=[m[0]['id']],operation='delete');receive(delete)
assert all(r['result']==0 for r in scan('membership',1));assert sql('select count(*) from reader_book_shelves')==[(0,)]
restore=rev(10,'membership',m[0]['entity_key'],m[0]['payload'],[delete['id']],'restore');receive(restore)
scan('membership',1);assert sql('select count(*) from reader_book_shelves')==[(1,)]
sdelete=rev(11,'shelf',child,parents=[c['id']],operation='delete');receive(sdelete);scan('shelf',1)
assert sql("select deleted from reader_shelves where name='Child'")==[(1,)]
srestore=rev(12,'shelf',child,c['payload'],[sdelete['id']],'restore');receive(srestore);scan('shelf',1)
assert sql("select deleted from reader_shelves where name='Child'")==[(0,)]
missing=rev(13,'tag','4'*32,{'name':'Missing'},['e'*32]);receive(missing)
a=rev(14,'tag','5'*32,{'name':'A'});b=rev(15,'tag','5'*32,{'name':'B'});receive(a);receive(b)
rows=scan('tag',1);assert [(r['selection'],r['result']) for r in rows if r['key'] in ('4'*32,'5'*32)]==[(1,1),(2,1)]
assert sql("select count(*) from reader_tags where tag_id in ('"+'4'*32+"','"+'5'*32+"')")==[(0,)]
assert sql('select count(*) from reader_outbox')==[(0,)]
(folder/'evidence.json').write_text(json.dumps({'head':os.environ['GITHUB_SHA'],'run':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'checks':['bounded_pages','dependency_rescan','hierarchy','memberships_without_local_original','tombstones_restore','replay','missing_ancestor','concurrent_heads','no_outbox']}))

