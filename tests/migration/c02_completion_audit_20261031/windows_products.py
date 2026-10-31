# SPDX-License-Identifier: MIT
"""Independent Windows legacy/standalone/Wave3/package original-byte evidence.
No product, SDK or executable from an artifact is imported or executed.
"""
import ast
import io
import json
import ntpath
from pathlib import Path
import re
import sqlite3
import struct
import zipfile
import zlib
from protocols import need, sha, json_value, hexadecimal

BASE = "tests/migration/windows_registry_admission_20261031/"
TOOLS = ("exreader-legacy-migrate","exreader-legacy-migrate-tx","exreader-legacy-migrate-recovery")
OPERATIONS = ("migrate","recover-mirror","recover-migration")
HOSTS = ("registered","unregistered","pending","missing-gate","replaced-target","actual-host-final-release")
SCHEMA = "c02-windows-products-v1"

def relative(path):
    need(isinstance(path,str) and path and "\\" not in path and not path.startswith("/") and
         all(part not in ("",".","..") for part in path.split("/")) and ":" not in path,"wp-relative-artifact-path")
    return path

def win(path):
    need(isinstance(path,str) and "\0" not in path and re.match(r"^[A-Za-z]:[\\/]",path) is not None,
         "wp-absolute-original-windows-path")
    return ntpath.normcase(ntpath.normpath(path))

def provenance(value,spec,source):
    need(value["source"] == source and str(value["run"]) == str(spec["run"]) and
         str(value["attempt"]) == str(spec["attempt"]),"wp-qualified-producer")

def read_json(files,path):
    need(path in files,"wp-required-original:"+path)
    return json_value(files[path])

def _u(raw,offset,kind="<I"):
    length=struct.calcsize(kind)
    need(0 <= offset <= len(raw)-length,"wp-pe-integer-bounds")
    return struct.unpack_from(kind,raw,offset)[0]

