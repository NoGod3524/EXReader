"""Run the frozen ten-case Android shelf on the owned native hardware emulator.

This is hardware qualification, with an older authenticated Release producer.
It does not satisfy the final same-source or reader-interaction gates.
"""
import argparse, ctypes, difflib, hashlib, importlib.util, json, os, re
import stat, struct, subprocess, sys, time, traceback, zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRODUCER = {"source_sha": "03ecfa21f6cd8d8e354145d56ffdf24244ecbe61",
            "run_id": "41240610450", "attempt": "1"}
ARTIFACT = {"id": 13056959967, "bytes": 42119480,
            "sha256": "791a2a412820cbc308292f0edec869bc3079504eccd3e5383582d007313982e7"}
APP = "org.exreader.host"
HELPER = APP + ".uitest"

def need(value, message):
    if not value: raise ValueError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def bundle():
    need(sys.platform == "win32" and os.environ.get("GITHUB_ACTIONS") != "true", "native Windows only")
    need(os.environ.get("COMPUTERNAME", "").upper() == "LAP25002", "named native host")
    value = load(ROOT / "bundle.json")
    need(value["kind"] == "native-local-source-bundle" and re.fullmatch(r"[0-9a-f]{40}", value["execution_source_sha"]), "source bundle")
    need(set(value["files"]) == {"tests/reader_f08_final_20261031/native_android.py",
         "tests/reader_f08_final_20261031/android-native-profile.json", "tools/run_reader_shelf_ui.py",
         "tests/reader_f08_android_20261031/lane.py"}, "complete source bundle")
    for name, digest in value["files"].items():
        p = PurePosixPath(name)
        need(not p.is_absolute() and ".." not in p.parts and sha(ROOT / name) == digest, "bundle file: " + name)
    return value

def display():
    # DEVMODEW is 220 bytes on Windows; read the native physical display mode.
    # No display-changing API is bound by this adapter.
    mode = ctypes.create_string_buffer(220)
    struct.pack_into("<H", mode, 68, 220)
    api = ctypes.WinDLL("user32", use_last_error=True).EnumDisplaySettingsW
    api.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    api.restype = ctypes.c_int
    need(api(None, 0xffffffff, mode), "native display query")
    return [struct.unpack_from("<I", mode, offset)[0] for offset in (172, 176, 184)]

def adb(plan, *args, check=True, timeout=45):
    command = [str(Path(plan["sdk"]) / "platform-tools/adb.exe"), "-s", plan["serial"], *map(str, args)]
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    need(not check or result.returncode == 0, "adb command failed: " + " ".join(map(str, args[:4])))
    return result.stdout.decode(errors="replace")

