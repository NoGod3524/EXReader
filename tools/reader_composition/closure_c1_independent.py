"""Actions-only independent C1 APK, mapping and upload evidence."""
import hashlib,io,json,os,stat,struct,sys,zipfile
from pathlib import Path,PurePosixPath
assert os.environ.get('GITHUB_ACTIONS')=='true'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import fetch,download_artifact_zip
PIN=json.loads(Path(os.environ["CLOSURE_PINS"]).read_text())["c1"]
SOURCE=PIN["source"]
RUN,JOB,ARTIFACT,SIZE=PIN["run"],PIN["job"],PIN["artifact"],PIN["size"]
DIGEST=PIN["digest"]
OUT=Path('build/claude-c1-independent');OUT.mkdir(parents=True,exist_ok=True)
result=dict(accepted=False,source=SOURCE,run=RUN,job=JOB,artifact=ARTIFACT,
            catalog_changed=False,f07_accepted=False,complete_product=False,common_source_acceptance=False)
def sha(data):return hashlib.sha256(data).hexdigest()
def safe(raw):
    z=zipfile.ZipFile(io.BytesIO(raw));names=z.namelist()
    assert len(names)==len(set(n.casefold() for n in names))
    for i in z.infolist():
        n=i.filename;mode=(i.external_attr>>16)&0o170000
        assert n and '\\' not in n and ':' not in n and not PurePosixPath(n).is_absolute() and '..' not in n.split('/')
        assert mode in (0,stat.S_IFREG,stat.S_IFDIR) and not i.flag_bits&1
    return z
try:
    run=fetch(f'actions/runs/{RUN}/attempts/1');job=fetch(f'actions/jobs/{JOB}')
    assert (run['head_sha'],run['run_attempt'],run['status'],run['conclusion'])==(SOURCE,1,'completed','success')
    assert (job['run_id'],job['head_sha'],job['status'],job['conclusion'])==(RUN,SOURCE,'completed','success')
    pin=fetch(f'actions/artifacts/{ARTIFACT}')
    assert pin['name']==f'claude-c1-android-installed-sync-{RUN}-1' and not pin['expired']
    assert (pin['workflow_run']['id'],pin['workflow_run']['head_sha'])==(RUN,SOURCE)
    assert pin['size_in_bytes']==SIZE and pin['digest']=='sha256:'+DIGEST
    raw=download_artifact_zip(ARTIFACT);assert len(raw)==SIZE and sha(raw)==DIGEST
    with safe(raw) as outer:
        def one(suffix):
            found=[n for n in outer.namelist() if n.endswith(suffix)]
            assert len(found)==1,(suffix,found)
            return outer.read(found[0])
        report=json.loads(one('installed-sync-result.json'))
        build=json.loads(one('c1-installed-sync/build.json'))
        ui=json.loads(one('device/ui/result.json'))
        install=json.loads(one('device/install.json'))
        snaps=json.loads(one('device/process-snapshots.json'))
        for v in (report,build,ui):
            assert (v['source_sha'],str(v['run_id']),str(v['attempt']))==(SOURCE,str(RUN),'1')
        assert report['passed'] is True and report['failures']==[] and report['sdk_version']=='3.42.0'
        assert report['installed_android_sync_runtime'] is True and report['physical_device'] is False
        assert report['f07_accepted'] is False and report['full_product_accepted'] is False
        assert len(report['gates'])>=14 and all(g['passed'] is True for g in report['gates'].values())
        raw_apk=one('device/installed-host.apk');apk_sha=sha(raw_apk)
        assert apk_sha==build['host_apk_sha256']==build['host_apk_after_runner_build_sha256']==install['installed_sha256']==report['host_apk_sha256']
        with safe(raw_apk) as apk:
            libs={n:sha(apk.read(n)) for n in apk.namelist() if n.startswith('lib/x86_64/') and n.endswith('.so')}
            assert libs==report['packaged_libs']
            item=apk.getinfo('lib/x86_64/libexreader_product.so');elf=apk.read(item)
            assert item.compress_type==0 and elf[:6]==b'\x7fELF\x02\x01'
            nl,el=struct.unpack_from('<HH',raw_apk,item.header_offset+26)
            start=item.header_offset+30+nl+el
            phoff=struct.unpack_from('<Q',elf,32)[0];entsize,count=struct.unpack_from('<HH',elf,54)
            loads=[]
            for i in range(count):
                o=phoff+i*entsize;kind,flags=struct.unpack_from('<II',elf,o)
                if kind==1 and flags&1:
                    offset=struct.unpack_from('<Q',elf,o+8)[0];size=struct.unpack_from('<Q',elf,o+32)[0]
                    assert size>0 and offset+size<=len(elf)
                    loads.append((offset,size))
            assert loads
            proof={}
            for kind in ('upload','listing'):
                rows=[s for s in snaps['snapshots'] if s['kind']==kind]
                assert len(rows)==1 and len(rows[0]['pids'])==1
                s=rows[0];found=[]
                for m in s['mappings']:
                    if not(m['path'].endswith('.apk') and 'x' in m['perms'] and s['lib_sha256'].get(m['path'])==apk_sha):continue
                    lo,hi=[int(v,16) for v in m['range'].split('-')]
                    for offset,size in loads:
                        if m['offset']==start+(offset//4096)*4096 and hi-lo>=((offset%4096+size+4095)//4096)*4096:
                            found.append(dict(mapping=m,elf_offset=offset,elf_size=size))
                assert found,('no executable product PT_LOAD identity',kind)
                proof[kind]=found
        assert ui['accepted'] is True and ui['checks']==16 and len(ui['boundaries'])==2 and len(ui['phases'])==4
        assert all(b['real_request_blocked'] and b['ui_action_observed'] for b in ui['boundaries'])
        assert all(p['expected_sdk_version']=='3.42.0' for p in ui['phases'])
        original=('abcdefghijk retained UI reading anchor.\n'+'Safe original paragraph.\n'*200).encode();digest=sha(original)
        puts=[r for r in ui['requests'] if r['method']=='PUT' and '/objects/' in r['path']]
        assert puts and all(r['path'].rsplit('/',1)[-1].split('.')[0]==r['body_sha256'] for r in puts if r.get('body_sha256'))
        assert any(r['path']==f'/dav/exreader-sync-v1/objects/{digest[:2]}/{digest}.txt' and r.get('stored') is True and r['response']==201 and r['body_sha256']==digest and r['body_bytes']==len(original) for r in puts)
        result.update(accepted=True,archive_sha256=DIGEST,apk_sha256=apk_sha,packaged_libraries=libs,
            executable_mapping_proof=proof,native_ui_checks=16,original_uploaded_sha256=digest,
            scope='retained APK bytes, executable ELF mappings, native receipt and TLS fixture upload only',
            symbol_binding='original passing producer; unstripped candidate not independently executed',
            physical_device=False,tamper_failure_path_verified=False)
except Exception as e:result['error']=repr(e)
finally:
    (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
assert result['accepted'],result.get('error')
