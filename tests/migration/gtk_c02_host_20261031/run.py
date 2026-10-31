"""Actions-only actual GTK library, page and search-owner admission checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import sqlite3
import subprocess
import selectors
import time
from capture import capture

assert os.environ.get("GITHUB_ACTIONS") == "true" and os.name == "posix"
p = argparse.ArgumentParser()
p.add_argument("--host", type=Path, required=True)
p.add_argument("--admission", type=Path, required=True)
p.add_argument("--font", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
host, admission, font = (str(x.resolve()) for x in (a.host, a.admission, a.font))
out = a.output.resolve()
out.mkdir(mode=0o700, parents=False, exist_ok=False)
rows = []
def save():
    (out / "report.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],
        run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
        cases=rows, actual_gtk=True, actual_sdk=True, actual_migration=False,
        full_c02_acceptance=False), indent=2) + "\n")
def done(name, **detail):
    rows.append(dict(name=name, passed=True, **detail))
    save()
def call(name, command, expected=0, **kwargs):
    r = subprocess.run(list(map(str, command)), capture_output=True, timeout=45, **kwargs)
    (out / (name + ".stdout")).write_bytes(r.stdout)
    (out / (name + ".stderr")).write_bytes(r.stderr)
    (out / (name + ".exit")).write_text(str(r.returncode) + "\n")
    assert r.returncode == expected, (name, r.returncode, r.stdout, r.stderr)
    return r
def snapshot(root):
    return {str(x.relative_to(root)): (x.stat().st_ino, hashlib.sha256(x.read_bytes()).hexdigest())
            for x in root.rglob("*") if x.is_file()}
def probe(name, library, expected=0):
    return call(name, [host, "probe", library, font], expected)
library = out / "library.sqlite"
probe("unknown-host", library, 2)
assert not library.exists() and not Path(str(library) + ".product.lock").exists()
done("unknown-refused-before-sdk-and-catalog")
r = call("create", [admission, "create", library])
assert json.loads(r.stdout)["admitted"] is True
assert json.loads(probe("created", library).stdout)["books"] == 0
done("explicit-creation-and-real-gtk-shelf")
second = out / "second.sqlite"
call("second-create", [admission, "create", second])
assert json.loads(probe("second-created", second).stdout)["books"] == 0
done("existing-valid-authority-supports-another-library")
authority = Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve() / ".exreader-c02-admission"
capture(authority, [library, second], out / "snapshots/clean")
before = snapshot(out)
call("duplicate-create", [admission, "create", library], 2)
assert library.stat().st_ino == before["library.sqlite"][0]
done("explicit-creation-never-overwrites")
book = out / "book.txt"
book.write_text("".join("silver tides remain visible number %d.\n" % i for i in range(100)))
log = (out / "held.stderr").open("wb")
child = subprocess.Popen([host, "hold", str(library), font, str(book)],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
try:
    ready = selectors.DefaultSelector()
    ready.register(child.stdout, selectors.EVENT_READ)
    assert ready.select(45), "actual GTK owner did not reach its live search"
    line = child.stdout.readline()
    (out / "held.stdout").write_bytes(line)
    event = json.loads(line)
    assert event["holding"] is True and event["search_results"] > 0
    assert event["search_complete"] is False, event
    call("exclusive-while-borrowed", [host, "owner", library], 2)
    done("actual-page-and-incomplete-search-keep-shared-custody", **event)
    capture(authority, [library, second], out / "snapshots/borrowed")
    probe("catalog-second-reader", library, 2)
    done("product-catalog-owner-still-exclusive")
    child.stdin.write(b"\n")
    child.stdin.flush()
    remaining = child.communicate(timeout=30)[0]
    with (out / "held.stdout").open("ab") as stream: stream.write(remaining)
    assert child.returncode == 0, child.returncode
finally:
    if child.poll() is None: child.kill(); child.wait(timeout=10)
    log.close()
call("exclusive-after-close", [host, "owner", library])
done("last-search-page-sdk-and-catalog-close-release-custody")
capture(authority, [library, second], out / "snapshots/released")
assert json.loads(probe("reopen-after-close", library).stdout)["books"] == 1
with sqlite3.connect("file:" + str(library) + "?mode=ro", uri=True) as db:
    records = db.execute("SELECT id,title,source FROM books ORDER BY id").fetchall()
    assert len(records) == 1 and bytes(records[0][2]) == book.read_bytes(), records
done("fresh-gtk-shelf-and-independent-original-bytes")
copied = out / "copied.sqlite"
shutil.copyfile(library, copied)
copied.chmod(0o600)
original = copied.read_bytes()
probe("copied-unregistered", copied, 2)
assert copied.read_bytes() == original and not Path(str(copied) + ".product.lock").exists()
done("copied-library-has-no-registration-fallback")
held = out / "held-original.sqlite"
library.rename(held)
shutil.copyfile(held, library)
library.chmod(0o600)
replacement = library.read_bytes()
probe("replacement-identity", library, 2)
assert library.read_bytes() == replacement
library.rename(out / "rejected-replacement.sqlite")
held.rename(library)
probe("original-identity-restored", library)
done("same-bytes-different-inode-refused")
alias = out / "alias"
alias.symlink_to(out, target_is_directory=True)
probe("symlink-parent", alias / "library.sqlite", 2)
done("parent-symlink-refused")
fake = out / "fake-home"
fake.mkdir(mode=0o700)
environment = dict(os.environ, HOME=str(fake))
call("home-does-not-select-authority", [admission, "check", library], env=environment)
assert not (fake / ".exreader-c02-admission").exists()
done("environment-cannot-select-authority")
r = call("leave-pending", [host, "pending", library])
descriptor = json.loads(r.stdout)
assert descriptor["pending"] is True
tracked = {str(library): library.read_bytes(),
           str(library) + ".product.sqlite": Path(str(library) + ".product.sqlite").read_bytes()}
probe("pending-actual-host", library, 2)
call("pending-command", [admission, "check", library], 2)
call("pending-duplicate-enroll", [admission, "enroll", library], 2)
assert all(Path(path).read_bytes() == data for path, data in tracked.items())
done("durable-pending-blocks-actual-host-before-any-catalog-write", descriptor=descriptor)
capture(authority, [library, second], out / "snapshots/pending")
authority = Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve() / ".exreader-c02-admission"
objects = []
for path in [authority, *sorted(authority.rglob("*"))]:
    native = path.stat()
    objects.append(dict(path=path.relative_to(authority).as_posix(), device=native.st_dev,
        inode=native.st_ino, mode=native.st_mode, links=native.st_nlink,
        bytes=native.st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None))
(out / "authority-native-identities.json").write_text(json.dumps(dict(
    root=str(authority), objects=objects, library=dict(path=str(library),
    device=library.stat().st_dev, inode=library.stat().st_ino,
    bytes=library.stat().st_size, sha256=hashlib.sha256(library.read_bytes()).hexdigest())), indent=2) + "\n")
shutil.copytree(authority, out / "retained-authority")

# Source contract: new qualification must retain actual static-link inputs.
GTK_C02_STATIC_LINK_INPUTS = 1
def retain_static_inputs():
    import shlex
    root = Path(__file__).resolve().parents[3]
    directory = out/"binary-binding"
    directory.mkdir()
    inputs = directory/"inputs"
    inputs.mkdir()
    def retain(path, category):
        path = Path(path).resolve(strict=True)
        with path.open("rb") as stream:
            first = os.fstat(stream.fileno())
            raw = stream.read()
            last = os.fstat(stream.fileno())
        assert (first.st_dev,first.st_ino,first.st_size,first.st_mtime_ns,first.st_ctime_ns) == (
            last.st_dev,last.st_ino,last.st_size,last.st_mtime_ns,last.st_ctime_ns)
        digest = hashlib.sha256(raw).hexdigest()
        target = inputs/(digest+"-"+path.name)
        if target.exists():
            assert target.read_bytes() == raw
        else:
            target.write_bytes(raw)
        return dict(path=target.relative_to(out).as_posix(),physical_path=str(path),
                    bytes=len(raw),sha256=digest,device=first.st_dev,inode=first.st_ino,category=category)
    clean_environment = dict(PATH="/usr/bin:/bin",LANG="C",LC_ALL="C")
    def tool(path):
        path = Path(path).resolve(strict=True)
        assert path.parent == Path("/usr/bin"), path
        raw = path.read_bytes()
        version = subprocess.check_output([str(path),"--version"],env=clean_environment,text=True,timeout=10)
        return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),version=version)
    targets = (
        ("runtime-host",Path(host),Path(host),Path(host).parent,
         Path(host).parent/"CMakeFiles/c02-gtk-host-check.dir/link.txt"),
        ("product-host",root/"build/gtk/actual-host/gtk-host/exreader-linux",
         root/"build/gtk/actual-host/gtk-host/exreader-linux",root/"build/gtk/actual-host/gtk-host",
         root/"build/gtk/actual-host/gtk-host/CMakeFiles/exreader-linux.dir/link.txt"),
        ("admission",root/"build/sdk-admission/exreader-c02-admission",Path(admission),
         root/"build/sdk-admission",root/"build/sdk-admission/CMakeFiles/exreader-c02-admission.dir/link.txt"))
    records = []
    for name,built,executed,cwd,link in targets:
        lines = [line for line in link.read_text().splitlines() if line.strip()]
        assert len(lines) == 1, (name,lines)
        command = shlex.split(lines[0])
        assert command and Path(command[0]).is_absolute() and command.count("-o") == 1
        output_index = command.index("-o")+1
        assert output_index < len(command) and (cwd/command[output_index]).resolve() == built.resolve()
        driver = tool(command[0])
        linker_name = subprocess.check_output([command[0],"-print-prog-name=ld"],
                                              env=clean_environment,text=True,timeout=10).strip()
        linker_path = shutil.which(linker_name,path=clean_environment["PATH"])
        assert linker_path, linker_name
        arguments = []
        for index,argument in enumerate(command[1:],1):
            if index == output_index or argument.startswith("-"):
                continue
            path = (cwd/argument).resolve(strict=True)
            assert path.is_file(), (name,argument)
            item = retain(path,"link-input")
            item.update(argument=index,original_argument=argument,
                        sdk_installed=path.is_relative_to(root/"stage-sdk"),
                        c02_installed=path.is_relative_to(root/"stage-c02"))
            arguments.append(item)
        assert any(item["sdk_installed"] and Path(item["physical_path"]).name == "libexr_library.a"
                   for item in arguments), (name,"missing actual installed SDK library")
        assert any(Path(item["physical_path"]).name == "libexreader-posix-c02-sdk-admission.a"
                   for item in arguments), (name,"missing actual C02 SDK adapter")
        record = dict(name=name,working_directory=str(cwd.resolve()),argv=command,
                      output_argument=output_index,link_script=retain(link,"cmake-link-script"),
                      driver=driver,linker=tool(linker_path),inputs=arguments,
                      built=retain(built,"build-elf"),executed=retain(executed,"actual-elf"))
        record["build_equals_executed"] = record["built"]["sha256"] == record["executed"]["sha256"]
        records.append(record)
        print("C02-GTK-LINK-INPUTS "+json.dumps(dict(name=name,argv=command,driver=driver,linker=record["linker"],
            build_equals_executed=record["build_equals_executed"],
            inputs=[dict(argument=item["argument"],file=Path(item["physical_path"]).name,
                         sdk=item["sdk_installed"],c02=item["c02_installed"],sha256=item["sha256"])
                    for item in arguments])),flush=True)
    receipt = dict(schema="c02-gtk-static-link-inputs-v1",source=os.environ["GITHUB_SHA"],
        run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
        sdk_base="8357eafa28423a7ab93ba08b823af80f01ad1505",sdk_version="3.42.0",targets=records)
    (directory/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")

retain_static_inputs()
assert len(rows) == 13
save()
report = json.loads((out / "report.json").read_text())
report.update(passed=True, complete=True,static_link_inputs="binary-binding/receipt.json")
(out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print("C02-ACTUAL-GTK cases=13 failed=0")
