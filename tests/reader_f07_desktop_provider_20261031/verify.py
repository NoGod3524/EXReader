"""Independent Actions audit; never execute downloaded host/consumer binaries."""
import copy
import hashlib
import io
import json
import ntpath
import posixpath
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
HERE=Path(__file__).resolve().parent
LOCK=json.loads((HERE/'source_lock.json').read_text())
OUT=Path('build/f07-desktop-audit')
MAX_ZIP=256*1024*1024
PRODUCER_SOURCE='01ab528888f5c5be97e5824d69e2908e31e68e24'
PRODUCER_RUN='41186261435'
PRODUCER_ATTEMPT='1'
VERIFIER_BASE='c11c118f074d7324b664160e6c447ee161e97804'
PINS={
 'windows':(13036129037,31654088,'c71801182be4188ad1fea84d2b5b2691e50735fbfa8763acbb7c1fe8d5efd9e4'),
 'macos':(13037275549,59058964,'eb77ff395cbbc907172ef709b5a7b3ed79fd4f21fa28a8b444099f4487e3b169')}

class Refused(Exception):
    pass

def need(ok,reason):
    if not ok: raise Refused(reason)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def norm(s):
    return s.replace('\\','/')

def readzip(raw,nested=False):
    need(len(raw)<=MAX_ZIP,'zip_bytes')
    result={}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=z.infolist()
        need(len(entries)<= (3000 if nested else 300),'zip_count')
        seen=set(); total=0
        for e in entries:
            n=e.filename
            need(n and '\\' not in n and ':' not in n and not n.startswith('/') and
                 all(x not in ('','.','..') for x in n.rstrip('/').split('/')),'zip_path')
            need(n.casefold() not in seen,'zip_alias');seen.add(n.casefold())
            mode=(e.external_attr>>16)&0o170000
            need(mode in (0,stat.S_IFREG,stat.S_IFDIR) and not e.flag_bits&1,'zip_type')
            need(e.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'zip_method')
            total+=e.file_size
            need(e.file_size<=128*1024*1024 and total<=512*1024*1024,'zip_size')
            if not e.is_dir():
                if not nested: need('/' not in n,'zip_flat')
                result[n]=z.read(e)
    return result

def txt(files,name):
    need(name in files,'missing_'+name)
    return files[name].decode('utf-8','strict')

def reseal(files):
    b=json.loads(files['binding.json'])
    b['files']={n:dict(bytes=len(v),sha256=sha(v)) for n,v in files.items() if n!='binding.json'}
    files['binding.json']=json.dumps(b).encode()

def macowners(mapping,symbol):
    live=mapping.split('# Dead Stripped Symbols:')[0]
    objs=dict(re.findall(r'^\[\s*(\d+)\]\s+(.+)$',live,re.M))
    ids=re.findall(r'^0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+\[\s*(\d+)\]\s+_'+re.escape(symbol)+r'\s*$',live,re.M)
    return [objs.get(i,'<unknown-object>') for i in ids]

def winowners(mapping,symbol):
    # MSVC public-symbol rows, not GNU LOAD lines or library listings.
    rows=re.findall(r'^\s*[0-9a-fA-F]+:[0-9a-fA-F]+\s+_?'+re.escape(symbol)+r'\s+[0-9a-fA-F]+\s+(.*?)\s*$',mapping,re.M)
    return [r.split()[-1] if r.split() else '' for r in rows]

def owners(mapping,symbol,platform):
    return macowners(mapping,symbol) if platform=='macos' else winowners(mapping,symbol)

def owned_by(owner,path,platform):
    path=norm(path)
    if platform=='macos':
        return bool(re.fullmatch(re.escape(path)+r'(?:\[\d+\])?\(sqlite3\.c\.o\)',norm(owner)))
    stem=Path(path).stem.lower()
    # MSVC MAP abbreviates the archive to its basename; full-path link evidence is checked separately.
    return bool(re.fullmatch(re.escape(stem)+r'(?:\.lib)?:sqlite3\.c\.(?:obj|o)',norm(owner).split('/')[-1].lower()))


