"""Actions-only retained builds. No production/source rewrite and no automatic CI submission."""
import argparse
import hashlib
import importlib.abc
import importlib.util
import os
from pathlib import Path
import runpy
import subprocess
import sys
from identity import ROOT, SCOPE, identity, require, write_json

class SDK342Loader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Version-only in-memory adapter; recorded source remains byte-for-byte unmodified."""
    def __init__(self, audit):
        self.audit = audit
        self.target = ROOT / "tests/reader_windows_raw3/host_build.py"
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "host_build":
            return importlib.util.spec_from_file_location(fullname, self.target, loader=self)
        return None
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        text = self.target.read_text(encoding="utf-8")
        require("3.41.0" in text, "frozen Windows helper version no longer matches")
        adapted = text.replace("3.41.0", SCOPE["sdk_version"])
        self.audit.append({"path": str(self.target.relative_to(ROOT)),
                           "original_sha256": hashlib.sha256(text.encode()).hexdigest(),
                           "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
                           "replacement": ["3.41.0", SCOPE["sdk_version"]],
                           "occurrences": text.count("3.41.0")})
        exec(compile(adapted, str(self.target), "exec"), module.__dict__)

def prepare_hash(host, environment, audit):
    """Build the frozen product dependency for the same target, without replacing its owner."""
    prefix = (ROOT / "build/dot-f03-hash" / host / "stage").resolve()
    build = prefix.parent / "build"
    argv = ["cmake", "-S", str(ROOT / "extras/opds"), "-B", str(build), "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
            "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_INSTALL_PREFIX=" + str(prefix)]
    if host == "android":
        toolchain = environment.get("C11_TOOLCHAIN")
        require(toolchain and Path(toolchain).is_file(), "installed matching Android toolchain required")
        argv += ["-DCMAKE_TOOLCHAIN_FILE=" + toolchain, "-DANDROID_ABI=x86_64",
                 "-DANDROID_PLATFORM=android-26", "-DANDROID_STL=c++_static"]
    subprocess.run(argv, cwd=ROOT, env=environment, check=True)
    subprocess.run(["cmake", "--build", str(build), "--parallel", "4", "--target", "install"],
                   cwd=ROOT, env=environment, check=True)
    require(prefix.is_dir() and prefix == prefix.resolve(), "canonical installed hash prefix required")
    environment["EXREADER_ORIGINAL_HASH_PREFIX"] = str(prefix)
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = str(prefix)
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as stream:
        stream.write("EXREADER_ORIGINAL_HASH_PREFIX=" + str(prefix) + "\n")
    audit.append({"dependency": "EXReaderOPDSHash 0.1.0", "target": host,
                  "source": "extras/opds", "configure": argv, "prefix": str(prefix)})

def build_linux_recipe(host, audit):
    """Actions executes named original build steps; only explicit SDK version pins change."""
    import yaml
    if host == "gtk":
        workflow = ROOT / ".github/workflows/windows-gtk-organization-interop.yml"
        job = "gtk-first"
        names = ["Build installed SDK, catalog, account modules and real GTK host"]
    else:
        workflow = ROOT / ".github/workflows/android-organization-sync.yml"
        job = "android"
        names = ["Prepare existing C11 candidate test sources",
                 "Install the Android platform CMake NDK and API34 image",
                 "Build and install the frozen 3.41 SDK for x86_64",
                 "Install the raw0.2 product and reviewed wave3 packages into one prefix",
                 "Author the deterministic fixtures and the bundled font",
                 "Build the real wave3 host with search directory reading settings and sync",
                 "Build independent organization sync instrumentation",
                 "Build unchanged original sync UI runner", "Build strict 3.41 sync UI adapter"]
    recipe = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    steps = recipe["jobs"][job]["steps"]
    environment = dict(os.environ)
    environment.update({k: str(v) for k, v in recipe.get("env", {}).items()})
    environment.update({k: str(v) for k, v in recipe["jobs"][job].get("env", {}).items()})
    if host == "gtk":
        prepare_hash(host, environment, audit)
    for name in names:
        if host == "android" and name == "Install the raw0.2 product and reviewed wave3 packages into one prefix":
            prepare_hash(host, environment, audit)
        choices = [step for step in steps if step.get("name") == name]
        require(len(choices) == 1 and "run" in choices[0], "original recipe missing: " + name)
        original = choices[0]["run"]
        adapted = original.replace("3.41.0", SCOPE["sdk_version"])
        require("$" + "{{" not in adapted, "unresolved Actions expression")
        audit.append({"workflow": str(workflow.relative_to(ROOT)), "step": name,
                      "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
                      "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
                      "replacement": ["3.41.0", SCOPE["sdk_version"]],
                      "occurrences": original.count("3.41.0")})
        subprocess.run(["bash", "-euo", "pipefail", "-c", adapted], cwd=ROOT,
                       env=environment, check=True)
        env_file = Path(environment["GITHUB_ENV"])
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and (key.startswith("C11_") or key in ("ANDROID_HOME", "ANDROID_SDK_ROOT")):
                    environment[key] = value
        sdk_root = environment.get("ANDROID_SDK_ROOT")
        if sdk_root:
            environment["PATH"] = str(Path(sdk_root) / "platform-tools") + os.pathsep + environment["PATH"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", choices=["windows", "gtk", "macos", "iphone", "ipad", "android"], required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--native-tests", action="store_true")
    p.add_argument("--sdk", type=Path)
    p.add_argument("--products", type=Path)
    p.add_argument("--resources", type=Path)
    p.add_argument("--destination")
    a = p.parse_args()
    stamp = identity()
    changes = []
    accepted = False
    try:
        if a.native_tests:
            require(a.sdk is not None and a.products is not None, "installed SDK/products required")
            work = ROOT / "build/dot-f03-native" / a.host
            work.mkdir(parents=True, exist_ok=False)
            if a.host == "android":
                init = work / "f03.init.gradle"
                path = (Path(__file__).resolve().parent / "android").as_posix()
                init.write_text("gradle.beforeProject { p -> if (p.path == ':uitest') { "
                                "p.pluginManager.withPlugin('com.android.application') { "
                                "p.android.sourceSets.androidTest.java.srcDir new File('"
                                + path + "') } } }\n", encoding="utf-8")
                subprocess.run(["gradle", "-p", str(ROOT / "examples/android"), "--no-daemon",
                                "--stacktrace", "-I", str(init),
                                "-PexrSdk=" + str(a.sdk.resolve()),
                                "-PexrProduct=" + str(a.products.resolve()),
                                ":uitest:assembleDebug", ":uitest:assembleDebugAndroidTest"],
                               cwd=ROOT, check=True)
            else:
                require(a.host in ("macos", "iphone", "ipad"), "unsupported native target")
                require(a.resources is not None and a.resources.is_dir(), "original fixtures required")
                require(a.destination is not None, "exact actual device destination required")
                os.environ["EXR_APPLE_SDK_VERSION"] = SCOPE["sdk_version"]
                project = work / "project"
                subprocess.run(["ruby", "tests/reader_team24_apple/make_project.rb", str(project),
                                str(a.resources.resolve()), str(Path(__file__).resolve().parent), "base"],
                               cwd=ROOT, check=True)
                scheme = "EXReaderHost-macOS" if a.host == "macos" else "EXReaderHost-iOS"
                subprocess.run(["xcodebuild", "build-for-testing", "-project",
                                str(project / "EXReaderHost.xcodeproj"), "-scheme", scheme,
                                "-destination", a.destination, "-derivedDataPath", str(work / "derived"),
                                "EXR_SDK_DIR=" + str(a.sdk.resolve()),
                                "EXR_PRODUCTS_DIR=" + str(a.products.resolve()),
                                "CODE_SIGNING_ALLOWED=" + ("YES" if a.host == "macos" else "NO")],
                               cwd=ROOT, check=True)
        elif a.host in ("android", "gtk"):
            require(sys.platform.startswith("linux"), "Linux runner required")
            build_linux_recipe(a.host, changes)
        elif a.host == "windows":
            require(os.name == "nt", "Windows build requires Windows runner")
            prepare_hash("windows", os.environ, changes)
            loader = SDK342Loader(changes)
            sys.meta_path.insert(0, loader)
            path = ROOT / "tests/reader_wave3_c09/build.py"
            text = path.read_text(encoding="utf-8")
            require("3.41.0" in text, "frozen C09 version no longer matches")
            adapted = text.replace("3.41.0", SCOPE["sdk_version"])
            changes.append({"path": str(path.relative_to(ROOT)),
                            "original_sha256": hashlib.sha256(text.encode()).hexdigest(),
                            "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
                            "replacement": ["3.41.0", SCOPE["sdk_version"]],
                            "occurrences": text.count("3.41.0")})
            sys.argv = [str(path)]
            exec(compile(adapted, str(path), "exec"),
                 {"__name__": "__main__", "__file__": str(path), "__package__": None})
        else:
            require(sys.platform == "darwin", "Apple build requires macOS runner")
            os.environ["EXR_APPLE_SDK_VERSION"] = SCOPE["sdk_version"]
            target = "macos" if a.host == "macos" else "iphonesimulator"
            path = ROOT / "tests/apple_sdk342_host/build.py"
            sys.argv = [str(path), "--target", target]
            runpy.run_path(str(path), run_name="__main__")
        accepted = True
    finally:
        write_json(a.output, {**stamp, "host": a.host, "build_completed": accepted,
                              "sdk_version": SCOPE["sdk_version"], "in_memory_adapters": changes,
                              "product_source_changed": False, "complete_product_accepted": False})
if __name__ == "__main__":
    main()
