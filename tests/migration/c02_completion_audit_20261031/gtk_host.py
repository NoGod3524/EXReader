# SPDX-License-Identifier: MIT
"""Independent actual GTK host artifact semantics after API/ZIP provenance checks."""
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import shutil
import sqlite3
import struct
import subprocess
from protocols import SDK, need, sha, json_value
from gtk_snapshots import audit_gtk_snapshots

def sqlite_books(raw):
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(raw)
        connection.execute("PRAGMA query_only=ON")
        return connection.execute("SELECT id,title,source FROM books ORDER BY id").fetchall()
    finally:
        connection.close()

def audit_gtk_host(files, spec, source, expected_cases, verification_output=None):
    runtime = spec["runtime_prefix"]
    evidence = spec["evidence_prefix"]
    package = spec["package_prefix"]
    report = json_value(files[runtime + "report.json"])
    need(report["source"] == source and str(report["run"]) == str(spec["run"]) and
         str(report["attempt"]) == str(spec["attempt"]), "gtk-runtime-producer")
    need(report["actual_gtk"] is True and report["actual_sdk"] is True and
         report["actual_migration"] is False and report["full_c02_acceptance"] is False and
         report["passed"] is True and report["complete"] is True, "gtk-runtime-scope")
    rows = report["cases"]
    need(len(rows) == len(expected_cases) and len(rows) >= 13 and
         {row["name"] for row in rows} == expected_cases and
         all(row["passed"] is True for row in rows), "gtk-source-declared-original-cases")
    snapshots = audit_gtk_snapshots(files, runtime)
    original = files[runtime + "book.txt"]
    need(original and len(original.splitlines()) == 100, "gtk-original-source-fixture")
    for phase in ("clean", "borrowed", "released", "pending"):
        primary = sqlite_books(files[runtime + "snapshots/" + phase + "/library-0.sqlite"])
        secondary = sqlite_books(files[runtime + "snapshots/" + phase + "/library-1.sqlite"])
        need(not secondary, "gtk-second-library-independently-empty")
        if phase == "clean":
            need(not primary, "gtk-clean-library-independently-empty")
        else:
            need(len(primary) == 1 and type(primary[0][0]) is int and primary[0][0] > 0 and
                 bytes(primary[0][2]) == original, "gtk-actual-sqlite-retained-original")
    for name in ("unknown-host", "pending-actual-host", "replacement-identity", "copied-unregistered"):
        need(b"Library admission refused." in files[runtime + name + ".stderr"],
             "gtk-actual-before-sdk-refusal:" + name)
    for name in ("c02-gtk-host-check", "exreader-linux", "exreader-c02-admission"):
        need(files[evidence + name].startswith(b"\x7fELF"), "gtk-actual-native-binary:" + name)
    manifest = json_value(files[package + "build.json"])
    need(manifest["source_sha"] == source and manifest["sdk_version"] == "3.42.0" and
         manifest["c02_admission"] is True, "gtk-package-producer")
    for name in ("exreader-linux", "exreader-c02-admission"):
        need(files[package + "EXReader-Linux/bin/" + name] == files[evidence + name],
             "gtk-packaged-exact-qualified-binary")
    binding = verify_static_binding(files,spec,source,verification_output)
    capabilities = ["gtk-actual-before-sdk-admission", "gtk-last-search-page-custody",
                    "gtk-original-sqlite-content", "gtk-native-authority-byte-decoder", "gtk-packaged-admission"]
    if binding["installed_sdk_byte_binding"]:
        capabilities.extend(["gtk-installed-static-sdk-byte-binding","gtk-strict-static-relink"])
    return dict(capabilities=capabilities,runtime_cases=len(rows),original_sha256=sha(original),
                native_snapshots=snapshots,actual_migration=False,
                installed_sdk_byte_binding=binding["installed_sdk_byte_binding"],binaries=binding)

def _qualified_static_source(source):
    need(re.fullmatch(r"[0-9a-f]{40}",source) is not None,"gtk-qualified-source-sha")
    result = subprocess.run(["git","show",source+":tests/migration/gtk_c02_host_20261031/run.py"],
                            capture_output=True,check=True)
    text = result.stdout.decode()
    marker = "GTK_C02_STATIC_LINK_INPUTS"
    values = re.findall(r"^"+marker+r" = ([01])$",text,re.M)
    need(values == ["1"] or not values and marker not in text,"gtk-static-source-contract")
    return values == ["1"]

