#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only driver for the J23 application-boundary fuzz regression.

It never builds anything: the caller installs the packages and compiles the two
installed consumers first. Here every fixture expectation is checked against a
real process, the bounded deterministic mutation loops run under the sanitizer
environment, and every abnormal case is replayed twice in fresh processes.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boundary_cases import FUZZ_TARGETS, REQUIRED_CASES  # noqa: E402

HEX32 = "0123456789abcdef0123456789abcdef"
HEX64 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
EPUB = "epub:" + HEX64

DEFAULT_ITERATIONS = 2500
DEFAULT_BUDGET_MS = 90000
DEFAULT_SEED = 0x6A32332D66757A7A


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe(value):
    return json.dumps(value, sort_keys=True)[:2000]


class Driver:
    def __init__(self, arguments):
        self.arguments = arguments
        self.root = Path(arguments.output).resolve()
        self.work = self.root / "work"
        self.evidence = self.root / "evidence"
        self.observations = self.evidence / "observations"
        for directory in (self.work, self.evidence, self.observations):
            directory.mkdir(parents=True, exist_ok=True)
        self.consumer_path = str(Path(arguments.consumer).resolve())
        self.c_consumer_path = str(Path(arguments.c_consumer).resolve())
        self.fixtures = Path(arguments.fixtures).resolve()
        self.manifest = json.loads((self.fixtures / "manifest.json").read_text(encoding="utf-8"))
        self.seeds = {item["file"]: item for item in self.manifest["seeds"]}
        self.cases = []
        self.fuzz_runs = []
        self.replays = []
        self.notes = []

    # ---------------------------------------------------------------- tools

    def consumer(self, *arguments, expect_success=True, timeout=900):
        command = [self.consumer_path] + [str(item) for item in arguments]
        completed = subprocess.run(
            command, cwd=str(self.work), capture_output=True, text=True,
            errors="replace", timeout=timeout,
        )
        output = (completed.stdout or "").strip().splitlines()
        parsed = None
        if output:
            try:
                parsed = json.loads(output[-1])
            except json.JSONDecodeError:
                parsed = None
        if expect_success and completed.returncode != 0:
            raise AssertionError(
                "consumer %s exited %d: %s %s"
                % (arguments[0], completed.returncode, completed.stdout.strip()[-800:], completed.stderr.strip()[-800:])
            )
        return completed.returncode, parsed, completed

    def c_consumer(self, *arguments):
        command = [self.c_consumer_path] + [str(item) for item in arguments]
        completed = subprocess.run(
            command, cwd=str(self.work), capture_output=True, text=True, timeout=300
        )
        require(completed.returncode == 0, "C consumer exited %d" % completed.returncode)
        return json.loads((completed.stdout or "").strip().splitlines()[-1])

    def seed_bytes(self, name):
        return (self.fixtures / name).read_bytes()

    def stage(self, name, target=None):
        destination = self.work / "stage" / (target or Path(name).name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.fixtures / name, destination)
        return destination

    def fresh_db(self, name):
        path = self.work / "db" / (name + ".db")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        status, output, _ = self.consumer("wire-heads", str(path), "tag", HEX32)
        require(status == 0 and output["status"] == 0, "could not initialise the product catalog")
        return path

    def record(self, name, function):
        started = time.time()
        try:
            detail = function() or {}
            entry = {"name": name, "ok": True, "detail": detail}
        except Exception as error:  # noqa: BLE001 - a refusal is evidence
            entry = {
                "name": name,
                "ok": False,
                "detail": {"error": str(error), "traceback": traceback.format_exc(limit=6)},
            }
        entry["seconds"] = round(time.time() - started, 3)
        self.cases.append(entry)
        (self.observations / (name + ".json")).write_text(
            json.dumps(entry, indent=2) + "\n", encoding="utf-8"
        )
        line = {"case": name, "ok": entry["ok"]}
        if not entry["ok"]:
            line["detail"] = entry["detail"]["error"][:600]
        print(json.dumps(line), flush=True)
        return entry["ok"]

    # ------------------------------------------------------------ fixtures

    def verify_preferences_seeds(self):
        seen = 0
        for name, item in sorted(self.seeds.items()):
            if item["kind"] != "preferences":
                continue
            seen += 1
            staged = self.stage(name, "manifest-" + Path(name).name)
            limit = item.get("limit", 0)
            arguments = ["preferences-load", str(staged)] + ([str(limit)] if limit else [])
            status, output, _ = self.consumer(*arguments)
            require(status == 0, "preferences-load did not run for " + name)
            require(
                output.get("name") == item["status"],
                "%s expected %s, observed %s" % (name, item["status"], output.get("name")),
            )
            require(
                staged.stat().st_size == item["bytes"], name + " changed size after a load"
            )
        require(seen == 13, "unexpected preferences seed count")
        return {"seeds": seen}

    def verify_wire_seeds(self):
        database = self.fresh_db("manifest")
        seen = 0
        for name, item in sorted(self.seeds.items()):
            if item["kind"] != "wire":
                continue
            seen += 1
            path = self.fixtures / name
            data = self.seed_bytes(name)
            status, output, _ = self.consumer("wire-validate", str(database), str(path))
            require(status == 0, "wire-validate did not run for " + name)
            require(
                output.get("name") == item["status"],
                "%s expected %s, observed %s" % (name, item["status"], output.get("name")),
            )
            if item["status"] == "OK":
                require(output["sha256"] == sha256_bytes(data), name + " SHA differs from Python")
                require(output["bytes"] == len(data), name + " byte count differs from Python")
                decode = item.get("decode")
                if decode:
                    status, decoded, _ = self.consumer("wire-decode", str(database), str(path))
                    require(status == 0, "wire-decode did not run for " + name)
                    if "status" in decode:
                        require(decoded["status"] == decode["status"], name + " decode status differs")
                    else:
                        require(decoded["status"] == 0, name + " decode refused a valid wire")
                        for key, value in decode.items():
                            require(
                                decoded.get(key) == value,
                                "%s decode field %s expected %r, observed %r"
                                % (name, key, value, decoded.get(key)),
                            )
        require(seen == 12, "unexpected wire seed count")
        return {"seeds": seen}

    # --------------------------------------------------------- named cases

    def case_preferences_defaults(self):
        _, output, _ = self.consumer("preferences-defaults")
        require(output["abi_version"] == 1, "preferences ABI is not 1")
        require(output["font_size"] == 24, "default font size is not 24")
        require(abs(output["line_spacing"] - 1.6) < 1e-6, "default line spacing is not 1.6")
        require(output["paragraph_spacing"] == 12, "default paragraph spacing is not 12")
        require(output["margin"] == 48, "default margin is not 48")
        require(output["theme"] == 1, "default theme is not light")
        require(output["page_turn_direction"] == 1, "default direction is not ltr")
        require(output["page_turn_input"] == 1, "default input is not tap")
        require(output["fixed_page_zoom"] == 100, "default zoom is not 100")
        require(output["light_foreground"] == "#1A1A1AFF", "default light foreground differs")
        require(output["dark_background"] == "#101010FF", "default dark background differs")
        return output

    def case_preferences_roundtrip(self):
        path = self.work / "roundtrip.json"
        status, saved, _ = self.consumer("preferences-save", str(path), "defaults")
        require(status == 0 and saved["name"] == "OK", "saving defaults failed")
        canonical = (self.fixtures / "preferences" / "valid.json").read_bytes()
        require(path.read_bytes() == canonical, "saved bytes differ from the canonical document")
        digest = sha256_file(path)
        _, loaded, _ = self.consumer("preferences-load", str(path))
        require(loaded["name"] == "OK", "loading the canonical document failed")
        require(loaded["font_size"] == 24 and loaded["margin"] == 48, "loaded values differ")
        require(sha256_file(path) == digest, "load modified the settings file")

        status, custom, _ = self.consumer("preferences-save", str(path), "custom")
        require(status == 0 and custom["name"] == "OK", "saving the custom record failed")
        _, loaded, _ = self.consumer("preferences-load", str(path))
        require(abs(loaded["font_size"] - 33.5) < 1e-4, "custom font size did not round trip")
        require(abs(loaded["line_spacing"] - 1.75) < 1e-6, "custom line spacing did not round trip")
        require(loaded["theme"] == 2 and loaded["page_turn_direction"] == 2, "custom enums differ")
        require(loaded["page_turn_input"] == 4 and loaded["fixed_page_zoom"] == 175, "custom turn/zoom differ")
        require(loaded["dark_background"] == "#101010FE", "custom color did not round trip")
        return {"canonical_sha256": sha256_bytes(canonical)}

    def case_unknown_version(self):
        path = self.stage("preferences/unknown_version.json", "unknown-version.json")
        digest = sha256_file(path)
        _, output, _ = self.consumer("preferences-load", str(path))
        require(output["name"] == "VERSION", "unknown version was not refused as VERSION")
        require(output["memory_changed"] is False, "unknown version modified the caller record")
        require(abs(output["font_size"] - 7.25) < 1e-4, "unknown version replaced the record")
        require(sha256_file(path) == digest, "unknown version modified the settings file")
        return {"status": output["name"], "file_sha256": digest}

    def case_limit_ceiling(self):
        overflow = self.stage("preferences/overflow_limit.json", "overflow.json")
        _, output, _ = self.consumer("preferences-load", str(overflow))
        require(output["name"] == "LIMIT", "an oversized file was not refused as LIMIT")
        valid = self.stage("preferences/valid.json", "ceiling-valid.json")
        _, output, _ = self.consumer("preferences-load", str(valid), "300000")
        require(output["name"] == "ARGUMENT", "a raised file ceiling was not refused")
        return {"status": output["name"]}

    def case_lower_limit(self):
        valid = self.stage("preferences/valid.json", "lower-valid.json")
        digest = sha256_file(valid)
        _, output, _ = self.consumer("preferences-load", str(valid), "64")
        require(output["name"] == "LIMIT", "a lowered ceiling did not refuse the file")
        _, output, _ = self.consumer("preferences-load", str(valid), "65536")
        require(output["name"] == "OK", "the exact 64 KiB ceiling refused a small file")
        require(sha256_file(valid) == digest, "a limited load modified the file")
        return {"status": output["name"]}

    def case_nan_range(self):
        path = self.stage("preferences/nan_number.json", "nan.json")
        _, output, _ = self.consumer("preferences-load", str(path))
        require(output["name"] == "RANGE", "a non-finite number was not refused as RANGE")
        require(output["memory_changed"] is False, "a RANGE refusal modified the record")
        return {"status": output["name"]}

    def generic_preferences_refusal(self, seed, expected):
        path = self.stage(seed, "refusal-" + Path(seed).name)
        digest = sha256_file(path)
        _, output, _ = self.consumer("preferences-load", str(path))
        require(output["name"] == expected, "%s was refused as %s" % (seed, output["name"]))
        require(output["memory_changed"] is False, seed + " modified the caller record")
        require(sha256_file(path) == digest, seed + " modified the file")
        return {"status": output["name"]}

    def case_import_legacy_partial(self):
        _, output, _ = self.consumer("preferences-import-legacy", "0x000b")
        require(output["name"] == "OK", "a partial legacy import failed")
        require(output["applied"] == 11, "applied bits differ")
        require(output["preserved"] == 0x0FF4, "preserved bits differ")
        require(output["font_size"] == 30 and output["margin"] == 30, "imported values differ")
        require(output["theme"] == 1 and output["fixed_page_zoom"] == 100, "unlisted fields changed")
        return output

    def case_import_legacy_unknown_bits(self):
        _, output, _ = self.consumer("preferences-import-legacy", "0x8000")
        require(output["name"] == "ARGUMENT", "unknown legacy bits were not refused")
        require(output["applied"] == 0xFFFFFFFF and output["preserved"] == 0xFFFFFFFF, "the report was written")
        require(output["font_size"] == 24 and output["margin"] == 48, "the record changed")
        return {"status": output["name"]}

    def case_import_legacy_invalid_merge(self):
        _, output, _ = self.consumer("preferences-import-legacy", "0x0001", "invalid")
        require(output["name"] == "RANGE", "an invalid merged record was not refused")
        require(output["applied"] == 0xFFFFFFFF, "the report was written on a refusal")
        require(output["font_size"] == 24, "the record changed on a refusal")
        return {"status": output["name"]}

    def case_status_names(self):
        expected = {
            0: "OK",
            1: "ARGUMENT",
            2: "IO",
            3: "FORMAT",
            4: "VERSION",
            5: "RANGE",
            6: "CANCELLED",
            7: "LIMIT",
            999: "UNKNOWN",
        }
        observed = {}
        for value, name in expected.items():
            _, output, _ = self.consumer("preferences-status-name", str(value))
            require(output["name"] == name, "status name %d differs" % value)
            observed[str(value)] = name
        themes = {}
        for stored, system, resolved in (
            (1, 9, 1),
            (2, 1, 2),
            (3, 1, 1),
            (3, 2, 2),
            (3, 3, 1),
            (9, 2, 1),
            (0, 2, 1),
        ):
            _, output, _ = self.consumer("preferences-theme", str(stored), str(system))
            require(
                output["resolved"] == resolved,
                "effective theme for stored=%d system=%d differs" % (stored, system),
            )
            themes["%d/%d" % (stored, system)] = output["resolved"]
        return {"names": observed, "themes": themes}

    def case_unicode_path(self):
        directory = self.work / "设置"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "阅读 设置.json"
        status, saved, _ = self.consumer("preferences-save", str(path), "defaults")
        require(status == 0 and saved["name"] == "OK", "a Unicode path could not be saved")
        _, loaded, _ = self.consumer("preferences-load", str(path))
        require(loaded["name"] == "OK" and loaded["font_size"] == 24, "a Unicode path did not load")
        require(path.read_bytes() == (self.fixtures / "preferences" / "valid.json").read_bytes(), "Unicode round trip differs")
        return {"path": str(path)}

    def case_empty_path(self):
        _, output, _ = self.consumer("preferences-save", "", "defaults")
        require(output["name"] == "ARGUMENT", "an empty save path was not refused")
        output = self.c_consumer("load", "")
        require(output["name"] == "ARGUMENT", "an empty C load path was not refused")
        return {"status": output["name"]}

    def case_preferences_cross_process(self):
        path = self.work / "cross-process.json"
        status, saved, _ = self.consumer("preferences-save", str(path), "custom")
        require(status == 0 and saved["name"] == "OK", "the first process did not save")
        _, loaded, _ = self.consumer("preferences-load", str(path))
        require(loaded["name"] == "OK", "the second process did not load")
        require(abs(loaded["font_size"] - 33.5) < 1e-4 and loaded["theme"] == 2, "cross-process values differ")
        require(loaded["fixed_page_zoom"] == 175, "cross-process zoom differs")
        return {"path": str(path)}

    def case_wire_seed_valid(self, seed, expected_fields):
        database = self.fresh_db("seed-" + Path(seed).stem)
        path = self.fixtures / seed
        data = self.seed_bytes(seed)
        _, output, _ = self.consumer("wire-validate", str(database), str(path))
        require(output["name"] == "OK", seed + " did not validate")
        require(output["sha256"] == sha256_bytes(data), seed + " SHA differs")
        for key, value in expected_fields.items():
            require(output.get(key) == value, "%s field %s differs" % (seed, key))
        return {"sha256": output["sha256"], "bytes": output["bytes"]}

    def case_wire_v1_progress(self):
        return self.case_wire_seed_valid(
            "wire/v1_progress_reflow.json",
            {
                "entity_kind": "progress",
                "operation": "put",
                "location_kind": "reflow_global",
                "parent_count": 0,
            },
        )

    def case_wire_v2_epub(self):
        result = self.case_wire_seed_valid(
            "wire/v2_epub_annotation.json",
            {
                "entity_kind": "annotation",
                "entity_key": EPUB + ":" + HEX32,
                "location_kind": "epub_chapter",
                "book_key": EPUB,
            },
        )
        database = self.fresh_db("decode-epub")
        status, decoded, _ = self.consumer(
            "wire-decode", str(database), str(self.fixtures / "wire/v2_epub_annotation.json")
        )
        require(status == 0 and decoded["status"] == 0, "the EPUB v2 wire did not decode")
        require(decoded["mode"] == 2 and decoded["anchor_version"] == 2, "the EPUB decode mode differs")
        require(decoded["part"] == 0 and decoded["part_path"] == "OEBPS/ch1.xhtml", "the EPUB route differs")
        return result

    def case_wire_refusal(self, seed, expected):
        database = self.fresh_db("refusal-" + Path(seed).stem)
        _, output, _ = self.consumer("wire-validate", str(database), str(self.fixtures / seed))
        require(output["name"] == expected, "%s expected %s observed %s" % (seed, expected, output["name"]))
        require(output["bytes"] == 0 and output["sha256"] == "", "a refused wire published metadata")
        return {"status": output["name"]}

    def case_wire_hash_mismatch(self):
        database = self.fresh_db("hash-mismatch")
        path = self.fixtures / "wire/v1_progress_reflow.json"
        _, output, _ = self.consumer("wire-validate", str(database), str(path), "0" * 64)
        require(output["name"] == "HASH", "a wrong transport SHA was not refused as HASH")
        return {"status": output["name"]}

    def case_wire_local_pending(self):
        database = self.fresh_db("local-pending")
        path = self.fixtures / "wire/v1_progress_reflow.json"
        digest = sha256_bytes(self.seed_bytes("wire/v1_progress_reflow.json"))
        _, queued, _ = self.consumer("wire-local", str(database), str(path))
        require(queued["name"] == "OK" and queued["created"] == 1, "a valid local revision was not queued")
        require(queued["sha256"] == digest, "the queued SHA differs")
        identifier = queued["revision_id"]
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["count"] == 1 and outbox["rows"][0]["id"] == identifier, "the pending row is missing")
        _, retried, _ = self.consumer("wire-retry", str(database), identifier, "3")
        require(retried["name"] == "OK", "retry failed")
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["rows"][0]["attempts"] == 1, "retry did not increase the attempt count")
        require(outbox["rows"][0]["last_error"] == "revision_error_3", "retry stored an unexpected token")
        _, refused, _ = self.consumer("wire-ack", str(database), identifier, "0" * 64)
        require(refused["name"] == "HASH", "a wrong ack SHA was not refused")
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["count"] == 1, "a refused ack removed the pending row")
        _, acked, _ = self.consumer("wire-ack", str(database), identifier, digest)
        require(acked["name"] == "OK", "a verified ack failed")
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["count"] == 0, "ack left a pending row")
        retained = self.work / "retained.json"
        _, fetched, _ = self.consumer("wire-get", str(database), identifier, str(retained))
        require(fetched["name"] == "OK", "the retained revision is gone after ack")
        require(retained.read_bytes() == self.seed_bytes("wire/v1_progress_reflow.json"), "the retained bytes differ")
        _, heads, _ = self.consumer("wire-heads", str(database), "progress", EPUB)
        require(heads["revisions"] == 1 and heads["heads"] == 1, "the retained history differs")
        require(heads["projection_safe"] == 1, "the retained history is not safe")
        _, again, _ = self.consumer("wire-local", str(database), str(path))
        require(again["name"] == "OK" and again["created"] == 0, "a duplicate local write was not idempotent")
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["count"] == 0, "a duplicate local write requeued the revision")
        return {"revision_id": identifier, "sha256": digest}

    def case_wire_receive_no_queue(self):
        database = self.fresh_db("receive-no-queue")
        progress = self.fixtures / "wire/v1_progress_reflow.json"
        annotation = self.fixtures / "wire/v1_annotation_reflow.json"
        progress_sha = sha256_bytes(progress.read_bytes())
        annotation_sha = sha256_bytes(annotation.read_bytes())
        _, received, _ = self.consumer("wire-receive", str(database), str(progress), progress_sha)
        require(received["name"] == "OK" and received["created"] == 1, "a remote revision was not stored")
        identifier = received["revision_id"]
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["count"] == 0, "a remote receive queued a local row")
        retained = self.work / "received.json"
        _, fetched, _ = self.consumer("wire-get", str(database), identifier, str(retained))
        require(fetched["name"] == "OK" and retained.read_bytes() == progress.read_bytes(), "the remote bytes differ")
        _, again, _ = self.consumer("wire-receive", str(database), str(progress), progress_sha)
        require(again["name"] == "OK" and again["created"] == 0, "a duplicate remote receive was not idempotent")
        _, other, _ = self.consumer("wire-receive", str(database), str(annotation), annotation_sha)
        require(other["name"] == "OK" and other["created"] == 1, "a second remote entity was not stored")
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["count"] == 0, "remote receives changed the pending queue")
        return {"revision_id": identifier, "sha256": progress_sha}

    def case_wire_decode(self):
        database = self.fresh_db("decode")
        _, decoded, _ = self.consumer(
            "wire-decode", str(database), str(self.fixtures / "wire/v1_annotation_reflow.json")
        )
        require(decoded["status"] == 0, "the annotation wire did not decode")
        require(decoded["entity_kind"] == "annotation", "the decoded kind differs")
        require(decoded["annotation_id"] == HEX32, "the decoded annotation id differs")
        require(decoded["mode"] == 1 and decoded["anchor_version"] == 1, "the decoded mode differs")
        require(decoded["start"] == 0 and decoded["end"] == 5, "the decoded span differs")
        require(decoded["exact_size"] == 5 and decoded["exact"] == "alpha", "the decoded quote differs")
        require(decoded["parser_version"] == "j23-fuzz/1", "the decoded parser version differs")
        _, refused, _ = self.consumer(
            "wire-decode", str(database), str(self.fixtures / "wire/v1_tag.json")
        )
        require(refused["status"] == 1, "a non-reading wire was not refused as ARGUMENT")
        return {"decoded": decoded["entity_kind"], "refused": refused["name"]}

    def case_validation_does_not_write(self):
        database = self.fresh_db("read-only")
        digest = sha256_file(database)
        for name, item in sorted(self.seeds.items()):
            if item["kind"] != "wire":
                continue
            status, output, _ = self.consumer("wire-validate", str(database), str(self.fixtures / name))
            require(status == 0, "validate did not run for " + name)
        require(sha256_file(database) == digest, "validate changed the product catalog bytes")
        _, heads, _ = self.consumer("wire-heads", str(database), "tag", HEX32)
        require(heads["revisions"] == 0, "validate inserted a revision")
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["count"] == 0, "validate queued a revision")
        return {"database_sha256": digest}

    def case_encode(self, kind, expected, verify):
        database = self.fresh_db("encode-" + kind)
        wire = self.work / ("encoded-" + kind + ".json")
        status, output, _ = self.consumer("encode", str(database), kind, str(wire))
        require(status == 0, "encode did not run")
        require(output["name"] == expected, "%s expected %s observed %s" % (kind, expected, output["name"]))
        detail = {"status": output["name"], "gap": output["gap"]}
        if expected == "OK":
            require(wire.exists() and wire.stat().st_size == output["bytes"], "encoded bytes differ")
            _, validated, _ = self.consumer("wire-validate", str(database), str(wire))
            require(validated["name"] == "OK", "the encoded wire does not validate")
            require(validated["bytes"] == output["bytes"], "the encoded wire size differs")
            detail.update(verify(database, wire, validated))
        else:
            require(output["bytes"] == 0, "a refused encode returned bytes")
            require(not wire.exists() or wire.stat().st_size == 0, "a refused encode wrote a file")
        return detail

    def case_cross_process_revisions(self):
        database = self.fresh_db("cross-process")
        digest = sha256_bytes(self.seed_bytes("wire/v1_progress_reflow.json"))
        path = self.fixtures / "wire/v1_progress_reflow.json"
        _, received, _ = self.consumer("wire-local", str(database), str(path))
        require(received["created"] == 1, "the first process did not queue")
        identifier = received["revision_id"]
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["count"] == 1, "the second process lost the pending row")
        retained = self.work / "cross-retained.json"
        _, fetched, _ = self.consumer("wire-get", str(database), identifier, str(retained))
        require(fetched["name"] == "OK", "the third process could not read the bytes")
        require(retained.read_bytes() == self.seed_bytes("wire/v1_progress_reflow.json"), "cross-process bytes differ")
        _, acked, _ = self.consumer("wire-ack", str(database), identifier, digest)
        require(acked["name"] == "OK", "the fourth process could not ack")
        _, outbox, _ = self.consumer("wire-outbox", str(database))
        require(outbox["count"] == 0, "the fifth process still sees a pending row")
        _, fetched, _ = self.consumer("wire-get", str(database), identifier, str(retained))
        require(fetched["name"] == "OK", "ack deleted the retained history")
        return {"revision_id": identifier}

    def case_c_abi_parity(self):
        _, cpp_defaults, _ = self.consumer("preferences-defaults")
        c_defaults = self.c_consumer("defaults")
        for key in ("abi_version", "font_size", "line_spacing", "paragraph_spacing", "margin", "theme", "fixed_page_zoom"):
            require(c_defaults[key] == cpp_defaults[key], "C/C++ defaults differ for " + key)
        for value, name in ((3, "FORMAT"), (6, "CANCELLED"), (999, "UNKNOWN")):
            output = self.c_consumer("status-name", str(value))
            require(output["name"] == name, "C status name %d differs" % value)
        valid = self.stage("preferences/valid.json", "c-valid.json")
        output = self.c_consumer("load", str(valid))
        require(output["name"] == "OK" and output["memory_changed"] == 1, "the C load failed")
        nan = self.stage("preferences/nan_number.json", "c-nan.json")
        output = self.c_consumer("load", str(nan))
        require(output["name"] == "RANGE" and output["memory_changed"] == 0, "the C refusal differs")
        database = self.fresh_db("c-abi")
        wire = self.fixtures / "wire/v1_progress_reflow.json"
        output = self.c_consumer("validate-wire", str(database), str(wire))
        require(output["name"] == "OK", "the C wire validate failed")
        require(output["sha256"] == sha256_bytes(wire.read_bytes()), "the C wire SHA differs")
        return {"c_status": output["name"]}

    def case_negative_controls(self):
        """Real sanitizer/runtime failures must surface as failures, not rejects."""
        expectations = {
            "heap-overflow": ("AddressSanitizer", lambda code: code != 0),
            "signed-overflow": ("runtime error", lambda code: code != 0),
            "leak": ("LeakSanitizer", lambda code: code in (23, -6)),
            "abort": ("", lambda code: code == -6),
            "terminate": ("", lambda code: code == -6),
            "exit-code": ("", lambda code: code == 7),
        }
        observed = {}
        for kind, (signature, check) in expectations.items():
            command = [self.consumer_path, "selftest", kind]
            completed = subprocess.run(
                command, cwd=str(self.work), capture_output=True, text=True,
                errors="replace", timeout=120,
            )
            require(check(completed.returncode), "%s ended with unexpected code %d" % (kind, completed.returncode))
            require(signature in completed.stderr, "%s did not report %r" % (kind, signature))
            try:
                self.consumer("selftest", kind)
            except AssertionError:
                pass
            else:
                raise AssertionError("the driver accepted a failing selftest " + kind)
            observed[kind] = completed.returncode
        started = time.time()
        try:
            self.consumer("selftest", "hang", timeout=3)
        except subprocess.TimeoutExpired:
            observed["hang"] = "timeout"
        else:
            raise AssertionError("a hanging child was not stopped by the timeout")
        require(time.time() - started < 30, "the timeout did not fire promptly")
        return observed

    # ------------------------------------------------------------- fuzzing

    def fuzz(self, target):
        directory = self.work / "fuzz" / target
        directory.mkdir(parents=True, exist_ok=True)
        seeds_dir = directory / "seeds"
        seeds_dir.mkdir(exist_ok=True)
        for name, item in self.seeds.items():
            if item.get("fuzz") and item["kind"] == ("preferences" if target == "preferences" else "wire"):
                require(item["status"] == "OK" and item["bytes"] > 0, name + " is not a nonempty legal seed")
                require((self.fixtures / name).stat().st_size == item["bytes"], name + " differs from its manifest size")
                shutil.copyfile(self.fixtures / name, seeds_dir / Path(name).name)
        require(any(seeds_dir.iterdir()), "no fuzz seeds for " + target)
        journal = directory / "journal.log"
        current = directory / "current.bin"
        if journal.exists():
            journal.unlink()
        try:
            status, summary, completed = self.fuzz_child(target, seeds_dir, journal, current, directory)
        except subprocess.TimeoutExpired:
            lines = journal.read_text(encoding="utf-8", errors="replace").splitlines() if journal.exists() else []
            self.fuzz_runs.append({"target": target, "iterations": 0, "stop": "timeout",
                                   "journal_lines": len(lines), "exit": "timeout"})
            replay_ok = self.replay_case(target) if current.exists() else "no case"
            raise AssertionError("fuzz target %s exceeded its hard timeout; last journal line %s; replay %s"
                                 % (target, lines[-1] if lines else "none", replay_ok))
        return self.fuzz_finish(target, journal, current, status, summary, completed)

    def fuzz_child(self, target, seeds_dir, journal, current, directory):
        return self.consumer(
            "fuzz",
            target,
            str(seeds_dir),
            str(self.arguments.iterations),
            str(self.arguments.seed),
            str(journal),
            str(current),
            str(directory),
            str(self.arguments.budget_ms),
            expect_success=False,
            timeout=self.arguments.budget_ms // 1000 + 300,
        )

    def fuzz_finish(self, target, journal, current, status, summary, completed):
        directory = journal.parent
        lines = journal.read_text(encoding="utf-8", errors="replace").splitlines() if journal.exists() else []
        entry = {
            "target": target,
            "iterations": int(summary.get("iterations", 0)) if summary else 0,
            "stop": summary.get("stop") if summary else "crash",
            "journal_lines": len(lines),
            "journal_sha256": sha256_file(journal) if journal.exists() else "",
            "current_sha256": sha256_file(current) if current.exists() else "",
            "current_bytes": current.stat().st_size if current.exists() else 0,
            "exit": status,
            "seconds": summary.get("elapsed_ms", 0) if summary else 0,
        }
        self.fuzz_runs.append(entry)
        if status != 0:
            last = lines[-1] if lines else "no journal line"
            replay_ok = self.replay_case(target)
            raise AssertionError(
                "fuzz target %s exited %d (%s); last journal line %s; replay %s"
                % (target, status, (summary or {}).get("violation", completed.stdout.strip()[-400:]), last, replay_ok)
            )
        require(summary is not None and summary.get("target") == target, "fuzz target %s printed no summary" % target)
        require(entry["iterations"] > 0, "fuzz target %s ran no case" % target)
        require(
            entry["stop"] == "iterations" or entry["iterations"] > 50,
            "fuzz target %s stopped almost immediately" % target,
        )
        require(len(lines) == entry["iterations"], "the crash journal lost iterations")
        return entry

    def replay_case(self, target):
        directory = self.work / "fuzz" / target
        current = directory / "current.bin"
        require(current.exists(), "no staged case to replay for " + target)
        digest = sha256_file(current)
        first_status, first, _ = self.consumer(
            "replay", target, str(current), str(directory), expect_success=False
        )
        second_status, second, _ = self.consumer(
            "replay", target, str(current), str(directory), expect_success=False
        )
        matched = first_status == second_status and first == second
        entry = {
            "target": target,
            "case_sha256": digest,
            "bytes": current.stat().st_size,
            "exit": first_status,
            "output": first,
            "matched": matched,
        }
        self.replays.append(entry)

        def check():
            if not matched:
                raise AssertionError("replay outputs differ")
            return entry

        self.record("replay." + target, check)
        return "matched" if matched else "differed"

    def case_determinism(self, target):
        result = self.replay_case(target)
        require(result == "matched", "replay differed for " + target)
        return self.replays[-1]

    # ------------------------------------------------------------ reduction

    def installed_manifest(self):
        prefix = Path(self.arguments.installed_prefix)
        sdk = Path(self.arguments.sdk_prefix)
        files = []
        for base, patterns in (
            (prefix / "include", ["**/*.h"]),
            (prefix / "lib", ["*.a"]),
            (sdk / "include", ["**/*.h"]),
            (sdk / "lib", ["*.a", "**/EXReaderConfigVersion.cmake"]),
        ):
            if not base.exists():
                continue
            for pattern in patterns:
                for path in sorted(base.glob(pattern)):
                    if not path.is_file():
                        continue
                    files.append(
                        {
                            "path": str(path.relative_to(base)),
                            "bytes": path.stat().st_size,
                            "sha256": sha256_file(path),
                        }
                    )
        consumers = []
        for path in (Path(self.arguments.consumer), Path(self.arguments.c_consumer)):
            consumers.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
        return {"installed": files, "consumers": consumers}

    def evidence_environment(self):
        def capture(command):
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
                return (completed.stdout + completed.stderr).strip().splitlines()[:4]
            except Exception:  # noqa: BLE001 - a missing tool is recorded, not invented
                return ["unavailable"]

        return {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cc": capture(["clang", "--version"]),
            "cxx": capture(["clang++", "--version"]),
            "cmake": capture(["cmake", "--version"]),
            "python": platform.python_version(),
            "asan_options": os.environ.get("ASAN_OPTIONS", ""),
            "ubsan_options": os.environ.get("UBSAN_OPTIONS", ""),
            "lsan_options": os.environ.get("LSAN_OPTIONS", ""),
        }

    # ----------------------------------------------------------------- run

    def run(self):
        require(os.environ.get("GITHUB_ACTIONS") == "true", "the fuzz driver runs only on Actions")
        require(sys.platform.startswith("linux"), "this package is granted on the Linux sanitizer runner only")
        source = os.environ["GITHUB_SHA"]
        run_id = int(os.environ["GITHUB_RUN_ID"])
        attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
        environment = self.evidence_environment()
        require("detect_leaks=1" in environment["asan_options"], "LeakSanitizer is not enabled")
        require("halt_on_error=1" in environment["ubsan_options"], "UBSan does not halt")

        self.record("preferences.seed_manifest", self.verify_preferences_seeds)
        self.record("wire.seed_manifest", self.verify_wire_seeds)
        self.record("preferences.defaults", self.case_preferences_defaults)
        self.record("preferences.roundtrip", self.case_preferences_roundtrip)
        self.record("preferences.unknown_version_keeps_file", self.case_unknown_version)
        self.record("preferences.limit_ceiling", self.case_limit_ceiling)
        self.record("preferences.lower_limit", self.case_lower_limit)
        self.record("preferences.nan_range", self.case_nan_range)
        self.record("preferences.truncated_format", lambda: self.generic_preferences_refusal("preferences/truncated.json", "FORMAT"))
        self.record("preferences.duplicate_key_format", lambda: self.generic_preferences_refusal("preferences/duplicate_key.json", "FORMAT"))
        self.record("preferences.nul_string_format", lambda: self.generic_preferences_refusal("preferences/nul_string.json", "FORMAT"))
        self.record("preferences.unknown_enum_format", lambda: self.generic_preferences_refusal("preferences/bad_enum.json", "FORMAT"))
        self.record("preferences.import_legacy_partial", self.case_import_legacy_partial)
        self.record("preferences.import_legacy_unknown_bits", self.case_import_legacy_unknown_bits)
        self.record("preferences.import_legacy_invalid_merge", self.case_import_legacy_invalid_merge)
        self.record("preferences.status_names", self.case_status_names)
        self.record("preferences.unicode_path", self.case_unicode_path)
        self.record("preferences.empty_path", self.case_empty_path)
        self.record("preferences.cross_process_reopen", self.case_preferences_cross_process)
        self.record("wire.seed_v1_progress_valid", self.case_wire_v1_progress)
        self.record("wire.seed_v2_epub_annotation_valid", self.case_wire_v2_epub)
        self.record("wire.unknown_field_format", lambda: self.case_wire_refusal("wire/unknown_field.json", "FORMAT"))
        self.record("wire.duplicate_key_format", lambda: self.case_wire_refusal("wire/duplicate_key.json", "FORMAT"))
        self.record("wire.invalid_utf8_format", lambda: self.case_wire_refusal("wire/invalid_utf8.json", "FORMAT"))
        self.record("wire.byte_limit", lambda: self.case_wire_refusal("wire/byte_limit.bin", "LIMIT"))
        self.record("wire.hash_mismatch", self.case_wire_hash_mismatch)
        self.record("wire.pending_intent_local_then_ack", self.case_wire_local_pending)
        self.record("wire.receive_idempotent_without_queue", self.case_wire_receive_no_queue)
        self.record("wire.decode_v1_matches_seed", self.case_wire_decode)
        self.record("wire.decode_not_reading_refused", self.case_decode_non_reading)
        self.record("wire.validation_does_not_write", self.case_validation_does_not_write)
        self.record(
            "encode.v1_annotation_valid",
            lambda: self.case_encode(
                "v1-annotation",
                "OK",
                lambda database, wire, validated: {
                    "encoded_sha256": sha256_bytes(wire.read_bytes()),
                    "validated_entity": validated["entity_kind"],
                },
            ),
        )
        self.record(
            "encode.v2_point_valid",
            lambda: self.case_encode(
                "v2-point",
                "OK",
                lambda database, wire, validated: {"encoded_sha256": sha256_bytes(wire.read_bytes()), "anchor": 2},
            ),
        )
        self.record(
            "encode.v1_chapter_scope_refused",
            lambda: self.case_encode("v1-chapter", "NOT_REPRESENTABLE", lambda *_: {}),
        )
        self.record(
            "encode.v2_nul_refused",
            lambda: self.case_encode("v2-nul", "NOT_REPRESENTABLE", lambda *_: {}),
        )
        self.record(
            "encode.argument_refused",
            lambda: self.case_encode("argument", "ARGUMENT", lambda *_: {}),
        )
        self.record("cross_process.revisions_reopen", self.case_cross_process_revisions)
        self.record("c_abi.parity", self.case_c_abi_parity)

        self.record("harness.crash_and_exit_negative_controls", self.case_negative_controls)
        for target in FUZZ_TARGETS:
            self.record("fuzz." + target + ".invariants", lambda target=target: self.fuzz(target))
        for target in FUZZ_TARGETS:
            self.record("determinism." + target, lambda target=target: self.case_determinism(target))

        return self.finish(source, run_id, attempt, environment)

    def case_decode_non_reading(self):
        database = self.fresh_db("decode-non-reading")
        _, output, _ = self.consumer("wire-decode", str(database), str(self.fixtures / "wire/v1_tag.json"))
        require(output["status"] == 1, "a non-reading wire was not refused")
        return {"status": output["name"]}

    def finish(self, source, run_id, attempt, environment):
        names = [case["name"] for case in self.cases]
        missing = [name for name in REQUIRED_CASES if name not in names]
        extra = [name for name in names if name not in REQUIRED_CASES and not name.startswith("replay.")]
        failures = [case["name"] for case in self.cases if not case["ok"]]
        replay_failures = [case["name"] for case in self.cases if case["name"].startswith("replay.") and not case["ok"]]
        accepted = not missing and not extra and not failures and not replay_failures
        try:
            manifest = self.installed_manifest()
        except Exception as error:  # noqa: BLE001 - a missing install tree is a refusal
            manifest = {"error": str(error)}
            accepted = False
        result = {
            "package": "J23 reader application boundary fuzz",
            "accepted": accepted,
            "source_sha": source,
            "start_sha": "f43baf9182d75907c0cb5d6f77048f27bca8c950",
            "sdk_sha": "9854061be331fe603a1822d9b2b36ee357154927",
            "run_id": run_id,
            "attempt": attempt,
            "workflow": ".github/workflows/reader-app-boundary-fuzz.yml",
            "platform": "linux",
            "granted_platform": "linux",
            "toolchain": {"cc": "clang", "cxx": "clang++", "sanitizers": "address,undefined,leak"},
            "environment": environment,
            "limits": {
                "iterations": self.arguments.iterations,
                "time_budget_ms": self.arguments.budget_ms,
                "seed": self.arguments.seed,
            },
            "cases": self.cases,
            "checks": len(self.cases),
            "required_cases": list(REQUIRED_CASES),
            "missing_cases": missing,
            "unexpected_cases": extra,
            "failures": failures,
            "replay_failures": replay_failures,
            "fuzz": self.fuzz_runs,
            "replay": self.replays,
            "manifest": manifest,
            "notes": self.notes,
            "uncovered": [
                "Windows, macOS, iOS, Android and GTK hosts were not built or run",
                "no host UI, theme observer, product wiring or synchronization client was exercised",
                "no SDK document was loaded: encode cases use explicit public selector values only",
                "the frozen SDK, product schema1 and the wire/anchor contracts were not modified",
            ],
            "host_ui_accepted": False,
            "sync_accepted": False,
            "sdk_changed": False,
            "schema_changed": False,
            "complete_product": False,
        }
        (self.evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        (self.root / "summary.json").write_text(
            json.dumps(
                {
                    "accepted": accepted,
                    "checks": len(self.cases),
                    "failed": failures,
                    "missing": missing,
                    "unexpected": extra,
                    "source_sha": source,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"accepted": accepted, "checks": len(self.cases), "failures": failures}), flush=True)
        return 0 if accepted else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--c-consumer", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--installed-prefix", required=True)
    parser.add_argument("--sdk-prefix", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--budget-ms", type=int, default=DEFAULT_BUDGET_MS)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=DEFAULT_SEED)
    arguments = parser.parse_args()
    return Driver(arguments).run()


if __name__ == "__main__":
    raise SystemExit(main())