def installed_header(files,b,platform):
    cmd=json.loads(txt(files,'sdk-header-deps.command.json'))
    argv=cmd['argv']
    obj='CMakeFiles/f07-sdk.dir/probe.c.'+('obj' if platform=='windows' else 'o')
    need(len(argv)==6 and argv[0]=='ninja' and argv[1]=='-C' and
         argv[3:]==['-t','deps',obj],'installed_header')
    path=ntpath if platform=='windows' else posixpath
    expected=path.normpath(b['product_prefix']+'/include/exreader-product/sqlite3.h')
    consumer_expected=path.normpath(path.join(path.dirname(b['product_prefix']),'consumer'))
    need(path.isabs(cmd['cwd']),'installed_header')
    base=path.normpath(path.join(cmd['cwd'],argv[2]))
    # Relative entries use the actual recorded -C directory, never audit-machine cwd.
    canon=lambda p: path.normcase(path.normpath(p)) if platform=='windows' else path.normpath(p)
    need(path.isabs(base) and canon(base)==canon(consumer_expected),'installed_header')
    rows=[l.strip() for l in txt(files,'sdk-header-deps.log').splitlines()
          if path.basename(l.strip()).lower()=='sqlite3.h']
    resolved=[path.normpath(path.join(base,l)) for l in rows]
    need(len(resolved)==1 and canon(resolved[0])==canon(expected),'installed_header')
    need(files['sqlite3-installed.h'] and b['files']['sqlite3-installed.h']['sha256']==sha(files['sqlite3-installed.h']),
         'installed_header')
    return dict(command_cwd=cmd['cwd'],consumer_argument=argv[2],consumer_resolved=base,
                raw_header_rows=rows,resolved_header=resolved[0],expected_header=expected,
                installed_header_sha256=sha(files['sqlite3-installed.h']),
                independent_source_header_bytes_available=False)

def windows_loaded_sqlite(files,targets):
    log=txt(files,'host-build.log')
    searches=list(re.finditer(r'(?mi)^\s*Searching\s+(.+?\.lib):\s*$',log))
    loaded=[]
    for i,m in enumerate(searches):
        block=log[m.end():searches[i+1].start() if i+1<len(searches) else len(log)]
        full=norm(m.group(1).strip())
        for archive,member in re.findall(r'(?mi)^\s*Loaded\s+(.+?\.lib)\(\s*([^)]+)\s*\)\s*$',block):
            if member.strip().lower() not in ('sqlite3.c.obj','sqlite3.c.o'):
                continue
            need(ntpath.normcase(ntpath.basename(archive))==ntpath.normcase(ntpath.basename(full)),
                 'provider_link_identity')
            need(ntpath.isabs(full),'provider_link_identity')
            keys=[k for k in ('product','sdk') if ntpath.normcase(ntpath.normpath(full))==
                  ntpath.normcase(ntpath.normpath(targets[k]))]
            need(len(keys)==1,'provider_link_identity')
            loaded.append(dict(key=keys[0],archive=targets[keys[0]],member=member.strip()))
    unique={(r['key'],r['member'].lower()) for r in loaded}
    need(len(unique)==1,'provider_loaded_ambiguous')
    return loaded

def runtime_details(files):
    out={}
    for name in ('codec','sdk'):
        lines=txt(files,name+'-runtime.log').splitlines()
        ids=[l[len('sourceid='):] for l in lines if l.startswith('sourceid=')]
        options=sorted(l[len('option='):] for l in lines if l.startswith('option='))
        need(len(ids)==1 and options,'aux_runtime')
        out[name]=dict(source_id=ids[0],compile_options=options,fts5='ENABLE_FTS5' in options)
    header=re.findall(r'^#define\s+SQLITE_SOURCE_ID\s+"([^"]+)"',txt(files,'sqlite3-installed.h'),re.M)
    need(len(header)==1 and header[0]==out['codec']['source_id'],'installed_header_source_id')
    out['same_source_id']=out['codec']['source_id']==out['sdk']['source_id']
    out['same_compile_options']=out['codec']['compile_options']==out['sdk']['compile_options']
    out['codec_only_options']=sorted(set(out['codec']['compile_options'])-set(out['sdk']['compile_options']))
    out['sdk_only_options']=sorted(set(out['sdk']['compile_options'])-set(out['codec']['compile_options']))
    out['scope']='independent public consumers; not live host queries'
    return out

