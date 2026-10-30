"""Actions-only real range-lock refusal tests, independent of the original 26."""
import argparse
import hashlib
import json
import os
import pathlib
import queue
import struct
import subprocess
import threading

p = argparse.ArgumentParser()
p.add_argument("--probe", required=True)
p.add_argument("--fixture-probe", required=True)
p.add_argument("--work", required=True)
a = p.parse_args()
probe = str(pathlib.Path(a.probe).resolve())
original = str(pathlib.Path(a.fixture_probe).resolve())
work = pathlib.Path(a.work).resolve()
work.mkdir(parents=True, exist_ok=False)
processes = []
events = []
results = []

def spawn(args, name):
    err = (work / (name + ".stderr.txt")).open("w", encoding="utf-8")
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=err, text=True)
    q = queue.Queue()
    def read():
        for line in proc.stdout:
            q.put(line.rstrip("\n"))
        q.put(None)
    threading.Thread(target=read, daemon=True).start()
    processes.append((proc, err, name))
    return proc, q, name

def line(child):
    proc, q, name = child
    item = q.get(timeout=30)
    events.append({"process": name, "stdout": item})
    assert item is not None, (name, proc.poll(), "unexpected EOF")
    return item

def signal(child):
    child[0].stdin.write("\n")
    child[0].stdin.flush()

def finish(child):
    code = child[0].wait(timeout=30)
    assert code == 0, (child[2], code)

def kill(child):
    child[0].kill()
    child[0].wait(timeout=10)

def original_run(root, verb="read"):
    r = subprocess.run([original, verb, str(root), "normal"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    return json.loads(r.stdout)

def digest(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "generation": struct.unpack_from("<Q", raw, 64)[0],
            "pending": struct.unpack_from("<Q", raw, 72)[0]}

passed = False
try:
    for name, drift in (("window-lock-clean", False), ("window-lock-drift", True)):
        parent = work / name
        parent.mkdir()
        root = parent / "private"
        writer = spawn([original, "fixture", str(root), "after"], name + "-writer")
        assert line(writer) == "ready-after"
        kill(writer)
        assert original_run(root, "shared")["stale"] is True
        lease = pathlib.Path(original_run(root, "leasepath")["lease"])
        initial = digest(lease)
        reader = spawn([probe, "reader", str(root), "normal"], name + "-reader")
        assert line(reader) == "acquired-ready"
        helper = spawn([probe, "helper", str(lease), "drift" if drift else "normal"],
                       name + "-helper")
        assert line(helper) == "window-held"
        signal(reader)
        data = json.loads(line(reader))
        assert data["source"] == os.environ["GITHUB_SHA"], data
        assert data["opened"] and data["object_retained"], data
        assert data["classification"] == 0 and not data["checked"], data
        assert data["hook_calls"] == 1 and not data["lease_restored"], data
        assert data["open_reason"] == "restart-lease-window", data
        assert data["open_native"] == 33, data
        assert data["check_reason"] == "restart-not-qualified", data
        # These are unpopulated result fields, NOT assertions about disk state.
        assert data["result_generation_unconfirmed"] == 0, data
        assert data["result_pending_unconfirmed"] == 0, data
        # Remove the helper's lock before measuring C01 exclusion.
        signal(helper)
        assert line(helper) == "window-released"
        finish(helper)
        held_bytes = digest(lease)
        if drift:
            assert held_bytes["generation"] == 5 and held_bytes["pending"] == 0
        else:
            assert held_bytes == initial
        alive = original_run(root, "shared")
        assert alive["status"] == 2 and alive["stale"] is False, alive
        if drift:
            kill(reader)
        else:
            signal(reader)
            assert line(reader) == "reader-closed"
            finish(reader)
        after = original_run(root, "shared")
        reopened = original_run(root)
        if drift:
            assert not reopened["opened"], reopened
            assert reopened["open_reason"] == "restart-lease-generation", reopened
            # Deliberate residual measurement: no assertion of crash isolation.
        else:
            assert after["stale"] is True, after
            assert reopened["opened"] and reopened["class"] == 3 and reopened["checked"], reopened
        final_bytes = digest(lease)
        assert final_bytes == held_bytes, (held_bytes, final_bytes)
        data.update(case=name, initial_lease=initial, held_lease=held_bytes,
                    final_lease=final_bytes, helper_released_before_shared_probe=True,
                    shared_while_object_alive=alive, exit_mode="kill" if drift else "close",
                    shared_after_exit=after, reader_after_exit=reopened,
                    crash_isolation_claim=False)
        results.append(data)
        print("WINDOW-LOCK-CASE " + name + " PASS " + json.dumps(data, sort_keys=True), flush=True)
    assert len(results) == 2
    passed = True
finally:
    for proc, err, name in processes:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        err.close()
    receipt = dict(source=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
                   attempt=os.environ["GITHUB_RUN_ATTEMPT"], passed=passed,
                   checks=len(results), results=results, events=events,
                   original_suite_unchanged_checks=26, classification_only=True,
                   full_p0_acceptance=False, physical_power_loss=False)
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print("WINDOW-LOCK-SUMMARY cases=2 failed=0 source=" + os.environ["GITHUB_SHA"], flush=True)
