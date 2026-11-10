# SPDX-License-Identifier: MIT
"""X4 acceptance. Run with Python -X utf8: EXE FONT CHECK_SHELL_SAVE OUTPUT.

Uses the host's native acceptance driver. Process death is always the requested
PowerShell Stop-Process -Force, including three production-writer checkpoints.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
import zlib


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def wait_for(predicate, process, timeout=90):
    start = time.monotonic()
    while not predicate():
        assert process.poll() is None, f"Process exited: {process.returncode}"
        if time.monotonic() - start > timeout:
            raise TimeoutError("Acceptance checkpoint not reached")
        time.sleep(.05)


def force(process):
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                    f"Stop-Process -Id {process.pid} -Force"], check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    process.wait(timeout=10)


def start(exe, font, out, profile, store, script, extra=()):
    out.mkdir(parents=True, exist_ok=True)
    drive = out / "run.drive"
    drive.write_text("\n".join(script) + "\n", encoding="utf-8")
    env = dict(os.environ, EXREADER_ANNOTATIONS_DIR=str(store))
    args = [str(exe), "--offscreen", "--font", str(font), "--data", str(profile),
            "--evidence", str(out), "--drive", str(drive), *extra]
    return subprocess.Popen(args, env=env, creationflags=subprocess.CREATE_NO_WINDOW,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def finish(process, out):
    try:
        code = process.wait(timeout=90)
    except subprocess.TimeoutExpired:
        force(process)
        raise AssertionError((out / "drive.log").read_text(encoding="utf-8")[-4000:])
    log = (out / "drive.log").read_text(encoding="utf-8")
    assert code == 0 and "\tFAIL\t" not in log, (code, log[-4000:])


def dump(out, name):
    return json.loads((out / f"{name}.annotations.json").read_text(encoding="utf-8"))


def payload(path):
    data = path.read_bytes()
    assert data[:8] == b"EXRAUTO1" and len(data) >= 24
    length, crc, header_crc = struct.unpack_from("<QII", data, 8)
    assert length == len(data) - 24
    assert zlib.crc32(data[:20]) == header_crc and zlib.crc32(data[24:]) == crc
    return data[24:]


def main():
    exe, font, checker, out = [Path(p).resolve() for p in sys.argv[1:5]]
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"Use an empty output directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    storage = out / "storage"
    storage.mkdir(exist_ok=True)
    selftest = subprocess.check_output([str(checker), "selftest", str(storage)], text=True)
    baseline = (storage / "atomic.json").read_bytes()
    results = {"storage_selftest": selftest.strip(), "atomic_kills": []}
    for stage in ("writing", "flushed", "before-replace"):
        ready = storage / "ready"
        ready.unlink(missing_ok=True)
        process = subprocess.Popen([str(checker), "kill", str(storage), stage],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            wait_for(ready.exists, process)
            force(process)
        finally:
            if process.poll() is None:
                force(process)
        actual = (storage / "atomic.json").read_bytes()
        assert actual == baseline
        (storage / f"{stage}.json").write_bytes(actual)
        staged = (storage / "atomic.json.tmp").read_bytes()
        results["atomic_kills"].append({"stage": stage, "sha256": sha(actual),
                                        "bytes": len(actual), "pid": process.pid,
                                        "staged_bytes": len(staged)})

    store, profile = out / "store", out / "profile"
    store.mkdir(exist_ok=True)
    book = out / "X4 Acceptance.html"
    book.write_text("<html><head><title>X4 Acceptance</title></head><body>"
                    "<p>X4 persistence acceptance document. Select this text to attach a note.</p>"
                    "<p>A complete note must survive process termination.</p></body></html>", encoding="utf-8")
    setup = ["shell|on", "shell_client|1100|700", "wait_idle"]
    writer = out / "writer"
    script = ["import|" + str(book), "open|X4 Acceptance", *setup,
              "select_pointer|down|0|0", "select_pointer|move|15|1", "select_pointer|up|15|1",
              "annot_command|6", "annot_edit|explicit baseline", "annot_dump|saved",
              "annot_command|6", "annot_edit|unsaved draft 中文 😀 before force kill|2|preview",
              "annot_dump|edited", "probe_wait|35000", "annot_dump|waited",
              "annot_autosave", "annot_autosave", "annot_dump|unchanged", "probe_wait|120000"]
    process = start(exe, font, writer, profile, store, script)
    try:
        wait_for(lambda: (writer / "edited.annotations.json").exists(), process)
        log = (writer / "drive.log").read_text(encoding="utf-8")
        assert "\tFAIL\t" not in log, log
        observed_edit = time.time()
        original, = store.glob("*.json")
        original_bytes, original_time = original.read_bytes(), original.stat().st_mtime_ns
        auto = Path(str(original) + ".autosave")
        assert not auto.exists()
        wait_for(lambda: (writer / "waited.annotations.json").exists(), process, 50)
        waited = time.time()
        data = payload(auto)
        assert "unsaved draft 中文 😀 before force kill" in data.decode("utf-8")
        assert original.read_bytes() == original_bytes and original.stat().st_mtime_ns == original_time
        assert auto.stat().st_mtime_ns > original_time
        assert dump(writer, "saved")["dirty"] == 0
        assert dump(writer, "edited")["dirty"] == dump(writer, "waited")["dirty"] == 1
        auto_time = auto.stat().st_mtime_ns
        # A dirty document with no further edits must not rewrite the same copy.
        wait_for(lambda: (writer / "unchanged.annotations.json").exists(), process)
        assert auto.stat().st_mtime_ns == auto_time
        (writer / "original-before.json").write_bytes(original_bytes)
        (writer / "autosave-payload.json").write_bytes(data)
        (writer / "autosave-container.bin").write_bytes(auto.read_bytes())
        results["autosave"] = {"configured_seconds": 30, "wait_seconds": waited-observed_edit,
                               "original_utc": utc(original_time / 1e9), "autosave_utc": utc(auto_time / 1e9),
                               "payload_sha256": sha(data), "original_sha256": sha(original_bytes),
                               "container_sha256": sha(auto.read_bytes()), "pid": process.pid}
        force(process)
    finally:
        if process.poll() is None:
            force(process)

    restart = out / "restart"
    process = start(exe, font, restart, profile, store,
                    ["annot_answer|yes", "wait_idle", *setup,
                     "annot_prompt|有未保存的修改，是否恢复？", "annot_dump|recovered",
                     "annot_autosave", "annot_save", "annot_dump|saved", "quit"])
    finish(process, restart)
    recovered = dump(restart, "recovered")
    assert recovered["dirty"] == 1 and recovered["prompts"] == 1
    assert original.read_bytes() == data
    (restart / "recovered-saved.json").write_bytes(original.read_bytes())
    assert dump(restart, "saved")["dirty"] == 0 and not auto.exists()
    results["recovery"] = {"prompt": "有未保存的修改，是否恢复？", "dirty_after_recovery": 1,
                           "recovered_sha256": sha(original.read_bytes()), "matches_before_force": True}

    # The explicit baseline now is the recovered draft. Create and truncate a newer copy.
    create = out / "make-corrupt"
    process = start(exe, font, create, profile, store,
                    ["open|X4 Acceptance", *setup, "annot_pick|0|marker",
                     "annot_edit|this copy will be truncated|0|preview", "annot_autosave",
                     "annot_dump|ready", "probe_wait|120000"], ["--autosave-seconds", "1"])
    try:
        wait_for(lambda: (create / "ready.annotations.json").exists(), process)
        force(process)
    finally:
        if process.poll() is None:
            force(process)
    saved = original.read_bytes()
    healthy_copy = auto.read_bytes()
    declined = out / "declined"
    process = start(exe, font, declined, profile, store,
                    ["annot_answer|no", "wait_idle", *setup,
                     "annot_prompt|有未保存的修改，是否恢复？", "annot_dump|declined", "quit"])
    finish(process, declined)
    assert dump(declined, "declined")["dirty"] == 0
    assert not auto.exists() and original.read_bytes() == saved
    results["declined_recovery"] = {"sidecar_deleted": True, "dirty": 0, "original_unchanged": True}
    auto.write_bytes(healthy_copy[:13])
    (out / "truncated.autosave").write_bytes(auto.read_bytes())
    corrupt = out / "corrupt"
    process = start(exe, font, corrupt, profile, store,
                    ["open|X4 Acceptance", *setup, "annot_dump|rejected", "quit"])
    finish(process, corrupt)
    error = dump(corrupt, "rejected")["error"]
    assert error == "副本损坏，无法恢复" and original.read_bytes() == saved
    results["corrupt"] = {"error": error, "exit_code": process.returncode,
                          "original_sha256": sha(saved), "truncated_bytes": auto.stat().st_size}
    auto.unlink()

    # Native save/discard/cancel decisions and configurable timer, without touching the original.
    choices = out / "choices"
    process = start(exe, font, choices, profile, store,
                    ["open|X4 Acceptance", *setup, "annot_pick|0|marker", "annot_edit|discard me|0|preview",
                     "probe_wait|1200", "annot_dump|dirty", "annot_answer|cancel", "shelf_return",
                     "annot_dump|cancelled", "annot_answer|no", "shelf_return", "wait_idle", "annot_dump|discarded", "quit"],
                    ["--autosave-seconds", "1"])
    finish(process, choices)
    assert dump(choices, "cancelled")["dirty"] == 1 and dump(choices, "discarded")["dirty"] == 0
    assert not auto.exists() and original.read_bytes() == saved
    results["choices"] = {"cancel_keeps_dirty": True, "discard_clears_dirty": True,
                          "original_unchanged": True, "interval_seconds": 1}

    # Three consecutive window captures include the native title bar and its '*'.
    titles = out / "titles"
    process = start(exe, font, titles, profile, store,
                    ["open|X4 Acceptance", *setup, "annot_pick|0|marker",
                     "annot_edit|dirty title first edit|1|preview", "annot_dump|edit-1", "snapshot|edit-1",
                     "annot_save", "annot_close", "annot_dump|save-2", "snapshot|save-2",
                     "annot_pick|0|marker", "annot_edit|dirty title second edit|2|preview",
                     "annot_dump|edit-3", "snapshot|edit-3", "annot_answer|cancel", "annot_request_close",
                     "annot_dump|close-cancelled", "annot_answer|yes", "quit"])
    finish(process, titles)
    states = [dump(titles, name) for name in ("edit-1", "save-2", "edit-3")]
    assert [state["dirty"] for state in states] == [1, 0, 1]
    assert [state["title"].startswith("* ") for state in states] == [True, False, True]
    assert dump(titles, "close-cancelled")["dirty"] == 1
    assert json.loads(original.read_bytes())["annotations"][0]["text"] == "dirty title second edit"
    assert not auto.exists()
    results["dirty_titles"] = [{"dirty": state["dirty"], "title": state["title"],
                                "screenshot": f"titles/{name}.png"}
                               for state, name in zip(states, ("edit-1", "save-2", "edit-3"))]
    results["close"] = {"cancel_keeps_window_and_dirty": True, "save_closes_and_persists": True}
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
