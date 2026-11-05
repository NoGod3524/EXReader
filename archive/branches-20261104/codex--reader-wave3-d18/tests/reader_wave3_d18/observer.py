"""Simulator-external observer: read-only backups, public SDK and product SELECTs.
The HTTP test-control channel never calls an app handler or changes product data.
"""
import http.server, json, pathlib, shutil, sqlite3, subprocess, threading, time, traceback, urllib.parse
from common import OUT, identity, digest, hashed, write

def backup(source, destination):
    assert source.is_file(), 'actual store missing: '+str(source)
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=5) as src:
        with sqlite3.connect(destination) as dst: src.backup(dst)

def catalog(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        assert {'reader_books','reader_local_books','reader_revisions','reader_outbox'} <= set(tables), tables
        result={}
        def value(v): return {'blob_hex':v.hex()} if isinstance(v,bytes) else v
        for table in tables:
            assert '"' not in table
            rows=[[value(v) for v in row] for row in db.execute('SELECT * FROM "'+table+'" ORDER BY rowid')]
            columns=[row[1] for row in db.execute('PRAGMA table_info("'+table+'")')]
            result[table]=dict(columns=columns,rows=rows)
        return result

class Observer:
    def __init__(self, host, udid, program, resources):
        self.host,self.udid,self.program,self.resources=host,udid,program,resources
        self.out=OUT/host/'observations';self.out.mkdir(parents=True,exist_ok=True)
        self.labels=[]
    def container(self):
        return pathlib.Path(subprocess.check_output(['xcrun','simctl','get_app_container',self.udid,'org.exreader.host','data'],text=True).strip())
    def sample(self,label,index):
        container=self.container();base=container/'Library/Application Support/EXReader'
        choices=[p for p in base.rglob('library.sqlite') if (p.parent/'reader-catalog.db').is_file()]
        assert len(choices)==1, {'error':'ambiguous/missing actual stores','listing':[str(p.relative_to(container)) for p in base.rglob('*')]}
        sdk_live=choices[0];product_live=sdk_live.parent/'reader-catalog.db'
        folder=self.out/label/str(index);folder.mkdir(parents=True)
        backup(sdk_live,folder/'library.sqlite');backup(product_live,folder/'reader-catalog.db')
        public=json.loads(subprocess.check_output([str(self.program),str(folder/'library.sqlite')],text=True))
        product=catalog(folder/'reader-catalog.db')
        sources=[{k:v for k,v in item.items() if k!='position'} for item in public['originals']]
        semantic=dict(sdk_sha256=public['sdk_sha256'],product_sha256=hashed(product),sources_sha256=hashed(sources),
            revisions_sha256=hashed({k:product[k] for k in ('reader_revisions','reader_outbox')}))
        result=dict(**identity(),host=self.host,label=label,sample=index,monotonic=time.monotonic(),
            paths=dict(container=str(container),sdk=str(sdk_live),catalog=str(product_live)),
            public_sdk=public,product=product,semantic=semantic,
            copies={p.name:dict(bytes=p.stat().st_size,sha256=digest(p)) for p in folder.iterdir() if p.is_file()},
            method='SDK: read-only SQLite backup then public SDK query on copy; catalog: read-only backup and read-only SELECT; live stores never opened for writing')
        write(folder/'snapshot.json',result);return result
    def stable(self,label):
        assert label not in self.labels and all(c.isalnum() or c in '.-_' for c in label)
        self.labels.append(label);time.sleep(0.6)
        samples=[self.sample(label,0)]
        for i in range(1,16):
            time.sleep(0.5);samples.append(self.sample(label,i))
            if samples[-2]['semantic']==samples[-1]['semantic']:
                result=dict(**samples[-1],idle=dict(stable=True,sample_count=len(samples),separation_seconds=samples[-1]['monotonic']-samples[-2]['monotonic'],baseline_pair=[samples[-2]['sample'],samples[-1]['sample']]))
                write(self.out/(label+'.json'),result);print('D18_SNAPSHOT '+json.dumps(dict(label=label,host=self.host,semantic=result['semantic'],books=result['public_sdk']['book_count'])),flush=True);return result
        raise RuntimeError('store did not become idle: '+label)
    def start(self):
        observer=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    query=urllib.parse.urlparse(self.path);params=urllib.parse.parse_qs(query.query)
                    if query.path=='/prepare':
                        documents=observer.container()/'Documents';documents.mkdir(exist_ok=True)
                        for filename,resource in [('D18-Broken.epub','Broken.epub'),('D18-Sample.epub','Sample.epub')]: shutil.copyfile(observer.resources/resource,documents/filename)
                        result=dict(ok=True,files={p.name:digest(p) for p in documents.glob('D18-*.epub')})
                        write(observer.out/'picker-fixtures.json',result)
                    else:
                        assert query.path=='/snapshot';result=observer.stable(params['label'][0]);result=dict(ok=True,label=result['label'],semantic=result['semantic'],book_count=result['public_sdk']['book_count'])
                    raw=json.dumps(result).encode();self.send_response(200)
                except Exception as e:
                    traceback.print_exc();raw=json.dumps(dict(ok=False,error=str(e))).encode();self.send_response(500)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        self.server=http.server.HTTPServer(('127.0.0.1',19718),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
