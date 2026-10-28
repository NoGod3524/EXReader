"""Actions-only F06 Apple adapter preserving the original page-theme profile."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f06'

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    target = sys.argv[1]
    assert target in ('macos', 'iphone')
    OUT.mkdir(parents=True, exist_ok=True)
    builder = load('tests/reader_f06_packages/build.py', 'f06_original_build')
    original_run = builder.run
    def explicit_sdk(*args):
        args = list(args)
        for i in range(1, len(args)):
            if args[i-1] == '--sdk-version' and args[i] == '3.41.0': args[i] = '3.42.0'
        return original_run(*args)
    builder.run = explicit_sdk
    # The original adapter's --page-theme, wave3 and raw selector flags are
    # retained. Current 4971 correctly refuses this until Apple 3.42 theme is
    # independently supported; never silently omit the flag.
    payload = builder.apple(target)
    identity = load('tests/reader_f06_packages/identity.py', 'f06_original_identity')
    original_identity_run = identity.run
    def package_sdk(*args):
        if any(str(a).endswith(('assemble.py', 'desktop.py')) for a in args):
            args = (*args, '--sdk-version', '3.42.0')
        return original_identity_run(*args)
    identity.run = package_sdk
    identity.package(target, payload)
    if target == 'macos':
        executable = OUT / 'unpacked-macos/EXReader.app/Contents/MacOS/EXReader'
        report = OUT / 'macos/launch.json'
        data = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                    attempt=os.environ['GITHUB_RUN_ATTEMPT'], passed=False)
        process = subprocess.Popen([str(executable)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            time.sleep(3)
            assert process.poll() is None, 'relocated macOS application exited during launch'
            data.update(passed=True, pid=process.pid, executable_sha256=identity.delivery.sha256_file(executable))
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            output = process.stdout.read().decode('utf-8', errors='replace')
            data['output'] = output
            report.write_text(json.dumps(data, indent=2)+'\n')
        assert data['passed']
    else:
        identity.install_apple('iphone')
        identity.package('ipad', payload)
        identity.install_apple('ipad')

if __name__ == '__main__': main()