def evaluate(files,platform,source,run,attempt):
    b=json.loads(txt(files,'binding.json'))
    need((b.get('source'),b.get('product'),b.get('sdk'),b.get('run'),b.get('attempt'),b.get('platform'))==
         (source,LOCK['product'],LOCK['sdk'],run,attempt,platform),'identity')
    need(b.get('host_runtime_provider_observed') is False and b.get('F07_accepted') is False,'boundary')
    need(set(b['files'])==set(files)-{'binding.json'},'inventory')
    for name,pin in b['files'].items():
        need(pin==dict(bytes=len(files[name]),sha256=sha(files[name])),'file_hash')
    need('host.map' in files,'missing_map')
    need(files['host']==files['package-host'],'package_host')
    header=txt(files,'sdk-base.h')
    need('#define EXR_VERSION "3.42.0"' in header and
         re.search(r'#define\s+EXR_ABI_VERSION\s+1u(?:\s|$)',header),'sdk_version_abi')
    need(b['core_interface']==dict(type='INTERFACE_LIBRARY',links=['EXReader::exr_render']),'core_interface')
    sdk=norm(b['sdk_prefix']).rstrip('/'); product=norm(b['product_prefix']).rstrip('/')
    need(sdk!=product and (sdk.startswith('/') or re.match(r'^[A-Za-z]:/',sdk)),'target_prefix')
    ext='.lib' if platform=='windows' else '.a'
    pre='' if platform=='windows' else 'lib'
    expected=dict(product=product+'/lib/'+pre+'reader_catalog_sqlite'+ext,
                  sdk=sdk+'/lib/exreader/'+pre+'exr_vendor_exr_sqlite'+ext,
                  base=sdk+'/lib/'+pre+'exr_base'+ext,render=sdk+'/lib/'+pre+'exr_render'+ext)
    need(all(norm(b['targets'][k])==v for k,v in expected.items()),'target_prefix')
    header_evidence=installed_header(files,b,platform)
    runtime_evidence=runtime_details(files)
    for mode in ('sdk','codec'):
        runtime=txt(files,mode+'-runtime.log')
        need('version=3.42.0' in runtime and 'abi=1' in runtime and
             re.search(r'^sourceid=.{20,}$',runtime,re.M) and 'option=' in runtime,'aux_runtime')
    need(json.loads(txt(files,'negative-prefix.json'))==dict(refused=True,reason='F07_PREFIX'),'negative_prefix')
    hostmap=txt(files,'host.map')
    own=owners(hostmap,'sqlite3_open_v2',platform)
    need(len(own)==1,'provider_ambiguous')
    allowed=('product','sdk') if platform=='windows' else ('product',)
    selected=[key for key in allowed if owned_by(own[0],expected[key],platform)]
    need(len(selected)==1,'provider_owner')
    selected=selected[0]
    prepare=owners(hostmap,'sqlite3_prepare_v2',platform)
    need(len(prepare)==1 and owned_by(prepare[0],expected[selected],platform),'provider_owner')
    if platform=='windows':
        public=re.findall(r'^\s*[0-9a-fA-F]+:[0-9a-fA-F]+\s+_?(sqlite3_\w+)\s+[0-9a-fA-F]+\s+(.*?)\s*$',hostmap,re.M)
        need(public and all(parts.split() and owned_by(parts.split()[-1],expected[selected],platform)
                            for _,parts in public),'provider_ambiguous')
        loaded=windows_loaded_sqlite(files,expected)
        need(all(x['key']==selected for x in loaded),'provider_link_identity')
    else:
        loaded=[dict(key='product',archive=expected['product'],member='sqlite3.c.o')]
    provider_archive=dict(key=selected,path=expected[selected],
                          sha256=sha(files[selected+'.archive']),bytes=len(files[selected+'.archive']),
                          loaded_members=loaded)
    for mode,key in [('codec','product'),('sdk','sdk')]:
        o=owners(txt(files,mode+'.map'),'sqlite3_sourceid',platform)
        need(len(o)==1 and owned_by(o[0],expected[key],platform),'aux_provider')
    codecm=txt(files,'codec.map')
    need('exr_vendor_exr_sqlite' not in codecm and 'exr_library' not in codecm,'codec_separation')
    imports=txt(files,'host-imports.log')
    need(not re.search(r'(?i)(?:lib)?sqlite3[^\s/]*\.(?:dll|dylib)',imports),'system_sqlite')
    need(not re.search(r'(?i)(?:exr_wc_test_hook|exr_webdav_test_|EXR_.*TEST_HOOK)',hostmap),'test_hook')
    if platform=='windows':
        need(b['extra']['sdk_linkage']=='static-reading','linkage')
        need(not re.search(r'(?i)(?:lib)?exreader[^ \r\n]*\.dll',imports),'linkage')
        cache=txt(files,'host-cache.txt')
        for flag in ['EXR_READER_WINDOWS_WAVE3','EXR_READER_WINDOWS_CLOUD_CONTENT_BOUND','EXR_READER_WINDOWS_TXT_PROGRESS']:
            need(re.search(re.escape(flag)+r':BOOL=ON',cache),'host_profile')
        need('EXR_SDK_VERSION:STRING=3.42.0' in cache,'sdk_version_abi')
        link=norm(txt(files,'host-build.log')).lower()
        need('/verbose:lib' in link and norm(expected['product']).lower() in link,'link_command')
        need('sqlite3.c.obj' in link or 'sqlite3.c.o' in link,'link_members')
        report=json.loads(txt(files,'package-report.json'))
        need(report.get('passed') is True and report.get('checks',0)>=26 and report.get('engine_version')=='3.42.0','package_selftest')
        manifest=json.loads(txt(files,'package-build.json'))
        need(manifest['source_sha']==source and manifest['sdk_version']=='3.42.0' and manifest['linkage']=='static-reading','package_identity')
        need(manifest['files']['EXReader.exe']==sha(files['package-host']),'package_manifest')
    else:
        need(b['extra']['sdk_linkage']=='shared','linkage')
        need('libexreader' in imports and 'libexr_library.a' not in hostmap and
             'libreader_reading_state.a' not in hostmap,'linkage')
        sym=txt(files,'host-symbols.log')
        need(len(re.findall(r'\b[Tt]\s+_sqlite3_open_v2\s*$',sym,re.M))==1,'host_symbols')
        argv=json.loads(txt(files,'host-link.command.json'))['argv']
        need('swiftc' in argv and '-lexreader' in argv and '-why_load' in argv and
             sdk+'/lib' in list(map(norm,argv)),'link_command')
        manifest=json.loads(txt(files,'package-build.json'))
        need(manifest['source_sha']==source and manifest['sdk_version']=='3.42.0' and
             manifest['selector_bytes_candidate'] and manifest['wave3_enabled'],'package_identity')
        need(manifest['files']['Contents/MacOS/EXReader']==sha(files['package-host']),'package_manifest')
        signing=b['extra']['signing']
        need(signing and len({x['name'] for x in signing})==len(signing),'shared_binding')
        for i,x in enumerate(signing):
            need(x['installed_sha256']==x['pre_sign_sha256']==sha(files[x['installed_file']]) and
                 x['bundled_sha256']==sha(files[x['bundled_file']]),'shared_binding')
            need(manifest['files']['Contents/Frameworks/'+x['name']]==x['bundled_sha256'],'shared_binding')
            need('libexreader' in txt(files,'shared-id-%d.log'%i),'shared_installname')
        need(any(x['name'] in imports for x in signing),'shared_installname')
    package=readzip(files['package.zip'],nested=True)
    need(b['package_member'] in package and package[b['package_member']]==files['package-host'],'package_zip')
    return dict(platform=platform,host_provider=own,host_provider_archive=provider_archive,
                host_sha256=sha(files['host']),installed_header=header_evidence,runtime_consumers=runtime_evidence,
                sdk_linkage=b['extra']['sdk_linkage'],host_runtime_provider_observed=False,
                auxiliary_runtime_scope='independent public consumers only')

