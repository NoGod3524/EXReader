"""New union-source contract; historical narrow scope guards are not credited."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import unicodedata

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

BSD_CRITERION='sync-ios-bsd-two-profile-v1'
PUBLIC_OVERRIDE='tests/reader_public_boundary_v1_20261028/run.py'
PUBLIC_ORIGINAL_SHA='7752eeca7f45aaa22adbb5881fa93459448a66550181a6ca9e6376bfece92325'
RETAINED_MARKER='[sync-retained-replay]'
REPAIR_BASE='f25ce471ce057c3181eb81853e6912350a1b5fed'
REPAIR_TREE='303060019705b60728bb45467c1c6f93c13a6c0f'
REPAIR_PATHS=(PUBLIC_OVERRIDE,WORKFLOW,*('tests/reader_sync_public_hash_20261029/'+name for name in
    ('run.py','package_contract.py','test_contract.py','authenticate.py','source_lock.json')))

def repair_scope(delta):
    require(delta=={p:'M' for p in REPAIR_PATHS},'exact seven-path repair delta versus published f25 required')

def workflow_lane(message):
    require(isinstance(message,str),'push message must be text')
    return 'retained' if RETAINED_MARKER in message else 'native'

def current_lane():
    require(os.environ.get('GITHUB_EVENT_NAME')=='push','only reviewed push lanes allowed')
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    require(event['head_commit']['id']==identity()['source_sha'],'push event source differs')
    return workflow_lane(event['head_commit']['message'])

def frozen_source_projection(lock,current,historical):
    override=lock.get('public_validation_override',{})
    require(set(override)=={PUBLIC_OVERRIDE},'exact one public validation override required')
    row=override[PUBLIC_OVERRIDE]
    require(set(row)=={'historical_sha256','current_sha256','role'} and
        row['role']=='optional capture/replay comparator hooks; legacy defaults unchanged' and
        row['historical_sha256']==lock['public_packet'][PUBLIC_OVERRIDE]==PUBLIC_ORIGINAL_SHA and
        historical==PUBLIC_ORIGINAL_SHA and re.fullmatch('[0-9a-f]{64}',row['current_sha256']) is not None,
        'historical public validation override differs')
    expected={**lock['adopted'],**lock['public_packet']};expected[PUBLIC_OVERRIDE]=row['current_sha256']
    require(set(current)==set(expected),'frozen source projection incomplete')
    for path,sha in expected.items():require(current[path]==sha,'reviewed predecessor bytes changed: '+path)
    return override

def bsd_profiles(raw):
    """Two finite whole-archive geometries; never a per-member padding union."""
    require(raw.startswith(b'!<arch>\n'),'unsupported BSD archive magic')
    offset=8;names=set();frames=[];profiles={'M','A'}
    def number(field,base,label):
        pattern=rb'[0-7]+ *' if base==8 else rb'[0-9]+ *'
        require(re.fullmatch(pattern,field) is not None,'noncanonical BSD '+label)
        value=int(field,base);spelling=(format(value,'o') if base==8 else str(value)).encode()
        require(field==spelling.ljust(len(field),b' '),'noncanonical BSD '+label)
        return value
    while offset<len(raw):
        header=raw[offset:offset+60]
        require(len(header)==60 and header[58:]==b'`\n','malformed BSD member header')
        match=re.fullmatch(rb'#1/([1-9][0-9]*) *',header[:16])
        require(match is not None,'unsupported BSD extended member name')
        length=int(match[1])
        require(header[:16]==('#1/'+str(length)).encode().ljust(16,b' '),'noncanonical BSD name length')
        timestamp=number(header[16:28],10,'timestamp')
        uid=number(header[28:34],10,'uid');gid=number(header[34:40],10,'gid');mode=number(header[40:48],8,'mode')
        size=number(header[48:58],10,'size');start=offset+60;end=start+size
        require(0<length<size and end<=len(raw),'BSD member name/payload bounds')
        extended=raw[start:start+length];name=extended.split(b'\0',1)[0]
        require(name and all(32<=c<127 for c in name),'invalid BSD member name')
        require(extended==name+b'\0'*(length-len(name)),'non-NUL BSD name padding')
        minimal=len(name)+(-(start+len(name)))%8
        apple=((len(name)+7)//8)*8+4
        compatible=set()
        if length==minimal:compatible.add('M')
        if length==apple and offset%8==0 and (start+length)%8==0 and end%8==0 and (size-length)%8==0:
            compatible.add('A')
        decoded=name.decode('ascii');require(decoded not in names,'duplicate BSD member name');names.add(decoded)
        require(raw[end:end+size%2]==b'\n'*(size%2),'noncanonical BSD member padding')
        payload=raw[start+length:end]
        if not frames:
            require(offset==8 and decoded in ('__.SYMDEF','__.SYMDEF SORTED'),'unsupported first BSD index name')
            if decoded!='__.SYMDEF SORTED' or length!=20:compatible.discard('A')
        else:
            require(not decoded.startswith('__.SYMDEF'),'second or unknown BSD index member')
            require(payload and not payload.startswith((b'BC\xc0\xde',b'\xde\xc0\x17\x0b')),'bitcode/empty BSD object unsupported')
        require(compatible,'unsupported BSD name geometry')
        profiles&=compatible
        frames.append(dict(name=decoded,header_offset=offset,timestamp=timestamp,uid=uid,gid=gid,mode=mode,
            extended_name_bytes=length,name_bytes=len(name),nul_padding_bytes=length-len(name),
            payload_offset=start+length,payload_bytes=len(payload),payload_sha256=hashlib.sha256(payload).hexdigest(),
            member_end=end,outer_padding_bytes=size%2,compatible_profiles=sorted(compatible)))
        offset=end+size%2
    require(offset==len(raw) and len(frames)>1,'BSD index/archive extent')
    require(profiles,'mixed BSD whole-archive profiles')
    return dict(profiles=sorted(profiles),frames=frames)

def union_archive_equivalence(before,after,target):
    """Opt-in simulator criterion; original default parser/comparator stay intact."""
    if before==after or target not in ('iphone','ipad'):
        result=P.installed_archive_equivalence(before,after,target)
        result['union_criterion']=dict(version=BSD_CRITERION,profile_applied=False,profiles=[],
            original_default_used=True,producer_binary_attributed=False)
        return result
    require(len(before)==len(after),'archive total size differs')
    b=bsd_profiles(before);a=bsd_profiles(after)
    require(b['profiles']==a['profiles'],'archive whole profiles differ')
    def comparable(parsed):
        rows=[dict(r) for r in parsed['frames']];rows[0].pop('timestamp');return rows
    require(comparable(b)==comparable(a),'ordered BSD frame records differ')
    require(before[:24]==after[:24] and before[36:]==after[36:],'archive non-timestamp bytes differ')
    if 'M' in b['profiles']:
        result=P.installed_archive_equivalence(before,after,target)
    else:
        require(b['profiles']==['A'],'unknown BSD whole-archive profile')
        bi=b['frames'][0];ai=a['frames'][0]
        result=dict(exact_archive_equal=False,mode='iphonesimulator-first-bsd-index-timestamp-apple-name-profile',
            build_sha256=hashlib.sha256(before).hexdigest(),installed_sha256=hashlib.sha256(after).hexdigest(),
            comparison=dict(index_name=bi['name'],timestamp_offset=24,timestamp_bytes=12,
                build_timestamp=bi['timestamp'],installed_timestamp=ai['timestamp'],
                differing_offsets=[i for i in range(24,36) if before[i]!=after[i]],
                comparison_sha256=hashlib.sha256(before[:24]+b'0           '+before[36:]).hexdigest(),
                index_payload_sha256=bi['payload_sha256'],
                ordered_objects=[dict(name=f['name'],bytes=f['payload_bytes'],sha256=f['payload_sha256']) for f in b['frames'][1:]],
                all_non_timestamp_bytes_equal=True))
    result['union_criterion']=dict(version=BSD_CRITERION,profile_applied=True,profiles=b['profiles'],
        original_default_used='M' in b['profiles'],producer_binary_attributed=False,
        build_frames=b['frames'],installed_frames=a['frames'])
    return result

def budget(text):
    limits=list(map(int,re.findall(r'^    timeout-minutes: (\d+)$',text,re.M)))
    require(limits==[15,150,100,210,110,30],'original configured job limits changed')
    require('target: [macos, iphone]' in text,'Apple matrix cardinality changed')
    require(sum(limits)+110==725,'configured runner budget exceeds725')
    require('workflow_dispatch' not in text,'no second trigger route')
    skip="    if: ${{ !contains(github.event.head_commit.message, '[sync-retained-replay]') }}"
    require(text.count(skip)==4,'all four native job definitions must skip retained lane')
    require("    if: ${{ always() && needs.protocol.result == 'success' }}" in text,
        'authentication lane must require successful protocol')
    require("run.py retained" in text and "run.py authenticate" in text and
        "REPLAY_LANE: ${{ contains(github.event.head_commit.message, '[sync-retained-replay]') && 'retained' || 'native' }}" in text,
        'explicit retained/native authentication routing required')
    return 725

def guard():
    actions();lock=json.loads((HERE/'source_lock.json').read_text())
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    require(os.environ['GITHUB_REF_NAME']==BRANCH and identity()['attempt']=='1','one exact feature attempt only')
    require(git('rev-parse','HEAD')==identity()['source_sha'],'checkout differs from producer SHA')
    require(lock['base_sha']==BASE and git('rev-parse',BASE+'^{tree}')==lock['base_tree'],'base tree differs')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=ROOT,check=True)
    require(git('rev-parse',REPAIR_BASE+'^{tree}')==REPAIR_TREE,'published repair base tree differs')
    subprocess.run(['git','merge-base','--is-ancestor',REPAIR_BASE,'HEAD'],cwd=ROOT,check=True)
    repair_scope({p:s for s,p in (line.split('\t') for line in git('diff','--name-status',REPAIR_BASE,'HEAD').splitlines())})
    delta={p:s for s,p in (line.split('\t') for line in git('diff','--name-status',BASE,'HEAD').splitlines())}
    require(delta==lock['expected_delta'] and len(delta)==29 and delta.get(PUBLIC_OVERRIDE)=='M',
        'exact adopted16+Sync3+new9+one validation override delta required')
    require(not git('status','--porcelain','--untracked-files=no'),'tracked checkout dirty')
    require(len(lock['adopted'])==16 and len(lock['public_packet'])==25 and not(set(lock['adopted'])&set(lock['public_packet'])),'frozen source inventory')
    historical=hashlib.sha256(subprocess.check_output(['git','show',BASE+':'+PUBLIC_OVERRIDE],cwd=ROOT)).hexdigest()
    override=frozen_source_projection(lock,{p:digest(ROOT/p) for p in set(lock['adopted'])|set(lock['public_packet'])},historical)
    all_paths=sorted(set(lock['adopted'])|set(lock['public_packet'])|set(lock['owner'])|set(lock['added']))
    require(len(all_paths)==53,'complete common-source path inventory')
    result=dict(identity(),base_sha=BASE,source_scope_passed=True,
        authorized_paths_sha256={p:digest(ROOT/p) for p in all_paths},
        adopted_hash_source=lock['adopted_sha'],public_boundary_source=BASE,
        public_validation_override=override,legacy_public_default_criterion_unchanged=True,
        repair_base_sha=REPAIR_BASE,repair_paths=list(REPAIR_PATHS),
        lane=current_lane(),archive_criterion=BSD_CRITERION,
        original_source_guards_excluded=list(EXCLUSIONS)+P.EXCLUSIONS,
        configured_runner_minutes=budget((ROOT/WORKFLOW).read_text()),f07_accepted=False,physical_device=False)
    save(OUT/'source.json',result);save(P.OUT/'source.json',result)
    return result

def android_cache_identity(text,home,build):
    """Only the two observed CMake CLI types; never substring/last-row selection."""
    require(all(ord(c)>=32 or c in '\t\r\n' for c in text) and '\x7f' not in text,
            'unsupported actual Android cache control character')
    wanted={
        'ANDROID_ABI':({'STRING','UNINITIALIZED'},'x86_64'),
        'ANDROID_PLATFORM':({'STRING','UNINITIALIZED'},'android-26'),
        'ANDROID_STL':({'STRING','UNINITIALIZED'},'c++_static'),
        'CMAKE_HOME_DIRECTORY':({'INTERNAL'},home),
        'CMAKE_CACHEFILE_DIR':({'INTERNAL'},build),
        'CMAKE_TOOLCHAIN_FILE':({'FILEPATH'},None),
        'EXR_HOST_SDK_VERSION':({'STRING'},'3.42.0'),
        'EXR_READER_SELECTOR_BYTES_CANDIDATE':({'BOOL'},'ON')}
    rows={key:[] for key in wanted}
    for line in text.splitlines():
        for key in wanted:
            if not(line.startswith(key+':') or line.startswith(key+'=')):continue
            match=re.fullmatch(re.escape(key)+r':([A-Z_]+)=(.*)',line)
            require(match is not None,'malformed actual Android cache key: '+key)
            rows[key].append({'type':match[1],'value':match[2]})
    for key,(types,value) in wanted.items():
        require(len(rows[key])==1,'duplicate/missing actual Android cache key: '+key)
        row=rows[key][0]
        require(row['type'] in types and (value is None or row['value']==value),
                'actual Android cache identity differs: '+key)
    toolchain=rows['CMAKE_TOOLCHAIN_FILE'][0]['value']
    require(toolchain.startswith('/') and '\\' not in toolchain and ':' not in toolchain and
            PurePosixPath(toolchain).as_posix()==toolchain and '..' not in PurePosixPath(toolchain).parts and
            toolchain.endswith('/ndk/27.0.12077973/build/cmake/android.toolchain.cmake'),
            'actual Android cache toolchain origin differs')
    return {key:values[0] for key,values in rows.items()}

PROOF_REL='build/sync-public-hash/proof'
PARK_REL='build/public-boundary-v1/union-proof-park'
ISOLATION_REL='build/sync-public-hash/capture-isolation.json'
PUBLIC_REL='build/public-boundary-v1'

def checked_relative(name):
    p=PurePosixPath(name)
    require(bool(name) and p.parts and not p.is_absolute() and p.as_posix()==name and
            '..' not in p.parts and '\\' not in name and ':' not in name and
            all(ord(c)>=32 and ord(c)!=127 for c in name),'unsafe isolation relative path')
    return p

def proof_inventory(folder):
    """Physical producer measurement. Replayers must not credit transported modes."""
    folder=Path(folder)
    require(folder.is_dir() and not folder.is_symlink() and folder.is_absolute() and
            folder.resolve()==folder,'proof root/ancestor missing/alias')
    files={};directories={'.':folder.stat().st_mode&0o777};aliases={}
    for path in sorted(folder.rglob('*')):
        name=path.relative_to(folder).as_posix();checked_relative(name)
        key=unicodedata.normalize('NFC',name).casefold()
        require(key not in aliases,'proof case/Unicode alias');aliases[key]=name
        mode=path.lstat().st_mode
        require(not stat.S_ISLNK(mode) and (stat.S_ISREG(mode) or stat.S_ISDIR(mode)),
                'proof link/special entry')
        if stat.S_ISDIR(mode):directories[name]=mode&0o777
        else:files[name]=dict(record(path),mode=mode&0o777)
    require(files,'empty proof inventory')
    return dict(files=files,directories=directories)

def live_cache_inventory(root,exclude_proof):
    root=Path(root);files={};aliases=set()
    for start in (root/'build',root/'examples/android/app/.cxx'):
        if not start.exists():continue
        for path in sorted(start.rglob('CMakeCache.txt')):
            if root/PUBLIC_REL in path.parents:continue
            if exclude_proof and root/PROOF_REL in path.parents:continue
            name=path.relative_to(root).as_posix();checked_relative(name)
            key=unicodedata.normalize('NFC',name).casefold()
            require(key not in aliases,'live cache alias');aliases.add(key)
            require(path.is_file() and not path.is_symlink() and
                    path.resolve().is_relative_to(root.resolve()),'live cache escaped/aliased')
            require(all(not parent.is_symlink() for parent in path.parents if parent.is_relative_to(root)),
                    'live cache ancestor alias')
            files[name]=record(path)
    require(files,'no real live build cache retained')
    return files

def isolated_capture(root,ident,callback):
    """Move only our proof copy under the unchanged collector's existing exclusion."""
    root=Path(root);proof=root/PROOF_REL;park=root/PARK_REL
    # Reject aliases before creating any failure record beneath a potentially
    # redirected proof parent, and before moving any directory at all.
    require(root.is_absolute() and root.resolve()==root and proof.parent.resolve()==proof.parent and
            park.parent.resolve()==park.parent,'capture root/proof/parking ancestor alias')
    result=dict(ident,proof_path=PROOF_REL,parking_path=PARK_REL,capture_succeeded=False,
        restored=False,isolation_passed=False,errors=[],
        mode_directory_origin='producer-observed before/after, not transport filesystem metadata')
    moved=False;phase='preflight';original_error=None
    try:
        require(not park.exists() and not park.is_symlink(),'proof parking destination occupied')
        require(park.parent.is_dir() and not park.parent.is_symlink(),'public exclusion root missing/alias')
        result['before']=proof_inventory(proof)
        result['live_before']=live_cache_inventory(root,True)
        proof.rename(park);moved=True
        result['live_parked']=live_cache_inventory(root,False)
        require(result['live_parked']==result['live_before'],'parking hid/changed a live build cache')
        phase='capture';callback();result['capture_succeeded']=True
    except Exception as error:
        original_error=error;result['errors'].append(dict(phase=phase,type=type(error).__name__,message=str(error)))
    finally:
        if moved:
            try:
                require(not proof.exists() and not proof.is_symlink(),'proof restoration destination occupied')
                park.rename(proof);result['restored']=True
                result['after']=proof_inventory(proof)
                result['live_after']=live_cache_inventory(root,True)
                require(result['after']==result['before'],'restored proof files/directories/modes differ')
                require(result['live_after']==result['live_before'],'capture changed/omitted a live build cache')
                require(not park.exists() and not park.is_symlink(),'proof parking remained')
            except Exception as error:
                result['errors'].append(dict(phase='restoration',type=type(error).__name__,message=str(error)))
                if original_error is None:original_error=error
        result['isolation_passed']=bool(result['capture_succeeded'] and result['restored'] and not result['errors'])
        save(root/ISOLATION_REL,result)
    if result['errors']:
        raise ValueError('capture isolation failed: '+'; '.join(e['phase']+': '+e['message'] for e in result['errors'])) from original_error
    return result

