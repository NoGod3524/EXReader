#!/usr/bin/env python3
"""Fixed R6 archive diagnosis; no project or archived content execution."""
import hashlib,io,json,math,os,re,stat,struct,subprocess,sys,unicodedata,urllib.request,urllib.error,urllib.parse,zipfile,zlib
from pathlib import Path
import xml.etree.ElementTree as ET
C=json.loads(Path(__file__).with_name('contract.json').read_text(),parse_constant=lambda x: (_ for _ in ()).throw(ValueError('non-finite contract JSON')))
B=C['budgets'];OUT=Path('build/f03-r6-complete-evidence');OUT.mkdir(parents=True,exist_ok=True)
R={'schema':C['schema'],'accepted':False,'full_f03_accepted':False,'product_reexecuted':False,
   'evidence_verified':False,'identity_verified':False,'audit_completed':False,'all_inputs_complete':False,'all_outputs_complete':True,'problems':[],'checks':[],'findings':[],'selected':{},'stages':{},'final_reports':{},
   'case_results':{},'unarchived':C['unarchived'],'scope_limitations':C['scope_limitations']}
REPORT=R
used={'stream':0,'text':0,'output':0};selected={};parsed={};infos={};Z=None
class SafetyError(RuntimeError):pass
def safe(ok,message):
    if not ok:raise SafetyError(message)
def need(ok,message):
    if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def clean(message):
    value=str(message)
    value=re.sub(r'https?://[^\s\'"<>]+','[URL REDACTED]',value)
    value=re.sub(r'(?i)(authorization|token|signature|credential|sig)=?[^\s,;]*',r'\1=[REDACTED]',value)
    return value
def finite_float(value):
    number=float(value);need(math.isfinite(number),'non-finite JSON numeric value');return number
def safe_json(raw,**kwargs):
    return json.loads(raw,parse_float=finite_float,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('non-finite JSON constant')),**kwargs)
def output_raw(name,raw,reserve=True):
    if used['output']+len(raw)>B['output_bytes']-(8388608 if reserve else 0):
        R['all_outputs_complete']=False
        note('output_not_preserved',name,'raw output cap; identity retained',{'bytes':len(raw),'sha256':sha(raw)})
        return False
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);used['output']+=len(raw)
    return True
def save(name,value):
    raw=(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    return output_raw(name,raw)
def note(kind,path,message,detail=None):
    row={'kind':kind,'path':path,'message':clean(message)}
    if detail is not None:row['detail']=detail
    R['findings'].append(row)
def assess(ok,path,message,detail=None):
    if not ok:note('inconsistent_or_failed_evidence',path,message,detail)
    return bool(ok)
def check(name,ok):
    R['checks'].append({'id':name,'passed':bool(ok)});need(ok,name)
def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
def api(path):
    request=urllib.request.Request('https://api.github.com/repos/'+C['repository']+'/'+path,
      headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json',
               'X-GitHub-Api-Version':'2022-11-28','User-Agent':'f03-fixed-evidence'})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=60) as response:
        raw=response.read(B['api_bytes']+1);need(len(raw)<=B['api_bytes'],'API response cap')
    return safe_json(raw)
def remote_bytes(path,limit,destination):
    request=urllib.request.Request('https://api.github.com/repos/'+C['repository']+'/'+path,
      headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'User-Agent':'f03-fixed-evidence'})
    try:
        urllib.request.build_opener(NoRedirect).open(request,timeout=60)
        raise ValueError('expected authenticated download redirect')
    except urllib.error.HTTPError as error:
        safe(error.code==302,'download redirect status');url=error.headers['Location']
    host=urllib.parse.urlparse(url)
    safe(host.scheme=='https' and host.username is None and host.password is None and host.port in (None,443) and
         host.hostname and any(host.hostname.endswith(s) for s in
         ('.blob.core.windows.net','.githubusercontent.com','.amazonaws.com')),'download redirect host')
    safe(not destination.exists(),'exclusive download destination')
    total=0;digest=hashlib.sha256()
    with urllib.request.build_opener(NoRedirect).open(url,timeout=120) as response,destination.open('xb') as stream:
        while True:
            block=response.read(1048576)
            if not block:break
            total+=len(block);safe(total<=limit,'download byte cap')
            digest.update(block);stream.write(block)
    return total,digest.hexdigest()
def canonical(name):
    return isinstance(name,str) and bool(name) and not name.startswith('/') and '\\' not in name and ':' not in name and '\x00' not in name and all(x not in ('','..','.') for x in name.rstrip('/').split('/'))
def zip_index(z,nested=False):
    rows=z.infolist();safe(len(rows)<=B['index_entries'],'ZIP entries cap')
    seen=set();aliases=set();declared=0;out={}
    for e in rows:
        n=e.filename;safe(e.orig_filename==n and canonical(n),'unsafe/truncated ZIP name')
        alias=unicodedata.normalize('NFC',n.rstrip('/')).casefold();safe(n not in seen and alias not in aliases,'ZIP duplicate or file/directory alias')
        seen.add(n);aliases.add(alias)
        kind=stat.S_IFMT(e.external_attr>>16)
        safe(kind in (0,stat.S_IFREG,stat.S_IFDIR),'ZIP link or special file')
        safe(kind==0 or (kind==stat.S_IFDIR)==e.is_dir(),'ZIP mode/directory mismatch')
        safe(not e.flag_bits&1 and e.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'ZIP encryption/method')
        safe(e.file_size<=B['file_bytes'] and e.file_size<=max(1,e.compress_size)*B['compression_ratio'],'ZIP member size/ratio')
        declared+=e.file_size;safe(declared<=B['archive_declared_bytes'],'ZIP declared total cap')
        out[n]=e
    # An ancestor may only be a directory, never a file.
    for n in seen:
        parts=n.rstrip('/').split('/')
        for i in range(1,len(parts)):
            safe('/'.join(parts[:i]) not in seen,'ZIP file is path ancestor')
    return out
def stream_read(z,e,limit):
    safe(not e.is_dir() and stat.S_IFMT(e.external_attr>>16) in (0,stat.S_IFREG),'selected member not regular')
    safe(e.file_size<=limit,'selected member declared cap')
    result=bytearray()
    with z.open(e) as s:
        while True:
            safe(used['stream']<B['stream_bytes'] or len(result)==e.file_size,'shared stream budget before read')
            block=s.read(min(1048576,max(0,B['stream_bytes']-used['stream']),limit-len(result)+1))
            if not block:break
            used['stream']+=len(block);safe(used['stream']<=B['stream_bytes'],'shared actual ZIP stream budget')
            result.extend(block);safe(len(result)<=limit,'selected actual cap')
    safe(len(result)==e.file_size,'selected size mismatch')
    return bytes(result)
