"""Run the frozen ten-case Android shelf on the owned native hardware emulator.

New sampling requires an explicit same-source CI receipt and the exact eight-source bundle.
Read-only legacy replay preserves the older producer meaning. Full reader/census gates remain separate.
"""
import argparse, ctypes, difflib, hashlib, importlib.util, json, os, re
import stat, struct, subprocess, sys, time, traceback, zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LEGACY_PRODUCER = {"source_sha": "03ecfa21f6cd8d8e354145d56ffdf24244ecbe61",
            "run_id": "41240610450", "attempt": "1"}
LEGACY_ARTIFACT = {"id": 13056959967, "bytes": 42119480,
            "sha256": "791a2a412820cbc308292f0edec869bc3079504eccd3e5383582d007313982e7"}
BUNDLE_FILES=(
    'tests/reader_f08_final_20261031/native_android.py',
    'tests/reader_f08_final_20261031/android-native-profile.json',
    'tools/run_reader_shelf_ui.py',
    'tests/reader_f08_android_20261031/lane.py',
    'tests/reader_f08_final_20261031/android.py',
    'tests/reader_f08_final_20261031/source.py',
    'tests/reader_f08_final_20261031/contract.json',
    'tests/reader_f08_android_binding_20261031/audit.py',
)
PACKAGES=("app-debug.apk","app-debug-androidTest.apk","uitest-debug.apk","uitest-debug-androidTest.apk")
REPOSITORY="NoGod3524/EXReader"
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
    need(set(value["files"]) == set(BUNDLE_FILES), "complete eight-source bundle")
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

def adb(plan, *args, check=True, timeout=45, raw=False):
    command = [str(Path(plan["sdk"]) / "platform-tools/adb.exe"), "-s", plan["serial"], *map(str, args)]
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    need(not check or result.returncode == 0, "adb command failed: " + " ".join(map(str, args[:4])))
    return result if raw else result.stdout.decode(errors="replace")

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

def producer_receipt(receipt, expected_source):
    need(re.fullmatch(r"[0-9a-f]{40}", expected_source or ""), "explicit expected source")
    need(receipt["repository_full_name"] == REPOSITORY, "receipt repository")
    artifact, run = receipt["artifact"], receipt["run"]
    repo = run["repository"]
    need(repo["full_name"] == REPOSITORY and type(repo["id"]) is int and repo["id"] > 0, "run repository")
    origin = artifact["workflow_run"]
    need(origin["repository_id"] == origin["head_repository_id"] == repo["id"], "artifact repository")
    need(run["head_sha"] == origin["head_sha"] == expected_source, "expected source differs from CI")
    need(type(run["id"]) is int and run["id"] > 0 and origin["id"] == run["id"], "CI run identity")
    need(type(run["run_attempt"]) is int and run["run_attempt"] > 0, "CI attempt")
    need(type(artifact["id"]) is int and artifact["id"] > 0 and artifact["expired"] is False
         and type(artifact["size_in_bytes"]) is int and artifact["size_in_bytes"] > 0, "CI artifact identity")
    need(re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["digest"]), "CI artifact digest")
    return ({"source_sha": expected_source, "run_id": str(run["id"]), "attempt": str(run["run_attempt"])},
            {"id": artifact["id"], "name": artifact["name"], "bytes": artifact["size_in_bytes"],
             "sha256": artifact["digest"].removeprefix("sha256:")})