def _elf_functions(raw):
    from android_host import loadable_elf, elf_exports
    loadable_elf(raw)
    need(struct.unpack_from("<H",raw,16)[0] in (2,3),"gtk-executable-elf-type")
    offset = struct.unpack_from("<Q",raw,40)[0]
    width,count = struct.unpack_from("<HH",raw,58)
    need(width == 64 and 0 < count < 4096 and offset+width*count <= len(raw),"gtk-elf-section-table")
    sections = [struct.unpack_from("<IIQQQQIIQQ",raw,offset+i*width) for i in range(count)]
    symbols = {}
    for section in sections:
        if section[1] != 2:
            continue
        start,length,link,step = section[4],section[5],section[6],section[9]
        need(step == 24 and length % step == 0 and start+length <= len(raw) and link < count,
             "gtk-static-symbol-table")
        strings = sections[link]
        need(strings[1] == 3 and strings[4]+strings[5] <= len(raw),"gtk-static-symbol-strings")
        table = raw[strings[4]:strings[4]+strings[5]]
        for position in range(start,start+length,step):
            name,info,other,index,address,size = struct.unpack_from("<IBBHQQ",raw,position)
            if not name or info >> 4 not in (1,2) or info & 15 != 2 or index == 0:
                continue
            need(name < len(table) and table.find(b"\0",name) >= name,"gtk-static-symbol-name")
            text = table[name:table.find(b"\0",name)].decode("ascii")
            if text in symbols:
                need(symbols[text] == (address,size),"gtk-static-symbol-ambiguous")
            symbols[text] = (address,size)
    need(symbols,"gtk-retained-unstripped-symbols")
    _,_,needed = elf_exports(raw)
    need(not any("exreader" in item.lower() or "libexr_" in item.lower() for item in needed),
         "gtk-no-alternate-dynamic-sdk")
    return symbols

def _map_symbol_owners(raw,functions,owners):
    text = raw.decode()
    ranges,section = [],""
    for line in text.splitlines():
        found = re.match(r"^\s+(\.\S+)(?:\s|$)",line)
        if found:
            section = found[1]
        match = re.match(r"^\s+(?:\.\S+\s+)?(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+\.a)\(([^)]+)\)\s*$",line)
        if match and section.startswith(".text"):
            address,size = int(match[1],16),int(match[2],16)
            if size:
                ranges.append((address,address+size,Path(match[3]).name,match[4]))
    result = {}
    for name,allowed in owners.items():
        need(name in functions and functions[name][1] > 0,"gtk-required-static-function:"+name)
        address,size = functions[name]
        matched = [dict(archive=archive,member=member) for start,end,archive,member in ranges
                   if start <= address < address+size <= end and archive in allowed]
        need(len(matched) == 1,"gtk-static-function-archive-origin:"+name)
        result[name] = dict(address=address,bytes=size,**matched[0])
    return result

def _static_input(files,runtime,item):
    path = item["path"]
    need(isinstance(path,str) and path.startswith("binary-binding/inputs/") and
         len(Path(path).parts) == 3 and Path(path).name == item["sha256"]+"-"+Path(item["physical_path"]).name,
         "gtk-static-retained-input-path")
    raw = files[runtime+path]
    need(len(raw) == item["bytes"] and sha(raw) == item["sha256"],"gtk-static-retained-input-bytes")
    return raw

def _system_tool(item,clean_environment,output):
    path = Path(item["path"])
    need(path.is_absolute() and path.parent == Path("/usr/bin") and path.resolve() == path and
         re.fullmatch(r"(?:x86_64-linux-gnu-)?(?:gcc|g\+\+)(?:-\d+)?|(?:x86_64-linux-gnu-)?ld(?:\.bfd)?",path.name),
         "gtk-allowed-system-link-tool")
    raw = path.read_bytes()
    need(len(raw) == item["bytes"] and sha(raw) == item["sha256"],"gtk-exact-original-link-tool")
    result = subprocess.run([str(path),"--version"],env=clean_environment,capture_output=True,timeout=10,check=True)
    output.write_bytes(result.stdout+result.stderr)
    need(result.stdout.decode() == item["version"],"gtk-original-link-tool-version")
    return str(path)