def profile_check(plan, out):
    profile = load(HERE / "android-native-profile.json")
    need(display() == profile["desktop_mode_before_and_after"], "desktop mode differs")
    (out / "avd-config.ini").write_bytes(Path(plan["avd_config"]).read_bytes())
    config = {}
    for line in Path(plan["avd_config"]).read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1); config[key.strip()] = value.strip()
    wanted = {"hw.cpu.ncore": "4", "hw.ramSize": "4096", "vm.heapSize": "512",
              "hw.lcd.width": "1080", "hw.lcd.height": "2400", "hw.lcd.density": "420",
              "hw.lcd.vsync": "60", "hw.gpu.enabled": "yes", "hw.gpu.mode": "host"}
    need(all(config.get(k) == v for k, v in wanted.items()), "frozen AVD configuration differs")
    need(re.fullmatch(r"emulator-[0-9]+", plan["serial"]), "owned emulator serial")
    avd_name = adb(plan, "emu", "avd", "name").splitlines()[0].strip()
    need(avd_name == Path(plan["avd_config"]).parent.name.removesuffix(".avd"), "AVD/serial identity")
    need(adb(plan, "shell", "getprop", "sys.boot_completed").strip() == "1", "boot incomplete")
    need(adb(plan, "shell", "getprop", "ro.build.version.sdk").strip() == "34", "API differs")
    need(adb(plan, "shell", "getprop", "ro.product.cpu.abi").strip() == "x86_64", "ABI differs")
    size = adb(plan, "shell", "wm", "size"); density = adb(plan, "shell", "wm", "density")
    (out / "virtual-size.txt").write_text(size, encoding="utf-8")
    (out / "virtual-density.txt").write_text(density, encoding="utf-8")
    need(size.strip() == "Physical size: 1080x2400" and density.strip() == "Physical density: 420", "virtual display differs")
    cpu_online = adb(plan, "shell", "cat", "/sys/devices/system/cpu/online").strip()
    need(cpu_online == "0-3", "guest CPU count")
    cpu = "4"
    heap = adb(plan, "shell", "getprop", "dalvik.vm.heapsize").strip()
    growth = adb(plan, "shell", "getprop", "dalvik.vm.heapgrowthlimit").strip()
    save(out / "guest-heap.json", {"requested_mib": 512, "heap": heap, "growth": growth})
    need(heap == "576m" and growth == "192m", "effective guest heap differs")
    surface = adb(plan, "shell", "dumpsys", "SurfaceFlinger")
    (out / "surfaceflinger.txt").write_text(surface, encoding="utf-8")
    renderer = [line.strip() for line in surface.splitlines() if "GLES:" in line]
    need(len(renderer) == 1 and re.search(r"Arc.*140V", renderer[0], re.I), "actual Arc hardware renderer missing")
    need(not re.search(r"swiftshader|llvmpipe|lavapipe|\bwarp\b|microsoft basic", renderer[0], re.I), "software renderer")
    animation = {}
    for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        adb(plan, "shell", "settings", "put", "global", key, "1")
        animation[key] = adb(plan, "shell", "settings", "get", "global", key).strip()
        need(float(animation[key]) == 1, "animation profile")
    for name, value in {"surfaceflinger.txt": surface, "virtual-size.txt": size, "virtual-density.txt": density,
                        "getprop.txt": adb(plan, "shell", "getprop"), "meminfo.txt": adb(plan, "shell", "cat", "/proc/meminfo")}.items():
        (out / name).write_text(value, encoding="utf-8")
    save(out / "native-profile.json", {"profile_sha256": sha(HERE / "android-native-profile.json"),
         "avd_name": avd_name, "avd_config_sha256": sha(plan["avd_config"]), "config": config,
         "renderer": renderer[0], "animation": animation, "guest_cpus": int(cpu), "effective_heap": heap, "growth_limit": growth, "desktop": display()})

def prepare(archive, out):
    need(archive.stat().st_size == ARTIFACT["bytes"] and sha(archive) == ARTIFACT["sha256"], "authenticated Release ZIP")
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist(); seen = set()
        need(0 < len(infos) < 20000 and sum(i.file_size for i in infos) < 2 * 1024**3, "ZIP bounds")
        for info in infos:
            p = PurePosixPath(info.filename); key = str(p).casefold()
            need(str(p) != "." and not p.is_absolute() and ".." not in p.parts and "\\" not in info.filename
                 and ":" not in info.filename and key not in seen, "ZIP path")
            need(not info.flag_bits & 1 and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFDIR, stat.S_IFREG), "ZIP kind")
            seen.add(key)
        manifest = json.loads(z.read("manifest.json"))
        need(all(manifest.get(k) == v for k, v in PRODUCER.items()), "producer identity")
        need({i.filename for i in infos if not i.is_dir()} == set(manifest["files"]) | {"manifest.json"}, "complete ZIP inventory")
        for name, item in manifest["files"].items():
            payload = z.read(name)
            need(len(payload) == item["bytes"] and hashlib.sha256(payload).hexdigest() == item["sha256"], "ZIP entry: " + name)
        built = json.loads(z.read("build.json"))
        need(all(built.get(k) == v for k, v in PRODUCER.items()) and built["debug"] is False
             and built["configuration"] == "Release" and built["sdk_version"] == "3.42.0" and built["page_theme"] is True,
             "complete-feature optimized Release")
        need(sha(ROOT / "tools/run_reader_shelf_ui.py") == built["frozen_sampler_files"]["tools/run_reader_shelf_ui.py"], "frozen sampler")
        for name, item in built["packages"].items():
            payload = z.read("packages/" + name)
            need(len(payload) == item["bytes"] and hashlib.sha256(payload).hexdigest() == item["sha256"], "compiled APK")
            path = (ROOT / "examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
                    if name == "app-debug-androidTest.apk" else ROOT / "build/android-host/artifacts" / name)
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(payload)
        badging = z.read("release-apk-badging.txt")
        need(hashlib.sha256(badging).hexdigest() == built["release_badging_sha256"]
             and b"application-debuggable" not in badging, "Release manifest flags")
        with zipfile.ZipFile(ROOT / "build/android-host/artifacts/app-debug.apk") as app:
            need(b"Java_org_exreader_host_ProductFixture_" not in app.read("lib/x86_64/libexreader_product.so"), "private fixture JNI")
        fixture = ("Independent Android ownership and cancellation review.\n" * 200).encode()
        expected = json.loads(z.read("fixtures.json"))["NewReview.txt"]
        need(len(fixture) == expected["size"] and hashlib.sha256(fixture).hexdigest() == expected["sha256"], "original picker fixture")
        path = ROOT / "build/android-host/fixtures/NewReview.txt"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(fixture)
        save(out / "producer.json", {"artifact": ARTIFACT, "producer": PRODUCER, "build": built,
             "authenticated_zip_payloads": len(manifest["files"]), "qualification_only": True})