def prepare(archive, out, expected_source, receipt, code):
    producer, artifact = producer_receipt(receipt, expected_source)
    need(code["execution_source_sha"] == expected_source and set(code["files"]) == set(BUNDLE_FILES), "same-source execution bundle")
    need(archive.stat().st_size == artifact["bytes"] and sha(archive) == artifact["sha256"], "authenticated Release ZIP")
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
        need(all(manifest.get(k) == v for k, v in producer.items()) and manifest["f08_accepted"] is False, "producer identity")
        need({i.filename for i in infos if not i.is_dir()} == set(manifest["files"]) | {"manifest.json"}, "complete ZIP inventory")
        for name, item in manifest["files"].items():
            payload = z.read(name)
            need(len(payload) == item["bytes"] and hashlib.sha256(payload).hexdigest() == item["sha256"], "ZIP entry: " + name)
        built = json.loads(z.read("build.json")); final = json.loads(z.read("final-build.json")); source = json.loads(z.read("final-source.json"))
        need(all(built.get(k) == final.get(k) == source.get(k) == v for k, v in producer.items()), "same-source build identity")
        need(built["debug"] is False and built["configuration"] == "Release" and built["sdk_version"] == "3.42.0"
             and built["page_theme"] is True and built["release_fixture_jni_absent"] is True, "complete-feature optimized Release")
        required = {"-PexrSync=true", "-PexrSearch=true", "-PexrNavigation=true", "-PexrReading=true",
                    "-PexrPreferences=true", "-PexrPageTheme=true", "-PexrF08Review=true", "-PexrSelectorBytes=true", "-PexrWave3=true"}
        need(required <= set(built["gradle_flags"]), "frozen full-feature flags")
        need(final["source"] == source and final["packages"] == built["packages"]
             and final["original_build_sha256"] == hashlib.sha256(z.read("build.json")).hexdigest()
             and final["debug"] is False and final["measurement_performed"] is False and final["f08_accepted"] is False, "final build admission")
        contract = load(HERE / "contract.json")
        need(source["reviewed_source"] == contract["reviewed_source"] and source["contract_sha256"] == sha(HERE / "contract.json"), "reviewed contract")
        need(all(p.startswith(contract["allowed_test_prefix"]) or p == contract["allowed_workflow"] for p in source["changed"]), "unreviewed build source")
        need(json.loads(z.read("native-source/bundle.json")) == code and final["native_bundle_files"] == code["files"], "exact compiled native bundle")
        for name, digest in code["files"].items():
            need(sha(ROOT / name) == digest and hashlib.sha256(z.read("native-source/" + name)).hexdigest() == digest, "compiled bundle file: " + name)
            if name.startswith(contract["allowed_test_prefix"]):need(source["adapter_files"].get(name) == digest, "admitted native source: " + name)
        observer = {"examples/android/app/src/main/java/org/exreader/host/" + name for name in
                    ("CatalogFrameLatch.java", "CatalogShelf.java", "MainActivity.java", "ShelfWindowMetrics.java")}
        need(set(final["observer_source_sha256"]) == observer and all(re.fullmatch(r"[0-9a-f]{64}", v)
             for v in final["observer_source_sha256"].values()), "complete observer source identity")
        need(final["final_adapter_sha256"] == sha(HERE / "android.py"), "compiled final build adapter")
        need(sha(ROOT / "tools/run_reader_shelf_ui.py") == built["frozen_sampler_files"]["tools/run_reader_shelf_ui.py"], "frozen sampler")
        need(set(built["packages"]) == set(PACKAGES), "exact four compiled APKs")
        packages = {}
        for name, item in built["packages"].items():
            payload = z.read("packages/" + name)
            need(len(payload) == item["bytes"] and hashlib.sha256(payload).hexdigest() == item["sha256"], "compiled APK")
            packages[name] = payload
        badging = z.read("release-apk-badging.txt")
        need(hashlib.sha256(badging).hexdigest() == built["release_badging_sha256"]
             and b"application-debuggable" not in badging, "Release manifest flags")
        import io
        with zipfile.ZipFile(io.BytesIO(packages["app-debug.apk"])) as app:
            need(b"Java_org_exreader_host_ProductFixture_" not in app.read("lib/x86_64/libexreader_product.so"), "private fixture JNI")
            dex = [app.read(n) for n in app.namelist() if n.startswith("classes") and n.endswith(".dex")]
        markers = ("Lorg/exreader/host/CatalogFrameLatch;", "Lorg/exreader/host/ShelfWindowMetrics;",
                   "catalogApplied", "catalogReady", "catalogTreeDraw", "ready_pre_draw", "tree_draw_begin", "catalog-ready")
        need(set(final["observer_dex_markers"]) == set(markers) and all(final["observer_dex_markers"].values())
             and all(any(marker.encode("ascii") in data for data in dex) for marker in markers), "compiled first-catalog observer")
        fixture = z.read("fixtures/NewReview.txt"); expected = json.loads(z.read("fixtures.json"))["NewReview.txt"]
        need(final["picker_fixture"] == {"path": "fixtures/NewReview.txt", **expected}
             and len(fixture) == expected["size"] and hashlib.sha256(fixture).hexdigest() == expected["sha256"], "original picker fixture")
        # All validation precedes staging. Never borrow an APK or fixture from an older run.
        for name, payload in packages.items():
            path = (ROOT / "examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
                    if name == "app-debug-androidTest.apk" else ROOT / "build/android-host/artifacts" / name)
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(payload)
        path = ROOT / "build/android-host/fixtures/NewReview.txt"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(fixture)
        save(out / "producer-receipt.json", receipt)
        save(out / "producer.json", {"artifact": artifact, "producer": producer, "build": built,
             "final_build": final, "final_source": source, "authenticated_zip_payloads": len(manifest["files"]),
             "same_source_build": True, "qualification_only": True})


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
    plan = load(plan_path); current = bundle()
    need(plan["expected_source"] == plan["execution_source_sha"] == current["execution_source_sha"] == plan["identity"]["source_sha"], "worker same-source admission")
    proof = load(Path(plan["output"]) / "producer.json")
    producer, artifact = producer_receipt(load(Path(plan["output"]) / "producer-receipt.json"), plan["expected_source"])
    need(proof["producer"] == plan["producer"] == producer and proof["artifact"] == plan["artifact"] == artifact, "worker producer identity")
    for name, item in proof["build"]["packages"].items():
        path = (ROOT / "examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
                if name == "app-debug-androidTest.apk" else ROOT / "build/android-host/artifacts" / name)
        need(sha(path) == item["sha256"] and path.stat().st_size == item["bytes"], "staged APK differs: " + name)
    fixture = ROOT / "build/android-host/fixtures/NewReview.txt"
    need(sha(fixture) == proof["final_build"]["picker_fixture"]["sha256"], "staged picker fixture differs")
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

