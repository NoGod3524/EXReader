#!/usr/bin/env python3
"""Prepare/run F04 test adapters in Actions. Never edit the retained source files.

Existing original drivers remain immutable. The generated copies preserve every
original check and add record exchange probes; all substitutions fail closed.
This module does not dispatch a workflow or spend a CI authorization.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "build/f04-driver"
BASE = "94fb236a4a2da87dfbaf4f1dd2a47885d615a230"

def replace_once(source, before, after):
    assert source.count(before) == 1, ("adapter source drift", before)
    return source.replace(before, after, 1)

def retained(path):
    old = subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT)
    actual = (ROOT / path).read_bytes()
    assert old == actual, "retained original driver changed: " + path
    return actual.decode("utf-8")

def stage_apple(target='iphone', generic=False):
    source = retained("tests/apple_android_relay/apple/run.py")
    source = replace_once(source, "ROOT = Path(__file__).resolve().parents[3]", "ROOT = Path(" + repr(str(ROOT)) + ")")
    source = replace_once(source, "sys.path.insert(0, str(ROOT / 'tests/apple_android_relay'))",
                          "sys.path.insert(0, " + repr(str(HERE)) + ")")
    source = replace_once(source, "('position', 'uploaded')",
                          "('position', 'uploaded', 'created-records', 'incoming-bookmark', 'incoming-note', 'edited-records')")
    source = replace_once(source, "from relay import start, save",
                          "from relay import start, save, untrust_desktop, finish_cleanup")
    before = """    finally:
        if controller: controller.shutdown(); controller.server_close()
        if dav:
            (out / 'requests.json').write_text(json.dumps(dav.requests, indent=2))
            dav.server.shutdown(); dav.server.server_close()
        (out / 'result.json').write_text(json.dumps(data, indent=2))"""
    after = """    finally:
        actions = []
        if controller:
            actions.extend([('stop-controller', controller.shutdown), ('close-controller', controller.server_close)])
        if dav:
            actions.extend([
                ('save-requests', lambda: (out / 'requests.json').write_text(json.dumps(dav.requests, indent=2))),
                ('stop-fixture', dav.server.shutdown), ('close-fixture', dav.server.server_close)])
            if getattr(dav, 'fixture_trust', None):
                actions.append(('remove-fixture-trust', lambda: untrust_desktop(dav.fixture_trust)))
        actions.append(('remove-fixture-key', lambda: (out / 'key.pem').unlink(missing_ok=True)))
        finish_cleanup(actions, data, out / 'result.json')"""
    source = replace_once(source, before, after)
    source = replace_once(source, "ROOT / 'tests/apple_android_relay/apple/RelayUITests.swift'",
                          "ROOT / 'tests/dot_f04_reading_sync_20261031/apple_driver.swift'")
    source = replace_once(source, "identity = json.loads((sdk / 'wave3-packages.json').read_text())",
        "identity = json.loads((sdk / 'wave3-packages.json').read_text())\n"
        "        assert identity['sdk_version'] == '3.42.0'\n"
        "        data['sdk_version'] = identity['sdk_version']\n"
        "        data['f04_stage'] = 'iphone-android-reading-v1'")
    source = replace_once(source, "        data['passed'] = True",
        "        (out / 'program.bin').write_bytes(binary.read_bytes())\n"
        "        required = ('created-records',) if args.phase == 'apple-first' else ('incoming-bookmark', 'incoming-note')\n"
        "        assert all(name in checkpoints for name in required)\n"
        "        data['f04_checkpoints'] = {name: checkpoints[name] for name in required}\n"
        "        data['passed'] = True")
    source = replace_once(source, "'__PHASE__': args.phase, '__TOKEN__': token,",
        "'__PHASE__': args.phase, '__TOKEN__': token,\n"
        "                         '__INCOMING_PREFIX__': getattr(args, 'incoming_prefix', 'F04_ANDROID'),\n"
        "                         '__OUTGOING_PREFIX__': 'F04_" + target.upper() + "',")
    if target == "iphone" and not generic:
        source = source.replace("'F04_IPHONE'", "'F04_APPLE'")
        return source
    source = replace_once(source, "choices=['apple-first', 'apple-return']",
                          "choices=['" + target + "-peer']")
    source = replace_once(source, "    args = p.parse_args()",
        "    p.add_argument('--incoming-prefix', default='F04_WINDOWS')\n    args = p.parse_args()")
    source = replace_once(source, "'platform': 'iPhone Simulator'",
        "'platform': " + repr({"iphone": "iphone-simulator", "ipad": "ipad-simulator", "macos": "macos"}[target]))
    source = source.replace("data['f04_stage'] = 'iphone-android-reading-v1'",
                            "data['f04_stage'] = 'six-host-reading-preparation-v2'")
    source = replace_once(source, "from relay import start, save, untrust_desktop, finish_cleanup",
                          "from relay import start, save, untrust_desktop, finish_cleanup, input_metadata, retained_rows")
    source = replace_once(source, "                    checkpoints[name] = payload",
        "                    payload['retained_records'] = retained_rows(root / 'accounts' / matching[0]['id'] / 'reader-catalog.db')\n"
        "                    checkpoints[name] = payload")
    source = replace_once(source, "            previous = json.loads(args.previous.read_text())['data']",
        "            previous = input_metadata(json.loads(args.previous.read_text()))")
    source = replace_once(source, "        data['passed'] = True",
        "        assert 'edited-records' in checkpoints and 'uploaded' in checkpoints\n"
        "        data['f04_checkpoints'].update({k: checkpoints[k] for k in ('edited-records', 'uploaded', 'position')})\n"
        "        data['passed'] = True")
    if target == "ipad":
        source = replace_once(source, "d['name'].startswith('iPhone')", "d['name'].startswith('iPad')")
    if target == "macos":
        source = replace_once(source, "team24-apple-sdk-iphonesimulator-*", "team24-apple-sdk-macos-*")
        begin = source.index("        devices = json.loads(")
        finish = source.index("        checkpoints = {}", begin)
        source = source[:begin] + (
            "        data['device'] = {'name': 'macOS runner', 'physical_device': False}\n"
            "        dav, user, password = start(out, previous=args.previous)\n") + source[finish:]
        begin = source.index("                    container = Path(")
        finish = source.index("                    profiles =", begin)
        source = source[:begin] + (
            "                    root = Path.home() / 'Library/Application Support/EXReader'\n") + source[finish:]
        source = replace_once(source, "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_ALLOWED=YES")
        source = replace_once(source, "'-scheme', 'EXReaderHost-iOS'", "'-scheme', 'EXReaderHost-macOS'")
        source = replace_once(source, "'platform=iOS Simulator,id=' + udid", "'platform=macOS'")
        source = replace_once(source, "'derived/Build/Products/Debug-iphonesimulator/EXReaderHost.app'",
                              "'derived/Build/Products/Debug/EXReaderHost.app'")
        source = replace_once(source, "(app / 'Info.plist')", "(app / 'Contents/Info.plist')")
        source = replace_once(source, "binary = app / 'EXReaderHost'", "binary = app / 'Contents/MacOS/EXReaderHost'")
    return source

def stage_android(generic=False):
    source = retained("tests/apple_android_relay/android/run.py")
    source = replace_once(source, "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))",
                          "sys.path.insert(0, " + repr(str(HERE)) + ")")
    source = replace_once(source, "package + '.RelayAndroidTest'", "package + '.F04AndroidTest'")
    # MainActivity is singleTask: install ActivityMonitor before its first
    # launch, otherwise onNewIntent need not deliver an Activity to the monitor.
    # Only the test-input directory is prepared here; no app database is seeded.
    source = replace_once(source,
        "adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')",
        "adb('shell', 'run-as', package, 'mkdir', '-p', 'files')")
    source = replace_once(source, "'apple_progress_public_parse_real_jump', 'real_forward_pages_and_application_save',",
        "'apple_progress_public_parse_real_jump', 'peer_bookmark_and_annotation_originals_resolve',\n"
        "            'real_forward_pages_and_application_save', 'create_return_bookmark_and_annotation',")
    source = replace_once(source, "        report['checks'] = expected",
        "        report['f04_checks'] = ['peer_bookmark_and_annotation_originals_resolve', 'create_return_bookmark_and_annotation']\n"
        "        report['checks'] = [name for name in expected if name not in report['f04_checks']]\n"
        "        report['f04_stage'] = 'iphone-android-reading-v1'\n"
        "        report['sdk_version'] = '3.42.0'")
    source = replace_once(source, "        assert report['passed'] is True, report",
        "        save('program.bin', installed_apk)\n        assert report['passed'] is True, report")
    if generic:
        source = replace_once(source, "relay.load(args.previous, 'apple-first')", "relay.load(args.previous)")
        source = replace_once(source, "    args = parser.parse_args()",
            "    parser.add_argument('--incoming-prefix', default='F04_WINDOWS')\n    args = parser.parse_args()")
        before = "        payload = {key: previous['data'][key] for key in\n            ('original_sha256', 'original_bytes', 'book_identity', 'location', 'remote_title')}"
        source = replace_once(source, before,
            "        payload = relay.input_metadata(previous)\n        payload['incoming_prefix'] = args.incoming_prefix")
        source = source.replace("report['f04_stage'] = 'iphone-android-reading-v1'",
                                "report['f04_stage'] = 'six-host-reading-preparation-v2'\n"
                                "        report['platform'] = 'android-api34-x86_64'")
    return source

def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    generated = OUT / "android/org/exreader/host"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "F04AndroidTest.java").write_text((HERE / "android_driver.java").read_text())
    init = retained("tests/apple_android_relay/android/init.gradle")
    init = replace_once(init, "../../tests/apple_android_relay/android/java", "../../build/f04-driver/android")
    (OUT / "init.gradle").write_text(init)
    (OUT / "apple.py").write_text(stage_apple())
    (OUT / "android.py").write_text(stage_android())
    (OUT / "android-peer.py").write_text(stage_android(generic=True))
    for target in ("iphone", "ipad", "macos"):
        (OUT / (target + "-peer.py")).write_text(stage_apple(target, generic=True))
    print(json.dumps({"prepared": True, "runtime_accepted": False, "F04_accepted": False,
        "android_init": "build/f04-driver/init.gradle",
        "instrumentation": "org.exreader.host.F04AndroidTest"}), flush=True)

def prepare_hash_owner(platform):
    """Install the mandatory public hash dependency for this exact target."""
    assert platform in ("windows", "gtk", "android")
    retained("extras/opds/CMakeLists.txt")
    prefix = ROOT / ("build/f04-hash-" + platform + "/prefix")
    prefix.mkdir(parents=True, exist_ok=True)
    canonical = prefix.resolve().as_posix()
    previous = os.environ.get("EXREADER_ORIGINAL_HASH_PREFIX")
    assert previous in (None, "", canonical), "foreign original hash owner prefix"
    binary = prefix.parent / "build"
    args = ["cmake", "-S", str(ROOT / "extras/opds"), "-B", str(binary), "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
            "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_INSTALL_PREFIX=" + canonical]
    if platform == "android":
        sdk = Path(os.environ["ANDROID_HOME"])
        ndk = os.environ.get("C11_NDK", "27.0.12077973")
        toolchain = sdk / "ndk" / ndk / "build/cmake/android.toolchain.cmake"
        assert toolchain.is_file(), "install approved Android NDK before target hash build"
        args += ["-DCMAKE_TOOLCHAIN_FILE=" + toolchain.as_posix(), "-DANDROID_ABI=x86_64",
                 "-DANDROID_PLATFORM=android-26", "-DANDROID_STL=c++_static"]
    subprocess.run(args, cwd=ROOT, check=True)
    subprocess.run(["cmake", "--build", str(binary), "--parallel", "4"], cwd=ROOT, check=True)
    subprocess.run(["cmake", "--install", str(binary)], cwd=ROOT, check=True)
    assert (prefix / "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfig.cmake").is_file()
    # Installed ProductCatalog consumers also need this selector, not just store/native.
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = canonical
    return canonical

def build_producer(platform):
    """Actions-only recipe, still unreachable from the disabled workflow."""
    import hashlib
    # The historical package guards pin unrelated old branch path sets.
    # This package's exact twelve-file + frozen-SDK admission is mandatory;
    # build functions themselves and all their original assertions stay intact.
    subprocess.run([sys.executable, str(HERE / "admission.py")], cwd=ROOT, check=True)
    recipes = {
        "windows": ("tests/windows_sdk342/build.py", []),
        "gtk": ("tests/gtk_sdk342_package/run.py", ["build"]),
        "android": ("tests/android_sdk342_package/run.py", ["build"]),
        "macos": ("tests/apple_sdk342_host/build.py", ["--target", "macos"]),
        "iphonesimulator": ("tests/apple_sdk342_host/build.py", ["--target", "iphonesimulator"]),
    }
    path, arguments = recipes[platform]
    hash_prefix = prepare_hash_owner(platform) if platform in ("windows", "gtk", "android") else None
    original_recipe = retained(path)
    if platform == "android":
        (ROOT / "build/f06").mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / path), *arguments], cwd=ROOT, check=True)
    evidence = {"source_sha": os.environ["GITHUB_SHA"],
        "run_id": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "platform": platform, "sdk_source": "8357eafa28423a7ab93ba08b823af80f01ad1505",
        "sdk_version": "3.42.0", "recipe": path,
        "recipe_sha256": hashlib.sha256(original_recipe.encode()).hexdigest(),
        "host_runtime_accepted": False, "F04_accepted": False, "original_hash_prefix": hash_prefix}
    if platform == "android":
        import yaml
        workflow = retained(".github/workflows/reader-apple-android-relay.yml")
        steps = yaml.safe_load(workflow)["jobs"]["android"]["steps"]
        selected = [s for s in steps if s.get("name") == "Build real cross-platform relay instrumentation"]
        assert len(selected) == 1
        body = selected[0]["run"]
        body = replace_once(body, "$PWD/tests/apple_android_relay/android/init.gradle",
                            "$PWD/build/f04-driver/init.gradle")
        body = replace_once(body, "org.exreader.host.RelayAndroidTest", "org.exreader.host.F04AndroidTest")
        body = replace_once(body, "-PexrSdk=", "-PexrSdkVersion=3.42.0 -PexrSdk=")
        script = OUT / "android-instrumentation.sh"
        script.write_text(body)
        subprocess.run(["bash", "-e", "-o", "pipefail", str(script)], cwd=ROOT, check=True)
        # An instrumentation-only rebuild must not silently substitute the host APK.
        original_apk = ROOT / "build/wave3/artifacts/app-debug.apk"
        built_apk = ROOT / "examples/android/app/build/outputs/apk/debug/app-debug.apk"
        assert original_apk.read_bytes() == built_apk.read_bytes()
        evidence["instrumentation_recipe_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    candidates = {
        "windows": ROOT / "build/windows-sdk342/package/EXReader/EXReader.exe",
        "gtk": ROOT / "build/gtk-raw-wave3/retained-package/EXReader-Linux/bin/exreader-linux",
        "android": ROOT / "build/wave3/artifacts/app-debug.apk",
    }
    if platform in candidates:
        binary = candidates[platform]
        evidence["program"] = {"path": binary.relative_to(ROOT).as_posix(),
            "bytes": binary.stat().st_size, "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
    else:
        identity = ROOT / ("build/raw3-ios-sdk/" + platform + "/sdk342-installed-identity.json")
        installed = json.loads(identity.read_text())
        assert installed["source_sha"] == evidence["source_sha"]
        assert installed["sdk_version"] == "3.42.0"
        evidence["installed_identity_sha256"] = hashlib.sha256(identity.read_bytes()).hexdigest()
        evidence["program"] = None  # Real host is built by the later UI producer, not this SDK step.
    (OUT / ("build-" + platform + ".json")).write_text(json.dumps(evidence, indent=2) + "\n")

def cleanup_retained_fixture():
    """Remove only the certificate generated by this original Actions fixture."""
    certificate = ROOT / "build/v2-webdav-evidence/certificates/server.crt"
    if not certificate.is_file():
        return
    if sys.platform == "win32":
        output = subprocess.check_output(["openssl", "x509", "-in", str(certificate),
            "-noout", "-fingerprint", "-sha1"], text=True).strip()
        fingerprint = output.split("=", 1)[1].replace(":", "")
        subprocess.run(["certutil", "-delstore", "Root", fingerprint], check=True)
    else:
        installed = Path("/usr/local/share/ca-certificates/reader-v2-roundtrip.crt")
        if installed.exists():
            assert installed.read_bytes() == certificate.read_bytes(), "fixture trust path was replaced"
            subprocess.run(["sudo", "rm", "--", str(installed)], check=True)
            subprocess.run(["sudo", "update-ca-certificates"], check=True)
    certificate.with_suffix(".key").unlink(missing_ok=True)


def diagnostic_text(value, secrets=()):
    """Fail closed on nontext; known fixture values and auth-bearing lines are removed."""
    import re
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("diagnostic not plain text")
    for secret in secrets:
        if secret:
            value = value.replace(str(secret), "[REDACTED]")
    value = re.sub(r"-----BEGIN [^-]*KEY-----.*?-----END [^-]*KEY-----", "[KEY REMOVED]", value, flags=re.DOTALL)
    if re.search(r"-----(?:BEGIN|END) [^-]*KEY-----", value):
        raise ValueError("incomplete key block; diagnostic refused")
    value = re.sub(r"(?im)^.*(?:authorization|password|passwd|access.token|private.key|BEGIN .*KEY|credential).*$",
                   "[AUTH LINE REMOVED]", value)
    value = re.sub(r"(https?://)[^/\s@]+@", r"\1[REDACTED]@", value)
    return value

def collect_diagnostics(arguments):
    """Only fixed public text evidence; never recursive profiles, databases, or keys."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("windows", "retained", "android", "audit"), required=True)
    args = parser.parse_args(arguments)
    destination = ROOT / "build/f04-diagnostics" / args.kind
    destination.mkdir(parents=True, exist_ok=True)
    whitelist = {
        "windows": [("build/phase/result.json", "result.json")],
        "android": [("build/phase/result.json", "result.json")],
        "audit": [("build/f04-graph-auth/result.json", "graph.json"), ("build/f04-retained-auth/result.json", "retained.json")],
        "retained": [("build/f04-driver/retained-failure.json", "failure.json"),
                     ("build/v2-sdk-evidence/result.json", "sdk-result.json"),
                     ("build/v2-sdk-evidence/legacy/summary.json", "legacy-summary.json")]
    }
    manifest = {"source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "kind": args.kind,
                "diagnostic_only": True, "files": [], "missing": [], "refused": []}
    for source, name in whitelist[args.kind]:
        path = ROOT / source
        if not path.is_file():
            manifest["missing"].append(source); continue
        try:
            content = diagnostic_text(path.read_text(encoding="utf-8"))
            (destination / name).write_text(content, encoding="utf-8")
            manifest["files"].append(name)
        except Exception:
            manifest["refused"].append(source)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))

