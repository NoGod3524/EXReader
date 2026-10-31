#!/usr/bin/env python3
"""GTK participant: actual native account/reading controls, read-only observations."""
import argparse, configparser, hashlib, json, os
from pathlib import Path
import sys, time
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(HERE))
from check_linux_host import Session, command
import atspi_client as bus
from relay import start, save, identity, trust_desktop, untrust_desktop, retained_rows

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform.startswith("linux")
    p = argparse.ArgumentParser()
    for name in ("payload", "original", "output", "previous"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--incoming-prefix", default="F04_WINDOWS")
    args = p.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    os.environ.pop("NO_AT_BRIDGE", None); os.environ.pop("GTK_MODULES", None)
    os.environ["GTK_A11Y"] = "atspi"
    host = Session((args.payload / "bin/exreader-linux").resolve(),
                   (args.payload / "Reader.otf").resolve(), out)
    app = dav = trust = None
    report = dict(identity(), platform="linux-gtk", sdk_version="3.42.0",
                  f04_stage="six-host-reading-preparation-v2", passed=False,
                  F04_accepted=False, checks=[], navigations=[])
    original = args.original.read_bytes()
    expected = json.loads((HERE / "contract.json").read_text())["original"]
    assert hashlib.sha256(original).hexdigest() == expected["sha256"] and len(original) == expected["bytes"]
    report.update(original_sha256=expected["sha256"], original_bytes=len(original),
                  book_identity="epub:" + expected["sha256"])
    def observed(section):
        value = configparser.ConfigParser(interpolation=None); value.read(host.observe)
        return dict(value[section]) if value.has_section(section) else {}
    def wait(section, predicate, seconds=90):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            assert host.process.poll() is None, "native GTK host exited"
            value = observed(section)
            if value and predicate(value) and not host.read().get("busy") and not host.read().get("saving"):
                return value
            time.sleep(.05)
        raise TimeoutError((section, observed(section), host.read()))
    def element(name, roles=None):
        end = time.monotonic() + 30
        while time.monotonic() < end:
            node = next((n for n in bus.walk(app) if bus.name(n) == name and
                         (roles is None or bus.role(n) in roles)), None)
            if node: return node
            time.sleep(.05)
        raise TimeoutError("native control missing: " + name)
    def click_node(node):
        rect = bus.extents(node)
        assert rect and rect["width"] > 4 and rect["height"] > 4
        assert bus.states(node).get("showing") and bus.states(node).get("sensitive")
        command("xdotool", "mousemove", "--sync", rect["x"] + rect["width"] // 2, rect["y"] + rect["height"] // 2)
        command("xdotool", "click", "1")
    def click(name, roles=None):
        click_node(element(name, roles))
    def records():
        command("xdotool", "windowactivate", "--sync", host.window)
        host.key("ctrl+shift+r")
        wait("reading_records", lambda s: s["visible"] == "1" and s["running"] == "0")
    def close_records():
        host.key("Escape"); wait("reading_records", lambda s: s["visible"] == "0")
    def rows():
        return retained_rows(out / "profile/library.sqlite.product.sqlite")
    def select(marker):
        candidates = [n for n in bus.children(element("Bookmarks and annotations"))
                      if bus.role(n) == "list item" and marker in bus.name(n)]
        assert len(candidates) == 1, marker
        click_node(candidates[0])
    def action(name):
        before = int(observed("reading_records")["actions"]); click(name, {"push button"})
        return wait("reading_records", lambda s: int(s["actions"]) > before and s["running"] == "0")
    def edit(marker):
        before = int(observed("reading_records")["actions"]); click("Edit text", {"push button"})
        click_node(element("Reading record text", {"text"}))
        host.key("ctrl+a"); host.paste(marker); host.key("alt+s")
        wait("reading_records", lambda s: int(s["actions"]) >= before + 2 and s["running"] == "0")
    def frame():
        value = host.read()
        return {k: value[k] for k in ("book", "part", "page", "start", "end", "frame_generation")}
    def account_window():
        command("xdotool", "windowactivate", "--sync", host.window)
        host.key("ctrl+shift+a")
        wait("account", lambda s: s["visible"] == "1" and s["owner_busy"] == "0" and s["preparing"] == "0")
    def account_close():
        host.key("alt+F4")
        wait("account", lambda s: s["visible"] == "0" and s["session_present"] == "0")
    def sync():
        account_window(); host.key("alt+s")
        wait("account", lambda s: s["session_state"] == "4" and s["owner_busy"] == "0" and s["preparing"] == "0", 240)
        account_close()
    def check(name, condition):
        assert condition, name
        report["checks"].append(name)
    try:
        dav, user, password = start(out, previous=args.previous)
        trust = trust_desktop(out / "cert.pem", "f04-gtk")
        assert bus.init()[0]; host.launch(); app = bus.wait_application("exreader-linux")
        host.wait(lambda s: not s["saving"])
        # Real chooser, including its existing asynchronous selection handling.
        host.dialog(args.original.resolve())
        host.wait(lambda s: not s["saving"] and s["error"] == 0)
        account_window()
        for mnemonic, value in (("w", dav.base + "/dav/"), ("u", user), ("p", password)):
            host.key("alt+" + mnemonic, "ctrl+a"); host.paste(value)
        host.key("alt+h"); account_close()
        before = frame(); sync()
        check("remote_sync_does_not_move_active_reader", frame() == before)
        received = rows(); report["incoming"] = received
        records(); click("Saved product progress", {"push button"}); action("Open location")
        wait("reading_records", lambda s: s["visible"] == "0")
        check("public_found_progress", observed("reading_records")["match"] == "1")
        report["progress_navigation"] = {"frame": frame(), "record_state": observed("reading_records")}
        for suffix in ("BOOKMARK", "NOTE"):
            records(); marker = args.incoming_prefix + "_" + suffix; select(marker)
            action("Open location")
            wait("reading_records", lambda s: s["visible"] == "0")
            check("public_found_" + suffix.lower(), observed("reading_records")["match"] == "1")
            report["navigations"].append({"marker": marker, "frame": frame(),
                                          "record_state": observed("reading_records")})
        # Edits originate from genuine received records, preserving their global
        # identity/selector. Nothing synthesizes outbox or uses an SDK test writer.
        before = frame(); records(); action("Save progress")
        for suffix in ("BOOKMARK", "NOTE"):
            select(args.incoming_prefix + "_" + suffix); edit("F04_GTK_" + suffix)
        close_records()
        check("record_edits_do_not_navigate", frame() == before)
        sync()
        outgoing = rows(); report["outgoing"] = outgoing
        check("incoming_raw_wires_retained", all(row in outgoing for row in received))
        check("native_client_put", any(r["method"] == "PUT" and "/revisions/" in r["path"] for r in dav.requests))
        check("native_authenticated_transport", bool(dav.requests) and all(r["authenticated"] for r in dav.requests))
        report["program"] = {"sha256": hashlib.sha256(host.binary.read_bytes()).hexdigest(),
                             "bytes": host.binary.stat().st_size}
        report["passed"] = True; save(dav, out, "gtk-peer", report); dav = None
    finally:
        if host.process: host.close()
        if dav:
            (out / "requests.json").write_text(json.dumps(dav.requests, indent=2))
            dav.server.shutdown(); dav.server.server_close()
        if trust: untrust_desktop(trust)
        (out / "key.pem").unlink(missing_ok=True)
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        bus.exit_bus()
if __name__ == "__main__": main()