def original_cold_start(out, windows):
    # The frozen analyze() budgets only case 0's fixed first-interactive timestamp.
    result = {"case_id": "first_interactive_real_catalog", "binding_complete": False, "errors": [],
              "tti_upper_ms": None, "tti_upper_budget_passed": None, "original_tti_budget_ms": 2000,
              "name": "original cold-start Window-frame completion upper bound", "f08_accepted": False}
    try:
        case = load(out / "execution/ui/first_interactive_real_catalog.json")
        identity = load(out / "plan.json")["identity"]
        need(case["id"] == result["case_id"] and all(case.get(k) == v for k, v in identity.items()), "original case 0 identity")
        observation = case["detail"]["observation"]
        start = observation["activity_started_elapsed_ns"]; first = observation["first_interactive_elapsed_ns"]
        need(type(start) is int and start > 0 and type(first) is int and first >= start, "original first-interactive elapsed timestamps")
        need(type(observation["first_interactive_ms"]) in (int, float)
             and observation["first_interactive_ms"] == (first-start)/1e6, "original first-interactive ms definition")
        candidates = []
        for window in windows:
            path = out / "execution/windows/catalog-ready" / window["file"]
            try:
                header = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            except (OSError, ValueError, IndexError):
                continue  # Incomplete other lifecycle files remain in the full audit.
            if header.get("kind") == "start" and header.get("activity_started_elapsed_ns") == start:
                candidates.append((window, path))
        need(len(candidates) == 1, "missing/duplicate original cold-start Window")
        window, path = candidates[0]; result["file"] = window["file"]
        need(window["binding_complete"], "original cold-start association missing: " + "; ".join(window["errors"]))
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        ready = [row for row in rows if row.get("kind") == "ready_pre_draw"]
        need(len(ready) == 1 and ready[0]["elapsed_ns"] == first, "original fixed first-interactive/pre-draw differs")
        result.update(window, errors=[], name=result["name"], case_id=case["id"], activity_started_elapsed_ns=start,
                      original_first_interactive_elapsed_ns=first, original_first_interactive_ms=observation["first_interactive_ms"])
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        result["errors"].append(str(error))
    return result


