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
assert len(rows) == 13
save()
report = json.loads((out / "report.json").read_text())
report.update(passed=True, complete=True)
(out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print("C02-ACTUAL-GTK cases=13 failed=0")