def sampler(plan, out=None):
    source = (ROOT / "tools/run_reader_shelf_ui.py").read_text(encoding="utf-8")
    original_identity = "identity={'source_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),'attempt':os.environ.get('GITHUB_RUN_ATTEMPT')}"
    original_guard = "require(os.environ.get('GITHUB_ACTIONS')=='true' and identity['source_sha'],'cloud-only shelf execution')"
    need(source.count(original_identity) == source.count(original_guard) == 1, "exact identity/entry adapter")
    adapted = source.replace(original_identity, "identity=_native_identity()")
    adapted = adapted.replace(original_guard, "require(_native_admitted(),'native-local shelf admission')")
    if out:
        (out / "entry-adapter.diff").write_text("".join(difflib.unified_diff(source.splitlines(True), adapted.splitlines(True))), encoding="utf-8")
    namespace = {"__name__": "f08_native_frozen_sampler", "__file__": str(ROOT / "tools/run_reader_shelf_ui.py"),
                 "_native_identity": lambda: dict(plan["identity"]),
                 "_native_admitted": lambda: bool(bundle()) and display() == [1920, 1200, 60]}
    exec(compile(adapted, namespace["__file__"], "exec"), namespace)
    return namespace

def worker(plan_path):
    plan = load(plan_path); bundle()
    os.chdir(ROOT)
    os.environ["ANDROID_SERIAL"] = plan["serial"]
    os.environ["PATH"] = str(Path(plan["sdk"]) / "platform-tools") + os.pathsep + os.environ["PATH"]
    sys.argv = ["run_reader_shelf_ui.py", "--output", str(Path(plan["output"]) / "execution")]
    sampler(plan, Path(plan["output"]))["main"]()

def collect_terminal_state(plan, out):
    errors = []
    for name, query in {
        "terminal-power.txt": ["dumpsys", "power"],
        "terminal-display.txt": ["dumpsys", "display"],
        "terminal-input.txt": ["dumpsys", "input"],
        "terminal-window.txt": ["dumpsys", "window", "windows"],
        "terminal-surfaceflinger.txt": ["dumpsys", "SurfaceFlinger"],
    }.items():
        try:
            (out / name).write_text(adb(plan, "shell", *query, timeout=8), encoding="utf-8")
        except Exception as error:
            errors.append({"file": name, "error": repr(error)})
    installed = out / "installed.apk"
    try:
        paths = [p.removeprefix("package:") for p in adb(plan, "shell", "pm", "path", APP).splitlines()
                 if p.startswith("package:")]
        need(len(paths) == 1, "installed package path")
        adb(plan, "pull", paths[0], installed)
        actual = sha(installed)
        expected = load(out / "producer.json")["build"]["packages"]["app-debug.apk"]["sha256"]
        save(out / "installed-identity.json", {"package_path": paths[0], "sha256": actual,
             "producer_sha256": expected, "matches_producer": actual == expected})
        if actual != expected:
            errors.append({"file": "installed.apk", "error": "installed bytes differ from producer"})
    except Exception as error:
        errors.append({"file": "installed.apk", "error": repr(error)})
    save(out / "terminal-collection.json", {"errors": errors})
    return errors