def controls(files,platform,source,run,attempt):
    evaluate(files,platform,source,run,attempt)
    cases=[]
    def bad(name,reason,mutate,seal=True):
        f=copy.deepcopy(files); mutate(f)
        if seal: reseal(f)
        try: evaluate(f,platform,source,run,attempt)
        except Refused as e:
            need(str(e)==reason,'control_wrong_reason');cases.append(dict(name=name,reason=reason,refused=True));return
        raise Refused('control_accepted')
    bad('missing-map','missing_map',lambda f:f.pop('host.map'))
    def duplicate(f):
        m=txt(f,'host.map')
        if platform=='windows':
            row=next(l for l in m.splitlines() if re.match(r'^\s*[0-9A-Fa-f]+:[0-9A-Fa-f]+\s+sqlite3_open_v2\s',l))
            m+='\n'+row+'\n'
        else:
            row=next(l for l in m.splitlines() if re.match(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*\d+\]\s+_sqlite3_open_v2\s*$',l))
            m=row+'\n'+m
        f['host.map']=m.encode()
    bad('ambiguous-provider','provider_ambiguous',duplicate)
    def wrongprefix(f):
        b=json.loads(f['binding.json']);b['targets']['base']='/wrong/libexr_base.a';f['binding.json']=json.dumps(b).encode()
    bad('wrong-prefix','target_prefix',wrongprefix)
    bad('wrong-version','sdk_version_abi',lambda f:f.update({'sdk-base.h':f['sdk-base.h'].replace(b'3.42.0',b'3.40.0')}))
    # Windows SDK is a legal host provider under the frozen desktop contract.
    # Corrupt the actual owner to an unknown archive, not to another legal archive.
    chosen=evaluate(files,platform,source,run,attempt)['host_provider_archive']['key']
    token=b'exr_vendor_exr_sqlite' if chosen=='sdk' else b'reader_catalog_sqlite'
    bad('wrong-owner','provider_owner',lambda f:f.update({'host.map':f['host.map'].replace(token,b'foreign_catalog_sqlite')}))
    suffix=b'\n/usr/lib/libsqlite3.dylib\n' if platform=='macos' else b'\nsqlite3.dll\n'
    bad('system-sqlite','system_sqlite',lambda f:f.update({'host-imports.log':f['host-imports.log']+suffix}))
    bad('archive-hash','file_hash',lambda f:f.update({'product.archive':f['product.archive']+b'X'}),False)
    bad('wrong-header','installed_header',lambda f:f.update({'sdk-header-deps.log':f['sdk-header-deps.log'].replace(b'sqlite3.h',b'foreign-sqlite3.h')}))
    def wrong_consumer(f):
        cmd=json.loads(f['sdk-header-deps.command.json'])
        cmd['argv'][2]=cmd['argv'][2]+'-foreign'
        f['sdk-header-deps.command.json']=json.dumps(cmd).encode()
    bad('wrong-consumer-directory','installed_header',wrong_consumer)
    return dict(positive=1,negative=9,original_negative_count=7,cases=cases)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None

def api(path):
    req=urllib.request.Request('https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+path,
         headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=60) as r:
        return json.load(r)

def download(artifact):
    url='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/artifacts/'+str(artifact['id'])+'/zip'
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN']})
    try:
        urllib.request.build_opener(NoRedirect).open(req,timeout=60)
        raise Refused('artifact_redirect_missing')
    except urllib.error.HTTPError as e:
        need(e.code in (301,302,303,307),'artifact_redirect')
        location=e.headers['Location']
    need(location.startswith('https://'),'artifact_redirect')
    # The signed object URL receives no Authorization header.
    with urllib.request.urlopen(location,timeout=120) as r:
        raw=r.read(MAX_ZIP+1)
    need(len(raw)==artifact['size_in_bytes'] and len(raw)<=MAX_ZIP,'artifact_bytes')
    need(artifact.get('digest')=='sha256:'+sha(raw),'artifact_hash')
    return raw

def inspect_again(files,platform,report):
    folder=OUT/platform
    folder.mkdir()
    # Inspect, never execute, original artifact bytes.
    (folder/'host').write_bytes(files['host'])
    (folder/'product.archive').write_bytes(files['product.archive'])
    (folder/'selected.archive').write_bytes(files[report['host_provider_archive']['key']+'.archive'])
    commands=[['llvm-ar','t',str(folder/'product.archive')],
              ['llvm-nm','--defined-only',str(folder/'product.archive')]]
    if platform=='macos':
        commands.append(['llvm-nm','--defined-only',str(folder/'host')])
    else:
        commands.append(['llvm-readobj','--coff-imports',str(folder/'host')])
    commands += [['llvm-ar','t',str(folder/'selected.archive')],
                 ['llvm-nm','--defined-only',str(folder/'selected.archive')]]
    for i,cmd in enumerate(commands):
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        (folder/('independent-%d.log'%i)).write_bytes(p.stdout)
        p.check_returncode()
        if i in (1,4): need(b'sqlite3_open_v2' in p.stdout,'independent_archive_symbols')
        if i==3:
            members=p.stdout.decode('utf-8','strict').splitlines()
            expected_member=report['host_provider_archive']['loaded_members'][0]['member']
            need(sum(ntpath.basename(x.strip()).lower()==expected_member.lower() for x in members)==1,
                 'independent_archive_member')
        if i==2:
            if platform=='macos':
                need(len(re.findall(rb'\b[Tt]\s+_sqlite3_open_v2\s*$',p.stdout,re.M))==1,'independent_host_symbols')
            else:
                need(not re.search(rb'(?i)(sqlite3|exreader)[^\r\n]*\.dll',p.stdout),'independent_imports')

def main():
    need(os.environ.get('GITHUB_ACTIONS')=='true','actions_only')
    OUT.mkdir(parents=True,exist_ok=False)
    source,run,attempt=PRODUCER_SOURCE,PRODUCER_RUN,PRODUCER_ATTEMPT
    verifier_source=os.environ['GITHUB_SHA']
    scope={'tests/reader_f07_desktop_provider_20261031/verify.py',
           '.github/workflows/dot-f07-desktop-header-evidence-20261031.yml',
           'docs/reader-total-progress/DOT_F07_DESKTOP_PROVIDER_20261031.md'}
    changed=set(subprocess.check_output(['git','diff','--name-only',VERIFIER_BASE,verifier_source],text=True).splitlines())
    need(changed==scope,'verifier_scope')
    result=dict(audit_completed=False,audit_passed=False,F07_accepted=False,formal='95/108',errors=[],platforms=[])
    try:
        meta=api('/actions/runs/'+run)
        need(meta['head_sha']==source and str(meta['run_attempt'])==attempt,'run_identity')
        jobs=api('/actions/runs/'+run+'/attempts/'+attempt+'/jobs?per_page=100')['jobs']
        artifacts=api('/actions/runs/'+run+'/artifacts?per_page=100')['artifacts']
        for platform in ('windows','macos'):
            matched=[j for j in jobs if j['name']==platform]
            need(len(matched)==1 and matched[0]['conclusion']=='success','producer_job')
            name='f07-desktop-'+platform+'-'+run+'-'+attempt
            arts=[a for a in artifacts if a['name']==name]
            need(len(arts)==1 and not arts[0]['expired'] and arts[0]['workflow_run']['head_sha']==source,'artifact_identity')
            a=arts[0]
            pin=PINS[platform]
            need((a['id'],a['size_in_bytes'],a.get('digest'))==(pin[0],pin[1],'sha256:'+pin[2]),'fixed_artifact_pin')
            raw=download(a);(OUT/(platform+'-original.zip')).write_bytes(raw)
            files=readzip(raw)
            report=evaluate(files,platform,source,run,attempt)
            report['controls']=controls(files,platform,source,run,attempt)
            inspect_again(files,platform,report)
            report['artifact']=dict(id=a['id'],bytes=len(raw),sha256=sha(raw))
            result['platforms'].append(report)
        result.update(audit_completed=True,audit_passed=True)
    except Exception as e:
        result['errors'].append(str(e) if isinstance(e,Refused) else type(e).__name__)
    result.update(source=source,run=run,attempt=attempt,
                  verifier_source=verifier_source,verifier_run=os.environ['GITHUB_RUN_ID'],
                  verifier_attempt=os.environ['GITHUB_RUN_ATTEMPT'],product_rebuilt=False)
    (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print('F07_DESKTOP_AUDIT '+json.dumps(result),flush=True)
    if not result['audit_passed']: raise SystemExit(1)

if __name__=='__main__':main()
