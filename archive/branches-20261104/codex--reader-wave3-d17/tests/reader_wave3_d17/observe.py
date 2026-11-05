"""Independent SDK public reads and product-only read-only SQLite snapshots."""
import hashlib,json,os,pathlib,sqlite3,subprocess,sys,time
assert os.environ.get('GITHUB_ACTIONS')=='true'
config=json.loads(pathlib.Path('/tmp/exreader-wave3-d17.json').read_text())
profile=pathlib.Path.home()/'Library/Application Support/EXReader'
def snapshot():
    sdk=json.loads(subprocess.check_output([config['observer'],str(profile/'library.sqlite')],env=dict(os.environ,DYLD_LIBRARY_PATH=config['sdk_lib'])))
    db=sqlite3.connect((profile/'reader-catalog.db').as_uri()+'?mode=ro',uri=True)
    db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
    assert db.execute('PRAGMA application_id').fetchone()[0]==1163416144
    tables=[r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
    assert {'reader_books','reader_local_books','reader_revisions','reader_outbox'}<=set(tables)
    product={}
    for name in tables:
        assert '"' not in name
        q=db.execute('select * from "'+name+'" order by rowid')
        product[name]={'columns':[r[0] for r in q.description],'rows':[[{'blob':x.hex()} if isinstance(x,bytes) else x for x in row] for row in q.fetchall()]}
    db.close()
    return {'sdk':sdk,'product':product}
a=snapshot();time.sleep(.15);b=snapshot();assert a==b,'owner was not stable during independent observation'
result=dict(source_sha=config['source_sha'],run_id=config['run_id'],attempt=config['attempt'],profile=str(profile),observer_sha256=hashlib.sha256(pathlib.Path(config['observer']).read_bytes()).hexdigest(),state=a,observed_twice_equal=True)
path=pathlib.Path(config['out'])/'snapshots'/sys.argv[1];path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,sort_keys=True,indent=2));print(path)