def catalog_completion(out):
    spec = importlib.util.spec_from_file_location("f08_catalog_completion", ROOT / "tests/reader_f08_android_binding_20261031/audit.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    value = module.audit_directory(out / "execution/windows")
    value["original_cold_start"] = original_cold_start(out, value["windows"])
    return value


def authenticate_native(out):
    manifest = load(out / "manifest.json")
    actual = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() and p != out / "manifest.json"}
    need(actual == set(manifest["files"]), "complete native inventory")
    for name, item in manifest["files"].items():
        need(sha(out / name) == item["sha256"] and (out / name).stat().st_size == item["bytes"], "native payload: " + name)
    need(manifest["identity"] == load(out / "plan.json")["identity"], "native manifest identity")
    return manifest


def replay(out):
    plan = load(out / "plan.json"); current = bundle()
    need(current["execution_source_sha"] == plan["execution_source_sha"] == plan["expected_source"] == plan["identity"]["source_sha"], "execution/build source differs")
    producer, artifact = producer_receipt(load(out / "producer-receipt.json"), plan["expected_source"])
    proof = load(out / "producer.json")
    need(producer == plan["producer"] == proof["producer"] and artifact == plan["artifact"] == proof["artifact"], "same-source producer receipt")
    need(current["files"] == proof["final_build"]["native_bundle_files"], "replay bundle differs from compiled bundle")
    need(load(out / "native-profile.json")["profile_sha256"] == sha(HERE / "android-native-profile.json"), "measured profile differs")
    namespace = sampler(plan)
    installed = load(out / "installed-identity.json")
    need(installed["matches_producer"] and sha(out / "installed.apk") == installed["producer_sha256"]
         == proof["build"]["packages"]["app-debug.apk"]["sha256"], "installed product identity")
    need(descriptive(out)["all_case_screenshots_nonuniform"], "visible case content missing")
    analyzed = namespace["analyze"](out / "execution", plan["identity"])
    recorded = load(out / "execution/result.json")
    need(recorded["accepted"] and not recorded["problems"] and all(recorded.get(k) == v for k, v in analyzed.items()), "independent original replay")
    spec = importlib.util.spec_from_file_location("f08_frozen_budget", ROOT / "tests/reader_f08_android_20261031/lane.py")
    lane = importlib.util.module_from_spec(spec); spec.loader.exec_module(lane)
    original_evaluation = lane.evaluate(recorded, load(HERE / "android-native-profile.json"))
    completion = catalog_completion(out)
    need(completion == load(out / "catalog-completion.json"), "independent catalog completion replay")
    cold_start = completion["original_cold_start"]
    need(cold_start["binding_complete"], "original cold-start Window-frame completion association missing")
    upper_passed = cold_start["tti_upper_budget_passed"] is True
    evaluation = {**original_evaluation, "original_shelf_budget_accepted": original_evaluation["shelf_budget_accepted"],
                  "initial_cold_window_completion_upper_budget_passed": upper_passed,
                  "shelf_budget_accepted": original_evaluation["shelf_budget_accepted"] and upper_passed}
    return {"execution": "native-local", "identity": plan["identity"], "execution_source_sha": plan["execution_source_sha"],
            "producer": producer, "artifact": artifact, "original_analysis": analyzed, "evaluation": evaluation,
            "catalog_completion": completion, "same_source_build": True,
            "scope": "same-source original ten shelf UI cases with separate Window-frame completion upper bounds",
            "same_source_final_acceptance": False, "f08_accepted": False}