C02_ARCHIVES = {"libexreader-posix-c02-sdk-admission.a","libexreader-posix-c02-admission.a",
                "libexreader-migration-coordinator-hardening.a"}
def _target_origin(record):
    suffix = {"runtime-host":"/build/gtk","product-host":"/build/gtk/actual-host/gtk-host",
              "admission":"/build/sdk-admission"}[record["name"]]
    cwd = record["working_directory"]
    need(isinstance(cwd,str) and cwd.startswith("/") and posixpath.normpath(cwd) == cwd and
         cwd.endswith(suffix),"gtk-source-build-working-directory")
    origin = cwd[:-len(suffix)]
    need(origin and origin.startswith("/"),"gtk-source-workspace-origin")
    built = {"runtime-host":"/build/gtk/c02-gtk-host-check",
             "product-host":"/build/gtk/actual-host/gtk-host/exreader-linux",
             "admission":"/build/sdk-admission/exreader-c02-admission"}[record["name"]]
    executed = "/stage-c02/bin/exreader-c02-admission" if record["name"] == "admission" else built
    need(record["built"]["physical_path"] == origin+built and
         record["executed"]["physical_path"] == origin+executed,"gtk-source-build-and-executed-paths")
    return origin

def _input_origin(record,item,origin):
    physical = item["physical_path"]
    argument = item["original_argument"]
    expected = posixpath.normpath(argument if argument.startswith("/") else record["working_directory"]+"/"+argument)
    if expected.startswith(origin+"/"):
        need(physical == expected,"gtk-original-workspace-input-location")
    else:
        need(expected.startswith("/usr/lib/x86_64-linux-gnu/") and
             physical.startswith("/usr/lib/x86_64-linux-gnu/") and ".so" in Path(expected).name,
             "gtk-explicit-original-system-shared-input")
    need(item["sdk_installed"] is physical.startswith(origin+"/stage-sdk/") and
         item["c02_installed"] is physical.startswith(origin+"/stage-c02/"),"gtk-computed-original-prefix-classification")
    name = Path(physical).name
    if name.startswith("libexr_"):
        need(item["sdk_installed"] is True and name.endswith(".a"),"gtk-original-installed-sdk-archive")
    if name in C02_ARCHIVES:
        prefix = origin+"/stage-c02/lib/" if record["name"] != "admission" else {
            "libexreader-posix-c02-sdk-admission.a":origin+"/build/sdk-admission/",
            "libexreader-posix-c02-admission.a":origin+"/stage-native/lib/",
            "libexreader-migration-coordinator-hardening.a":origin+"/stage-abi2/lib/"}[name]
        need(physical == prefix+name,"gtk-source-specific-native-archive-location")

