"""New union-source contract; historical narrow scope guards are not credited."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'build/sync-public-hash'
BASE='cbaece83b65adb94115e861e519e0147e0e0786f'
BRANCH='codex/reader-sync-public-hash-20261029'
WORKFLOW='.github/workflows/reader-sync-public-hash-20261029.yml'
TARGETS=('linux','windows','android','macos','iphone')
ENTRIES=('linux','windows','android','macos','iphone','ipad')
EXCLUSIONS=('public-boundary exact25 source guard/build orchestration',
    'original-hash exact16 source guard/main build orchestration',
    'original public/hash aggregate branch/workflow/artifact wrappers')

def require(value,message):
    if not value:raise ValueError(message)

def actions():
    require(os.environ.get('GITHUB_ACTIONS')=='true','all execution is Actions-only')
    require(os.environ.get('GITHUB_REPOSITORY')=='NoGod3524/EXReader','wrong repository')

def identity():
    return dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def record(path):return dict(bytes=Path(path).stat().st_size,sha256=digest(path))

def save(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

def load(relative,name,alias=None):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    module=importlib.util.module_from_spec(spec)
    prior=sys.modules.get('package_contract')
    try:
        if alias is not None:sys.modules['package_contract']=alias
        spec.loader.exec_module(module)
    finally:
        if alias is not None:
            if prior is None:sys.modules.pop('package_contract',None)
            else:sys.modules['package_contract']=prior
    return module

P=load('tests/reader_public_boundary_v1_20261028/run.py','union_frozen_public')
H=load('tests/reader_original_hash_boundary_20261029/package_contract.py','union_frozen_hash_contract')

def budget(text):
    limits=list(map(int,re.findall(r'^    timeout-minutes: (\d+)$',text,re.M)))
    require(limits==[15,150,100,210,110,30],'original configured job limits changed')
    require('target: [macos, iphone]' in text,'Apple matrix cardinality changed')
    require(sum(limits)+110==725,'configured runner budget exceeds725')
    require('workflow_dispatch' not in text,'no second trigger route')
    return 725

def guard():
    actions();lock=json.loads((HERE/'source_lock.json').read_text())
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    require(os.environ['GITHUB_REF_NAME']==BRANCH and identity()['attempt']=='1','one exact feature attempt only')
    require(git('rev-parse','HEAD')==identity()['source_sha'],'checkout differs from producer SHA')
    require(lock['base_sha']==BASE and git('rev-parse',BASE+'^{tree}')==lock['base_tree'],'base tree differs')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=ROOT,check=True)
    delta={p:s for s,p in (line.split('\t') for line in git('diff','--name-status',BASE,'HEAD').splitlines())}
    require(delta==lock['expected_delta'] and len(delta)==28,'exact adopted16+Sync3+new9 delta required')
    require(not git('status','--porcelain','--untracked-files=no'),'tracked checkout dirty')
    require(len(lock['adopted'])==16 and len(lock['public_packet'])==25 and not(set(lock['adopted'])&set(lock['public_packet'])),'frozen source inventory')
    for path,sha in {**lock['adopted'],**lock['public_packet']}.items():
        require(digest(ROOT/path)==sha,'reviewed predecessor bytes changed: '+path)
    all_paths=sorted(set(lock['adopted'])|set(lock['public_packet'])|set(lock['owner'])|set(lock['added']))
    require(len(all_paths)==53,'complete common-source path inventory')
    result=dict(identity(),base_sha=BASE,source_scope_passed=True,
        authorized_paths_sha256={p:digest(ROOT/p) for p in all_paths},
        adopted_hash_source=lock['adopted_sha'],public_boundary_source=BASE,
        original_source_guards_excluded=list(EXCLUSIONS)+P.EXCLUSIONS,
        configured_runner_minutes=budget((ROOT/WORKFLOW).read_text()),f07_accepted=False,physical_device=False)
    save(OUT/'source.json',result);save(P.OUT/'source.json',result)
    return result

def path_key(value,cwd):return H.canonical_dependency(value,cwd)

def union_scope(source):
    require(source==guard(),'union source/run/attempt/protected bytes differ')

def no_private_dependencies(paths):
    forbidden={'opds_internal.h','sha256.inc','reader_selector_bytes_detail.h'}
    require(not any(p.replace('\\','/').rsplit('/',1)[-1] in forbidden or
        any(part in p.replace('\\','/') for part in ('/extras/opds/','/apps/reader/original-export/src/')) for p in paths),
        'private implementation dependency remains')

def vectors(text):
    value=json.loads(text)
    sizes=(0,3,55,56,63,64,65,65535,65536,65537)
    require(set(value)=={str(n) for n in sizes},'adapter vector inventory')
    for n in sizes:
        data=b'abc' if n==3 else bytes(i%251 for i in range(n))
        require(value[str(n)]==hashlib.sha256(data).hexdigest(),'adapter digest differs at '+str(n))
    return value

def flags(target):
    common=['-DCMAKE_POSITION_INDEPENDENT_CODE=ON']
    if target=='android':
        ndk=Path(os.environ['ANDROID_HOME'])/'ndk'/os.environ['C11_NDK']
        common+=['-DCMAKE_TOOLCHAIN_FILE='+str(ndk/'build/cmake/android.toolchain.cmake'),
                 '-DANDROID_ABI=x86_64','-DANDROID_PLATFORM=android-26','-DANDROID_STL=c++_static']
    elif target=='macos':common+=['-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0']
    elif target=='iphone':common+=['-DCMAKE_SYSTEM_NAME=iOS','-DCMAKE_OSX_SYSROOT=iphonesimulator',
        '-DCMAKE_OSX_ARCHITECTURES=arm64','-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0','-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    return common

def providers(text,platform,wanted):
    # Native LLD indentation separates input contributions from demangled names.
    if platform=='android':
        try:return {s:P.lld_symbol_origin(text,s)[0] for s in wanted}
        except AssertionError as error:raise ValueError(str(error)) from error
    return H.map_providers(text,platform,wanted)

def sync_reuse_rejection(text,prefix):
    require('SYNC_DEPENDENCIES_READY' in text and 'SYNC_UNEXPECTED_ADMISSION' not in text and
        'OPDSHash unexpected usage requirement: INTERFACE_LINK_OPTIONS' in ' '.join(text.split()) and
        'EXReaderSyncConfig.cmake' in text,'Sync reused-dependency guard not reached/rejected')

def configured_paths(folder,link,target):
    actual=(folder/('trees/'+Path(link['original_build']).name+'/imported-paths.txt')).read_text().splitlines()
    require(actual==link['imported_paths'],'actual imported target paths differ')
    suffix='.lib' if target=='windows' else '.a'
    def archive(name):return ('' if target=='windows' else 'lib')+name+suffix
    if 'sync_prefix' in link:
        expected=[link['sync_prefix']+'/lib/'+archive('reader_sync'),link['hash_prefix']+'/lib/'+archive('opds_sha256_stream')]
        text=(folder/('trees/'+Path(link['original_build']).name+'/sync-links.txt')).read_text()
        require(text==link['sync_links'] and '$<LINK_ONLY:EXReaderOPDSHash::opds_sha256_stream>' in text and
            'EXReaderRevisions::reader_revision_hash' not in text,'configured Sync public dependency differs')
        selected=(folder/('trees/'+Path(link['original_build']).name+'/sync-config.txt')).read_text().strip()
        require(selected==link['sync_config']==link['sync_prefix']+'/lib/cmake/EXReaderSync/EXReaderSyncConfig.cmake','selected Sync configuration differs')
    else:
        expected=[link['hash_prefix']+'/lib/'+archive('opds_sha256_stream')]+[link['product_prefix']+'/lib/'+archive(n)
            for n in ('reader_original_import','reader_catalog','reader_catalog_sqlite')]
    require(actual==expected,'configured imported target owner differs')

def validate(folder,expected_source=None):
    """Replay this named-boundary evidence, not historical admission wrappers."""
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_text())
    require(all(manifest[k]==v for k,v in identity().items()),'proof source/run/attempt differs')
    files={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p!=folder/'manifest.json'}
    require(files==set(manifest['files']),'complete new proof inventory differs')
    for path,meta in manifest['files'].items():require(record(folder/path)==meta,'proof byte identity differs: '+path)
    report=json.loads((folder/'report.json').read_text());target=report['target']
    require(target in TARGETS and all(report[k]==v for k,v in identity().items()),'proof target/source identity')
    require(report['source']==(guard() if expected_source is None else expected_source),'union source identity differs')
    for key in ('f07_accepted','installed_android_sync_runtime','mobile_full_runtime','full_product_accepted'):
        require(report[key] is False,'inflated acceptance '+key)
    platform='ios-simulator' if target=='iphone' else target
    commands=json.loads((folder/'commands.json').read_text());by_output={}
    for command in commands:
        output=command['output'];require(output not in by_output,'duplicate command output identity');by_output[output]=command
        require(command['argv'] and command['cwd'] and command['returncode']==command['expected_returncode'],'unexpected command failure')
        require(record(folder/output)==command['output_record'],'command output bytes differ')
        for path,meta in command['subjects'].items():require(record(folder/path)==meta,'command subject bytes differ')
    def cmd(output,argv=None,positive=True):
        require(output in by_output,'missing exact command output '+output);row=by_output[output]
        if argv is not None:require(row['argv']==argv,'wrong command identity '+output)
        if positive:require(row['returncode']==0,'required positive command failed')
        return row
    owners=report['owners'];wanted={'hash','importer'}|({'sync-raw','sync-off'} if target=='android' else set())
    require(set(owners)==wanted,'named installed owner set differs')
    roles={};definitions={};imports={}
    def native(role,row):
        members=H.archive_members((folder/row['archive']).read_bytes())
        require([n for n,p in members]==[r['name'] for r in row['members']],'exact native member inventory')
        defined=set();undefined=set()
        for (_,payload),entry in zip(members,row['members']):
            require((folder/entry['object']).read_bytes()==payload,'native member bytes differ')
            query=cmd(entry['symbols']);require(query['subjects']=={entry['object']:record(folder/entry['object'])},'unbound native symbol subject')
            argv=query['argv'];require(len(argv)==3 and argv[1]==('/symbols' if target=='windows' else '-g') and
                argv[2].replace('\\','/').endswith('/proof/'+entry['object']),'wrong native symbol command')
            d,u=H.symbols((folder/entry['symbols']).read_text(),platform,payload if target=='windows' else None,role)
            require(not (defined&d&H.PUBLIC),'duplicate public hash definition');defined|=d;undefined|=u
        roles[role]=row;definitions[role]=defined;imports[role]=undefined
    dependency_evidence={}
    for label,row in owners.items():
        prefix=row['prefix'];build=row['build'];source=row['source'];installed=row['installed']
        sdk,stage,product,_=P.layout(target)
        selected=OUT/'hash-stage' if label=='hash' else product if label=='importer' else stage if label=='sync-raw' else P.OUT/'legacy-stage'
        required_prefix=report['original_workspace']+'/'+selected.relative_to(ROOT).as_posix()
        require(prefix==required_prefix,'actual owner prefix differs')
        root=report['original_workspace']+'/'
        require(build.startswith(root) and row['cache']=='original/'+build.removeprefix(root)+'/CMakeCache.txt' and
            row['install_manifest']=='original/'+build.removeprefix(root)+'/install_manifest.txt','owner build metadata path differs')
        expected_source=report['original_workspace']+('/extras/opds/src/opds_sha256_stream.c' if label=='hash' else
            '/apps/reader/original-import/original_import.cpp' if label=='importer' else '/apps/reader/sync/src/sync.cpp')
        require(path_key(source,build)==path_key(expected_source,build),'compiled owner source differs')
        manifest_rows=(folder/row['install_manifest']).read_text().splitlines()
        require(len(manifest_rows)==len(set(manifest_rows)) and
            sorted(p.replace('\\','/') for p in manifest_rows)==sorted(prefix+'/'+p for p in installed),'actual owner install manifest differs')
        for path,meta in installed.items():
            require(H.relative_object_spelling(path,'linux')==path,'unsafe owner installed path')
            require(meta['path']=='original/'+prefix.removeprefix(root)+'/'+path,'installed owner retained path differs')
            require(record(folder/meta['path'])=={k:meta[k] for k in ('bytes','sha256')},'installed owner projection differs')
        expected_headers={'include/exreader-opds-hash/opds_sha256_stream.h'} if label=='hash' else (
            {'include/exreader-product/'+n for n in ('catalog.h','sqlite3.h','original_import.h')} if label=='importer' else {'include/reader_sync.h'})
        require({p for p in installed if p.startswith('include/')}==expected_headers,'exact installed owner header inventory differs')
        library_names=('opds_sha256_stream',) if label=='hash' else ('reader_original_import','reader_catalog','reader_catalog_sqlite') if label=='importer' else ('reader_sync',)
        def library_name(name):return name+'.lib' if target=='windows' else 'lib'+name+'.a'
        require({p for p in installed if p.endswith(('.a','.lib'))}=={'lib/'+library_name(n) for n in library_names},'exact installed owner archive inventory differs')
        namespace='EXReaderOPDSHash' if label=='hash' else 'EXReaderProductCatalog' if label=='importer' else 'EXReaderSync'
        export_paths=[v['path'] for p,v in installed.items() if p.startswith('lib/cmake/'+namespace+'/') and 'Targets' in p and p.endswith('.cmake')]
        require(export_paths,'installed owner exports missing')
        exported='\n'.join((folder/p).read_text() for p in export_paths)
        require(set(re.findall(r'add_library\((\S+) STATIC IMPORTED\)',exported))=={namespace+'::'+n for n in library_names},'actual static export target inventory differs')
        require(all('${_IMPORT_PREFIX}/lib/'+library_name(n) in exported for n in library_names),'actual exported archive path differs')
        if label!='hash':require('$<LINK_ONLY:EXReaderOPDSHash::opds_sha256_stream>' in exported,'exported public hash dependency missing')
        basename='opds_sha256_stream' if label=='hash' else 'reader_original_import' if label=='importer' else 'reader_sync'
        filename=basename+'.lib' if target=='windows' else 'lib'+basename+'.a'
        require(installed['lib/'+filename]['path']==row['archive'],'installed archive owner differs')
        before=(folder/row['built_archive']).read_bytes();after=(folder/row['archive']).read_bytes()
        require(H.archive_equivalence(before,after,platform)==row['archive_equivalence'],'original archive equivalence differs')
        members=H.archive_members(before);require(len(members)==1 and members[0][0]==row['member'] and
            members[0][1]==(folder/row['object']).read_bytes(),'compiled object not exact installed member')
        cache=(folder/row['cache']).read_text();home=re.findall(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$',cache,re.M)
        directory=re.findall(r'^CMAKE_CACHEFILE_DIR:INTERNAL=(.+)$',cache,re.M)
        require(len(directory)==1 and path_key(directory[0],build)==path_key(build,build),'cache build directory differs')
        wanted_home='/extras/opds' if label=='hash' else '/apps/reader/store/native' if label=='importer' else '/apps/reader/sync'
        require(len(home)==1 and path_key(home[0],build)==path_key(report['original_workspace']+wanted_home,build),'owner build cache home differs')
        obj=row['object_spelling']
        if row['generator']=='Ninja':
            query=cmd(row['deps'],['ninja','-C',build,'-t','deps']);require(query['returncode']==0,'dependency query failed')
            groups,spellings=H.object_dependency_groups((folder/row['deps']).read_text(),[obj],platform)
            aq=cmd(row['archive_query'],['ninja','-C',build,'-t','query',filename])
            ar,_=P.ninja_explicit_inputs((folder/row['archive_query']).read_text(),filename,
                'C_STATIC_LIBRARY_LINKER' if label=='hash' else 'CXX_STATIC_LIBRARY_LINKER')
            require(ar==[obj],'actual archive inputs differ')
            cmd(row['compiler_query'],['ninja','-C',build,'-t','query',obj])
            inputs,outputs=P.ninja_explicit_inputs((folder/row['compiler_query']).read_text(),obj,
                'C_COMPILER' if label=='hash' else 'CXX_COMPILER')
            require([path_key(p,build) for p in inputs]==[path_key(source,build)] and filename in outputs,'compiler/archive source edge differs')
            paths=groups[obj]
        else:
            require(row['generator']=='Make','unsupported original generator')
            groups=P.make_dependency_group((folder/row['deps']).read_text())
            require(set(groups)=={obj} and groups[obj]['status']=='VALID','exact current Make dependency object missing')
            import shlex
            linked=[p for p in shlex.split((folder/row['archive_link']).read_text()) if p.endswith(('.o','.obj'))]
            require(linked==[obj],'Make archive member edge differs');paths=groups[obj]['paths'];spellings={}
            require([path_key(p,build) for p in paths].count(path_key(source,build))==1,'Make compiled source missing')
        require(paths,'empty owner dependency coverage')
        expected_header=report['original_workspace']+('/extras/opds/include/opds_sha256_stream.h' if label=='hash'
            else '/build/sync-public-hash/hash-stage/include/exreader-opds-hash/opds_sha256_stream.h')
        require(path_key(row['required_header'],build)==path_key(expected_header,build) and
            path_key(expected_header,build) in [path_key(p,build) for p in paths],'exact public hash dependency missing')
        header=owners['hash']['installed']['include/exreader-opds-hash/opds_sha256_stream.h']
        require((folder/header['path']).read_bytes()==(ROOT/'extras/opds/include/opds_sha256_stream.h').read_bytes(),
            'installed public hash header bytes differ')
        require(row['native']['archive']==row['archive'],'native symbols use a different installed archive')
        relative=H.relative_object_spelling(obj,platform)
        require(row['object']=='original/'+build.removeprefix(report['original_workspace']+'/')+'/'+relative,
            'compiled object retained path differs')
        if label!='hash':no_private_dependencies([path_key(p,build) for p in paths])
        if label.startswith('sync-'):
            require(row['raw'] is (label=='sync-raw'),'Sync profile claim differs')
            require(re.findall(r'^EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=(.+)$',cache,re.M)==['ON' if row['raw'] else 'OFF'],'actual Sync raw profile differs')
            exports='\n'.join((folder[v['path']]).read_text() for p,v in installed.items() if p.endswith('.cmake'))
            require('$<LINK_ONLY:EXReaderOPDSHash::opds_sha256_stream>' in exports and
                'EXReaderRevisions::reader_revision_hash' not in exports,'Sync exported dependency is not public hash only')
        dependency_evidence[label]=dict(count=len(paths),spellings=spellings,installed_archive_sha256=H.digest(folder/row['archive']))
        native(label,row['native'])
    require(definitions['hash']==H.PUBLIC|H.PRIVATE,'public hash function owner set differs')
    require(not ((definitions['hash']|imports['hash'])&H.FORBIDDEN),'generic/private hash helper leaked')
    for consumer in wanted-{'hash'}:
        require(H.PUBLIC<=imports[consumer] and not((definitions[consumer]|imports[consumer])&(H.FORBIDDEN|H.PRIVATE)),
                'consumer does not use only public hash operations: '+consumer)
        require(not(definitions[consumer]&H.PUBLIC),'consumer defines hash provider')
    checks=report['hash_checks']
    require(set(checks['oracles'])=={'normal','revision'},'coexistence oracle inventory')
    for role,row in checks['oracles'].items():
        native(role,row);require('opds_sha256_hex' in definitions[role] and not(definitions[role]&(H.PUBLIC|H.PRIVATE)),'coexistence owner collision')
    links=checks['links'];require(set(links)=={'installed','relocated','normal-first','hash-first','revision-first','hash-revision'},'hash final link matrix')
    if target=='android':
        require(set(report['sync']['probes'])=={'sync-raw','sync-off'},'Sync both profile final links required')
        links={**links,**report['sync']['probes']}
    for name,link in links.items():
        configured_paths(folder,link,target)
        require(record(folder/link['image'])==link['image_record'],'final image record differs')
        H.image_target((folder/link['image']).read_bytes(),platform)
        line,inputs,responses=H.link_closure(folder,link)
        cmd(link['commands'],['ninja','-C',link['original_build'],'-t','commands','probe'])
        extra='reader_sync_step' if name.startswith('sync-') else 'reader_original_verified_path' if name in ('installed','relocated') else 'opds_sha256_hex'
        mapped=providers((folder/link['map']).read_text(),platform,H.PUBLIC|{extra})
        if target=='android':H.android_binding((folder/('trees/'+Path(link['original_build']).name+'/CMakeCache.txt')).read_text(),line,
            name in ('installed','relocated','sync-raw','sync-off'))
        for symbol,origin in mapped.items():
            role='hash' if symbol in H.PUBLIC else (link['owner'] if name.startswith('sync-') else 'importer' if extra=='reader_original_verified_path' else
                'normal' if name in ('normal-first','hash-first') else 'revision')
            member=re.fullmatch(r'(.+):([^:]+\.(?:o|obj))',origin,re.I) if target=='windows' else re.fullmatch(r'(.+\.a)(?:\[\d+\])?\(([^()]+)\)',origin)
            require(member is not None,'final provider lacks exact archive/member')
            library,member_name=member.groups();native_row=roles[role]
            expected=report['original_workspace']+'/'+native_row['archive'].removeprefix('original/')
            if name=='relocated' and role in ('hash','importer'):
                expected=checks['relocated']+'/'+('hash' if role=='hash' else 'product')+'/lib/'+Path(expected).name
            if target=='windows' and '/' not in library.replace('\\','/'):
                require(library.removesuffix('.lib')==Path(expected).name.removesuffix('.lib'),'wrong map basename owner')
                require(sum(Path(p).name.lower()==Path(expected).name.lower() for p in inputs)==1,'ambiguous map input basename')
            else:
                if target=='windows' and not library.lower().endswith('.lib'):library+='.lib'
                require(path_key(library,link['original_build'])==path_key(expected,link['original_build']),'wrong map archive path')
            require(path_key(expected,link['original_build']) in inputs,'provider absent from exact final inputs')
            candidates=[r for r in native_row['members'] if r['name'].replace('\\','/')==member_name or
                ('/' not in member_name and r['name'].replace('\\','/').rsplit('/',1)[-1]==member_name)]
            require(len(candidates)==1,'missing/ambiguous map member')
            H.require_member_definition(folder,candidates[0],platform,symbol,role)
        if name in ('normal-first','hash-first','revision-first','hash-revision'):
            oracle='normal' if name in ('normal-first','hash-first') else 'revision'
            hp=path_key(owners['hash']['prefix']+'/lib/'+Path(roles['hash']['archive']).name,link['original_build'])
            op=path_key(report['original_workspace']+'/'+roles[oracle]['archive'].removeprefix('original/'),link['original_build'])
            require((inputs.index(op)<inputs.index(hp)) is (name in ('normal-first','revision-first')),'coexistence link order differs')
    negatives=checks['negatives'];require(set(negatives)==set(H.NEGATIVE_REASONS)|{'wrong-abi','cached'},'hash package negatives incomplete')
    for name,control in negatives.items():
        row=cmd(control['output'],control['argv'],False);require(row['returncode']==control['returncode']!=0,'negative command status differs')
        if name=='cached':require('Foreign cached OPDSHash package directory' in (folder/control['output']).read_text(),'cached package rejection reason differs')
        else:H.negative_reason(name,(folder/control['output']).read_text())
    # Complete relocation copies, including shared-prefix files, must match every
    # original byte. Presence is derived from the actual retained original root.
    for role,original_prefix,relocated in (('hash',owners['hash']['prefix'],'hash'),('product',owners['importer']['prefix'],'product')):
        old=report['original_workspace']+'/'
        original=folder/'original'/original_prefix.removeprefix(old)
        copy=folder/'trees/relocated'/relocated
        require(original.is_dir() and copy.is_dir(),'relocation input root missing')
        left={p.relative_to(original).as_posix():record(p) for p in original.rglob('*') if p.is_file()}
        right={p.relative_to(copy).as_posix():record(p) for p in copy.rglob('*') if p.is_file()}
        projection=report['prefixes'][role]
        require(left=={p:{k:m[k] for k in ('bytes','sha256')} for p,m in projection.items()},'original complete prefix projection differs')
        require(all(m['path']=='original/'+original_prefix.removeprefix(old)+'/'+p for p,m in projection.items()),'prefix projection path differs')
        require(left==right,'relocated complete package bytes differ')
    desktop=target in ('windows','linux','macos')
    if desktop:
        for name,link in checks['links'].items():
            row=cmd('runtime/'+name+'.log',[link['original_build']+'/'+link['image_name']])
            require(row['subjects']=={link['image']:record(folder/link['image'])},'desktop runtime image binding differs')
            if name not in ('installed','relocated'):H.vector_output((folder/row['output']).read_text())
        for name in ('internal','fault'):
            program='trees/controls-build/'+name+('.exe' if target=='windows' else '')
            row=cmd('runtime/'+name+'.log');require(row['subjects']=={program:record(folder/program)},'control runtime subject differs')
            expected=[report['original_workspace']+'/build/sync-public-hash/probes/controls-build/'+Path(program).name]
            if name=='fault':expected.append(report['original_workspace']+'/build/sync-public-hash/probes/fault-fixture')
            require(row['argv']==expected,'control runtime command differs')
            H.image_target((folder/program).read_bytes(),platform)
        H.vector_output((folder/'runtime/internal.log').read_text())
        require('IMPORT_FAULT_OK' in (folder/'runtime/fault.log').read_text(),'original importer fault controls missing')
        require('16,792,975-byte fixture, interruption, cancellation, duplicate, reopen and corruption checks passed' in
                (folder/'runtime/original.log').read_text(),'unchanged original-import fixture not passed')
        row=cmd('runtime/original.log');require(len(row['argv'])==2 and row['argv'][1]==report['original_workspace']+'/tests/reader_catalog/original_import_actions.py','old original script command differs')
        root='original/'+owners['importer']['build'].removeprefix(report['original_workspace']+'/')+'/'
        suffix='.exe' if target=='windows' else ''
        program=root+'reader-original-import-check'+suffix
        require(row['subjects']=={program:record(folder/program)},'original executable subject missing')
        H.image_target((folder/program).read_bytes(),platform)
        row=cmd('runtime/catalog.log');programs=[root+p+suffix for p in ('reader-catalog-check','reader-originals-check')]
        require(row['argv']==['ctest','--test-dir',owners['importer']['build'],'--output-on-failure','--no-tests=error'] and
            row['subjects']=={p:record(folder/p) for p in programs},'original catalog command/subjects differ')
        for p in programs:H.image_target((folder/p).read_bytes(),platform)
    if target=='android':
        runtime=report['sync']['runtime'];require(set(runtime)=={'sync-raw','sync-off','adapter','internal'},'Android runtime controls incomplete')
        controls=report['sync']['reuse_negatives'];require(set(controls)=={'sync-raw','sync-off'},'both Sync dependency-reuse negatives required')
        for label,control in controls.items():
            row=cmd(control['output'],control['argv'],False)
            expected_config=owners[label]['prefix']+'/lib/cmake/EXReaderSync/EXReaderSyncConfig.cmake'
            require(row['returncode']==control['returncode']!=0 and control['selected_config']==expected_config and
                '-DEXReaderSync_DIR='+owners[label]['prefix']+'/lib/cmake/EXReaderSync' in row['argv'] and
                report['original_workspace']+'/build/sync-public-hash/probes/'+label+'-mutation-src' in row['argv'],
                'Sync negative selected package/command differs')
            sync_reuse_rejection((folder/control['output']).read_text(),owners[label]['prefix'])
        require(report['sync']['adapter_source_runtime'] is True and report['sync']['installed_android_sync_runtime'] is False,'Android runtime scope inflated')
        for name,item in runtime.items():
            row=cmd(item['output'],item['command']);require(item['command']==['adb','shell','/data/local/tmp/exr-sync-hash-'+identity()['run_id']+'-'+identity()['attempt']+'/'+name],'Android CLI invocation differs')
            require(row['subjects']=={item['program']:record(folder/item['program'])} and item['record']==record(folder/item['program']) and
                item['remote_sha256']==item['record']['sha256'],'Android installed CLI byte binding differs')
            H.image_target((folder/item['program']).read_bytes(),'android')
            remote=item['command'][-1]
            cmd(item['hash_output'],['adb','shell','sha256sum',remote])
            require((folder/item['hash_output']).read_text().split()==[item['remote_sha256'],remote],'retained Android remote hash differs')
            if name.startswith('sync-'):require((folder/item['output']).read_text().strip()=='SYNC_INSTALLED_LINK_PROBE_OK','installed argument probe failed')
        text=(folder/runtime['adapter']['output']).read_text().splitlines();vectors(text[0]);require(text[1:]==['SYNC_ANDROID_ADAPTER_FAULTS_OK'],'adapter completion differs')
        H.vector_output((folder/runtime['internal']['output']).read_text())
        host=report['sync']['host'];build=host['original_build'];image=host['original_image']
        require(host['final_image_runtime_claim'] is False,'final host runtime scope inflated')
        require(host['image']=='original/'+image.removeprefix(report['original_workspace']+'/') and
            record(folder/host['image'])==host['image_record'],'actual host image identity differs')
        H.image_target((folder/host['image']).read_bytes(),'android')
        cmd(host['alias'],['ninja','-C',build,'-t','query','exreader_product'])
        nodes,_=P.ninja_explicit_inputs((folder/host['alias']).read_text(),'exreader_product','phony')
        require(nodes==[host['image_node']] and path_key(nodes[0],build)==path_key(image,build),'actual host alias differs')
        cmd(host['commands'],['ninja','-C',build,'-t','commands',host['image_node']])
        mapfile,line=P.android_link_binding((folder/host['commands']).read_text(),Path(image),Path(build))
        require(mapfile.as_posix()==host['map_path'] and host['map']=='original/'+host['map_path'].removeprefix(report['original_workspace']+'/') and
            line==host['actual_link_command'],'actual host link/map binding differs')
        H.android_binding((folder/host['cache']).read_text(),line,True)
        import shlex
        inputs=[path_key(p,build) for p in shlex.split(line) if p.endswith(('.a','.o'))]
        symbols=cmd(host['symbols']);require(symbols['argv'][1:]==['-A',image] and
            symbols['subjects']=={host['image']:record(folder/host['image'])},'actual host symbols unbound')
        table=(folder/host['symbols']).read_text();mapping=(folder/host['map']).read_text()
        for symbol in H.PUBLIC|{'reader_sync_step'}:
            role='sync-raw' if symbol=='reader_sync_step' else 'hash'
            origin,address=P.lld_symbol_origin(mapping,symbol)
            library=owners[role]['prefix']+'/lib/'+Path(roles[role]['archive']).name
            require(origin==library+'('+owners[role]['member']+')' and path_key(library,build) in inputs,'actual host provider owner differs')
            H.require_member_definition(folder,roles[role]['members'][0],'android',symbol,role)
            values=re.findall(r'^'+re.escape(image)+r':\s+([0-9a-fA-F]+)\s+[Tt]\s+'+symbol+r'$',table,re.M)
            require(len(values)==1 and int(values[0],16)==address,'actual host symbol/map address differs')
    return dict(target=target,named_public_hash_boundary=True,sync_static_boundary=target=='android',
        android_adapter_source_runtime=target=='android',installed_android_sync_runtime=False,
        desktop_hash_runtime=desktop,f07_accepted=False,full_product_accepted=False,
        source_sha=identity()['source_sha'],dependencies=dependency_evidence)