def read(path,kind='text',optional=False):
    safe(canonical(path) and not path.endswith('/'),'invalid selected path')
    if path in selected:return selected[path]
    if path not in infos:
        note('missing_archive',path,'optional gate/report absent' if optional else 'required selected input absent')
        return None
    cap=B['file_bytes'] if kind=='binary' else (B['log_bytes'] if path.endswith(('.txt','.log','.jsonl')) else B['json_xml_bytes'])
    if kind!='binary':safe(used['text']+infos[path].file_size<=B['text_bytes'],'text budget before read')
    raw=stream_read(Z,infos[path],cap)
    if kind!='binary':
        used['text']+=len(raw);safe(used['text']<=B['text_bytes'],'cumulative text cap')
        selected[path]=raw
    R['selected'][path]={'bytes':len(raw),'sha256':sha(raw),'kind':kind}
    if kind!='binary':
        # Reserve space for the complete structured ledger, never silently omit a selected identity.
        if used['output']+len(raw)<=B['output_bytes']-8388608:
            p=OUT/'selected'/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);used['output']+=len(raw)
        else:
            R['selected'][path]['raw_output_omitted']='output cap reserve; identity and findings retained'
            R['all_outputs_complete']=False
            note('output_not_preserved',path,'selected raw output omitted with identity retained')
    return raw
def obj(path,optional=False):
    if path in parsed:return parsed[path]
    raw=read(path,optional=optional)
    if raw is None:return None
    try:
        def pairs(rows):
            d={}
            for k,v in rows:
                need(k not in d,'duplicate JSON key');d[k]=v
            return d
        value=safe_json(raw,object_pairs_hook=pairs)
        need(isinstance(value,dict),'expected JSON object')
        parsed[path]=value;return value
    except (ValueError,UnicodeError) as e:
        note('invalid_schema',path,str(e));return None
def identity(v,path):
    return assess(isinstance(v,dict) and all(v.get(k)==x for k,x in R['producer'].items()),path,'source/run/attempt identity')
def text(path):
    raw=read(path)
    if raw is None:return ''
    try:return raw.decode('utf-8')
    except UnicodeError:
        note('invalid_schema',path,'invalid UTF-8');return raw.decode('utf-8',errors='replace')
def digest_match(path,record):
    raw=read(path,'binary')
    if raw is None:return None
    expected_size=record.get('bytes',record.get('size',record.get('screenshot_bytes')))
    expected_sha=record.get('sha256',record.get('screenshot_sha256'))
    assess((expected_size is None or len(raw)==expected_size) and (expected_sha is None or sha(raw)==expected_sha),
           path,'referenced bytes/SHA mismatch')
    return raw
def png(path,record):
    data=digest_match(path,record)
    if data is None:return
    try:
        need(data.startswith(b'\x89PNG\r\n\x1a\n'),'PNG signature');offset=8;types=[]
        while offset<len(data):
            need(offset+12<=len(data),'PNG chunk header')
            size=int.from_bytes(data[offset:offset+4],'big');end=offset+8+size;need(end+4<=len(data),'PNG chunk bound')
            kind=data[offset+4:offset+8];need(zlib.crc32(data[offset+4:end])==int.from_bytes(data[end:end+4],'big'),'PNG CRC')
            types.append(kind)
            if kind==b'IHDR':
                need(size==13,'PNG IHDR');w,h=struct.unpack_from('>II',data,offset+8)
                need(0<w<=8192 and 0<h<=8192 and w*h<=20000000,'PNG dimensions')
            offset=end+4
        need(types and types[0]==b'IHDR' and types[-1]==b'IEND' and types.count(b'IHDR')==types.count(b'IEND')==1,'PNG structure')
    except ValueError as e:note('invalid_binary',path,str(e))
def attempt(label,fn):
    try:fn()
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,UnicodeError,ET.ParseError,struct.error) as e:
        note('invalid_schema',label,type(e).__name__+': '+str(e))

def child(root,name,pattern):
    need(isinstance(name,str) and re.fullmatch(pattern,name) is not None and canonical(name),'unapproved referenced child')
    return root+'/'+name
def xml_group(root,class_name,count,names=None):
    paths=sorted(p for p in infos if re.fullmatch(re.escape(root)+r'/(?:[A-Za-z0-9_-]+/)*TEST-[^/:\\]+\.xml',p))
    if not paths:note('missing_archive',root,'XML report group absent');return
    actual=[]
    for p in paths:
        raw=read(p)
        if raw is None:continue
        decoded=raw.decode('utf-8-sig')
        need('\x00' not in decoded and '<!DOCTYPE' not in decoded.upper() and '<!ENTITY' not in decoded.upper(),'XML DTD/entity/UTF16 prohibited')
        tree=ET.fromstring(decoded)
        for suite in tree.iter('testsuite'):
            assess(not any(int(suite.get(k,'0')) for k in ('failures','errors','skipped')),p,'XML suite failure/skip',dict(suite.attrib))
        for item in tree.iter('testcase'):
            actual.append(item.get('name'))
            assess(item.get('classname')==class_name,p,'XML class differs',dict(item.attrib))
            for k in ('failure','error','skipped'):
                failure=item.find(k)
                if failure is not None:note('actual_case_failure',p,item.get('name'),{'kind':k,'attributes':failure.attrib,'text':failure.text})
    assess(len(actual)==count and len(set(actual))==count and (names is None or set(actual)==set(names)),root,'XML complete unique case identity',actual)
    R['case_results'][root]={'names':actual,'expected_count':count,'exact_names_checked':names is not None}
def manual(path,class_name,method=None,count=1):
    raw=text(path)
    if not raw:return
    assess(re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$',raw,re.M)==['-1'] and
           ('OK ('+str(count)+' test'+('s' if count!=1 else '')+')') in raw and
           not any(x in raw for x in ('FAILURES!!!','INSTRUMENTATION_FAILED','INSTRUMENTATION_ABORTED')),
           path,'instrumentation terminal status')
    classes=set(re.findall(r'^INSTRUMENTATION_STATUS: class=(.+)\s*$',raw,re.M))
    assess(classes=={class_name},path,'instrumentation class')
    if method:assess(set(re.findall(r'^INSTRUMENTATION_STATUS: test=(.+)\s*$',raw,re.M))=={method},path,'instrumentation method')
    codes=re.findall(r'^INSTRUMENTATION_STATUS_CODE: (-?\d+)\s*$',raw,re.M)
    assess(codes==['1','0']*count,path,'instrumentation start/completion sequence',codes)