def _relink_target(files,runtime,record,output):
    output.mkdir()
    environment = dict(PATH="/usr/bin:/bin",LANG="C",LC_ALL="C",TMPDIR=str(output))
    driver = _system_tool(record["driver"],environment,output/"driver-version.txt")
    linker = _system_tool(record["linker"],environment,output/"ld-version.txt")
    need(re.fullmatch(r"(?:x86_64-linux-gnu-)?ld(?:\.bfd)?",Path(linker).name),"gtk-gnu-linker-role")
    current = subprocess.check_output([driver,"-print-prog-name=ld"],env=environment,text=True,timeout=10).strip()
    located = shutil.which(current,path=environment["PATH"])
    need(located is not None and Path(located).resolve() == Path(linker),"gtk-driver-uses-original-linker")
    need("g++" in Path(driver).name or "gcc" in Path(driver).name,"gtk-system-compiler-driver")
    original = record["argv"]
    need(isinstance(original,list) and 3 < len(original) <= 512 and
         all(isinstance(value,str) and value and "\0" not in value for value in original),
         "gtk-bounded-link-argv")
    source = _static_input(files,runtime,record["link_script"]).decode()
    lines = [line for line in source.splitlines() if line.strip()]
    need(len(lines) == 1 and shlex.split(lines[0]) == original,"gtk-original-cmake-link-argv")
    need(original[0] in ("/usr/bin/cc","/usr/bin/c++","/usr/bin/gcc","/usr/bin/g++",driver) and
         Path(original[0]).resolve() == Path(driver),"gtk-original-driver-command")
    index = record["output_argument"]
    need(type(index) is int and 1 < index < len(original) and original.count("-o") == 1 and
         original[index-1] == "-o","gtk-single-link-output")
    destination = original[index] if original[index].startswith("/") else record["working_directory"]+"/"+original[index]
    need(posixpath.normpath(destination) == record["built"]["physical_path"],"gtk-original-link-output-path")
    arguments,selected,owners = [],{},{}
    origin = _target_origin(record)
    inputs = record["inputs"]
    need(inputs and len({item["argument"] for item in inputs}) == len(inputs),"gtk-unique-input-arguments")
    for item in inputs:
        ordinal = item["argument"]
        need(type(ordinal) is int and 1 <= ordinal < len(original) and ordinal != index and
             original[ordinal] == item["original_argument"] and not original[ordinal].startswith("-"),
             "gtk-exact-retained-input-ordinal")
        _input_origin(record,item,origin)
        raw = _static_input(files,runtime,item)
        if raw.startswith(b"!<arch>\n"):
            suffix = ".a"
        else:
            need(len(raw) >= 64 and raw[:7] == b"\x7fELF\x02\x01\x01" and
                 struct.unpack_from("<H",raw,18)[0] == 62,"gtk-explicit-elf-link-input")
            kind = struct.unpack_from("<H",raw,16)[0]
            need(kind in (1,3),"gtk-object-or-shared-link-input")
            suffix = ".o" if kind == 1 else ".so"
        path = output/("input-%03d"%ordinal+suffix)
        path.write_bytes(raw)
        selected[ordinal] = path.name
        owners.setdefault(Path(item["physical_path"]).name,set()).add(path.name)
    allowed = {"-O3","-DNDEBUG","-lm","-ldl"}
    for ordinal,value in enumerate(original[1:],1):
        if ordinal in selected:
            arguments.append(selected[ordinal])
        elif ordinal == index:
            arguments.append("relinked.elf")
        elif value == "-o":
            arguments.append(value)
        else:
            need(value in allowed,"gtk-unobserved-or-unsafe-link-argument:"+value)
            arguments.append(value)
    command = [driver,*arguments,"-Wl,-Map,proof.map,--cref"]
    (output/"strict-argv.json").write_text(json.dumps(dict(argv=command,environment=environment),indent=2)+"\n")
    result = subprocess.run(command,cwd=output,env=environment,capture_output=True,timeout=45)
    (output/"stdout.txt").write_bytes(result.stdout)
    (output/"stderr.txt").write_bytes(result.stderr)
    need(result.returncode == 0,"gtk-independent-static-relink-failed:"+record["name"])
    raw = (output/"relinked.elf").read_bytes()
    expected = _static_input(files,runtime,record["built"])
    need(raw == expected,"gtk-independent-static-relink-exact-build-elf:"+record["name"])
    required = {"exr_library_open":{"libexr_library.a"},"exr_library_close":{"libexr_library.a"},
                "pc02_sdk_open_user":{"libexreader-posix-c02-sdk-admission.a"},
                "pc02_check":{"libexreader-posix-c02-admission.a"},
                "pc02_close":{"libexreader-posix-c02-admission.a"}}
    required = {name:{alias for item in archives for alias in owners.get(item,set())}
                for name,archives in required.items()}
    need(all(required.values()),"gtk-required-original-sdk-and-c02-archives")
    origins = _map_symbol_owners((output/"proof.map").read_bytes(),_elf_functions(raw),required)
    return dict(name=record["name"],build_sha256=sha(raw),bytes=len(raw),exact_relink=True,
                native_symbol_archive_origins=origins,input_count=len(selected),
                link_map_sha256=sha((output/"proof.map").read_bytes()))