def descriptive(out):
    # This report never promotes partial UI execution to acceptance.
    frozen = sampler(load(out / "plan.json"))
    ui_path = out / "execution/ui/validation.json"
    ui = load(ui_path) if ui_path.exists() else {}
    rows, windows, capture_records = [], [], []
    for path in sorted((out / "execution/windows").glob("*.jsonl")):
        data = path.read_bytes()
        need(data.endswith(b"\n"), "truncated native Window trace")
        events = [json.loads(line) for line in data.splitlines()]
        header = events[0]
        need(header["kind"] == "start", "native Window header")
        frames = [r for r in events[1:] if r["kind"] == "frame"]
        need(all(r["pid"] == header["pid"] and r["window_id"] == header["window_id"]
                 and r["sequence"] == i + 1 and type(r["total_ns"]) is int and r["total_ns"] >= 0
                 for i, r in enumerate(frames)), "native frame identity/sequence")
        capture_records.extend(r for r in events[1:] if r.get("kind") not in ("frame", "stop"))
        rows.extend(frames)
        windows.append({"file": path.name, "callbacks": len(frames),
                        "closed_cleanly": events[-1]["kind"] == "stop", "sha256": sha(path)})
    ordinary = [r for r in rows if r["first_draw"] == 0]
    segments = [{**interval, "completed_frame_ms": frozen["summarize"]([
        r["total_ns"] / 1e6 for r in ordinary
        if interval["started_elapsed_ns"] <= r["callback_elapsed_ns"] <= interval["finished_elapsed_ns"]])}
        for interval in ui.get("intervals", [])]
    pss_path = out / "execution/pss-sampling.json"
    pss = load(pss_path) if pss_path.exists() else {"samples": [], "errors": ["missing PSS summary"]}
    valid = []
    pss_errors = list(pss["errors"])
    for record in pss["samples"]:
        if record.get("total_pss_kib") is None:
            continue
        try:
            raw = (out / "execution/pss" / (str(record["slot"]) + ".txt")).read_text()
            need(frozen["pss_total"](raw, record["pid"]) == record["total_pss_kib"], "raw PSS differs")
            need(not record.get("process_changed_during_sample"), "PSS process changed")
            valid.append(record["total_pss_kib"])
        except Exception as error:
            pss_errors.append({"slot": record["slot"], "error": repr(error)})
    screenshots = []
    from PIL import Image
    for path in sorted((out / "execution/ui/shots").glob("*.png")):
        with Image.open(path) as image:
            size = list(image.size); extrema = image.convert("RGB").getextrema()
        screenshots.append({"file": path.name, "sha256": sha(path), "size": size,
                            "nonuniform": any(low != high for low, high in extrema)})
    cases = ui.get("cases", [])
    first = next((c.get("detail", {}).get("observation", {}).get("first_interactive_ms")
                  for c in cases if c.get("id") == "first_interactive_real_catalog"), None)
    return {"sampling_identity": load(out / "plan.json")["identity"],
            "ui_passed": ui.get("passed"), "ui_failed": ui.get("failed"), "ui_skipped": ui.get("skipped"),
            "first_interactive_ms": first, "all_callbacks": frozen["summarize"]([r["total_ns"] / 1e6 for r in rows]),
            "ordinary_callbacks": frozen["summarize"]([r["total_ns"] / 1e6 for r in ordinary]),
            "callback_drops": sum(r["drop_count"] for r in rows), "windows": windows, "segments": segments,
            "sampled_peak_pss_kib": max(valid, default=None), "valid_pss_samples": len(valid),
            "pss_collection_errors": pss_errors, "other_capture_records": capture_records,
            "unknown_first_draw": sum(r["first_draw"] not in (0, 1) for r in rows), "screenshots": screenshots,
            "all_case_screenshots_nonuniform": len(screenshots) == 10 and all(r["nonuniform"] for r in screenshots),
            "native_frame_census_proven": False, "partial_diagnostics_only": True, "f08_accepted": False}

def replay(out):
    plan = load(out / "plan.json"); current = bundle()
    need(current["execution_source_sha"] == plan["execution_source_sha"], "execution source differs")
    need(load(out / "native-profile.json")["profile_sha256"] == sha(HERE / "android-native-profile.json"), "measured profile differs")
    namespace = sampler(plan)
    installed = load(out / "installed-identity.json")
    need(installed["matches_producer"] and sha(out / "installed.apk") == installed["producer_sha256"], "installed product identity")
    need(descriptive(out)["all_case_screenshots_nonuniform"], "visible case content missing")
    analyzed = namespace["analyze"](out / "execution", plan["identity"])
    recorded = load(out / "execution/result.json")
    need(recorded["accepted"] and not recorded["problems"] and all(recorded.get(k) == v for k, v in analyzed.items()), "independent original replay")
    spec = importlib.util.spec_from_file_location("f08_frozen_budget", ROOT / "tests/reader_f08_android_20261031/lane.py")
    lane = importlib.util.module_from_spec(spec); spec.loader.exec_module(lane)
    evaluation = lane.evaluate(recorded, load(HERE / "android-native-profile.json"))
    return {"execution": "native-local", "identity": plan["identity"], "execution_source_sha": plan["execution_source_sha"],
            "producer": PRODUCER, "artifact": ARTIFACT, "original_analysis": analyzed, "evaluation": evaluation,
            "scope": "native hardware qualification of the unchanged ten shelf UI cases", "same_source_final_acceptance": False,
            "f08_accepted": False}