def pe_image(raw):
    need(len(raw)>=64 and raw[:2]==b"MZ","wp-real-pe-dos-header")
    pe=_u(raw,60);need(64<=pe<=len(raw)-24 and raw[pe:pe+4]==b"PE\0\0","wp-real-pe-signature")
    machine,count,stamp,_,_,optional,flags=struct.unpack_from("<HHIIIHH",raw,pe+4)
    start=pe+24
    need(machine==0x8664 and 0<count<=96 and flags&2 and not flags&0x2000 and
         optional>=112 and start+optional+40*count<=len(raw) and _u(raw,start,"<H")==0x20b,
         "wp-amd64-pe32plus-executable")
    image_base=_u(raw,start+24,"<Q");headers=_u(raw,start+60);directories=_u(raw,start+108)
    need(headers<=len(raw) and 0<directories<=16 and optional>=112+8*directories,"wp-pe-directories")
    sections=[]
    for index in range(count):
        at=start+optional+40*index
        size,address,stored,offset=struct.unpack_from("<IIII",raw,at+8)
        characteristics=_u(raw,at+36)
        need(offset+stored<=len(raw),"wp-pe-section-file-bounds")
        sections.append(dict(index=index+1,address=address,virtual=size,stored=stored,offset=offset,
                             flags=characteristics))
    def location(address,size=1):
        candidates=[s["offset"]+address-s["address"] for s in sections
                    if s["address"]<=address and address+size<=s["address"]+s["stored"]]
        if address<headers and address+size<=headers:
            candidates.append(address)
        need(len(candidates)==1,"wp-unambiguous-pe-rva")
        return candidates[0]
    def text(address):
        at=location(address);end=raw.find(b"\0",at,min(len(raw),at+4096))
        need(end>=at,"wp-pe-terminated-string")
        return raw[at:end].decode("ascii")
    imports=[]
    for number,width,delayed in ((1,20,False),(13,32,True)):
        if number>=directories:
            continue
        address,size=struct.unpack_from("<II",raw,start+112+8*number)
        if not address and not size:
            continue
        need(address and width<=size<=65536,"wp-pe-import-directory")
        at=location(address,size);terminated=False
        for index in range(size//width):
            values=struct.unpack_from("<"+"I"*(width//4),raw,at+index*width)
            if not any(values):
                terminated=True;break
            if delayed:
                attributes,name,_,_,thunk,_,_,_=values
                need(attributes==1,"wp-delay-import-rva-profile")
            else:
                thunk,_,_,name,iat=values
                thunk=thunk or iat
            library=text(name).lower()
            need(re.fullmatch(r"[a-z0-9_.+-]+\.dll",library) is not None,"wp-pe-library-basename")
            need("exreader" not in library and not library.startswith(("libexr","exr_")),"wp-no-runtime-sdk-dll-import")
            functions=[]
            for slot in range(16384):
                value=_u(raw,location(thunk+8*slot,8),"<Q")
                if not value:break
                functions.append("#"+str(value&0xffff) if value>>63 else text(value+2))
            else:
                raise ValueError("wp-pe-import-thunks-not-terminated")
            need(not any(function.startswith(("exr_","_exr_","wh3wr_","pc02_")) for function in functions),
                 "wp-no-sdk-or-native-gate-import-from-substitute-dll")
            imports.append(dict(library=library,delayed=delayed,functions=functions))
        need(terminated,"wp-pe-import-descriptors-not-terminated")
    entry=_u(raw,start+16)
    need(any(s["flags"]&0x20000000 and s["address"]<=entry<s["address"]+s["stored"] for s in sections),
         "wp-pe-native-entry-code")
    return dict(machine=machine,image_base=image_base,timestamp=stamp,sections=sections,imports=imports,
                sha256=sha(raw),bytes=len(raw),sdk_dll_imports=[])

def source_contract(source,git_bytes):
    workflow=git_bytes(source,".github/workflows/dot-c02-registry-admission-20261031.yml").decode()
    if not all(name in workflow for name in ("legacy_guard_check.py","build_full_host.py","evidence/standalone","evidence/wave3")):
        return dict(historical_incomplete=True,host_capture=False,legacy_capture=False,package_capture=False)
    host=git_bytes(source,BASE+"host_check.py").decode()
    legacy=git_bytes(source,BASE+"legacy_guard_check.py").decode()
    build=git_bytes(source,BASE+"build_full_host.py").decode()
    def count(text,variable,expected):
        found=[]
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node,ast.Assert) or not isinstance(node.test,ast.Compare):
                continue
            test=node.test
            if (isinstance(test.left,ast.Call) and isinstance(test.left.func,ast.Name) and
                test.left.func.id=="len" and len(test.left.args)==1 and
                isinstance(test.left.args[0],ast.Name) and test.left.args[0].id==variable and
                len(test.ops)==1 and isinstance(test.ops[0],ast.Eq) and
                len(test.comparators)==1 and isinstance(test.comparators[0],ast.Constant)):
                found.append(test.comparators[0].value)
        need(found==[expected],"wp-qualified-original-case-count:"+variable)
    count(host,"results",6);count(legacy,"rows",18)
    for required in ("--probe-owner","--prepare-pending","--prepare-unregistered"):
        need(required in host,"wp-qualified-host-scenarios")
    need('"c02-owner-required"' in legacy and all('"'+n+'"' in legacy for n in TOOLS+OPERATIONS),
         "wp-qualified-installed-legacy-contract")
    def capture(text):
        marker="WINDOWS_C02_PRODUCT_EVIDENCE"
        values=re.findall(r"^"+marker+r" = ([01])$",text,re.M)
        need(values==["1"] or not values and marker not in text,"wp-qualified-capture-contract")
        return values==["1"]
    def assigned(path,name):
        tree=ast.parse(git_bytes(source,path).decode())
        values=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and
                any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
        need(len(values)==1 and isinstance(values[0],(tuple,list)),"wp-qualified-module-list")
        return list(values[0])
    modules=assigned("tests/reader_windows_raw3/host_build.py","MODULES")+assigned("tests/reader_wave3_c09/build.py","NEW_MODULES")
    need(len(modules)==len(set(modules)) and len(modules)>=23,"wp-original-full-profile-modules")
    presets=json_value(git_bytes(source,"CMakePresets.json"))
    definitions={row["name"]:row for row in presets["configurePresets"]}
    chain,cache=[],{}
    def visit(name):
        need(name not in chain and name in definitions,"wp-qualified-reading-preset-inheritance")
        chain.append(name);row=definitions[name];parents=row.get("inherits",[])
        if isinstance(parents,str):parents=[parents]
        for parent in parents:visit(parent)
        cache.update(row.get("cacheVariables",{}));chain.pop()
    visit("reading-library")
    need(cache.get("EXR_BUILD_SHARED_COMPAT")=="OFF" and cache.get("EXR_ENABLE_LIBRARY")=="ON",
         "wp-qualified-static-reading-sdk-profile")
    registry=git_bytes(source,BASE+"registry_test.c").decode()
    literal=re.findall(r'static const char original\[\]=("(?:\\.|[^"\\])*")',registry)
    need(len(literal)==1,"wp-qualified-original-sdk-book")
    original=ast.literal_eval(literal[0]).encode("utf-8")
    reader=git_bytes(source,"examples/reader.c").decode()
    found=re.findall(r"static int selftest\(wchar_t \*\*argv, int argc\) \{(.*?)fprintf\(report,",reader,re.S)
    need(len(found)==1,"wp-qualified-selftest-body")
    checks=len(re.findall(r"\bCHECK\(",found[0]))-1
    need(checks>=26,"wp-preserved-native-selftest-checks")
    return dict(historical_incomplete=False,host_capture=capture(host),legacy_capture=capture(legacy),
                package_capture=capture(build),modules=modules,original=original,selftest_checks=checks)

class Trace:
    def __init__(self,files,prefix,report,roles):
        self.files,self.prefix,self.binaries=files,prefix,report["binaries"]
        need(report["evidence_schema"]==SCHEMA and report["platform"]=="Windows" and
             report["command_log"]=="commands.jsonl" and set(self.binaries)==set(roles),"wp-capture-schema")
        need(read_json(files,prefix+"binaries.json")==self.binaries,"wp-separate-binary-original-inventory")
        self.images={}
        for role,item in self.binaries.items():
            need(item["retained"]=="binaries/"+role+".exe" and hexadecimal(item["sha256"],64) and
                 type(item["bytes"]) is int and item["bytes"]>0,"wp-executed-binary-descriptor")
            win(item["source_path"])
            raw=files[prefix+item["retained"]]
            need(len(raw)==item["bytes"] and sha(raw)==item["sha256"],"wp-executed-original-exe-bytes:"+role)
            self.images[role]=pe_image(raw)
        self.rows=[json_value(line) for line in files[prefix+"commands.jsonl"].splitlines()]
        need([r["index"] for r in self.rows]==list(range(1,len(self.rows)+1)) and
             len({r["label"] for r in self.rows})==len(self.rows),"wp-complete-unique-command-trace")
        self.by_label={}
        for row in self.rows:
            role=row["role"];need(role in self.binaries,"wp-command-known-role")
            item=self.binaries[role];argv=row["argv"]
            need(isinstance(argv,list) and argv and all(isinstance(a,str) and "\0" not in a for a in argv) and
                 win(argv[0])==win(item["source_path"]) and type(row["pid"]) is int and row["pid"]>0 and
                 type(row["exit"]) is int and row["timed_out"] is False and row["binary_sha256"]==item["sha256"],
                 "wp-actual-pid-argv-binary-binding")
            win(row["cwd"])
            for stream in ("stdout","stderr"):
                need(row[stream]=="commands/%03d.%s"%(row["index"],stream),"wp-command-output-path")
                raw=files[prefix+row[stream]]
                need(len(raw)==row[stream+"_bytes"] and sha(raw)==row[stream+"_sha256"],"wp-command-output-original-bytes")
            self.by_label[row["label"]]=row
    def command(self,label,role,args,exit_code,aliases=()):
        need(label in self.by_label,"wp-required-command:"+label)
        row=self.by_label[label]
        need(row["role"]==role and row["argv"][1:]==list(map(str,args)) and row["exit"]==exit_code,
             "wp-command-exact-contract:"+label)
        stdout=self.files[self.prefix+row["stdout"]];stderr=self.files[self.prefix+row["stderr"]]
        for base in aliases:
            need(self.files[self.prefix+base+".stdout"]==stdout and self.files[self.prefix+base+".stderr"]==stderr,
                 "wp-old-raw-output-agrees-with-trace")
        return row,stdout,stderr

def seed_paths(raw):
    lines=raw.decode("utf-8").splitlines()
    result={}
    for tag in ("HOST_LIBRARY ","HOST_GATE "):
        values=[line[len(tag):] for line in lines if line.startswith(tag)]
        need(len(values)==1,"wp-original-native-seed-route")
        win(values[0]);result[tag.strip()]=values[0]
    return result

def artifact_under(prefix,physical,cwd):
    part=ntpath.relpath(win(physical),win(cwd)).replace("\\","/")
    relative(part)
    return prefix+part

def _books(raw):
    connection=sqlite3.connect(":memory:")
    try:
        connection.deserialize(raw);connection.execute("PRAGMA query_only=ON")
        need(connection.execute("PRAGMA integrity_check").fetchall()==[("ok",)],"wp-original-sqlite-integrity")
        return connection.execute("SELECT id,title,source FROM books ORDER BY id").fetchall()
    finally:
        connection.close()

def _original_book(raw,original):
    rows=_books(raw)
    need(len(rows)==1 and type(rows[0][0]) is int and rows[0][0]>0 and rows[0][1]=="C02" and
         bytes(rows[0][2])==original,"wp-original-frozen-sdk-book-content")


def _host(files,prefix,catalog,spec,source,required,original):
    path=prefix+"report.json"
    if path not in files:
        need(not required,"wp-required-host-group:"+prefix)
        return dict(missing=[prefix+"original-runtime-group"])
    report=read_json(files,path);provenance(report,spec,source)
    rows=report["cases"]
    need(report["complete"] is True and report["passed"] is True and report["full_c02_acceptance"] is False and
         [r["name"] for r in rows]==list(HOSTS) and all(r["passed"] is True for r in rows),"wp-original-six-host-cases:"+prefix)
    for row in rows[:-1]:
        need(row["exit"]==(0 if row["name"]=="registered" else 2),"wp-host-case-exit")
        folder=prefix+row["name"]+"/"
        seed_paths(files[folder+"seed.log"])
        if row["name"]!="registered":
            need(b"C02 admission] refused before SDK open" in files[folder+"stderr.txt"],"wp-before-sdk-refusal")
    final=rows[-1]
    need(type(final["pid"]) is int and final["pid"]>0 and all(final[k] is True for k in
         ("visible_window","blocked_while_live","admitted_after_close")),"wp-original-final-owner-observation")
    if "binaries" not in report:
        need(not required,"wp-required-host-capture:"+prefix)
        return dict(cases=6,missing=[prefix+"executed-binary-command-window-originals"])
    need(report["catalog_mode"]==catalog,"wp-actual-host-catalog-profile")
    trace=Trace(files,prefix,report,("host","consumer"))
    expected=[]
    for row in rows[:-1]:
        name=row["name"];expected+=["seed-"+name,"host-"+name]
        mode="--prepare-unregistered" if name=="unregistered" else "--prepare-pending" if name=="pending" else "--prepare-host"
        seeded,stdout,stderr=trace.command("seed-"+name,"consumer",[mode],0)
        folder=prefix+name+"/"
        need(stdout+stderr==files[folder+"seed.log"],"wp-seed-actual-trace-output")
        paths=seed_paths(stdout);library=paths["HOST_LIBRARY"]
        args=trace.by_label["host-"+name]["argv"][1:]
        need(len(args)==10 and args[0]=="--data" and args[2]=="--library" and args[3]==library and
             args[4]=="--font" and args[6]=="--drive" and args[8]=="--evidence","wp-host-actual-argv")
        root=seeded["cwd"]
        need(win(args[1])==win(ntpath.join(root,"profile")) and win(args[7])==win(ntpath.join(root,"quit.drive")) and
             win(args[9])==win(ntpath.join(root,"drive")),"wp-host-fixed-private-profile")
        executed,so,se=trace.command("host-"+name,"host",args,row["exit"])
        need(so==files[folder+"stdout.txt"] and se==files[folder+"stderr.txt"],"wp-host-original-output-agrees")
        observed=read_json(files,folder+"target-observation.json")
        before=files[folder+"target-before.sqlite"]
        need(observed["source_path"]==library and observed["before"]==row["target"] and
             sha(before)==row["target"]["sha256"],"wp-original-before-target-bytes")
        _original_book(before,original)
        current=artifact_under(folder,library,root)
        need(current in files and sha(files[current])==observed["after"]["sha256"],"wp-original-after-target-bytes")
        _original_book(files[current],original)
        product=current+".product.sqlite"
        if name=="registered":
            need((product in files)==(catalog=="product") and b"C02 admission] refused" not in se,
                 "wp-real-catalog-only-after-admission")
        else:
            need(observed["after"]==observed["before"] and files[current]==before and product not in files,
                 "wp-before-sdk-refusal-preserves-target-and-no-catalog")
    expected+=["seed-actual-host-final-release","owner-probe-live","host-actual-host-final-release","owner-probe-after-close"]
    need([r["label"] for r in trace.rows]==expected,"wp-all-fourteen-actual-host-commands")
    seeded,stdout,stderr=trace.command("seed-actual-host-final-release","consumer",["--prepare-host"],0)
    folder=prefix+"actual-host-final-release/"
    need(stdout+stderr==files[folder+"seed.log"],"wp-final-original-seed")
    paths=seed_paths(stdout);library=paths["HOST_LIBRARY"]
    live,so,se=trace.command("owner-probe-live","consumer",["--probe-owner",library],10)
    after,ao,ae=trace.command("owner-probe-after-close","consumer",["--probe-owner",library],0)
    need(not so and not ao,"wp-probe-native-output-not-fabricated")
    _original_book(files[artifact_under(folder,library,seeded["cwd"])],original)
    host=trace.by_label["host-actual-host-final-release"]
    need(host["role"]=="host" and host["exit"]==0 and host["pid"]==final["pid"] and
         host["argv"][1:]==["--data",ntpath.join(seeded["cwd"],"profile"),"--library",library,
                           "--font",trace.by_label["host-registered"]["argv"][6]] and
         live["pid"]!=host["pid"] and after["pid"]!=host["pid"],"wp-real-final-host-and-independent-probes")
    need(files[prefix+host["stdout"]]==files[folder+"stdout.txt"] and
         files[prefix+host["stderr"]]==files[folder+"stderr.txt"],"wp-final-host-original-outputs")
    idle=read_json(files,folder+"input-idle.json");window=read_json(files,folder+"window-observation.json")
    need(idle==dict(pid=host["pid"],result=0) and window["schema"]=="c02-win32-visible-owner-v1" and
         window["pid"]==host["pid"] and window["input_idle"]==0 and len(window["windows"])==1 and
         window["windows"][0]["pid"]==host["pid"] and window["windows"][0]["visible"] is True and
         type(window["windows"][0]["handle"]) is int and window["windows"][0]["handle"]>0,"wp-win32-original-visible-window")
    return dict(cases=6,commands=14,host_sha256=trace.binaries["host"]["sha256"],
                consumer_sha256=trace.binaries["consumer"]["sha256"],host_image=trace.images["host"],missing=[])

def _legacy(files,spec,source,required,original):
    prefix="legacy-guard/";path=prefix+"guard-report.json"
    if path not in files:
        need(not required,"wp-required-legacy-group")
        return dict(missing=["legacy-guard:original-runtime-group"])
    report=read_json(files,path);provenance(report,spec,source)
    names=[tool+"-"+operation+"-before-files" for tool in TOOLS for operation in OPERATIONS]
    ordered=[name for tool in TOOLS for name in
             [*(tool+"-"+operation+"-before-files" for operation in OPERATIONS),tool+"-unknown-dump"]]
    ordered += [tool+"-read-grant-and-report-refusal" for tool in TOOLS]+[tool+"-pending-sdk-refusal" for tool in TOOLS]
    need(report["passed"] is True and [r["name"] for r in report["cases"]]==ordered and
         all(r["passed"] is True for r in report["cases"]),"wp-original-eighteen-legacy-cases")
    for tool in TOOLS:
        for operation in OPERATIONS:
            need(b"c02-owner-required" in files[prefix+tool+"-"+operation+".stdout"],"wp-old-mutating-legacy-refusal")
    if "binaries" not in report:
        need(not required,"wp-required-legacy-capture")
        return dict(cases=18,missing=["legacy-guard:executed-binaries-command-target-originals"])
    trace=Trace(files,prefix,report,(*TOOLS,"admission","consumer"))
    observed=read_json(files,prefix+"target-observations.json")
    library=observed["registered"]["source_path"];out=ntpath.dirname(library)
    need(win(library)==win(ntpath.join(out,"registered.sqlite")),"wp-registered-legacy-route")
    unknown,pack,report_path=[ntpath.join(out,leaf) for leaf in ("unknown.sqlite","absent.exrpack","report.json")]
    expected=[]
    for tool in TOOLS:
        expected.append(tool+"-version")
        _,stdout,_=trace.command(tool+"-version",tool,["--version"],0,(tool+"-version",))
        need(re.fullmatch(rb"exreader-legacy-migrate [^ \r\n]+ \(EXReader SDK 3\.42\.0\)\r?\n",stdout) is not None,
             "wp-actual-legacy-sdk-version")
        for operation in OPERATIONS:
            label=tool+"-"+operation;expected.append(label)
            _,stdout,_=trace.command(label,tool,[operation,"--pack",pack,"--target",unknown,
                "--report",report_path,"--break-lock"],2,(label,))
            json_value(stdout)
            need(b"c02-owner-required" in stdout,"wp-actual-mutating-legacy-before-files")
        label=tool+"-unknown-dump";expected.append(label)
        trace.command(label,tool,["dump","--target",unknown],2,(label,))
    expected.append("create")
    _,stdout,_=trace.command("create","admission",["create",library,ntpath.join(out,"registered-domain")],0,("create",))
    need(json_value(stdout)["admitted"] is True,"wp-actual-legacy-registration")
    for tool in TOOLS:
        for suffix,args,code in (("admitted-dump",["dump","--target",library],0),
            ("report-library",["dump","--target",library,"--report",library],2)):
            label=tool+"-"+suffix;expected.append(label)
            trace.command(label,tool,args,code,(label,))
    expected.append("pending-seed")
    seed,stdout,stderr=trace.command("pending-seed","consumer",["--prepare-pending"],0)
    need(stdout+stderr==files[prefix+"pending-seed.log"],"wp-legacy-pending-source-trace")
    pending=seed_paths(stdout)["HOST_LIBRARY"]
    need(win(pending)==win(observed["pending"]["source_path"]),"wp-legacy-exact-pending-route")
    for tool in TOOLS:
        label=tool+"-pending-dump";expected.append(label)
        trace.command(label,tool,["dump","--target",pending],2,(label,))
    need([r["label"] for r in trace.rows]==expected and len(expected)==26,"wp-all-twentysix-actual-legacy-commands")
    need(all(prefix+leaf not in files for leaf in ("unknown.sqlite","unknown.sqlite.migrate-lock","report.json")),
         "wp-unknown-legacy-never-creates")
    for name,member in (("registered",prefix+"registered.sqlite"),
                        ("pending",artifact_under(prefix+"pending/",pending,seed["cwd"]))):
        before=files[prefix+name+"-before.sqlite"];after=files[member];item=observed[name]
        need(sha(before)==item["before_sha256"]==item["after_sha256"]==sha(after) and before==after,
             "wp-legacy-read-and-refusal-retain-original-target")
        if name=="registered":
            need(_books(before)==[],"wp-actual-empty-new-sdk-library")
        else:
            _original_book(before,original)
    return dict(cases=18,commands=26,admission_sha256=trace.binaries["admission"]["sha256"],
                consumer_sha256=trace.binaries["consumer"]["sha256"],
                tools={role:trace.binaries[role]["sha256"] for role in TOOLS},missing=[])

def _zip(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        rows=[r for r in archive.infolist() if not r.is_dir()]
        need(len(rows)<=20000 and sum(r.file_size for r in rows)<=512*1024*1024,"wp-inner-package-bounds")
        result={}
        for row in rows:
            path=relative(row.filename)
            need(path not in result and not row.flag_bits&1 and (row.external_attr>>16)&0o170000!=0o120000,
                 "wp-inner-package-unique-regular-files")
            result[path]=archive.read(row)
        return result

def _png(raw):
    need(raw.startswith(b"\x89PNG\r\n\x1a\n"),"wp-real-rendered-png")
    offset=8;count=0;ended=False;width=height=0;compressed=[]
    while offset<len(raw):
        need(offset+12<=len(raw),"wp-png-chunk-bounds")
        length=struct.unpack_from(">I",raw,offset)[0];kind=raw[offset+4:offset+8];end=offset+12+length
        need(end<=len(raw) and zlib.crc32(raw[offset+4:end-4])&0xffffffff==struct.unpack_from(">I",raw,end-4)[0],
             "wp-png-real-crc")
        if count==0:
            need(kind==b"IHDR" and length==13,"wp-png-first-ihdr")
            width,height,depth,color,compression,filtering,interlace=struct.unpack_from(">IIBBBBB",raw,offset+8)
            need(0<width<=1440 and 0<height<=1440 and depth==8 and color==6 and
                 compression==filtering==interlace==0,"wp-real-rgba-render")
        if kind==b"IDAT":compressed.append(raw[offset+8:end-4])
        if kind==b"IEND":
            need(length==0 and end==len(raw),"wp-png-exact-iend");ended=True
        count+=1;offset=end
    need(ended and count>=3 and compressed,"wp-complete-native-render-image")
    expected=(width*4+1)*height
    decoder=zlib.decompressobj()
    pixels=decoder.decompress(b"".join(compressed),expected+1)
    need(len(pixels)==expected and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and
         all(pixels[row*(width*4+1)]<=4 for row in range(height)),"wp-complete-rendered-png-pixels")
    return dict(width=width,height=height,sha256=sha(raw))

def _map(raw,image):
    text=raw.decode(errors="strict");base=re.findall(r"Preferred load address is\s+([0-9a-fA-F]+)",text)
    stamp=re.findall(r"Timestamp is\s+([0-9a-fA-F]+)",text)
    need(len(base)==len(stamp)==1 and int(base[0],16)==image["image_base"] and
         int(stamp[0],16)==image["timestamp"],"wp-real-link-map-pe-identity")
    expected={"wh3wr_open":"exreader-coordinator-native.lib","wh3wr_close":"exreader-coordinator-native.lib",
              "exr_webdav_download_observed":None,"exr_library_open":"exr_library.lib"}
    result={}
    for name,owner in expected.items():
        lines=[line for line in text.splitlines() if re.search(r"\b"+name+r"\b",line)]
        parsed=[]
        for line in lines:
            found=re.match(r"^\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{8})\s+"+name+r"\s+([0-9a-fA-F]{8,16})\s+(?:f\s+)?(.+)$",line)
            if not found:continue
            section,offset,address=int(found[1],16),int(found[2],16),int(found[3],16)
            need(1<=section<=len(image["sections"]),"wp-map-native-section")
            entry=image["sections"][section-1];rva=address-image["image_base"]
            need(entry["flags"]&0x20000000 and rva==entry["address"]+offset and
                 entry["address"]<=rva<entry["address"]+entry["stored"] and
                 (owner is None or re.search(r"(?:^|[\\/ ])"+re.escape(owner.removesuffix(".lib"))+r"(?:\.lib)?:",found[4],re.I)),"wp-native-sdk-guard-map-code-origin")
            parsed.append(dict(address=address,object=found[4].strip()))
        need(len(parsed)==1,"wp-one-native-map-symbol:"+name)
        result[name]=parsed[0]
    return result

def _formal(files,spec,source,contract,wave):
    root="full-host-package/";missing=[]
    if "full-host-build.json" not in files or root+"build.json" not in files:
        need(not contract["package_capture"],"wp-required-formal-package-group")
        return dict(missing=["formal-package:original-build-and-package"])
    build=read_json(files,"full-host-build.json");provenance(build,spec,source)
    need(build["platform"]=="Windows Wave3 raw SDK3.42" and build["sdk_version"]=="3.42.0" and
         build["binary"] in ("host/EXReaderWave3.exe","host\\EXReaderWave3.exe") and
         build["full_c02_acceptance"] is False and
         build["installed_modules"]==contract["modules"],"wp-qualified-all-full-profile-modules")
    original=files["EXReaderWave3.exe"];image=pe_image(original)
    need(sha(original)==build["binary_sha256"],"wp-original-wave3-build-exe")
    if wave.get("host_sha256") is not None:
        need(sha(original)==wave["host_sha256"],"wp-wave3-actual-executed-build-binary")
    manifest=read_json(files,root+"build.json")
    need(manifest["schema"]==1 and manifest["passed"] is True and manifest["source_sha"]==source and
         manifest["sdk_version"]=="3.42.0" and manifest["c02_admission"] is True and
         manifest["linkage"]=="static-reading","wp-formal-qualified-static-package")
    prefix=root+"EXReader/"
    actual={path[len(prefix):]:raw for path,raw in files.items() if path.startswith(prefix)}
    need(actual and set(actual)==set(manifest["files"]) and
         all(sha(raw)==manifest["files"][path] for path,raw in actual.items()),"wp-formal-all-original-payload-bytes")
    need(not any(path.lower().endswith(".dll") for path in actual),"wp-static-package-has-no-sdk-dll")
    need(actual["EXReader.exe"]==original,"wp-formal-host-executed-binding")
    for name in ("EXReader.exe","exreader-c02-admission.exe","exreader-c02-migrate.exe"):
        pe_image(actual[name])
    inner=_zip(files[root+"EXReader-Windows.zip"])
    need(inner==actual,"wp-original-inner-zip-exact-payload")
    report=read_json(files,root+"report.json")
    need(report["schema"]==1 and report["passed"] is True and report["platform"]=="Windows" and
         report["engine_version"]=="3.42.0" and type(report["checks"]) is int and
         report["checks"]==manifest["selftest_checks"]==contract["selftest_checks"] and sha(files[root+"report.json"])==manifest["report_sha256"] and
         sha(files[root+"page.png"])==manifest["image_sha256"],"wp-original-formal-selftest-all-checks")
    rendered=_png(files[root+"page.png"])
    need((rendered["width"],rendered["height"])==(720,1040),"wp-original-selftest-exact-render-geometry")
    need((str(report["checks"])+" Windows native host checks passed").encode() in files["full-host-build-logs/package-with-admission.log"],
         "wp-original-packager-completion-output")
    observed=read_json(files,root+"admission-check.json")
    need(len(observed)==2 and [r["command"][0] for r in observed]==["create","check"] and
         all(r["exit"]==0 and json_value(r["stdout"].encode())["admitted"] is True for r in observed),
         "wp-original-packaged-admission-create-and-check")
    migration=read_json(files,"actual-migration/migration-result.json")
    providers={row["provider"] for row in migration["versions"].values()}
    need(len(providers)==1,"wp-one-actual-migration-provider")
    version=f"exreader-c02-migrate {source} provider={next(iter(providers))} SDK=3.42.0"
    need(manifest["migration_version"]==version,"wp-packaged-exact-migration-provider")
    for name in ("exreader-c02-admission.exe","exreader-c02-migrate.exe"):
        info=migration["binaries"][name]
        need(len(actual[name])==info["bytes"] and sha(actual[name])==info["sha256"],"wp-package-real-migration-command-bytes")
    if "link_map" in build:
        need(build["evidence_schema"]==SCHEMA and build["binary_bytes"]==len(original) and
             build["link_map"]=="full-host-build-logs/windows-host.map" and
             sha(files[build["link_map"]])==build["link_map_sha256"],"wp-original-full-host-link-map")
        symbols=_map(files[build["link_map"]],image)
    else:
        need(not contract["package_capture"],"wp-required-original-link-map")
        missing.append("formal-package:original-static-sdk-native-link-map");symbols={}
    witness_path=root+"execution/receipt.json"
    if witness_path not in files:
        need(not contract["package_capture"],"wp-required-formal-actual-execution")
        missing.append("formal-package:actual-executed-package-originals")
    else:
        witness=read_json(files,witness_path);provenance(witness,spec,source)
        need(witness["schema"]=="c02-windows-package-execution-v1" and witness["platform"]=="Windows" and
             witness["passed"] is True and witness["full_c02_acceptance"] is False and
             witness["commands"]=="commands.jsonl","wp-package-execution-receipt")
        capture=dict(witness,evidence_schema=SCHEMA,command_log=witness["commands"])
        trace=Trace(files,root+"execution/",capture,("host","admission","migration"))
        for role,name in (("host","EXReader.exe"),("admission","exreader-c02-admission.exe"),("migration","exreader-c02-migrate.exe")):
            need(trace.binaries[role]["sha256"]==sha(actual[name]),"wp-package-execution-native-binary-chain")
        need([r["label"] for r in trace.rows]==["packaged-selftest","packaged-migration-version","packaged-create","packaged-check"],
             "wp-all-four-formal-execution-commands")
        args=trace.by_label["packaged-selftest"]["argv"][1:]
        need(len(args)==6 and args[0]=="--self-test" and
             [ntpath.basename(p) for p in args[1:]]==["Reader.otf","Sample.epub","Sample.pdf","selftest-report.json","selftest-page.png"],
             "wp-packaged-selftest-real-inputs")
        package_path=ntpath.dirname(trace.binaries["host"]["source_path"])
        execution_path=ntpath.dirname(args[4])
        need(all(win(path)==win(ntpath.join(package_path,name)) for path,name in
             zip(args[1:4],("Reader.otf","Sample.epub","Sample.pdf"))) and
             win(args[5])==win(ntpath.join(execution_path,"selftest-page.png")),
             "wp-selftest-actual-package-input-and-output-routes")
        need(all(win(ntpath.dirname(item["source_path"]))==win(package_path) for item in trace.binaries.values()),
             "wp-all-actual-programs-from-one-formal-package")
        trace.command("packaged-selftest","host",args,0)
        _,stdout,_=trace.command("packaged-migration-version","migration",["--version"],0)
        need(stdout.decode().strip()==version,"wp-actual-packaged-migration-version")
        create=trace.by_label["packaged-create"]["argv"][1:]
        check=trace.by_label["packaged-check"]["argv"][1:]
        need(len(create)==3 and create[0]=="create" and check==["check",create[1]] and
             win(create[1])==win(ntpath.join(execution_path,"admission","library.sqlite")) and
             win(create[2])==win(ntpath.join(execution_path,"admission","native-domain")),
             "wp-real-packaged-create-check-routes")
        for label,command in (("packaged-create",create),("packaged-check",check)):
            _,stdout,_=trace.command(label,"admission",command,0)
            need(json_value(stdout)["admitted"] is True,"wp-real-packaged-admission")
        execution=root+"execution/"
        need(witness["report"]=="selftest-report.json" and witness["image"]=="selftest-page.png" and
             sha(files[execution+witness["report"]])==witness["report_sha256"] and
             sha(files[execution+witness["image"]])==witness["image_sha256"],"wp-package-original-render-and-check-report")
        result=read_json(files,execution+witness["report"])
        need(result==report and witness["selftest_checks"]==report["checks"],"wp-packaged-execution-same-all-native-checks")
        rendered_again=_png(files[execution+witness["image"]])
        need((rendered_again["width"],rendered_again["height"])==(720,1040),"wp-witness-exact-render-geometry")
        need(_books(files[execution+"admission/library.sqlite"])==[],"wp-real-packaged-create-empty-sdk-library")
    return dict(missing=missing,host_sha256=sha(original),migration_sha256=sha(actual["exreader-c02-migrate.exe"]),
                admission_sha256=sha(actual["exreader-c02-admission.exe"]),selftest_checks=report["checks"],
                native_map_symbols=symbols,render=rendered,static_sdk_no_runtime_dll_import=True)

def audit_windows_products(files,spec,source,git_bytes):
    need(spec["role"]=="registry-product" and spec["platform"]=="Windows" and hexadecimal(source,40),
         "wp-qualified-windows-role")
    contract=source_contract(source,git_bytes)
    if contract["historical_incomplete"]:
        return dict(capabilities=[],missing=["windows-original-guarded-legacy-standalone-wave3-and-formal-package"],
                    executed_binary_byte_binding=False,formal_package_binary_binding=False)
    legacy=_legacy(files,spec,source,contract["legacy_capture"],contract["original"])
    profiles={name:_host(files,name+"/","none" if name=="standalone" else "product",
                        spec,source,contract["host_capture"],contract["original"]) for name in ("product","standalone","wave3")}
    formal=_formal(files,spec,source,contract,profiles["wave3"])
    missing=[*legacy["missing"],*(item for result in profiles.values() for item in result["missing"]),*formal["missing"]]
    if not missing:
        consumers={p["consumer_sha256"] for p in profiles.values()}|{legacy["consumer_sha256"]}
        need(len(consumers)==1 and legacy["admission_sha256"]==formal["admission_sha256"],
             "wp-one-actual-registry-consumer-and-installed-admission")
    capabilities=["windows-original-extra-product-cases"]
    if not missing:capabilities+=["windows-three-guarded-legacy-binaries","windows-standalone-wave3-actual-final-owner",
                                  "windows-formal-package-executed-byte-binding","windows-static-sdk-map-no-runtime-dll"]
    return dict(capabilities=capabilities,missing=missing,legacy=legacy,profiles=profiles,formal_package=formal,
                executed_binary_byte_binding=not missing,formal_package_binary_binding=not missing)

def diagnose_windows_products(files):
    """Actions caller has already API-bound and retained the original ZIP."""
    need(__import__("os").environ.get("GITHUB_ACTIONS")=="true","wp-diagnostics-actions-only")
    reports=("legacy-guard/guard-report.json","standalone/report.json","wave3/report.json","full-host-build.json",
             "full-host-package/build.json","full-host-package/report.json","full-host-package/admission-check.json",
             "full-host-package/execution/receipt.json")
    result=dict(scope="windows-product-diagnostic-only",reports={},members=[])
    for path in reports:
        if path in files:result["reports"][path]=json_value(files[path])
    for path,raw in sorted(files.items()):
        if path.lower().endswith((".exe",".dll",".zip",".map")) or path.endswith("commands.jsonl"):
            row=dict(path=path,bytes=len(raw),sha256=sha(raw))
            if path.endswith(".exe"):
                try:row["pe"]=pe_image(raw)
                except ValueError as error:row["pe_error"]=str(error)
            if path.endswith(".map"):
                row["selected_lines"]=[line for line in raw.decode(errors="replace").splitlines() if
                    any(name in line for name in ("Preferred load","Timestamp","wh3wr_open","wh3wr_close",
                                                  "exr_library_open","exr_webdav_download_observed"))]
            result["members"].append(row)
    print("C02-WINDOWS-PRODUCT-DIAGNOSTIC "+json.dumps(result),flush=True)
    return result

def windows_products_negative_controls(files,spec,source,git_bytes,output):
    baseline=audit_windows_products(files,spec,source,git_bytes)
    if not baseline["executed_binary_byte_binding"]:
        return []
    need(__import__("os").environ.get("GITHUB_ACTIONS")=="true","wp-negative-execution-actions-only")
    directory=Path(output);directory.mkdir(parents=True,exist_ok=False)
    controls=[]
    cases=[("windows-products-remove-legacy","legacy-guard/",None,"wp-required-legacy-group"),
           ("windows-products-remove-standalone","standalone/",None,"wp-required-host-group:"),
           ("windows-products-remove-wave3","wave3/",None,"wp-required-host-group:"),
           ("windows-products-remove-formal-package","full-host-package/",None,"wp-required-formal-package-group"),
           ("windows-products-substitute-standalone-exe",None,"standalone","wp-executed-original-exe-bytes:host"),
           ("windows-products-forge-owner-probe-output",None,"probe","wp-probe-native-output-not-fabricated"),
           ("windows-products-substitute-formal-exe",None,"formal","wp-formal-host-executed-binding"),
           ("windows-products-weaken-legacy-cases",None,"cases","wp-original-eighteen-legacy-cases")]
    context=dict(source=source,run=spec["run"],attempt=spec["attempt"],artifact=spec["artifact"]["id"],
                 original_zip_sha256=spec["artifact"]["sha256"])
    for name,prefix,kind,expected in cases:
        removals=sorted(path for path in files if prefix and path.startswith(prefix))
        updates={}
        if kind=="standalone":
            report=json_value(files["standalone/report.json"]);item=report["binaries"]["host"]
            path="standalone/"+item["retained"];raw=bytearray(files[path]);image=pe_image(bytes(raw))
            section=next(s for s in image["sections"] if s["flags"]&0x20000000 and s["stored"])
            raw[section["offset"]]^=1;updates[path]=bytes(raw)
        elif kind=="probe":
            path="standalone/commands.jsonl"
            rows=[json_value(line) for line in files[path].splitlines()]
            row=next(row for row in rows if row["label"]=="owner-probe-live")
            raw=b'{"admitted":true}\n';updates["standalone/"+row["stdout"]]=raw
            row.update(stdout_bytes=len(raw),stdout_sha256=sha(raw))
            updates[path]=b"".join((json.dumps(row)+"\n").encode() for row in rows)
        elif kind=="formal":
            path="full-host-package/EXReader/EXReader.exe";raw=bytearray(files[path]);image=pe_image(bytes(raw))
            section=next(s for s in image["sections"] if s["flags"]&0x20000000 and s["stored"])
            raw[section["offset"]]^=1;updates[path]=bytes(raw)
            manifest=json_value(files["full-host-package/build.json"])
            manifest["files"]["EXReader.exe"]=sha(updates[path])
            updates["full-host-package/build.json"]=(json.dumps(manifest)+"\n").encode()
        elif kind=="cases":
            path="legacy-guard/guard-report.json";report=json_value(files[path]);report["cases"]=report["cases"][:-1]
            updates[path]=(json.dumps(report)+"\n").encode()
        candidate=dict(schema="c02-windows-products-resealed-patch-v1",name=name,producer=context,
                       removals=removals,updates=[dict(path=path,bytes=len(raw),sha256=sha(raw))
                                               for path,raw in sorted(updates.items())])
        members={"candidate.json":(json.dumps(candidate,sort_keys=True,indent=2)+"\n").encode(),
                 **{"updates/"+path:raw for path,raw in updates.items()}}
        members["file-hashes.json"]=(json.dumps([dict(path=path,bytes=len(raw),sha256=sha(raw))
            for path,raw in sorted(members.items())],indent=2)+"\n").encode()
        path=directory/(name+".zip")
        with zipfile.ZipFile(path,"x",zipfile.ZIP_DEFLATED) as archive:
            for member,raw in sorted(members.items()):archive.writestr(member,raw)
        packed=path.read_bytes();restored=_zip(packed)
        inventory=json_value(restored["file-hashes.json"])
        need(len(inventory)==len(restored)-1 and {row["path"] for row in inventory}==set(restored)-{"file-hashes.json"} and
             all(len(restored[row["path"]])==row["bytes"] and sha(restored[row["path"]])==row["sha256"] for row in inventory),
             "wp-negative-refreshed-original-byte-inventory")
        request=json_value(restored["candidate.json"])
        need(request["schema"]==candidate["schema"] and request["name"]==name and request["producer"]==context and
             request["removals"]==removals,"wp-negative-qualified-original-context")
        reconstructed=dict(files)
        for member in request["removals"]:relative(member);reconstructed.pop(member)
        for item in request["updates"]:
            member=relative(item["path"]);raw=restored["updates/"+member]
            need(len(raw)==item["bytes"] and sha(raw)==item["sha256"],"wp-negative-actual-zip-update")
            reconstructed[member]=raw
        reconstructed["file-hashes.json"]=(json.dumps([dict(path=key,bytes=len(raw),sha256=sha(raw))
            for key,raw in sorted(reconstructed.items()) if key!="file-hashes.json"],indent=2)+"\n").encode()
        try:
            audit_windows_products(reconstructed,spec,source,git_bytes)
        except ValueError as error:
            need(str(error).startswith(expected),"wp-negative-unexpected-refusal:"+name+":"+str(error))
            controls.append(dict(name=name,rejected=True,reason=str(error),bytes=len(packed),sha256=sha(packed),
                original=context,actual_zip_readback=True,refreshed_inventory=True))
            (directory/(name+".result.json")).write_text(json.dumps(controls[-1],indent=2)+"\n")
        else:
            raise ValueError("wp-resealed-product-negative-accepted:"+name)
    need(len(controls)==8,"wp-eight-resealed-product-negatives")
    (directory/"result.json").write_text(json.dumps(controls,indent=2)+"\n")
    return controls
