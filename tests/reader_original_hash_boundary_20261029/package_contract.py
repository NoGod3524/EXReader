"""Independent Actions-only proof contract for this narrow public hash boundary."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import subprocess
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
BRANCH = 'codex/reader-original-hash-boundary-20261029'
WORKFLOW = '.github/workflows/reader-original-hash-boundary-20261029.yml'
TARGETS = ('windows', 'linux', 'macos', 'android', 'ios-device', 'ios-simulator')
OWNER_PATHS = ('extras/opds/include/opds_sha256_stream.h', 'extras/opds/src/opds_core.c',
    'extras/opds/src/opds_sha256_stream.c', 'extras/opds/CMakeLists.txt',
    'extras/opds/EXReaderOPDSHashConfig.cmake.in', 'apps/reader/original-import/original_import.cpp',
    'apps/reader/store/native/CMakeLists.txt', 'apps/reader/store/native/EXReaderProductCatalogConfig.cmake.in')
VALIDATION_PATHS = tuple('tests/reader_original_hash_boundary_20261029/' + name for name in
    ('run.py','stream_check.c','import_fault_check.cpp','package_contract.py','test_contract.py','authenticate.py')) + (
    WORKFLOW, 'docs/reader-total-progress/reader-original-hash-boundary-20261029.md')
PUBLIC = {'opds_sha256_stream_create','opds_sha256_stream_update','opds_sha256_stream_finish_hex','opds_sha256_stream_destroy'}
PRIVATE = {'exreader_opds_hash_private_init','exreader_opds_hash_private_update','exreader_opds_hash_private_final_hex'}
FORBIDDEN = {'opds_sha_init','opds_sha_update','opds_sha_final_hex','opds_sha256_hex'}
NEGATIVE_REASONS = {
    'missing':'Set READER_ORIGINAL_HASH_PREFIX or EXREADER_ORIGINAL_HASH_PREFIX',
    'wrong-prefix':'Could not find a package configuration file provided by "EXReaderOPDSHash"',
    'precreated':'Pre-created or foreign OPDSHash target is forbidden',
    'redirected':'OPDSHash imported archive escapes its exact owner',
    'conflict':'Conflicting original hash prefix selectors',
    'mutated':'OPDSHash unexpected usage requirement: INTERFACE_LINK_OPTIONS',
    'config-injection':'OPDSHash unexpected configured requirement: IMPORTED_LINK_DEPENDENT_LIBRARIES_RELEASE'}

def negative_reason(name,text):
    text=' '.join(text.split())
    if name=='wrong-abi':
        require('opds_sha256_stream' in text and re.search(r'incompatib|conflict|architecture|machine type|built for|wrong format|EM:',text,re.I),
            'wrong-ABI fixture did not reach native ABI rejection')
    else:require(NEGATIVE_REASONS[name] in text,'package negative hit an unrelated rejection: '+name)

def require(ok, message):
    if not ok: raise ValueError(message)

def actions_only():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'execution is Actions-only')

def identity():
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'])

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def record(path): return dict(bytes=Path(path).stat().st_size,sha256=digest(path))
def save(path, data):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8')

def guard():
    actions_only()
    def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    require(git('rev-parse','HEAD')==identity()['source_sha'],'checkout identity')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=ROOT,check=True)
    changed=set(git('diff','--name-only',BASE,'HEAD').splitlines())
    require(changed == set(OWNER_PATHS+VALIDATION_PATHS),'exact sixteen-file source scope: '+repr(sorted(changed)))
    # SDK, existing tests, workflows and other owners are outside the exact set.
    return dict(identity(),base_sha=BASE,files={p:record(ROOT/p) for p in sorted(changed)},source_scope_passed=True)

def safe_members(z):
    names={}; types={}; total=0
    for i in z.infolist():
        name=i.filename; p=PurePosixPath(name)
        require(name and p.parts and not p.is_absolute() and '\\' not in name and ':' not in name and
            all(ord(c)>=32 and ord(c)!=127 for c in name) and '..' not in p.parts and
            p.as_posix()+('/' if i.is_dir() else '')==name,'unsafe archive path')
        mode=(i.external_attr>>16)&0xffff
        require(not stat.S_ISLNK(mode) and stat.S_IFMT(mode) in (0,stat.S_IFREG,stat.S_IFDIR),'special archive entry')
        require(i.file_size<=2*1024**3,'member resource limit')
        total+=i.file_size;require(total<=8*1024**3,'archive resource limit')
        for n in range(1,len(p.parts)+1):
            spelling='/'.join(p.parts[:n]);key=unicodedata.normalize('NFC',spelling).casefold()
            kind='dir' if n<len(p.parts) or i.is_dir() else 'file'
            require(key not in types or types[key]==(spelling,kind),'archive alias/file-directory collision')
            types[key]=(spelling,kind)
        require(name not in names,'duplicate archive entry');names[name]=i
    return names

def extract(z, dest):
    names=safe_members(z);dest=Path(dest);require(not dest.exists(),'extraction destination must be fresh')
    dest.mkdir(parents=True)
    for name,i in names.items():
        out=dest/name
        if i.is_dir(): out.mkdir(parents=True,exist_ok=True)
        else:
            out.parent.mkdir(parents=True,exist_ok=True)
            with z.open(i) as src,out.open('wb') as dst:
                while block:=src.read(1024*1024): dst.write(block)
    return dest

def archive_members(raw):
    require(raw.startswith(b'!<arch>\n'),'unsupported static archive format')
    offset=8;longnames=b'';members=[];seen=set()
    while offset<len(raw):
        require(offset+60<=len(raw),'truncated archive header')
        header=raw[offset:offset+60];require(header[58:]==b'`\n','archive header trailer')
        name=header[:16].decode('ascii').rstrip();size=int(header[48:58]);start=offset+60;end=start+size
        require(size>=0 and end<=len(raw),'archive member bounds');payload=raw[start:end]
        if name=='//':longnames=payload
        elif name in ('/','/SYM64/'):pass
        else:
            if name.startswith('#1/'):
                length=int(name[3:]);require(length<=len(payload),'BSD long name bounds')
                name=payload[:length].rstrip(b'\0').decode();payload=payload[length:]
            elif name.startswith('/'):
                pos=int(name[1:]);require(pos<len(longnames),'archive long name offset')
                tail=longnames[pos:];stop=tail.find(b'\n');stop=len(tail) if stop<0 else stop
                name=tail[:stop].split(b'\0',1)[0].rstrip(b'/').decode()
            else:name=name.rstrip('/')
            if not name.startswith('__.SYMDEF'):
                require(name not in seen and name,'duplicate/empty archive member');seen.add(name)
                require(payload and not payload.startswith((b'BC\xc0\xde',b'\xde\xc0\x17\x0b')),'bitcode/empty member unsupported')
                members.append((name,payload))
        offset=end+(size%2)
    require(offset==len(raw) and members,'archive extent or no members');return members

def symbols(text, target):
    definitions=set();undefined=set()
    for line in text.splitlines():
        if target=='windows':
            if '|' not in line or 'External' not in line:continue
            require('WeakExternal' not in line,'weak COFF external is unsupported')
            m=re.match(r'^\s*[0-9A-Fa-f]+\s+([0-9A-Fa-f]+)\s+(UNDEF|SECT[0-9A-Fa-f]+)\b(.*?)\bExternal\s+\|\s+(\S+)\s*$',line)
            require(m is not None,'unknown COFF external row: '+line)
            value,section,kind,name=m.groups()
            if section=='UNDEF':
                require(int(value,16)==0,'COFF common symbol is not a function import');undefined.add(name)
            else:
                # Only function definitions can grant the public ABI.
                if '()' in kind:definitions.add(name)
        else:
            if not line.strip():continue
            m=re.match(r'^\s*(?:[0-9a-fA-F]+\s+)?([A-Za-z?])\s+(\S+)\s*$',line)
            require(m is not None,'unrecognized native nm row: '+line)
            kind,name=m.groups()
            require(kind in set('ABCDGIRSTUVWabcdgirstuvwpNn'),'unsupported native nm symbol kind: '+kind)
            if target.startswith('ios') or target=='macos':name=name[1:] if name.startswith('_') else name
            if kind=='T':definitions.add(name)
            elif kind=='U':undefined.add(name)
            elif (name in PUBLIC|PRIVATE|FORBIDDEN):raise ValueError('non-function/weak hash entry')
    return definitions,undefined

def deps_groups(text,required_valid=()):
    result={};lines=text.splitlines();i=0
    while i<len(lines):
        if not lines[i].strip():i+=1;continue
        m=re.match(r'^(.*): #deps (\d+), deps mtime \d+ \((VALID|STALE)\)$',lines[i])
        require(m is not None,'unknown Ninja dependency header: '+lines[i]);obj,count,status=m.groups();i+=1
        if obj in required_valid:require(status=='VALID','fresh relevant object dependency record is stale')
        require(obj not in result,'duplicate dependency object');rows=[]
        while i<len(lines) and lines[i].startswith('    '):rows.append(lines[i][4:]);i+=1
        require(len(rows)==int(count),'truncated dependency coverage')
        result[obj]=rows
    return result

def canonical_dependency(path,cwd):
    # Windows paths must be resolved lexically on the Linux authenticator too.
    p=path.replace('\\','/');base=cwd.replace('\\','/').rstrip('/')
    require(not re.match(r'^[A-Za-z]:[^/]',p),'drive-relative dependency')
    if not (p.startswith('/') or re.match(r'^[A-Za-z]:/',p)):p=base+'/'+p
    drive=''
    if re.match(r'^[A-Za-z]:/',p):drive=p[:2].lower();p=p[2:]
    parts=[]
    for part in p.split('/'):
        if part in ('','.'):continue
        if part=='..':require(parts,'dependency root escape');parts.pop()
        else:parts.append(part)
    return drive+'/'+'/'.join(parts)

def vector_output(text):
    rows=re.findall(r'^VECTOR (\d+) (\d+) ([0-9a-f]{64})$',text,re.M)
    expected={(n,k) for n in (0,1,3,55,56,63,64,65,65535,65536,65537) for k in (1,7,64,65536)}
    require(len(rows)==len(expected) and {(int(n),int(k)) for n,k,_ in rows}==expected,'vector matrix incomplete')
    for n,_,value in rows:
        require(hashlib.sha256(bytes((i*29+7)&255 for i in range(int(n)))).hexdigest()==value,'independent vector digest mismatch')
    require('STREAM_OK' in text,'stream completion marker')

def map_providers(text,target,wanted=None):
    """Exact native symbol -> retained archive/member, never substring presence."""
    wanted=PUBLIC if wanted is None else set(wanted)
    rows={};extent=None;objects={}
    def add(symbol,origin):
        symbol=symbol.removeprefix('_') if target=='macos' or target.startswith('ios') else symbol
        if symbol in wanted:
            require(symbol not in rows,'duplicate final stream provider')
            rows[symbol]=origin.replace('\\','/')
    for line in text.splitlines():
        if target=='windows':
            m=re.fullmatch(r'\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8,16}\s+(\S+)\s+[0-9A-Fa-f]{8,16}\s+(?:[fi]\s+)*(.+?)\s*',line)
            if m:add(*m.groups())
        elif target=='macos' or target.startswith('ios'):
            m=re.fullmatch(r'\[\s*(\d+)\]\s+(.+)',line)
            if m:objects[m[1]]=m[2]
            m=re.fullmatch(r'0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+\[\s*(\d+)\]\s+(\S+)',line)
            if m and m[2].removeprefix('_') in wanted:
                require(m[1] in objects,'Mach-O symbol has unknown object ordinal');add(m[2],objects[m[1]])
        elif target=='android':
            # LLD map: VMA LMA Size Align InputSection/Symbol. Preserve extent.
            m=re.match(r'^\s*([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+\d+\s+(.+?)\s*$',line)
            if m:
                start,size,tail=int(m[1],16),int(m[2],16),m[3]
                if ':(' in tail:extent=(start,start+size,tail.rsplit(':(',1)[0])
                elif tail.startswith('.'):extent=None
                elif tail in wanted:
                    require(extent is not None and extent[0]<=start<extent[1],'LLD symbol lacks exact input extent');add(tail,extent[2])
                elif re.search(r'\.a\(|\.o(?:\s|$)|\.obj(?:\s|$)',tail):
                    raise ValueError('unsupported LLD input contribution row')
            elif ':(' in line or (re.match(r'^\s*[0-9a-fA-F]+\s',line) and re.search(r'\.a\(|\.o(?:\s|$)|\.obj(?:\s|$)',line)):
                raise ValueError('malformed LLD contribution row')
        else:
            if re.match(r'^\s*\.\S+',line):extent=None
            m=re.match(r'^\s*(?:\.\S+\s+)?0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)(?:\s+(.*?))?\s*$',line)
            if m:
                extent=(int(m[1],16),int(m[1],16)+int(m[2],16),m[3]) if m[3] else None
            elif re.match(r'^\s*(?:\.\S+|0x\S+)',line) and re.search(r'\.a\(|\.o(?:\s|$)|\.obj(?:\s|$)',line):
                raise ValueError('malformed GNU input contribution row')
            m=re.match(r'^\s*0x([0-9a-fA-F]+)\s+(\S+)\s*$',line)
            if m and m[2] in wanted:
                address=int(m[1],16);require(extent is not None and extent[0]<=address<extent[1],'GNU symbol lacks exact input extent');add(m[2],extent[2])
    require(set(rows)==wanted,'final required provider symbol coverage differs')
    return rows

def link_closure(folder,link):
    """Expand every referenced response file from the exact retained link build."""
    cwd=link['original_build'];build=folder/'trees'/Path(cwd).name
    command=(folder/link['commands']).read_text();seen=set();responses={}
    def expand(text):
        pattern=r'@(?:"([^"\r\n]+)"|([^\s"\r\n]+))'
        def one(match):
            name=match[1] or match[2]
            path=canonical_dependency(name,cwd);base=canonical_dependency(cwd,cwd)
            require(path.startswith(base+'/'),'response file escapes original link build')
            relative=path[len(base)+1:];require(relative not in seen,'response cycle/repeated ambiguous response')
            seen.add(relative);p=build/relative;require(p.is_file(),'referenced response file not retained')
            raw=p.read_bytes();responses[relative]=record(p)
            return expand(raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig'))
        return re.sub(pattern,one,text)
    final=[]
    for line in command.splitlines():
        seen=set();responses={}
        # Unwrap only the observed Windows shell /C outer command envelope;
        # preserve all inner path/response-file quoting for tokenization.
        shell=re.match(r'^.*?\bcmd(?:\.exe)?\s+/C\s+"(.*)"\s*$',line,re.I)
        if shell:line=shell[1]
        expanded=expand(line).replace('\\','/')
        tokens=[t.strip('"') for t in shlex.split(expanded,posix=False)]
        outputs=[];maps=[];flat=[]
        for token in tokens:
            if token.startswith('-Wl,'):flat.extend(token[4:].split(','))
            elif token!='-Xlinker':flat.append(token)
        for i,token in enumerate(flat):
            if token=='-o':
                require(i+1<len(flat),'missing linker output operand');outputs.append(flat[i+1])
            elif token.lower().startswith('/out:'):outputs.append(token.split(':',1)[1])
            if token in ('-Map','-map'):
                require(i+1<len(flat),'missing map operand');maps.append(flat[i+1])
            elif token.startswith('-Map='):maps.append(token[5:])
            elif token.lower().startswith('/map:'):maps.append(token.split(':',1)[1])
        wanted=canonical_dependency(cwd+'/'+link['image_name'],cwd)
        if wanted in [canonical_dependency(p,cwd) for p in outputs]:
            require(len(outputs)==1 and len(maps)==1,'ambiguous final output/map operands')
            require(canonical_dependency(maps[0],cwd)==canonical_dependency(cwd+'/'+Path(link['map']).name,cwd),'final map operand differs')
            final.append((expanded,tokens,dict(responses)))
    require(len(final)==1,'one actual final linker command required')
    expanded,tokens,responses=final[0];inputs=[]
    for value in tokens:
        value=value.strip('"')
        if value.lower().startswith(('/wholearchive:','/defaultlib:')):value=value.split(':',1)[1]
        elif value.startswith('/') and not re.match(r'^/(?:home|Users|private|Volumes|workspace|tmp)/',value):continue
        if value.endswith(('.a','.lib','.o','.obj')):inputs.append(canonical_dependency(value,cwd))
    require(inputs,'actual link input closure absent')
    project_hash=canonical_dependency(link['hash_prefix']+'/lib/'+('opds_sha256_stream.lib' if link['image_name'].endswith('.exe') else 'libopds_sha256_stream.a'),cwd)
    same=[p for p in set(inputs) if p.rsplit('/',1)[-1]==project_hash.rsplit('/',1)[-1]]
    require(same==[project_hash],'actual link uses missing/ambiguous/wrong hash archive')
    return expanded,inputs,responses

def image_target(raw,target):
    if target=='windows':
        require(raw[:2]==b'MZ' and len(raw)>=64,'PE DOS header absent')
        offset=int.from_bytes(raw[60:64],'little')
        require(offset+24<=len(raw) and raw[offset:offset+4]==b'PE\0\0' and raw[offset+4:offset+6]==b'\x64\x86','PE x64 image identity')
    elif target in ('linux','android'):
        require(raw[:6]==b'\x7fELF\x02\x01' and len(raw)>=64 and int.from_bytes(raw[18:20],'little')==62,'ELF64 x86_64 image identity')
        require(int.from_bytes(raw[16:18],'little') in (2,3),'ELF is not a final executable/PIE')
        if target=='android':
            # Android's CRT ABI note is an actual-byte platform discriminator,
            # unlike e_machine, which is identical to the Linux host's ELF64.
            offset=int.from_bytes(raw[40:48],'little');size=int.from_bytes(raw[58:60],'little');count=int.from_bytes(raw[60:62],'little')
            require(size>=64 and count>0 and offset+size*count<=len(raw),'ELF section table bounds')
            apis=[]
            for i in range(count):
                section=raw[offset+i*size:offset+(i+1)*size]
                if int.from_bytes(section[4:8],'little')!=7:continue
                begin=int.from_bytes(section[24:32],'little');length=int.from_bytes(section[32:40],'little');end=begin+length
                require(end<=len(raw),'ELF note section bounds')
                while begin<end:
                    require(begin+12<=end,'ELF note header bounds')
                    namesz=int.from_bytes(raw[begin:begin+4],'little');descsz=int.from_bytes(raw[begin+4:begin+8],'little');kind=int.from_bytes(raw[begin+8:begin+12],'little')
                    name_start=begin+12;desc_start=name_start+((namesz+3)//4)*4;next_note=desc_start+((descsz+3)//4)*4
                    require(next_note<=end,'ELF note payload bounds')
                    if raw[name_start:name_start+namesz]==b'Android\0' and kind==1:
                        require(descsz>=4,'Android ABI note descriptor');apis.append(int.from_bytes(raw[desc_start:desc_start+4],'little'))
                    begin=next_note
            require(apis==[26],'actual ELF Android API26 ABI note missing/different')
    else:
        require(raw[:4]==b'\xcf\xfa\xed\xfe' and len(raw)>=32,'thin Mach-O64 image required')
        cpu=int.from_bytes(raw[4:8],'little');require(cpu in (0x01000007,0x0100000c),'Mach-O host CPU')
        if target.startswith('ios'):require(cpu==0x0100000c,'iOS arm64 image required')
        require(int.from_bytes(raw[12:16],'little')==2,'Mach-O is not executable')
        count=int.from_bytes(raw[16:20],'little');offset=32;platforms=[]
        for _ in range(count):
            require(offset+8<=len(raw),'truncated Mach-O command')
            command=int.from_bytes(raw[offset:offset+4],'little');size=int.from_bytes(raw[offset+4:offset+8],'little')
            require(size>=8 and offset+size<=len(raw),'Mach-O command bounds')
            if command==0x32:
                require(size>=24,'build-version bounds');platforms.append(int.from_bytes(raw[offset+8:offset+12],'little'))
            offset+=size
        require(platforms==[{'macos':1,'ios-device':2,'ios-simulator':7}[target]],'Mach-O actual target platform differs')

def compilation_output(row):
    matches=re.findall(r'(?:^|\s)(?:-o\s+|/Fo\s*)(?:"([^"\n]+)"|([^\s]+))',row['command'])
    require(len(matches)==1,'unknown/ambiguous compiler output option')
    return canonical_dependency(matches[0][0] or matches[0][1],row['directory'])

def android_binding(cache,command,needs_cxx):
    entries=dict(re.findall(r'^([^/#\n][^:\n]*):[^=\n]*=(.*)$',cache,re.M))
    for key,value in (('ANDROID_ABI','x86_64'),('ANDROID_PLATFORM','android-26'),('ANDROID_STL','c++_static')):
        require(entries.get(key)==value,'actual Android cache target differs: '+key)
    toolchain=entries.get('CMAKE_TOOLCHAIN_FILE','').replace('\\','/')
    require(toolchain.endswith('/ndk/27.0.12077973/build/cmake/android.toolchain.cmake'),'actual Android toolchain differs')
    ndk=toolchain.removesuffix('/build/cmake/android.toolchain.cmake')
    tokens=shlex.split(command);segments=[[]]
    for token in tokens:
        require(token not in ('|','||',';'),'unsupported Android link shell control')
        if token=='&&':segments.append([])
        else:segments[-1].append(token)
    segments=[s for s in segments if s and s!=[':']]
    require(len(segments)==1,'Android final driver command is ambiguous')
    argv=segments[0];driver=ndk+'/toolchains/llvm/prebuilt/linux-x86_64/bin/'+('clang++' if needs_cxx else 'clang')
    require(argv[0]==driver,'final driver is not declared Android NDK')
    targets=[];sysroots=[];runtime=[]
    for i,arg in enumerate(argv[1:],1):
        require(not arg.startswith(('-Xclang','-Wl,--sysroot','-Wl,-sysroot')),'unclassified Android target/root escape')
        if arg=='-Xlinker':
            require(i+1<len(argv) and (argv[i+1] in ('-Map','-map') or
                (argv[i+1].endswith('.map') and i>=2 and argv[i-2:i]==['-Xlinker','-Map'])),
                'unclassified Android linker escape')
        if arg in ('--target','-target','--sysroot','-isysroot'):
            require(i+1<len(argv),'missing Android target/root operand')
            (targets if arg in ('--target','-target') else sysroots).append(argv[i+1])
        elif arg.startswith(('--target=','-target=')):targets.append(arg.split('=',1)[1])
        elif arg.startswith(('--sysroot=','-isysroot=')):sysroots.append(arg.split('=',1)[1])
        if arg.startswith('-stdlib=') or arg in ('-static-libstdc++','-shared-libstdc++'):runtime.append(arg)
    require(len(targets)==1 and targets[0] in ('x86_64-none-linux-android26','x86_64-linux-android26'),'final Android target/API differs')
    require(sysroots==[ndk+'/toolchains/llvm/prebuilt/linux-x86_64/sysroot'],'final Android sysroot missing/conflicting')
    if needs_cxx:
        require(runtime.count('-static-libstdc++')==1 and not any(x in runtime for x in ('-shared-libstdc++','-stdlib=libstdc++')) and
            not any('libc++_shared' in arg for arg in argv),'final Android C++ runtime is not static')

def validate(folder, manifest, require_mutations=True):
    folder=Path(folder);expected=identity()
    require(all(manifest[k]==v for k,v in expected.items()),'artifact source/run/attempt mismatch')
    files={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    require(files==set(manifest['files']),'complete file inventory differs')
    for p,r in manifest['files'].items():require(record(folder/p)==r,'retained bytes differ: '+p)
    report=json.loads((folder/'report.json').read_text());target=report['target'];require(target in TARGETS,'target')
    require(all(report[k]==v for k,v in expected.items()),'report identity')
    require(report['f07_accepted'] is False and report['full_six_accepted'] is False,'inflated acceptance')
    source=json.loads((folder/'source.json').read_text())
    require(source==guard(),'current-source provenance differs')
    # Every command result has exact original argv/cwd, output and subject binding.
    commands=json.loads((folder/'commands.json').read_text())
    require(commands and len({row['output'] for row in commands})==len(commands),'missing/duplicate command outputs')
    for row in commands:
        require(row['returncode']==row['expected_returncode'] and row['argv'] and row['cwd'],'command failed')
        require(record(folder/row['output'])==row['output_record'],'command stdout bytes differ')
        for p,r in row.get('subjects',{}).items():require(record(folder/p)==r,'diagnostic subject differs')
    def command_for(output):
        matches=[row for row in commands if row['output']==output]
        require(len(matches)==1,'missing exact command evidence: '+output)
        return matches[0]
    owners=json.loads((folder/'owners.json').read_text())
    require(set(owners)=={'hash','product'},'owner set')
    hash_owner=owners['hash'];product=owners['product']
    require(set(hash_owner['headers'])=={'include/exreader-opds-hash/opds_sha256_stream.h'},'hash public header inventory')
    require(set(product['headers'])=={'include/exreader-product/catalog.h','include/exreader-product/sqlite3.h',
        'include/exreader-product/original_import.h'},'product private/extra header inventory')
    for name,owner in owners.items():
        prefix=owner['prefix'];inventory={p[len(prefix)+1:] for p in files if p.startswith(prefix+'/')}
        require(inventory==set(owner['installed']),'installed prefix has unowned/omitted files')
        relocated='prefix/relocated/'+name
        relocated_files={p[len(relocated)+1:] for p in files if p.startswith(relocated+'/')}
        require(relocated_files==inventory,'relocated package file inventory differs')
        for p in inventory:
            require(record(folder/relocated/p)==record(folder/prefix/p),'relocated package bytes differ: '+p)
        require(len(owner['installed'])==len(set(owner['installed'])),'duplicate installed file')
        for p in owner['headers']:
            require(p.startswith('include/') and p in owner['installed'],'header owner')
        actual_headers={p for p in inventory if p.startswith('include/')}
        require(actual_headers==set(owner['headers']),'complete header inventory')
        manifest_rows=(folder/owner['install_manifest']).read_text().splitlines()
        expected_rows=[owner['original_prefix']+'/'+p for p in owner['installed']]
        require(len(manifest_rows)==len(set(manifest_rows)) and sorted(x.replace('\\','/') for x in manifest_rows)==sorted(expected_rows),'actual install manifest ownership')
        actual_archives={p for p in inventory if p.endswith(('.a','.lib'))}
        wanted=('opds_sha256_stream',) if name=='hash' else ('reader_original_import','reader_catalog','reader_catalog_sqlite')
        expected_archives={'lib/'+(p+'.lib' if target=='windows' else 'lib'+p+'.a') for p in wanted}
        require(actual_archives==expected_archives,'exact installed archive owner inventory')
        namespace='EXReaderOPDSHash' if name=='hash' else 'EXReaderProductCatalog'
        configs=list((folder/prefix/'lib/cmake'/namespace).glob('*Targets*.cmake'))
        require(configs,'actual installed CMake target exports missing')
        combined='\n'.join(p.read_text() for p in configs)
        require(set(re.findall(r'add_library\((\S+) STATIC IMPORTED\)',combined))=={namespace+'::'+p for p in wanted},
            'additional/missing actual installed static target owner')
        for archive in wanted:
            require(f'add_library({namespace}::{archive} STATIC IMPORTED)' in combined,'actual imported static target missing')
            filename=archive+'.lib' if target=='windows' else 'lib'+archive+'.a'
            require('${_IMPORT_PREFIX}/lib/'+filename in combined,'actual exported library path differs')
        if name=='product':
            require('$<LINK_ONLY:EXReaderOPDSHash::opds_sha256_stream>' in combined,'static public hash dependency not exported')
    require((folder/hash_owner['prefix']/'include/exreader-opds-hash/opds_sha256_stream.h').read_bytes()==(ROOT/OWNER_PATHS[0]).read_bytes(),'installed public header source')
    native=json.loads((folder/'native.json').read_text());defs={};undef={}
    require(set(native)=={'hash','importer','normal','revision'},'native owner inventory')
    for owner,entry in native.items():
        actual=archive_members((folder/entry['archive']).read_bytes())
        require([n for n,_ in actual]==[m['name'] for m in entry['members']],'member inventory')
        defs[owner]=set();undef[owner]=set()
        for (name,payload),member in zip(actual,entry['members']):
            require((folder/member['object']).read_bytes()==payload,'member byte extraction')
            d,u=symbols((folder/member['symbols']).read_text(errors='strict'),target)
            require(not(defs[owner]&d&PUBLIC),'duplicate stream definition')
            defs[owner]|=d;undef[owner]|=u
            matching=[row for row in commands if row['output']==member['symbols']]
            require(len(matching)==1 and matching[0]['subjects']=={member['object']:record(folder/member['object'])},'native symbols not bound to exact member')
            argv=matching[0]['argv']
            require(len(argv)==3 and argv[1]==('/symbols' if target=='windows' else '-g') and
                argv[2].replace('\\','/').endswith('/evidence/'+member['object']), 'wrong native symbol invocation')
    require(defs['hash']==PUBLIC|PRIVATE,'hash-only global function export set differs')
    require(not ((defs['hash']|undef['hash'])&FORBIDDEN),'generic OPDS entry leaked into hash-only archive')
    require(PUBLIC<=undef['importer'] and not ((defs['importer']|undef['importer'])&(FORBIDDEN|PRIVATE)),'importer is not public-stream-only')
    require(not(defs['importer']&PUBLIC),'consumer defines provider')
    require('opds_sha256_hex' in defs['normal'] and 'opds_sha256_hex' in defs['revision'],'coexistence providers not actual helpers')
    require(not ((defs['normal']|defs['revision'])&(PUBLIC|PRIVATE)),'different package defines stream owner entry')
    dependency=json.loads((folder/'dependency.json').read_text())
    require(set(dependency)=={'hash','importer'},'compiled object coverage set')
    for owner,item in dependency.items():
        groups=deps_groups((folder/item['deps']).read_text(),required_valid=item['objects'])
        dependency_command=command_for(item['deps'])
        require(dependency_command['argv']==['ninja','-C',item['original_build'],'-t','deps'] and dependency_command['returncode']==0,
            'dependency evidence is not the exact original build database query')
        expected_objects=item['objects'];require(expected_objects and set(expected_objects)<=set(groups),'missing actual object dependencies')
        require((folder/item['build_archive']).read_bytes()==(folder/native[owner]['archive']).read_bytes(),
            'installed archive differs from the exact dependency-tracked build archive')
        require(set(item['object_files'])==set(expected_objects),'retained object inventory differs')
        archive_objects=archive_members((folder/item['build_archive']).read_bytes())
        require(len(archive_objects)==len(expected_objects),'archive member/object count differs')
        matched=[]
        for obj in expected_objects:
            payload=(folder/item['object_files'][obj]).read_bytes()
            matches=[i for i,(_,data) in enumerate(archive_objects) if data==payload]
            require(len(matches)==1 and matches[0] not in matched,'compiled object does not uniquely bind an actual installed archive member')
            matched.extend(matches)
        ninja=(folder/item['ninja']).read_text()
        cache=(folder/('trees/'+Path(item['original_build']).name+'/CMakeCache.txt')).read_text()
        homes=re.findall(r'^CMAKE_CACHEFILE_DIR:INTERNAL=(.+)$',cache,re.M)
        require(len(homes)==1 and canonical_dependency(homes[0],homes[0])==canonical_dependency(item['original_build'],item['original_build']),
            'dependency CWD not bound to actual retained CMake cache')
        compilation=json.loads((folder/('trees/'+Path(item['original_build']).name+'/compile_commands.json')).read_text())
        rule=re.search(r'^build '+re.escape(item['archive_output'])+r':[^\n]*',ninja,re.M)
        require(rule is not None,'actual archive link rule absent')
        linked=re.findall(r'[^\s:]+\.(?:o|obj)(?=\s|$)',rule.group())
        require(set(linked)==set(expected_objects) and len(linked)==len(expected_objects),'archive/object graph differs')
        for obj in expected_objects:
            require(groups[obj],'empty relevant object dependencies')
            commands_for_object=[row for row in compilation if compilation_output(row)==canonical_dependency(obj,item['original_build'])]
            require(len(commands_for_object)==1,'object lacks one exact retained compilation command')
            source_path=canonical_dependency(commands_for_object[0]['file'],commands_for_object[0]['directory'])
            suffix='/extras/opds/src/opds_sha256_stream.c' if owner=='hash' else '/apps/reader/original-import/original_import.cpp'
            require(source_path==canonical_dependency(report['original_workspace']+suffix,item['original_build']),
                'archive object compiled from a different production source')
            resolved=[canonical_dependency(p,item['original_build']) for p in groups[obj]]
            required=canonical_dependency(item['required_header'],item['original_build'])
            require(required in resolved,'compiled object lacks exact installed public header')
            if owner=='importer':
                require(not any(p.endswith(('/sha256.inc','/opds_internal.h','/opds_core.c')) for p in resolved),'consumer retained a private implementation dependency')
    # The installed-only probe must force both owner objects into a final image.
    links=json.loads((folder/'links.json').read_text())
    require(set(links)=={'installed','relocated','normal-first','hash-first','revision-first','hash-revision'},'final link matrix')
    for name,link in links.items():
        require(record(folder/link['image'])==link['image_record'] and (folder/link['image']).stat().st_size>0,'final image binding')
        image_target((folder/link['image']).read_bytes(),target)
        maptext=(folder/link['map']).read_text(errors='strict')
        extra='reader_original_verified_path' if name in ('installed','relocated') else 'opds_sha256_hex'
        providers=map_providers(maptext,target,PUBLIC|{extra})
        command,inputs,responses=link_closure(folder,link)
        if target=='android':
            android_binding((folder/('trees/'+name+'-build/CMakeCache.txt')).read_text(),command,name in ('installed','relocated'))
        query=command_for(link['commands'])
        require(query['argv']==['ninja','-C',link['original_build'],'-t','commands','probe'] and query['returncode']==0,
            'final commands not bound to exact retained probe build')
        hash_archive=canonical_dependency(link['hash_prefix']+'/lib/'+Path(native['hash']['archive']).name,link['original_build'])
        for symbol,origin in providers.items():
            owner='hash' if symbol in PUBLIC else ('importer' if symbol=='reader_original_verified_path' else
                ('normal' if name in ('normal-first','hash-first') else 'revision'))
            archive_name=Path(native[owner]['archive']).name
            original_archive=(link['hash_prefix']+'/lib/'+archive_name if owner=='hash' else
                link['product_prefix']+'/lib/'+archive_name if owner=='importer' else
                report['original_workspace']+'/build/hash-boundary/'+('normal-build/' if owner=='normal' else 'revision-build/')+archive_name)
            expected_archive=canonical_dependency(original_archive,link['original_build'])
            require(expected_archive in inputs,'required provider archive absent from exact final link inputs')
            if target=='windows':
                m=re.fullmatch(r'(.+):([^:]+\.(?:obj|o))',origin,re.I);require(m is not None,'COFF map lacks archive/member')
                library,member=m.groups()
                if '/' in library:
                    if not library.lower().endswith('.lib'):library+='.lib'
                    require(canonical_dependency(library,link['original_build'])==expected_archive,'wrong explicit map archive')
                else:require(library.removesuffix('.lib')==archive_name.removesuffix('.lib'),'wrong COFF map archive owner')
            else:
                m=re.fullmatch(r'(.+\.a)(?:\[\d+\])?\(([^()]+)\)',origin)
                require(m is not None,'map lacks native archive/member')
                library,member=m.groups();require(canonical_dependency(library,link['original_build'])==expected_archive,'wrong map archive path')
            candidates=[row for row in native[owner]['members'] if row['name'].replace('\\','/')==member or
                ('/' not in member and row['name'].replace('\\','/').rsplit('/',1)[-1]==member)]
            require(len(candidates)==1,'map member identity ambiguous/missing')
            defined,_=symbols((folder/candidates[0]['symbols']).read_text(),target)
            require(symbol in defined,'map symbol not defined by exact retained member')
        maptext=maptext.replace('\\','/')
        require(link['image_name'] in command and '.map' in command,'actual final link command absent')
        require(link['hash_prefix'] in command or link['hash_prefix'] in maptext,'final link does not identify exact installed hash prefix')
        if name not in ('installed','relocated'):
            oracle='normal' if name in ('normal-first','hash-first') else 'revision'
            oracle_archive=canonical_dependency(report['original_workspace']+'/build/hash-boundary/'+
                ('normal-build/' if oracle=='normal' else 'revision-build/')+Path(native[oracle]['archive']).name,link['original_build'])
            require((inputs.index(oracle_archive)<inputs.index(hash_archive)) is (name in ('normal-first','revision-first')),
                'actual coexistence archive order differs')
        if target in ('windows','linux','macos'):
            execution=command_for('runtime/'+name+'.log')
            require(execution['argv']==[link['original_build']+'/'+link['image_name']] and execution['returncode']==0,
                'runtime evidence does not execute exact retained image')
            require(execution['subjects']=={link['image']:record(folder/link['image'])},'runtime image byte binding differs')
        actual_paths=(folder/('trees/'+name+'-build/imported-paths.txt')).read_text().splitlines()
        require(actual_paths==link['imported_paths'],'actual imported target paths differ')
        require(len(actual_paths)==4 and actual_paths[0]==link['hash_prefix']+'/lib/'+Path(native['hash']['archive']).name,
            'hash target does not name the exact archive')
        require(actual_paths[1:]==[link['product_prefix']+'/lib/'+p for p in
            (('reader_original_import.lib','reader_catalog.lib','reader_catalog_sqlite.lib') if target=='windows' else
             ('libreader_original_import.a','libreader_catalog.a','libreader_catalog_sqlite.a'))], 'product imported target owner differs')
    desktop=target in ('windows','linux','macos')
    require(report['desktop_runtime_passed'] is desktop and report['mobile_runtime_passed'] is False,'runtime scope differs')
    if desktop:
        suffix='.exe' if target=='windows' else ''
        for label in ('internal','fault'):
            program='trees/controls-build/'+label+suffix
            row=command_for('runtime/'+label+'.log')
            wanted=[report['original_workspace']+'/build/hash-boundary/controls-build/'+label+suffix]
            if label=='fault':wanted.append(report['original_workspace']+'/build/hash-boundary/fault-fixture')
            require(row['argv']==wanted and row['returncode']==0 and row['subjects']=={program:record(folder/program)},'control runtime program/argv binding differs')
            image_target((folder/program).read_bytes(),target)
        for name in ('normal-first','hash-first','revision-first','hash-revision','internal'):
            vector_output((folder/('runtime/'+name+'.log')).read_text())
        require('IMPORT_FAULT_OK' in (folder/'runtime/fault.log').read_text(),'fault status controls missing')
        original_command=command_for('runtime/original.log')
        require(len(original_command['argv'])==2 and original_command['argv'][1].replace('\\','/')==report['original_workspace']+'/tests/reader_catalog/original_import_actions.py'
            and original_command['returncode']==0,'old test script was not actually executed unchanged')
        program='trees/catalog/reader-original-import-check'+suffix
        require(original_command['subjects']=={program:record(folder/program)},'old original executable identity differs')
        image_target((folder/program).read_bytes(),target)
        catalog_command=command_for('runtime/catalog.log')
        require(catalog_command['argv']==['ctest','--test-dir',report['original_workspace']+'/build/catalog','--output-on-failure','--no-tests=error'] and
            catalog_command['returncode']==0,'original catalog test command differs')
        programs=['trees/catalog/'+p+suffix for p in ('reader-catalog-check','reader-originals-check')]
        require(catalog_command['subjects']=={p:record(folder/p) for p in programs},'original catalog program bytes differ')
        for p in programs:image_target((folder/p).read_bytes(),target)
        require('16,792,975-byte fixture, interruption, cancellation, duplicate, reopen and corruption checks passed' in (folder/'runtime/original.log').read_text(),'unchanged original fixture checks missing')
        require(report['original_fixture']=={'bytes':16792975,'sha256':'4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'},'old fixture identity changed')
    require(set(report['negative_controls'])=={'missing','wrong-prefix','precreated','redirected','conflict','mutated','config-injection','wrong-abi'},'package negative set incomplete')
    for name,control in report['negative_controls'].items():
        actual=command_for(control['output'])
        require(all(actual[k]==control[k] for k in ('argv','cwd','returncode')) and actual['returncode']!=0,'negative failure not backed by actual command')
        require(any('/negative-'+name+'-build' in str(arg).replace('\\','/') for arg in actual['argv']), 'wrong negative command identity')
        negative_reason(name,(folder/control['output']).read_text())
    if require_mutations:
        mutations=json.loads((folder/'mutation-controls.json').read_text())
        expected_mutations={'mixed-source','private-include','missing-object','wrong-member','wrong-final-output','wrong-provider',
            'relocated-archive','relocated-header','relocated-config'}
        if desktop:expected_mutations.add('fabricated-control-runtime')
        if target=='android':expected_mutations.update(('host-target-substitution','android-api-binding'))
        require(set(mutations)==expected_mutations,
            'actual evidence mutation controls incomplete')
        require(all(row['rejected'] is True and row['expected_reason'] in row['actual_reason'] for row in mutations.values()),
            'mutation bypassed intended guard')
    return dict(boundary_link_passed=True,desktop_runtime_passed=desktop,mobile_runtime_passed=False,
        f07_accepted=False,full_six_accepted=False,target=target,files=len(files))