def verify_static_binding(files,spec,source,verification_output=None):
    runtime,evidence,package = (spec[key] for key in ("runtime_prefix","evidence_prefix","package_prefix"))
    required = _qualified_static_source(source)
    receipt_path = runtime+"binary-binding/receipt.json"
    if receipt_path not in files:
        need(not required,"gtk-source-requires-original-static-link-inputs")
        return dict(installed_sdk_byte_binding=False,source_requires_static_inputs=False)
    need(os.environ.get("GITHUB_ACTIONS") == "true" and verification_output is not None,
         "gtk-independent-link-only-on-actions-with-retained-output")
    receipt = json_value(files[receipt_path])
    need(receipt["schema"] == "c02-gtk-static-link-inputs-v1" and receipt["source"] == source and
         str(receipt["run"]) == str(spec["run"]) and str(receipt["attempt"]) == str(spec["attempt"]) and
         receipt["sdk_base"] == SDK and receipt["sdk_version"] == "3.42.0","gtk-static-qualified-producer")
    records = receipt["targets"]
    need([row["name"] for row in records] == ["runtime-host","product-host","admission"],
         "gtk-all-three-actual-static-targets")
    need(len({_target_origin(record) for record in records}) == 1,"gtk-same-qualified-build-workspace")
    hashes,sets = {},[]
    for record in records:
        names = set()
        origin = _target_origin(record)
        for item in record["inputs"]:
            _input_origin(record,item,origin)
            name = Path(item["physical_path"]).name
            if item["sdk_installed"] or name in C02_ARCHIVES:
                names.add(name)
                hashes.setdefault(name,set()).add(item["sha256"])
        sets.append(names)
    need(sets[0] == sets[1] == sets[2] and {"libexr_library.a","libexr_render.a",*C02_ARCHIVES} <= sets[0] and
         all(len(values) == 1 for values in hashes.values()),"gtk-same-installed-sdk-and-native-archives-all-targets")
    expected = [files[evidence+"c02-gtk-host-check"],files[evidence+"exreader-linux"],
                files[evidence+"exreader-c02-admission"]]
    output = Path(verification_output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    results = []
    try:
        for record,actual in zip(records,expected):
            executed = _static_input(files,runtime,record["executed"])
            built = _static_input(files,runtime,record["built"])
            need(executed == actual and built == executed and record["build_equals_executed"] is True,
                 "gtk-build-executed-identical-original-elf:"+record["name"])
            results.append(_relink_target(files,runtime,record,output/record["name"]))
        package_receipt = json_value(files[package+"binary-originals.json"])
        need(package_receipt["schema"] == "c02-gtk-package-binary-originals-v1" and
             package_receipt["source"] == source and package_receipt["sdk_version"] == "3.42.0",
             "gtk-package-original-binary-scope")
        for name,actual in zip(("exreader-linux","exreader-c02-admission"),expected[1:]):
            record = package_receipt["binaries"][name]
            need(record["original"] == "binary-originals/"+name+".elf" and
                 record["packaged"] == "EXReader-Linux/bin/"+name and
                 files[package+record["original"]] == files[package+record["packaged"]] == actual and
                 record["original_bytes"] == record["packaged_bytes"] == len(actual) and
                 record["original_sha256"] == record["packaged_sha256"] == sha(actual) and record["same_bytes"] is True,
                 "gtk-package-build-executed-byte-chain:"+name)
        result = dict(installed_sdk_byte_binding=True,source_requires_static_inputs=required,
                      proof="independent-static-relink-and-map-origins",targets=results)
        (output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
        return result
    except Exception as error:
        (output/"result.json").write_text(json.dumps(dict(installed_sdk_byte_binding=False,
            error=type(error).__name__,detail=str(error),targets=results),indent=2)+"\n")
        raise

def _loaded_function_byte(raw,name):
    address,size = _elf_functions(raw)[name]
    offset = struct.unpack_from("<Q",raw,32)[0]
    width,count = struct.unpack_from("<HH",raw,54)
    found = []
    for index in range(count):
        kind,flags,start,virtual,physical,length,memory,alignment = struct.unpack_from("<IIQQQQQQ",raw,offset+width*index)
        if kind == 1 and flags & 1 and virtual <= address < address+size <= virtual+length:
            found.append(start+address-virtual)
    need(len(found) == 1,"gtk-negative-loaded-code-location")
    return found[0]

def _archive_function_byte(raw,wanted):
    need(raw.startswith(b"!<arch>\n"),"gtk-negative-actual-static-archive")
    position,found = 8,[]
    while position < len(raw):
        need(position+60 <= len(raw) and raw[position+58:position+60] == b"`\n","gtk-negative-archive-header")
        size = int(raw[position+48:position+58].decode().strip())
        start,end = position+60,position+60+size
        need(size >= 0 and end <= len(raw),"gtk-negative-archive-member-bounds")
        member = raw[start:end]
        if member[:7] == b"\x7fELF\x02\x01\x01":
            need(len(member) >= 64 and struct.unpack_from("<HH",member,16) == (1,62),"gtk-negative-sdk-relocatable-object")
            offset = struct.unpack_from("<Q",member,40)[0]
            width,count = struct.unpack_from("<HH",member,58)
            need(width == 64 and 0 < count < 4096 and offset+width*count <= len(member),"gtk-negative-object-sections")
            sections = [struct.unpack_from("<IIQQQQIIQQ",member,offset+i*width) for i in range(count)]
            for section in sections:
                if section[1] != 2:
                    continue
                at,length,link,step = section[4],section[5],section[6],section[9]
                need(step == 24 and length % step == 0 and at+length <= len(member) and link < count,
                     "gtk-negative-object-symbols")
                strings = sections[link]
                need(strings[1] == 3 and strings[4]+strings[5] <= len(member),"gtk-negative-object-strings")
                table = member[strings[4]:strings[4]+strings[5]]
                for entry in range(at,at+length,step):
                    name,info,other,index,address,width = struct.unpack_from("<IBBHQQ",member,entry)
                    if not name or not (info >> 4 in (1,2) and info & 15 == 2 and 0 < index < count):
                        continue
                    if table[name:name+len(wanted)+1] != wanted.encode()+b"\0":
                        continue
                    content = sections[index]
                    need(content[1] == 1 and content[2] & 4 and content[3] == 0 and width > 0 and
                         address+width <= content[5] and content[4]+content[5] <= len(member),
                         "gtk-negative-selected-sdk-code-section")
                    found.append(start+content[4]+address)
        position = end+(size & 1)
    need(len(found) == 1,"gtk-negative-unique-selected-archive-function:"+wanted)
    return found[0]

def gtk_binary_negative_controls(files,spec,source,output):
    """Actions-only re-packed static SDK proof capsules, independently read back before rejection."""
    import io
    import zipfile
    runtime = spec["runtime_prefix"]
    receipt_path = runtime+"binary-binding/receipt.json"
    if receipt_path not in files:
        need(not _qualified_static_source(source),"gtk-new-source-needs-binary-negative-originals")
        return []
    need(os.environ.get("GITHUB_ACTIONS") == "true","gtk-binary-negative-actions-only")
    original = json_value(files[receipt_path])["targets"][0]
    need(original["name"] == "runtime-host","gtk-negative-original-runtime-target")
    root = Path(output)
    root.mkdir(parents=True,exist_ok=False)
    context = dict(source=source,run=spec["run"],attempt=spec["attempt"],
                   original_artifact=spec["artifact"]["id"],original_zip_sha256=spec["artifact"]["sha256"])
    cases = [
        ("gtk-expected-elf-selected-code","gtk-independent-static-relink-exact-build-elf:"),
        ("gtk-sdk-selected-code","gtk-independent-static-relink-exact-build-elf:"),
        ("gtk-native-selected-code","gtk-independent-static-relink-exact-build-elf:"),
        ("gtk-forged-tool-sha","gtk-exact-original-link-tool"),
        ("gtk-forbidden-plugin-argv","gtk-unobserved-or-unsafe-link-argument:"),
        ("gtk-shell-token-argv","gtk-unobserved-or-unsafe-link-argument:"),
        ("gtk-omitted-sdk-input","gtk-unobserved-or-unsafe-link-argument:"),
        ("gtk-mismatched-link-script","gtk-original-cmake-link-argv")]
    controls = []
    for name,expected in cases:
        record = json_value(json.dumps(original).encode())
        references = [*record["inputs"],record["built"],record["executed"],record["link_script"]]
        data = {item["path"]:_static_input(files,runtime,item) for item in references}
        def replace(item,raw):
            prior = item["path"]
            digest = sha(raw)
            path = "binary-binding/inputs/"+digest+"-"+Path(item["physical_path"]).name
            for value in references:
                if value["path"] == prior:
                    value.update(path=path,bytes=len(raw),sha256=digest)
            data[path] = raw
        def flip(raw,offset):
            need(0 <= offset < len(raw),"gtk-negative-mutation-bounds")
            changed = bytearray(raw)
            changed[offset] ^= 1
            return bytes(changed)
        if name == "gtk-expected-elf-selected-code":
            item = record["built"]
            raw = data[item["path"]]
            replace(item,flip(raw,_loaded_function_byte(raw,"exr_library_open")))
        elif name in ("gtk-sdk-selected-code","gtk-native-selected-code"):
            native = name == "gtk-native-selected-code"
            archive = "libexreader-posix-c02-admission.a" if native else "libexr_library.a"
            item = next(item for item in record["inputs"] if Path(item["physical_path"]).name == archive)
            raw = data[item["path"]]
            replace(item,flip(raw,_archive_function_byte(raw,"pc02_check" if native else "exr_library_open")))
        elif name == "gtk-forged-tool-sha":
            value = record["driver"]["sha256"]
            record["driver"]["sha256"] = ("0" if value[0] != "0" else "1")+value[1:]
        elif name in ("gtk-forbidden-plugin-argv","gtk-shell-token-argv"):
            record["argv"].append("-fplugin=/tmp/exreader-never-load.so" if name == "gtk-forbidden-plugin-argv" else ";")
            replace(record["link_script"],(shlex.join(record["argv"])+"\n").encode())
        elif name == "gtk-omitted-sdk-input":
            record["inputs"] = [item for item in record["inputs"] if Path(item["physical_path"]).name != "libexr_library.a"]
        else:
            replace(record["link_script"],(shlex.join(record["argv"])+" -lm\n").encode())
        references = [*record["inputs"],record["built"],record["executed"],record["link_script"]]
        candidate = {item["path"]:data[item["path"]] for item in references}
        candidate["candidate.json"] = (json.dumps(dict(schema="c02-gtk-binary-negative-v1",
            name=name,producer=context,target=record),sort_keys=True,indent=2)+"\n").encode()
        candidate["file-hashes.json"] = (json.dumps([dict(path=path,bytes=len(raw),sha256=sha(raw))
            for path,raw in sorted(candidate.items())],indent=2)+"\n").encode()
        path = root/(name+".zip")
        with zipfile.ZipFile(path,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for member,raw in sorted(candidate.items()):
                archive.writestr(member,raw)
        packed = path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(packed)) as archive:
            entries = archive.infolist()
            need(len(entries) == len({item.filename for item in entries}) <= 128 and
                 sum(item.file_size for item in entries) <= 512*1024*1024,"gtk-negative-capsule-bounds")
            restored = {}
            for item in entries:
                member = item.filename
                need(not member.startswith("/") and all(part not in ("",".","..") for part in member.split("/")) and
                     not item.flag_bits & 1,"gtk-negative-capsule-canonical-paths")
                restored[member] = archive.read(item)
        inventory = json_value(restored["file-hashes.json"])
        need({item["path"] for item in inventory} == set(restored)-{"file-hashes.json"} and
             len(inventory) == len(restored)-1 and all(len(restored[item["path"]]) == item["bytes"] and
             sha(restored[item["path"]]) == item["sha256"] for item in inventory),
             "gtk-negative-capsule-refreshed-inventory")
        decoded = json_value(restored["candidate.json"])
        need(decoded["schema"] == "c02-gtk-binary-negative-v1" and decoded["name"] == name and
             decoded["producer"] == context,"gtk-negative-capsule-original-source-binding")
        try:
            _relink_target(restored,"",decoded["target"],root/name)
        except ValueError as error:
            need(str(error).startswith(expected),"gtk-negative-unexpected-rejection:"+name+":"+str(error))
            controls.append(dict(name=name,rejected=True,reason=str(error),original=context,
                zip_bytes=len(packed),zip_sha256=sha(packed),refreshed_inventory=True))
        else:
            raise ValueError("gtk-binary-negative-unexpectedly-accepted:"+name)
    need(len(controls) == 8,"gtk-eight-binary-negative-capsules")
    (root/"result.json").write_text(json.dumps(controls,indent=2)+"\n")
    return controls