def host_suite(suite,definition,build):
    root='build/android-host/evidence/'+definition['folder'];path=root+'/validation.json';v=obj(path)
    if v is None:return
    identity(v,path);cases=v.get('cases',[]);ids=definition['ids'];n=len(ids)
    assess(v.get('schema')==1 and v.get('package')=='org.exreader.host' and v.get('api')==34 and v.get('abi')=='x86_64' and
           v.get('physical_device_execution') is False and v.get('device_is_emulator') is True,path,'host suite device schema')
    need(isinstance(cases,list) and len(cases)<=256,'host cases list outside bounded schema')
    assess([x.get('id') if isinstance(x,dict) else None for x in cases]==ids,path,'complete ordered named cases')
    statuses=[x.get('status') if isinstance(x,dict) else None for x in cases]
    observed={'total':len(cases),'passed':statuses.count('pass'),'failed':statuses.count('fail'),'skipped':statuses.count('skip')}
    assess(v.get('summary')=={'total':n,'passed':n,'failed':0,'skipped':0},path,'original required summary',{'reported':v.get('summary'),'observed':observed})
    assess(v.get('summary')==observed,path,'summary matches actual case states',{'reported':v.get('summary'),'observed':observed})
    if build:
        assess(v.get('apk_sha256')==build['artifacts']['app-debug.apk']['sha256'] and
               v.get('test_apk_sha256')==build['artifacts']['uitest-debug-androidTest.apk']['sha256'],path,'suite APK identity')
    R['case_results'][suite]={'summary':v.get('summary'),'cases':[]}
    # Collect every status/error/detail before any attachment can fail.
    for i,c in enumerate(cases,1):
        if not isinstance(c,dict):
            note('invalid_schema',path,'non-object case at index '+str(i));continue
        row={k:c[k] for k in ('id','status','error','detail','assertions','elapsed_ms') if k in c}
        R['case_results'][suite]['cases'].append(row)
        if c.get('status')!='pass':note('actual_case_failure',path,c.get('id','index-'+str(i)),row)
    for i,c in enumerate(cases,1):
        attempt(path+' case '+str(i),lambda i=i,c=c:host_case_attachments(root,suite,ids,i,c))
    cls='HostWalkthroughTest' if suite=='walkthrough' else 'HostReviewTest'
    manual('build/android-host/evidence/'+suite+'-instrumentation.txt','org.exreader.host.uitest.'+cls,'walkthrough' if suite=='walkthrough' else suite)
    logpath='build/android-host/evidence/'+suite+'-logcat.txt';raw=text(logpath)
    assess(bool(raw.strip()) and not any(x in raw for x in ('FATAL EXCEPTION','UnsatisfiedLinkError','Fatal signal')),logpath,'raw app/native fatal failure')
    if suite=='bounded':
        assess(all(x in raw for x in ('bounded page {','storage mode book=','host-review','code 7','code 3','code 5','code 6','Empty reading chapter is not supported')),logpath,'bounded native diagnostic markers')
    if suite=='review':
        seq=v.get('sequence',{});assess(all(seq.get(k)==x for k,x in {'fixture':'Large.epub','rendered_pages':49,'native_next_calls':49,'recovery_calls':0}.items()),path,'sequential 49-page report')
    exe=obj('build/android-host/evidence/execution.json')
    if exe:
        for suffix in ('instrumentation.txt','logcat.txt'):
            p='build/android-host/evidence/'+suite+'-'+suffix
            if p in R['selected']:assess(exe.get('files_sha256',{}).get(suite+'-'+suffix)==R['selected'][p]['sha256'],p,'execution raw-log SHA')
def host_case_attachments(root,suite,ids,i,c):
    need(isinstance(c,dict),'case object required')
    cid=c.get('id');need(cid in ids,'case identity outside exact contract')
    name=(str(i).zfill(2)+'-' if suite=='walkthrough' else '')+cid+'.json'
    per=obj(root+'/cases/'+name);assess(per==c,root+'/cases/'+name,'aggregate/per-case equality')
    shot=child(root,c.get('screenshot'),r'shots/[A-Za-z0-9_-]+\.png')
    png(shot,{'bytes':c.get('screenshot_bytes'),'sha256':c.get('screenshot_sha256')})
    if suite!='walkthrough':assess(isinstance(c.get('assertions'),list) and bool(c['assertions']),root,'case assertions recorded: '+cid)
    for proof in c.get('frame_observations',[]):
        for sample in proof.get('samples',[]):
            name=child(root,sample.get('png'),r'frames/[A-Za-z0-9_-]+\.png')
            png(name,{'bytes':sample.get('png_bytes'),'sha256':sample.get('png_sha256')})
def basic_device(path,names,count,key='pass'):
    v=obj(path)
    if v is None:return None
    identity(v,path);rows=v.get('checks',[])
    assess(v.get('api')==34 and v.get('abi')=='x86_64' and v.get('count')==count and v.get('failed')==0,path,'device count/API/ABI/failure')
    actual=[x.get('id') for x in rows]
    assess(len(rows)==count and len(set(actual))==count and (names is None or set(actual)==set(names)),path,'device complete named case set',actual)
    for row in rows:
        if row.get(key) is not True:note('actual_case_failure',path,row.get('id','unnamed'),row)
    return v