def validate_capture_isolation(extracted,inventory,ident):
    """Rehash content; bind file-mode projection to authenticated outer metadata."""
    extracted=Path(extracted);row=json.loads((extracted/ISOLATION_REL).read_text())
    require(all(row.get(k)==v for k,v in ident.items()) and row['proof_path']==PROOF_REL and
            row['parking_path']==PARK_REL,'capture isolation identity/path differs')
    require(row['capture_succeeded'] is True and row['restored'] is True and
            row['isolation_passed'] is True and row['errors']==[],'capture isolation failed/incomplete')
    require(row['before']==row['after'],'producer restored proof projection differs')
    require(row['live_before']==row['live_parked']==row['live_after'] and row['live_before'],
            'producer live-cache projection differs')
    require(row['mode_directory_origin']=='producer-observed before/after, not transport filesystem metadata',
            'isolation metadata origin differs')
    declared=row['after'];physical=proof_inventory(extracted/PROOF_REL)
    require(set(declared)=={'files','directories'} and '.' in declared['directories'],'proof projection shape differs')
    aliases={}
    for kind,values in (('dir',declared['directories']),('file',declared['files'])):
        for name,value in values.items():
            if name=='.':require(kind=='dir','root file alias');continue
            path=checked_relative(name);key=unicodedata.normalize('NFC',name).casefold()
            require(key not in aliases,'declared proof alias/type collision');aliases[key]=name
            mode=value if kind=='dir' else value['mode']
            if kind=='file':require(set(value)=={'bytes','sha256','mode'},'producer file projection shape differs')
            require(type(mode) is int and 0<=mode<=0o777,'invalid producer mode projection')
            for parent in path.parents:
                require(parent.as_posix() in declared['directories'],'incomplete producer directory ancestry')
    require(type(declared['directories']['.']) is int and 0<=declared['directories']['.']<=0o777,
            'invalid producer root mode')
    strip=lambda records:{p:{k:v[k] for k in ('bytes','sha256')} for p,v in records.items()}
    require(strip(physical['files'])==strip(declared['files']),'restored proof content differs')
    require(set(physical['directories'])<=set(declared['directories']),'transported directory not declared')
    expected={PROOF_REL+'/'+p for p in declared['files']}
    require({p for p in inventory['files'] if p.startswith(PROOF_REL+'/')}==expected,
            'outer proof inventory differs')
    for name,meta in declared['files'].items():
        actual=inventory['files'][PROOF_REL+'/'+name]
        require(all(actual[k]==meta[k] for k in ('bytes','sha256','mode')) and actual['symlink_target'] is None,
                'original outer file/mode projection differs')
    retained_live={name for name in inventory['files'] if
        (name.startswith('build/') or name.startswith('examples/android/app/.cxx/')) and
        name.endswith('/CMakeCache.txt') and not name.startswith((PROOF_REL+'/',PUBLIC_REL+'/'))}
    require(set(row['live_before'])==retained_live,'complete retained live-cache inventory differs')
    for name,meta in row['live_before'].items():
        checked_relative(name)
        require((name.startswith('build/') or name.startswith('examples/android/app/.cxx/')) and
                name.endswith('/CMakeCache.txt') and not name.startswith((PROOF_REL+'/',PUBLIC_REL+'/')),
                'invalid live build cache projection')
        require(name in inventory['files'] and all(inventory['files'][name][k]==meta[k] for k in ('bytes','sha256')) and
                record(extracted/name)==meta,'retained live build cache differs')
    return dict(restored_files_rehashed=len(declared['files']),live_caches_rehashed=len(row['live_before']),
        producer_directory_modes_equal=True,original_file_modes_outer_bound=True,
        transported_physical_modes_credited=False,transported_empty_directories_credited=False)

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
        require(host['cache']=='original/'+build.removeprefix(report['original_workspace']+'/')+'/CMakeCache.txt',
                'actual Android selected cache path differs')
        cache=(folder/host['cache']).read_text()
        selected=android_cache_identity(cache,report['original_workspace']+'/examples/android/app/src/main/cpp',build)
        require(host['cache_selection']==selected,'actual Android selected typed cache differs')
        H.android_binding(cache,line,True)
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