def run(args):
    code = bundle(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    plan = {"output": str(out), "sdk": str(args.sdk.resolve()), "serial": args.serial,
            "avd_config": str(args.avd_config.resolve()), "input_archive": str(args.archive.resolve()), "execution_source_sha": code["execution_source_sha"],
            "identity": {"source_sha": PRODUCER["source_sha"], "run_id": "native-lap25002-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), "attempt": "1"}}
    save(out / "plan.json", plan)
    before = display(); errors = []; process = None; measured = None
    try:
        from PIL import Image
        prepare(args.archive.resolve(), out); profile_check(plan, out)
        # Each cloud run used a fresh AVD. Clear only the owned test helper's
        # retained output before reusing the native AVD; original APP clearing
        # and the seed path remain inside the unchanged frozen sampler.
        if adb(plan, "shell", "pm", "path", HELPER, check=False).strip():
            clear = adb(plan, "shell", "pm", "clear", HELPER)
            (out / "clear-helper-before-sample.txt").write_text(clear, encoding="utf-8")
            need(clear.strip() == "Success", "fresh helper output")
        with (out / "worker.log").open("wb") as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "worker", "--plan", str(out / "plan.json")], stdout=log, stderr=subprocess.STDOUT)
            try: code = process.wait(timeout=1100)
            except subprocess.TimeoutExpired:
                errors.append("native sampling exceeded 1100 seconds")
                for package in (HELPER, APP): adb(plan, "shell", "am", "force-stop", package, check=False)
                try: code = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill(); code = process.wait(timeout=10)
        collection_errors = collect_terminal_state(plan, out)
        diagnostics = descriptive(out)
        save(out / "descriptive-diagnostics.json", diagnostics)
        need(code == 0 and not errors, "original native sampler failed")
        need(not collection_errors, "terminal evidence incomplete")
        need(diagnostics["all_case_screenshots_nonuniform"], "missing visible case content")
        measured = replay(out); save(out / "qualification.json", measured)
    except BaseException:
        errors.append(traceback.format_exc()); raise
    finally:
        cleanup = {}
        for package in (HELPER, APP):
            try:
                adb(plan, "shell", "am", "force-stop", package, check=False, timeout=10)
                cleanup[package] = adb(plan, "shell", "pidof", package, check=False, timeout=10).strip()
            except Exception as error:
                cleanup[package] = repr(error)
        save(out / "owned-process-cleanup.json", cleanup)
        after = display()
        save(out / "native-result.json", {"plan": plan, "display_before": before, "display_after": after,
             "display_unchanged": before == after == [1920, 1200, 60], "errors": errors,
             "collection_complete": measured is not None and not errors,
             "shelf_budget_accepted": bool(measured and measured["evaluation"]["shelf_budget_accepted"]),
             "f08_accepted": False})
        save(out / "manifest.json", {"execution": "native-local", "identity": plan["identity"], "files": {
             p.relative_to(out).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size}
             for p in sorted(out.rglob("*")) if p.is_file() and p != out / "manifest.json"}, "f08_accepted": False})
    need(before == after == [1920, 1200, 60], "desktop mode changed")
    need(all(not value for value in cleanup.values()), "owned Android processes remain")
    print(json.dumps({"output": str(out), "evaluation": measured["evaluation"], "f08_accepted": False}), flush=True)
    need(measured["evaluation"]["shelf_budget_accepted"], "native shelf budget exceeded")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("sample", "worker", "audit"))
    for name in ("archive", "sdk", "avd-config", "output", "plan"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--serial")
    args = parser.parse_args()
    if args.mode == "worker": worker(args.plan)
    elif args.mode == "audit":
        manifest = load(args.output / "manifest.json")
        actual = {p.relative_to(args.output).as_posix() for p in args.output.rglob("*") if p.is_file() and p != args.output / "manifest.json"}
        need(actual == set(manifest["files"]), "complete native inventory")
        for name, item in manifest["files"].items():
            need(sha(args.output / name) == item["sha256"] and (args.output / name).stat().st_size == item["bytes"], "native payload: " + name)
        need(replay(args.output) == load(args.output / "qualification.json"), "native qualification replay")
        print(json.dumps({"authenticated": True, "result": load(args.output / "qualification.json")}))
    else: run(args)

if __name__ == "__main__": main()