def kills(root,pairs,tag,witness=False):
    for phase in pairs:
        seed=text(root+'/seed-'+phase+'.txt');recovery=text(root+'/recover-'+phase+'.txt')
        assess('INSTRUMENTATION_RESULT: shortMsg=Process crashed.' in seed,root,'real process kill '+phase)
        assess(tag+' recover-'+phase in recovery and re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$',recovery,re.M)==['-1'] and 'PHASE_FAILED' not in recovery,root,'real recovery '+phase)
        if witness:assess(text(root+'/witness-'+phase+'.txt')==('1,1,0' if phase=='before' else '1,1,1'),root,'atomic witness '+phase)
def ui_cases(root,names,count):
    p=root+'/validation.json';v=obj(p)
    if v is None:return None
    identity(v,p);cases=v.get('cases',[])
    assess([x.get('id') if isinstance(x,dict) else None for x in cases]==names and v.get('passed')==count and v.get('failed')==0 and v.get('skipped')==0,p,'complete UI case contract')
    for row in cases:
        if not isinstance(row,dict):
            note('invalid_schema',p,'non-object UI case');continue
        if row.get('status')!='pass':note('actual_case_failure',p,row.get('id','unknown'),row)
    for row in cases:
        attempt(p+' UI case',lambda row=row:ui_attachment(root,names,row))
    return v
def ui_attachment(root,names,row):
    need(isinstance(row,dict),'UI case object')
    cid=row.get('id');need(cid in names,'unapproved UI case')
    identity(row,root)
    assess(obj(root+'/'+cid+'.json')==row,root,'UI individual report equality: '+cid)
    png(root+'/shots/'+cid+'.png',{})
def native_fields(data):
    need(len(data)>=64 and data[:6]==b'\x7fELF\x02\x01','ELF64 little endian')
    machine=struct.unpack_from('<H',data,18)[0];off=struct.unpack_from('<Q',data,32)[0]
    stride,count=struct.unpack_from('<HH',data,54);need(stride>=56 and off+stride*count<=len(data),'ELF program table')
    align=[];ids=[]
    for i in range(count):
        p=off+i*stride;k=struct.unpack_from('<I',data,p)[0]
        if k==1:align.append(struct.unpack_from('<Q',data,p+48)[0])
        if k==4:
            a=struct.unpack_from('<Q',data,p+8)[0];b=a+struct.unpack_from('<Q',data,p+32)[0];need(b<=len(data),'ELF note range')
            while a+12<=b:
                ns,vs,nk=struct.unpack_from('<III',data,a);a+=12
                need(a+ns<=b,'ELF note name');name=data[a:a+ns];a+=(ns+3)&~3
                need(a+vs<=b,'ELF note body');value=data[a:a+vs];a+=(vs+3)&~3
                if name.rstrip(b'\0')==b'GNU' and nk==3:ids.append(value.hex())
    return {'machine':machine,'load_alignments':sorted(set(align)),'build_ids':sorted(set(ids))}
def dex_classes(data):
    need(len(data)>=112 and data[:4]==b'dex\n','DEX header')
    def u32(p):
        need(p+4<=len(data),'DEX integer range');return struct.unpack_from('<I',data,p)[0]
    need(u32(32)==len(data) and u32(40)==0x12345678,'DEX size/endian')
    ns,so,nt,to,nc,co=u32(56),u32(60),u32(64),u32(68),u32(96),u32(100)
    need(so+4*ns<=len(data) and to+4*nt<=len(data) and co+32*nc<=len(data),'DEX table ranges')
    out=[]
    for i in range(nc):
        ti=u32(co+32*i);need(ti<nt,'DEX type index');si=u32(to+4*ti);need(si<ns,'DEX string index')
        p=u32(so+4*si)
        for j in range(5):
            need(p<len(data),'DEX string length');b=data[p];p+=1
            if b<128:break
        else:raise ValueError('DEX oversized length')
        end=data.find(b'\0',p,min(len(data),p+4096));need(end>=p,'DEX descriptor boundary')
        out.append(data[p:end].decode())
    need(len(out)==len(set(out)),'DEX duplicate class');return out
apk_cache={}
def apk(path,expected=None):
    raw=digest_match(path,expected or {})
    if raw is None:return None
    digest=sha(raw)
    if digest in apk_cache:return apk_cache[digest]
    result={'sha256':digest,'native':{},'classes':[],'assets':{}}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        idx=zip_index(z,True)
        for n,e in idx.items():
            if re.fullmatch(r'lib/x86_64/lib(?:exreader|exreader_jni|exreader_host|exreader_product)\.so',n):
                b=stream_read(z,e,B['file_bytes']);result['native'][n]={**native_fields(b),'sha256':sha(b)}
            elif re.fullmatch(r'classes(?:[0-9]+)?\.dex',n):
                result['classes']+=dex_classes(stream_read(z,e,B['file_bytes']))
            elif n in ('assets/Reader.otf','assets/cover-import.epub','assets/pdf-public.pdf'):
                b=stream_read(z,e,B['file_bytes']);result['assets'][n]={'bytes':len(b),'sha256':sha(b)}
    need(len(result['classes'])==len(set(result['classes'])),'APK duplicate class definitions')
    apk_cache[digest]=result
    return result

def import_suite():
    root='build/android-host-import/ui';p=root+'/result.json';v=obj(p)
    if not v:return
    identity(v,p)
    assess(v.get('accepted') is True and v.get('checks')==20 and v.get('reading_limit_bytes')==33554432 and
           v.get('api')==34 and v.get('abi')=='x86_64' and v.get('physical_device') is False,p,'real import20 device/limit contract')
    phases=v.get('phases',[]);assess([x.get('phase') for x in phases]==C['import20_phase_order'] and len({x.get('pid') for x in phases})==9,p,'nine ordered distinct process phases')
    total=0
    for row in phases:
        phase=row.get('phase');need(phase in C['import20_cases'],'unknown import phase');identity(row,p)
        names=C['import20_cases'][phase];total+=row.get('count',0)
        assess(row.get('passed') is True and row.get('count')==len(names) and
               [x.get('name') for x in row.get('checks',[])]==names and all(x.get('pass') is True for x in row.get('checks',[])),p,'import phase checks: '+phase)
        assess(obj(root+'/'+phase+'-raw-report.json')==row,p,'import raw phase equality: '+phase)
        for x in row.get('checks',[]):
            if x.get('pass') is not True:note('actual_case_failure',p,x.get('name'),x)
    assess(total==20,p,'complete import case count')
    stops=v.get('process_stops',[]);held=[x for x in stops if x.get('held_boundary')]
    assess(len(stops)==9 and all(x.get('force_stop') is True and not x.get('pid_after_stop') for x in stops),p,'nine actual stops')
    assess(len(held)==4 and {x.get('phase') for x in held}=={'kill-copy','kill-stable','kill-ready','kill-published'},p,'four held boundaries')
    for stop in held:
        phase=stop['phase'];need(phase in C['import20_cases'],'unapproved marker phase')
        marker_path=root+'/'+phase+'-boundary-marker.json';marker=obj(marker_path);raw=read(marker_path)
        phase_raw=read(root+'/'+phase+'-raw-report.json')
        if marker and raw and phase_raw:
            identity(marker,marker_path)
            assess(marker==stop.get('boundary_marker') and sha(raw)==stop.get('marker_sha256') and
                   marker.get('pid')==stop.get('instrumentation_pid') and
                   str(stop.get('instrumentation_pid')) in stop.get('pid_before_stop','').split() and
                   marker.get('report_bytes')==len(phase_raw) and marker.get('report_sha256')==sha(phase_raw),marker_path,'held marker/source/raw/process binding')
    packages={'org.exreader.host':'examples/android/app/build/outputs/apk/debug/app-debug.apk',
      'org.exreader.host.test':'build/android-host-import/test-apks/host-import-ui.apk',
      'org.exreader.hostimportsource':'tests/reader_android_host_import/source/build/outputs/apk/debug/hostimportsource-debug.apk'}
    identities=v.get('apk_identities',[])
    assess(len(identities)==3 and {x.get('package') for x in identities}==set(packages),p,'three actual installed packages')
    for x in identities:
        need(x.get('package') in packages,'unknown APK package');path=packages[x['package']]
        assess(x.get('artifact_path')==path and x.get('sha256')==x.get('installed_sha256'),path,'APK path/installed identity')
        apk(path,{'sha256':x.get('sha256')})
    captures=v.get('captures',[])
    assess(any(x.get('name')=='system-documentsui' and x.get('package')=='com.android.documentsui' for x in captures),p,'real DocumentsUI capture')
    for x in captures:
        path=child(root+'/captures',x.get('name','')+'.png',r'[A-Za-z0-9_-]+\.png');png(path,x)
    protocol=v.get('marker_protocol',{})
    assess(protocol.get('present_exit_code')==0 and protocol.get('absent_exit_code') not in (None,0),p,'marker protocol positive and negative')
def source_and_compilation():
    root='build/f03-production'
    for name in ('source-admission','hash-owner','test-compilation','import20-verification','result'):
        p=root+'/'+name+'.json';v=obj(p)
        if v:identity(v,p)
    adm=obj(root+'/source-admission.json');compile=obj(root+'/test-compilation.json')
    if adm and compile:
        assess(compile.get('accepted') is True and compile.get('runtime_accepted') is False,root,'predevice compilation status')
        assess(compile.get('staged_files_sha256')==adm.get('overlay_files_sha256'),root,'staged manifest identity')
        assess(compile.get('host_import_status_contract')==adm.get('host_import_status_contract') and
               compile.get('catalog_schema_contract')==adm.get('catalog_schema_contract'),root,'reviewed status/catalog contract binding')
        assess(compile.get('product_flags') and all(v is False for v in compile['product_flags'].values()),root,'original product flags disabled')
        for name,record in compile.get('apks',{}).items():
            need(name in ('test','provider'),'unknown precompiled APK key')
            expected=root+'/precompiled-test-apks/'+name+'.apk'
            assess(record.get('path')==expected,root,'precompiled fixed path')
            actual=apk(expected,record)
            if actual and name=='test':
                assess(set(compile.get('expected_test_classes',[]))<=set(actual['classes']),expected,'all expected DEX class definitions')
        app=apk('examples/android/app/build/outputs/apk/debug/app-debug.apk',{'sha256':compile.get('main_apk_sha256')})
        if app:assess('Lorg/exreader/host/ReadingReview;' not in app['classes'],root,'test helper absent from main APK')
        apk('build/android-host/artifacts/uitest-debug-androidTest.apk',{'sha256':compile.get('uitest_apk_sha256')})
    v=obj(root+'/hash-owner.json')
    if v:
        R['hash_owner_report_fields']=sorted(v)
        # Installed paths outside the uploaded evidence stay unknown, never substituted with this report.
        note('unarchived_input',root+'/hash-owner.json','original external installed-prefix lifecycle is not reexecuted; archived report retained')
def all_groups(build):
    for suite,definition in C['host_suites'].items():attempt(suite,lambda s=suite,d=definition:host_suite(s,d,build))
    for root in ('build/shelf-android','build/import-android','build/owner-android'):
        assess(text(root+'/source.txt').strip()==C['base'],root,'fixed source.txt')
        assess(text(root+'/device-api.txt').strip()=='34' and text(root+'/device-abi.txt').strip()=='x86_64',root,'fixed API/ABI')
    attempt('shelf XML',lambda:xml_group('build/shelf-android/catalog-reports','org.exreader.host.ShelfCatalogTest',12))
    attempt('catalog XML',lambda:xml_group('build/import-android/catalog-reports','org.exreader.host.CatalogStoreTest',8))
    attempt('mapping XML',lambda:xml_group('build/import-android/mapping-reports','org.exreader.host.ImportMappingTest',14,C['mapping_names']))
    attempt('mapping kills',lambda:kills('build/import-android',('before','during'),'EXR_MAPPING_RECOVERED'))
    attempt('shelf UI',lambda:ui_cases('build/shelf-android/ui-execution/ui',C['shelf_ui_names'],10))
    attempt('shelf samples',shelf_samples)
    attempt('owner device',lambda:basic_device('build/owner-android/device-report.json',C['owner_names'],18))
    attempt('owner XML',lambda:xml_group('build/owner-android/owner-reports','org.exreader.host.ProductOwnerTest',18,C['owner_names']))
    attempt('owner manual',lambda:manual('build/owner-android/owner-instrumentation.txt','org.exreader.host.ProductOwnerTest',count=18))
    attempt('owner kills',lambda:kills('build/owner-android',('before','after'),'EXR_OWNER_RECOVERED',True))
    attempt('owner native',owner_native)
    attempt('organization device',lambda:basic_device('build/organization-android/device-report.json',C['org_names'],8))
    attempt('organization XML',lambda:xml_group('build/organization-android/reports','org.exreader.host.OrganizationTest',8,C['org_names']))
    attempt('organization manual',lambda:manual('build/organization-android/instrumentation.txt','org.exreader.host.OrganizationTest',count=8))
    attempt('organization UI',organization_ui)
    attempt('recovery',recovery_evidence)
    attempt('import20',import_suite)
    attempt('source/precompile',source_and_compilation)
def shelf_samples():
    root='build/shelf-android/ui-execution';v=obj(root+'/pss-sampling.json')
    if v:
        assess(not v.get('errors'),root,'PSS sampling errors',v.get('errors'))
        for x in v.get('samples',[]):
            if x.get('total_pss_kib') is None:continue
            slot=x.get('slot');need(type(slot) is int and slot>=0,'PSS slot')
            p=root+'/pss/'+str(slot)+'.txt';raw=text(p)
            pid=re.search(r'\*\* MEMINFO in pid (\d+) \[org\.exreader\.host\] \*\*',raw)
            total=re.search(r'TOTAL PSS:\s*(\d+)',raw) or re.search(r'^\s*TOTAL\s+(\d+)\s',raw,re.M)
            assess(pid and total and int(pid[1])==x.get('pid') and int(total[1])==x.get('total_pss_kib'),p,'PSS raw PID/total')
    result=obj(root+'/result.json')
    if result:
        windows=result.get('windows',[]);assess(len(windows)>=3,root,'retained Window observations')
        for w in windows:
            p=child(root+'/windows',w.get('file'),r'[A-Za-z0-9_.-]+\.jsonl')
            raw=read(p)
            if raw is None:continue
            assess(len(raw)==w.get('bytes') and sha(raw)==w.get('sha256') and raw.endswith(b'\n'),p,'Window trace bytes/termination')
            rows=[safe_json(x) for x in raw.splitlines()];assess(rows and rows[0].get('kind')=='start',p,'Window header')
            frames=[x for x in rows if x.get('kind')=='frame']
            assess(len(frames)==w.get('callbacks') and [x.get('sequence') for x in frames]==list(range(1,len(frames)+1)),p,'Window sequence/callback count')
            assess(all(x.get('pid')==w.get('pid') and x.get('window_id')==w.get('window_id') and x.get('drop_count')==0 for x in frames),p,'Window identity/drop count')
def owner_native():
    root='build/owner-android';v=obj(root+'/native/inventory.json')
    if not v:return
    identity(v.get('identity'),root)
    expected={'debug.map','debug.so','debug.symbols.txt','debug.dynamic.txt','release.map','release.so','release.symbols.txt','release.dynamic.txt','sqlite3.h'}
    assess(set(v.get('files',{}))==expected,root,'native inventory exact nine members')
    for name,rec in v.get('files',{}).items():
        need(name in expected,'unknown native member');p=root+'/native/'+name
        raw=read(p,'binary' if name.endswith('.so') else 'text')
        if raw is not None:
            assess(len(raw)==rec.get('bytes') and sha(raw)==rec.get('sha256'),p,'native inventory bytes')
            if name.endswith('.so'):
                fields=native_fields(raw);assess(fields['machine']==62 and fields['load_alignments'] and min(fields['load_alignments'])>=16384 and len(fields['build_ids'])==1,p,'ELF x86_64 alignment/build identity')
    for variant in ('debug','release'):
        symbols=text(root+'/native/'+variant+'.symbols.txt');mapping=text(root+'/native/'+variant+'.map');dynamic=text(root+'/native/'+variant+'.dynamic.txt')
        assess(len(re.findall(r'\bsqlite3_open_v2\s*$',symbols,re.M))==1 and 'libreader_catalog_sqlite.a' in mapping and
               'sqlite3_open_v2' in mapping and 'exr_vendor_exr_sqlite' not in symbols and
               not re.search(r'NEEDED.*(?:sqlite|exreader)',dynamic,re.I),root,'isolated product SQLite provider '+variant)
    device=obj(root+'/device-report.json');header=text(root+'/native/sqlite3.h');match=re.search(r'#define SQLITE_SOURCE_ID\s+"([^"]+)"',header)
    if device and match:
        provider=device.get('provider',[])
        assess(len(provider)>=5 and provider[0]=='3.54.0' and provider[1]==provider[2]==match[1] and
               Path(provider[3]).name=='libexreader_product.so' and
               {'THREADSAFE=1','DQS=0','OMIT_LOAD_EXTENSION','MAX_LENGTH=2147483647'}<=set(provider[4].split(';')),root,'actual provider/version/options')
    for group in ('owner-android','import-android','organization-android'):
        apk('build/'+group+'/apks/app-debug.apk')
        if group!='organization-android':apk('build/'+group+'/apks/app-debug-androidTest.apk')
def organization_ui():
    root='build/organization-android'
    v=ui_cases(root+'/ui',C['org_ui_names'],8)
    seed,refused,verified=(obj(root+'/phases/'+n+'.json') for n in ('seed','refused','verified'))
    for n,x in zip(('seed','refused','verified'),(seed,refused,verified)):
        if x:identity(x,root+'/phases/'+n+'.json')
    if v and seed and refused and verified:
        detail=v['cases'][-1]['detail'];intent=refused['intent']
        assess(detail['old_pid']!=detail['new_pid'] and str(detail['old_pid']).isdigit() and str(detail['new_pid']).isdigit(),root,'real organization process restart')
        assess(seed['books']==2 and seed['shelves']==seed['removed_tags']==105,root,'original paging fixture')
        assess('refused' in refused['outcome'] and len(intent)==18 and intent['name']=='Killed retry' and intent['heads']==[],root,'complete saved intent')
        assess(verified['exact_retry'] is True and verified['product_fields_preserved'] is True and
               verified['revision']==intent['revision'] and verified['entity']==intent['id'] and detail['verified']==verified,root,'exact saved retry')
    for name in ('seed-ui','fault','release-fault','verify-ui'):
        p=root+'/seed-ui.txt' if name=='seed-ui' else root+'/ui/phase-'+name+'.txt'
        raw=text(p);assess('EXR_ORGANIZATION_PHASE '+name in raw and re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$',raw,re.M)==['-1'],p,'organization fixture phase')
    text(root+'/ui-instrumentation.txt')
def recovery_evidence():
    root='build/f03-recovery';v=basic_device(root+'/device-report.json',C['recovery_cases'],12,'passed')
    if v:assess([x.get('id') for x in v.get('checks',[])]==C['recovery_cases'] and all(x.get('source_preserved') is True for x in v.get('checks',[])),root,'ordered source-preserving recovery12')
    manual(root+'/instrumentation.txt','org.exreader.host.OrganizationBootstrapRecoveryTest',count=12)

def stage_and_final(job,log):
    matches=re.findall(r'F03_UPSTREAM: (\{[^\r\n]+\})',log)
    outcomes=None
    for raw in matches:
        try:
            value=safe_json(raw)
            if set(value)==set(C['stages']) and all(x in ('success','failure','skipped','cancelled') for x in value.values()):outcomes=value
        except ValueError:pass
    assess(outcomes is not None,'producer-job.log','actual full F03_UPSTREAM dictionary present')
    steps={s['number']:s for s in job['steps']}
    for name,number in C['stages'].items():
        step=steps.get(number,{})
        R['stages'][name]={'number':number,'name':step.get('name'),'api_status':step.get('status'),
          'api_conclusion':step.get('conclusion'),'actual_outcome':outcomes.get(name) if outcomes else None}
        assess(step.get('name')==C['stage_names'][name],'producer-job.json','fixed step identity: '+name)
        if step.get('conclusion')=='skipped':note('original_stage_skipped',name,'authenticated original API step skipped')
        elif outcomes and outcomes[name]!='success':note('original_stage_failed',name,'original actual outcome '+outcomes[name])
    for name,p in C['final_reports'].items():
        attempt(p,lambda name=name,p=p:final_report(name,p))
    original=obj('build/f03-production/result.json')
    assess(original and original.get('accepted') is False,'build/f03-production/result.json','original overall failure must remain')
def final_report(name,p):
    v=obj(p,optional=name in C['gate_counts'])
    entry={'path':p,'present':v is not None,'original_stage':R['stages'].get(name)}
    R['final_reports'][name]=entry
    if v:
        entry.update({k:v[k] for k in ('accepted','problems','problem','owner_checks','typed_kill_checks','native_checks','real_ui_checks','real_process_retry_checks') if k in v})
        if name=='host':
            summary=v.get('summary',{});entry['host_summary_present']=bool(summary)
            assess(v.get('candidate_only') is False and v.get('candidate_validated') is False,p,'no candidate promotion')
            assess(summary.get('source_sha')==C['base'] and summary.get('run',{}).get('id')==str(C['run_id']) and summary.get('run',{}).get('attempt')=='1',p,'host accepted-summary identity')
        else:identity(v,p)
        if v.get('accepted') is not True or v.get('problems') or v.get('problem'):note('formal_report_not_accepted',p,'original formal refusal',entry)
        if name in C['gate_counts']:
            checks=v.get('checks',[]);entry['check_count']=len(checks)
            assess(len(checks)==C['gate_counts'][name] and all(x.get('passed') is True for x in checks),p,'original complete gate results')
            entry['script_sha256']=v.get('script_sha256')
            assess(v.get('script_sha256')==sha(subprocess.check_output(['git','show',C['base']+':'+C['gate_scripts'][name]])),p,'original gate script identity')
        if name=='owner':
            assess(all(v.get(k)==n for k,n in {'owner_checks':18,'typed_kill_checks':2,'original_functional_checks':112,'original_gate_checks':87}.items()),p,'complete owner downstream fields')
        if name=='organization':
            assess(all(v.get(k)==n for k,n in {'native_checks':8,'real_ui_checks':8,'real_process_retry_checks':1,'original_owner_checks':18,'original_typed_kill_checks':2,'original_functional_checks':112,'original_gate_checks':87,'original_owner_altered_evidence_checks':19}.items()),p,'complete organization downstream fields')
    R['final_reports'][name]=entry

def host_build(build):
    if not build:return
    p='build/android-host/build.json';identity(build,p)
    assess(build.get('schema')==2 and build.get('sdk_built') is True and build.get('apk_built') is True and
           build.get('abi')=='x86_64' and build.get('abi_version')==1 and build.get('library_schema')==7 and
           build.get('ndk')=='27.0.12077973' and build.get('gradle')=='8.9' and build.get('sdk_version')=='3.42.0',p,'frozen build provenance/toolchain')
    expected={'app-debug.apk','uitest-debug.apk','uitest-debug-androidTest.apk'}
    assess(set(build.get('artifacts',{}))==expected,p,'exact original three APK set')
    for name in expected:
        rec=build.get('artifacts',{}).get(name,{})
        for root in ('build/android-host/artifacts','build/android-host/evidence/artifacts','build/android-host/evidence/installed'):
            actual=apk(root+'/'+name,rec)
            if actual and name=='app-debug.apk':
                assess(set(actual['native'])=={'lib/x86_64/'+x for x in ('libexreader.so','libexreader_jni.so','libexreader_host.so','libexreader_product.so')},root,'complete native APK set')
                for library,fields in actual['native'].items():
                    reported=build.get('native',{}).get(library,{})
                    assess(reported.get('sha256')==fields['sha256'] and reported.get('machine')==fields['machine'] and
                           reported.get('load_alignments')==fields['load_alignments'] and fields['build_ids']==[reported.get('build_id')],root,'build/native recorded fields '+library)
                assess(actual['assets'].get('assets/Reader.otf',{}).get('sha256')==build.get('font',{}).get('sha256'),root,'packaged font')
    exe=obj('build/android-host/evidence/execution.json')
    if exe:
        identity(exe,'build/android-host/evidence/execution.json')
        assess(exe.get('completed') is True and exe.get('errors')==[],'execution','transport/collection completed, not semantic case acceptance')
        assess(exe.get('installed')=={n:build['artifacts'][n]['sha256'] for n in expected},'execution','installed APK set')
        assess(exe.get('fixtures')=={n:v['sha256'] for n,v in build.get('fixtures',{}).items()},'execution','reported device fixture hashes')
        for suite in C['host_suites']:
            record=exe.get('suites',{}).get(suite,{})
            assess(all(record.get(k)==0 for k in ('exit_code','log_exit_code','pull_exit_code')),'execution','suite transport '+suite)
    for path in C['unarchived']:note('unarchived_input',path,'required by original full checker but not included in original upload list')

def main():
    need(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    need(os.environ['GITHUB_REPOSITORY']==C['repository'],'controller repository')
    need(os.environ['GITHUB_REF']=='refs/heads/'+C['branch'],'controller branch')
    need(os.environ['GITHUB_EVENT_NAME']=='push' and os.environ['GITHUB_RUN_ATTEMPT']=='1','unique push A1')
    head=git('rev-parse','HEAD')
    need(head==os.environ['GITHUB_SHA'],'checkout identity')
    need(git('show','-s','--format=%P','HEAD')==C['base'],'single fixed parent')
    need(C['marker'] in git('show','-s','--format=%B','HEAD'),'fixed marker')
    changes=git('diff','--name-status',C['base'],'HEAD').splitlines()
    need(sorted(changes)==sorted('A\t'+p for p in C['paths']),'strict three additions')
    REPORT['controller']={'source_sha':head,'run_id':os.environ['GITHUB_RUN_ID'],'attempt':'1'}
    run=api('actions/runs/'+str(C['run_id']))
    job=api('actions/jobs/'+str(C['job_id']))
    artifact=api('actions/artifacts/'+str(C['artifact_id']))
    save('producer-run.json',run);save('producer-job.json',job);save('producer-artifact.json',artifact)
    expected={'source_sha':C['base'],'run_id':str(C['run_id']),'attempt':str(C['attempt'])}
    REPORT['producer']=expected
    check('producer_workflow',run.get('path')=='.github/workflows/reader-f03-production-acceptance-v342.yml')
    check('producer_run',run['id']==C['run_id'] and run['run_attempt']==1 and
          run['head_sha']==C['base'] and run['head_branch']==C['producer_branch'] and
          run['repository']['full_name']==C['repository'] and run['event']=='push' and
          run['status']=='completed' and run['conclusion']=='failure')
    check('producer_job',job['id']==C['job_id'] and job['run_id']==C['run_id'] and
          job['head_sha']==C['base'] and job['run_attempt']==1 and
          job['status']=='completed' and job['conclusion']=='failure')
    ar=artifact['workflow_run']
    check('producer_artifact',artifact['id']==C['artifact_id'] and
          artifact['name']==C['artifact_name'] and artifact['size_in_bytes']==C['artifact_bytes'] and
          artifact['digest']=='sha256:'+C['artifact_sha256'] and not artifact['expired'] and
          ar['id']==C['run_id'] and ar['head_sha']==C['base'] and ar['head_branch']==C['producer_branch'] and
          ar['repository_id']==run['repository']['id'] and ar['head_repository_id']==run['head_repository']['id'])

    log_path=Path(os.environ['RUNNER_TEMP'])/'f03-r6-fixed-job.log'
    n,d=remote_bytes('actions/jobs/'+str(C['job_id'])+'/logs',B['job_log_bytes'],log_path)
    need(n==C['job_log_bytes'] and d==C['job_log_sha256'],'fixed original job log digest')
    safe(used['text']+n<=B['text_bytes'],'job log text cap before read')
    rawlog=log_path.read_bytes();used['text']+=len(rawlog)
    output_raw('producer-job.log',rawlog)
    log=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',rawlog.decode(errors='replace'))
    R['producer_job_log']={'bytes':n,'sha256':d}
    archive=Path(os.environ['RUNNER_TEMP'])/'f03-r6-fixed-evidence.zip'
    try:
        n,d=remote_bytes('actions/artifacts/'+str(C['artifact_id'])+'/zip',C['artifact_bytes'],archive)
        check('archive_digest',n==C['artifact_bytes'] and d==C['artifact_sha256'])
        R['identity_verified']=True
        global Z,infos
        with zipfile.ZipFile(archive) as Z:
            infos=zip_index(Z)
            save('archive-index.json',[{'path':p,'bytes':e.file_size,'compressed_bytes':e.compress_size,'crc32':e.CRC} for p,e in infos.items()])
            # These are literal upload roots; never search for a matching alternative prefix.
            need('build/android-host/build.json' in infos and 'build/f03-production/result.json' in infos,'fixed archive root absent')
            for p in C['root_reports']:obj(p,optional=p in [C['final_reports'][k] for k in C['gate_counts']])
            build=obj('build/android-host/build.json')
            attempt('build/archive identity',lambda:host_build(build))
            all_groups(build)
            attempt('full formal stage/report graph',lambda:stage_and_final(job,log))
            R['binary_inspections']={k:{'native':v['native'],'assets':v['assets'],'dex_class_count':len(v['classes'])} for k,v in apk_cache.items()}
            save('binary-class-inventory.json',{k:v['classes'] for k,v in apk_cache.items()})
            # Preserve full failures from already authenticated stdout, especially overwritten core result files.
            core=[]
            for line in log.splitlines():
                if '{' not in line:continue
                try:v=safe_json(line[line.index('{'):])
                except ValueError:continue
                if isinstance(v,dict) and v.get('source_sha')==C['base'] and v.get('run_id')==str(C['run_id']) and v.get('attempt')=='1':
                    if any(k in v for k in ('owner_checks','native_checks','recovery_accepted')) or v.get('checks')==20:
                        core.append({k:v[k] for k in ('accepted','problems','owner_checks','typed_kill_checks','native_checks','real_ui_checks','real_process_retry_checks','recovery_accepted','checks','phases') if k in v})
            R['original_stdout_core_results']=core
            R['evidence_verified']=True
            R['read_only_audit_completed']=True
            R['audit_completed']=True
            R['all_inputs_complete']=not any(x['kind'] in ('missing_archive','invalid_schema','invalid_binary','unarchived_input') for x in R['findings'])
            R['all_formal_inputs_passed']=False
    finally:
        if archive.exists():archive.unlink()
        if log_path.exists():log_path.unlink()
def finish():
    R['budgets_used']=used.copy()
    R['finding_counts']={k:sum(x['kind']==k for x in R['findings']) for k in sorted({x['kind'] for x in R['findings']})}
    encoded=(json.dumps(R,sort_keys=True,allow_nan=False)+'\n').encode()
    remaining=B['output_bytes']-used['output']
    if len(encoded)>remaining:
        original_sha=sha(encoded);original_bytes=len(encoded)
        R['all_outputs_complete']=False;R['evidence_verified']=False
        summary={'schema':R['schema'],'accepted':False,'full_f03_accepted':False,
          'identity_verified':R['identity_verified'],'evidence_verified':False,
          'audit_completed':R['audit_completed'],'all_inputs_complete':False,'all_outputs_complete':False,
          'failure_classification':'output_budget_incomplete',
          'original_ledger_sha256':original_sha,'original_ledger_bytes':original_bytes,
          'finding_counts':R['finding_counts'],'producer':R.get('producer'),'controller':R.get('controller'),
          'budgets_used':used.copy(),'selected':R['selected'],'stages':R['stages'],
          'failure_summaries':[{'kind':x['kind'],'path':x['path'],'message':clean(x['message'])[:256],
             'detail_sha256':sha(json.dumps(x.get('detail'),sort_keys=True,allow_nan=False).encode())}
             for x in R['findings']]}
        encoded=(json.dumps(summary,sort_keys=True,allow_nan=False)+'\n').encode()
        if len(encoded)>remaining:
            summary['selected_count']=len(summary.pop('selected'))
            summary['selected_index_sha256']=sha(json.dumps(R['selected'],sort_keys=True).encode())
            summary['failure_summary_count']=len(summary.pop('failure_summaries'))
            summary['details_not_preserved']='explicit output cap; no claim of complete evidence'
            encoded=(json.dumps(summary,sort_keys=True,allow_nan=False)+'\n').encode()
        if len(encoded)>remaining:
            encoded=(json.dumps({'accepted':False,'evidence_verified':False,'all_outputs_complete':False,
                       'error':'output budget incomplete','ledger_sha256':original_sha})+'\n').encode()
        if len(encoded)<=remaining:output_raw('result.json',encoded,reserve=False)
        print(encoded.decode(),end='')
    else:
        output_raw('result.json',encoded,reserve=False)
        print(encoded.decode(),end='')
try:
    main()
except Exception as error:
    R['problems'].append(type(error).__name__+': '+clean(error))
finally:
    finish()
if not R['evidence_verified']:sys.exit(1)