def replay_legacy(out):
    """Read only: retain the old producer/source and replay its original failure, without new acceptance."""
    authenticate_native(out)
    plan = load(out / "plan.json"); proof = load(out / "producer.json")
    need(proof["producer"] == LEGACY_PRODUCER and proof["artifact"] == LEGACY_ARTIFACT
         and plan["identity"]["source_sha"] == LEGACY_PRODUCER["source_sha"], "legacy producer identity")
    need(sha(ROOT / "tools/run_reader_shelf_ui.py") == proof["build"]["frozen_sampler_files"]["tools/run_reader_shelf_ui.py"], "legacy sampler differs")
    original, rejection = None, None
    try:
        original = sampler(plan)["analyze"](out / "execution", plan["identity"])
    except Exception as error:
        rejection = type(error).__name__ + ": " + str(error)
    return {"read_only_legacy_replay": True, "producer": LEGACY_PRODUCER, "artifact": LEGACY_ARTIFACT,
            "legacy_execution_source_sha": plan["execution_source_sha"], "identity": plan["identity"],
            "original_analysis": original, "original_analysis_rejection": rejection,
            "original_native_result": load(out / "native-result.json"), "diagnostics": descriptive(out),
            "same_source_build": False, "same_source_final_acceptance": False, "f08_accepted": False}


def fresh_owned_packages(plan, out):
    # Future authorized sampling only. All four APKs use this CI run's certificate.
    # Remove only these test-owned packages; the unchanged sampler then installs and seeds anew.
    records = []
    for package in (APP + ".test", HELPER + ".test", HELPER, APP):
        record = {"package": package, "previous_path": adb(plan, "shell", "pm", "path", package, check=False).strip()}
        if record["previous_path"]:
            result = adb(plan, "uninstall", package, check=False, raw=True)
            record.update(returncode=result.returncode, stdout=result.stdout.decode(errors="replace"), stderr=result.stderr.decode(errors="replace"))
            records.append(record); save(out / "fresh-owned-packages.json", records)
            need(result.returncode == 0 and record["stdout"].strip() == "Success", "fresh same-certificate package install")
        else:
            records.append(record); save(out / "fresh-owned-packages.json", records)


def run(args):
    code = bundle()
    receipt = load(args.producer_receipt); producer, artifact = producer_receipt(receipt, args.expected_source)
    need(code["execution_source_sha"] == args.expected_source, "native bundle differs from expected CI source")
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    plan = {"output": str(out), "sdk": str(args.sdk.resolve()), "serial": args.serial,
            "expected_source": args.expected_source, "producer": producer, "artifact": artifact,
            "avd_config": str(args.avd_config.resolve()), "input_archive": str(args.archive.resolve()), "execution_source_sha": code["execution_source_sha"],
            "identity": {"source_sha": args.expected_source, "run_id": "native-lap25002-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), "attempt": "1"}}
    save(out / "plan.json", plan)
    save(out / "producer-receipt.json", receipt)
    before = display(); errors = []; process = None; measured = None
    try:
        from PIL import Image
        prepare(args.archive.resolve(), out, args.expected_source, receipt, code); profile_check(plan, out)
        fresh_owned_packages(plan, out)
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
        save(out / "catalog-completion.json", catalog_completion(out))
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
    parser.add_argument("mode", choices=("sample", "worker", "audit", "audit-legacy"))
    for name in ("archive", "sdk", "avd-config", "output", "plan", "producer-receipt"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--serial")
    parser.add_argument("--expected-source", help="Explicit unified CI Git SHA; never inferred from the ZIP")
    args = parser.parse_args()
    if args.mode == "worker": worker(args.plan)
    elif args.mode == "audit":
        authenticate_native(args.output)
        need(replay(args.output) == load(args.output / "qualification.json"), "native qualification replay")
        print(json.dumps({"authenticated": True, "result": load(args.output / "qualification.json")}))
    elif args.mode == "audit-legacy":
        print(json.dumps(replay_legacy(args.output)))
    else:
        need(all(getattr(args, key) is not None for key in ("archive", "sdk", "avd_config", "output", "serial", "expected_source", "producer_receipt")), "sample requires explicit expected-source and producer-receipt plus device arguments")
        run(args)

if __name__ == "__main__": main()