def retained_protocol():
    """Run original 18/121 and native HTTPS checks, not the old four-ZIP aggregate."""
    import hashlib, yaml
    assert sys.platform in ("win32", "linux")
    subprocess.run([sys.executable, str(HERE / "admission.py")], cwd=ROOT, check=True)
    prepare_hash_owner("windows" if sys.platform == "win32" else "gtk")
    recipe = retained(".github/workflows/reader-reading-v2.yml")
    steps = yaml.safe_load(recipe)["jobs"]["sdk"]["steps"]
    names = [
        "Install one product provider and separate current and actual legacy revisions",
        "Build and install the frozen reading SDK once",
        "Install adapter against each revision implementation and compile isolated consumers",
        "Preserve original 121 cases and verify v2 product round trips from real captures",
        "Install optional source export and compile an independent C C++ consumer",
        "Real owner original export cancellation invalidation and atomic no-replace publication",
        "Install native sync and compile the complete original export and reading consumer",
        "Real native HTTPS transfers SDK-exported originals and all eighteen reading captures",
    ]
    records = []
    for index, name in enumerate(names):
        matches = [step for step in steps if step.get("name") == name]
        assert len(matches) == 1, name
        body = matches[0]["run"]
        # SDK selector and historical provider isolation only; probe sources
        # and assertions remain byte-identical (original 121 and all 18 cases).
        adapted = "\n".join(line + (" -DEXR_SDK_VERSION=3.42.0" if
            line.lstrip().startswith("cmake -S ") and "-DEXR_SDK=" in line else "")
            for line in body.splitlines()) + "\n"
        if index == 0:
            old = "210403d121d6484a8fff4ea7ffd911efa3163535"
            archive = "git archive " + old + " apps/reader/revisions extras/opds"
            assert adapted.count(archive) == 1
            adapted = adapted.replace(archive, archive + " apps/reader/store/native apps/reader/store/001_catalog.sql tests/reader_catalog/native_catalog_check.c licenses/sqlite-public-domain.txt")
            # YAML removes indentation; select the actual command exactly once.
            marker = "cmake -S build/v1-source/apps/reader/revisions"
            assert adapted.count(marker) == 1
            commands = (
                'cmake -S build/v1-source/apps/reader/store/native -B build/v1-product -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$ws/build/v1-product-stage"\n'
                'cmake --build build/v1-product --parallel 4\n'
                'cmake --install build/v1-product\n')
            adapted = adapted.replace(marker, commands + marker)
            lines = adapted.splitlines()
            adapted = "\n".join(line.replace('READER_PRODUCT_PREFIX="$ws/build/v2-product-stage"', 'READER_PRODUCT_PREFIX="$ws/build/v1-product-stage"')
                if line.startswith(marker) else line for line in lines) + "\n"
        if index == 2:
            lines = adapted.splitlines()
            adapted = "\n".join(line.replace("build/v2-product-stage", "build/v1-product-stage")
                if " -B build/v1-adapter " in line or " -B build/v1-consumer " in line else line for line in lines) + "\n"
        script = OUT / ("retained-" + str(index) + ".sh")
        script.write_text(adapted)
        is_tls = name == "Real native HTTPS transfers SDK-exported originals and all eighteen reading captures"
        if is_tls and sys.platform != "win32":
            assert not Path("/usr/local/share/ca-certificates/reader-v2-roundtrip.crt").exists(), "preexisting fixture trust path"
        try:
            completed = subprocess.run(["bash", "-e", "-o", "pipefail", str(script)], cwd=ROOT,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            print(diagnostic_text(completed.stdout), flush=True)
            if completed.returncode:
                (OUT / "retained-failure.json").write_text(json.dumps({
                    "step": name, "exit_code": completed.returncode, "passed": False,
                    "output": diagnostic_text(completed.stdout), "source_sha": os.environ["GITHUB_SHA"]}, indent=2))
                raise subprocess.CalledProcessError(completed.returncode, ["bash", str(script)])
        finally:
            if is_tls:
                original_failure = sys.exc_info()[0] is not None
                try:
                    cleanup_retained_fixture()
                except BaseException as cleanup_error:
                    (OUT / "retained-cleanup-error.txt").write_text(type(cleanup_error).__name__ + ": " + str(cleanup_error))
                    if not original_failure:
                        raise
        for line in Path(os.environ["GITHUB_ENV"]).read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator:
                os.environ[key] = value
        records.append({"name": name, "original_sha256": hashlib.sha256(body.encode()).hexdigest(),
                        "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest()})
    receipt = {"source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
        "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "sdk_version": "3.42.0",
        "sdk_source": "8357eafa28423a7ab93ba08b823af80f01ad1505", "platform": sys.platform,
        "original_workflow_sha256": hashlib.sha256(recipe.encode()).hexdigest(),
        "legacy_catalog_source": "210403d121d6484a8fff4ea7ffd911efa3163535",
        "legacy_revisions_source": "210403d121d6484a8fff4ea7ffd911efa3163535",
        "legacy_product_prefix": "build/v1-product-stage",
        "current_product_prefix": "build/v2-product-stage",
        "steps": records, "original_four_zip_aggregate": "not-run", "F04_accepted": False}
    (OUT / "retained-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")

def seal_phase(arguments):
    """Bind a successful real UI phase to its same-run build receipt."""
    import hashlib, shutil
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase-dir", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--installed-identity", type=Path)
    args = parser.parse_args(arguments)
    state = json.loads((args.phase_dir / "state.json").read_text())
    receipt = json.loads(args.build_receipt.read_text())
    for key, variable in (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT")):
        assert str(state[key]) == os.environ[variable] == str(receipt[key]), "phase/build identity"
    assert state["data"]["passed"] is True
    binary = (args.phase_dir / "program.bin").read_bytes()
    assert hashlib.sha256(binary).hexdigest() == state["data"]["program"]["sha256"]
    assert len(binary) == state["data"]["program"]["bytes"]
    if receipt["program"] is not None:
        assert receipt["program"]["sha256"] == hashlib.sha256(binary).hexdigest()
        assert receipt["program"]["bytes"] == len(binary)
    else:
        assert args.installed_identity is not None, "Apple SDK installed manifest required"
        manifest = args.installed_identity.read_bytes()
        assert hashlib.sha256(manifest).hexdigest() == receipt["installed_identity_sha256"]
        installed = json.loads(manifest)
        assert installed["source_sha"] == receipt["source_sha"] and installed["sdk_version"] == "3.42.0"
        assert state["data"]["program"]["bundle_source_sha"] == receipt["source_sha"]
        assert state["data"]["program"]["bundle_id"] == "org.exreader.host"
        shutil.copyfile(args.installed_identity, args.phase_dir / "installed-identity.json")
    shutil.copyfile(args.build_receipt, args.phase_dir / "build-receipt.json")

def package_build(arguments):
    """Explicit public build handoff; never include fixture keys or app profiles."""
    import shutil
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("windows", "gtk", "android", "macos", "iphonesimulator"), required=True)
    args = parser.parse_args(arguments)
    receipt = OUT / ("build-" + args.platform + ".json")
    record = json.loads(receipt.read_text())
    destination = ROOT / ("build/f04-build-" + args.platform)
    destination.mkdir(parents=True, exist_ok=False)
    if args.platform in ("macos", "iphonesimulator"):
        source = ROOT / ("build/raw3-ios-sdk/" + args.platform)
        for name in ("sdk", "raw-products"):
            shutil.copytree(source / name, destination / name)
        for name in ("sdk342-installed-identity.json", "wave3-packages.json", "sdk-identity.json", "raw-identity.json"):
            shutil.copy2(source / name, destination / name)
    elif args.platform == "android":
        # CA private key stays in this job, where build and actual peer execute.
        for name in ("app-debug.apk", "relay-debug-androidTest.apk"):
            shutil.copy2(ROOT / "build/wave3/artifacts" / name, destination / name)
        shutil.copy2(ROOT / record["program"]["path"], destination / "program.bin")
    else:
        package = ROOT / ("build/windows-sdk342/package" if args.platform == "windows" else
                          "build/gtk-raw-wave3/retained-package")
        shutil.copytree(package, destination / "package")
        shutil.copy2(ROOT / record["program"]["path"], destination / "program.bin")
        if args.platform == "windows":
            shutil.copy2(ROOT / "build/host-font-cache/Reader.otf", destination / "Reader.otf")
    shutil.copy2(receipt, destination / "build-receipt.json")


def windows_import_fixed():
    """Execute only the authenticated historical package, never rebuild it."""
    import hashlib, io, zipfile
    from pathlib import PurePosixPath
    sys.path.insert(0, str(ROOT / "tools"))
    from check_parallel_integration import fetch, download_artifact_zip
    contract = json.loads((HERE / "contract.json").read_text())
    pin = contract["windows_import_probe"]
    assert os.environ.get("F04_SCOPE") == "f04/windows-import-only"
    assert os.environ["GITHUB_REF"] == "refs/heads/" + contract["canonical"]["branch"]
    assert os.environ["F04_CONTROLLER_SHA"] == os.environ["GITHUB_SHA"]
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == os.environ["GITHUB_SHA"]
    changed = subprocess.check_output(["git", "diff", "--name-only", contract["base_source"], "HEAD"], cwd=ROOT, text=True).splitlines()
    assert set(changed) == set(contract["canonical"]["union_paths"])
    producer = fetch("actions/runs/" + pin["run_id"])
    assert producer["head_sha"] == pin["source_sha"] and str(producer["run_attempt"]) == pin["attempt"]
    job = fetch("actions/jobs/" + str(pin["job_id"]))
    assert job["head_sha"] == pin["source_sha"] and str(job["run_id"]) == pin["run_id"] and str(job["run_attempt"]) == pin["attempt"]
    steps = [x for x in job["steps"] if x["name"] == "Same-source Windows build"]
    assert len(steps) == 1 and steps[0]["conclusion"] == "success"
    artifact = fetch("actions/artifacts/" + str(pin["artifact_id"]))
    assert artifact["id"] == pin["artifact_id"] and not artifact["expired"]
    assert artifact["size_in_bytes"] == pin["size_in_bytes"] and artifact["digest"] == pin["digest"]
    assert artifact["workflow_run"]["head_sha"] == pin["source_sha"] and str(artifact["workflow_run"]["id"]) == pin["run_id"]
    blob = download_artifact_zip(pin["artifact_id"])
    assert len(blob) == pin["size_in_bytes"] and "sha256:" + hashlib.sha256(blob).hexdigest() == pin["digest"]
    destination = ROOT / "build/f04-fixed-windows"
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert sum(x.file_size for x in archive.infolist()) <= 500000000
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            assert not path.is_absolute() and ".." not in path.parts and "\\" not in entry.filename and ":" not in entry.filename
            assert ((entry.external_attr >> 16) & 0o170000) != 0o120000
            target = destination.joinpath(*path.parts)
            if entry.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry.filename))
    receipt = json.loads((destination / "build-receipt.json").read_text())
    assert all(str(receipt[k]) == pin[k] for k in ("source_sha", "run_id", "attempt"))
    assert receipt["sdk_version"] == "3.42.0" and receipt["platform"] == "windows"
    assert receipt["sdk_source"] == "8357eafa28423a7ab93ba08b823af80f01ad1505"
    exe = destination / "package/EXReader/EXReader.exe"
    data = exe.read_bytes()
    assert hashlib.sha256(data).hexdigest() == receipt["program"]["sha256"] and len(data) == receipt["program"]["bytes"]
    assert data == (destination / "program.bin").read_bytes()
    subprocess.run([sys.executable, str(HERE / "fixtures.py")], cwd=ROOT, check=True)
    out = ROOT / "build/phase"
    command = [sys.executable, str(HERE / "windows_driver.py"), "--phase", "windows-import-only",
        "--candidate", str(exe), "--font", str(destination / "Reader.otf"),
        "--original", str(ROOT / "build/apple-android/original/epub-alice.epub"),
        "--title", "Alice's Adventures in Wonderland", "--producer-receipt", str(destination / "build-receipt.json"),
        "--output", str(out)]
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    finally:
        result = out / "result.json"
        if result.is_file(): print("F04 IMPORT RESULT " + diagnostic_text(result.read_text()), flush=True)
    result = json.loads((out / "result.json").read_text())
    assert result["passed"] is True and result["F04_accepted"] is False
    assert result["program"]["sha256"] == receipt["program"]["sha256"]
    print(json.dumps({"controller_source": os.environ["GITHUB_SHA"], "controller_run": os.environ["GITHUB_RUN_ID"],
                      "product_producer": pin, "windows_import_path_only": True, "F04_accepted": False}), flush=True)

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    assert Path.cwd().resolve() == ROOT
    assert os.environ.get("EXR_APPLE_SDK_VERSION") == "3.42.0"
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "apple", "android", "android-peer", "iphone-peer", "ipad-peer", "macos-peer", "windows", "gtk", "build-windows", "build-gtk", "build-android", "build-macos", "build-iphonesimulator", "retained-protocol", "seal-phase", "package-build", "diagnostics", "windows-import-fixed"))
    args, rest = parser.parse_known_args()
    if args.action == "windows-import-fixed":
        assert not rest
        windows_import_fixed()
        return
    if args.action == "diagnostics":
        collect_diagnostics(rest)
        return
    prepare()
    if args.action == "package-build":
        package_build(rest)
        return
    if args.action == "seal-phase":
        seal_phase(rest)
        return
    if args.action == "retained-protocol":
        assert not rest, rest
        retained_protocol()
        return
    if args.action.startswith("build-"):
        assert not rest, rest
        build_producer(args.action.removeprefix("build-"))
        return
    if args.action != "prepare":
        driver = HERE / (args.action + "_driver.py") if args.action in ("windows", "gtk") else OUT / (args.action + ".py")
        completed = subprocess.run([sys.executable, str(driver), *rest], cwd=ROOT)
        raise SystemExit(completed.returncode)
if __name__ == "__main__":
    main()
