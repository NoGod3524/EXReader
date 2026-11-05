"""Original capability I/O and native parsing helpers; one bounded deadline."""
import hashlib,importlib.util,io,json,os,subprocess,sys,stat,time,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
DEADLINE=None

def remaining():
    if DEADLINE is None:return 120
    value=DEADLINE-time.monotonic()
    if value<=0:raise TimeoutError("reader diagnostic total deadline exhausted")
    return value

def command(args,**kw):
    kw["timeout"]=min(kw.get("timeout",120),remaining())
    return subprocess.check_output(list(map(str,args)),cwd=ROOT,**kw)

def need(v,message):
    if not v:raise ValueError(message)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(p,v):
    Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

def identity():return {'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT']}

def api(path):return json.loads(command(['gh','api','repos/NoGod3524/EXReader/'+path]))

def archive_bytes(meta):return command(['gh','api','repos/NoGod3524/EXReader/actions/artifacts/'+str(meta['id'])+'/zip'])

def load_native_tools():
    spec=importlib.util.spec_from_file_location('original_apple_measurements',ROOT/'tests/reader_f08_apple_20261031/run.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.command=command
    sys.path.insert(0,str(ROOT/'tests/apple_host'))
    import collect_evidence
    def load_results(path):
        previous=collect_evidence.command
        try:
            collect_evidence.command=lambda *args:command(args,text=True).strip()
            return collect_evidence.load_results(path)
        finally:collect_evidence.command=previous
    return module.extract_metrics,load_results

def binary(app,platform):return app/('Contents/MacOS/EXReaderHost' if platform=='macos' else 'EXReaderHost')

def validate_zip(data):
    z=zipfile.ZipFile(io.BytesIO(data));infos=z.infolist()
    need(0<len(infos)<100000 and sum(x.file_size for x in infos)<4*1024**3,'archive bounds')
    seen=set()
    for i in infos:
        remaining()
        p=PurePosixPath(i.filename);key=str(p).casefold()
        need(str(p)!='.' and not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename and ':' not in i.filename and key not in seen,'archive path')
        seen.add(key);need(not i.flag_bits&1 and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),'archive entry kind')
    manifest=json.loads(z.read('f08-manifest.json'))
    files={i.filename for i in infos if not i.is_dir()}
    need(files==set(manifest['files'])|{'f08-manifest.json'},'archive complete inventory')
    for name,item in manifest['files'].items():
        remaining()
        b=z.read(name);need(len(b)==item['bytes'] and hashlib.sha256(b).hexdigest()==item['sha256'],'archive file bytes '+name)
    return z,manifest
