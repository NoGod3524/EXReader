"""Actions-only fixed NDK input probe; no native tools or captured payload run."""
import json
import os
from pathlib import Path

import af07_contract as C

FAILED_INPUT_SHA = 'f5e33f488b74ee4efb1b398bbb72e0c14b9006f9c0e6db62c5c967e1e9336955'
SCRIPT = 'toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/x86_64-linux-android/26/libc++.so'
TARGET = 'toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/x86_64-linux-android/libc++_shared.so'


def verify_script(payload):
    C.require(C.sha(payload) == FAILED_INPUT_SHA, 'NDK input differs from actual failed inspector input')
    C.require(payload == b'INPUT(-lc++_shared)', 'unexpected exact NDK linker script bytes')
    return ['-lc++_shared']


def main():
    C.guard()
    ndk = Path(os.environ['ANDROID_HOME']) / 'ndk/27.0.12077973'
    report = dict(C.identity(), diagnostic_only=True, android_static_closure_accepted=False,
                  full_six_platform_f07_accepted=False, include_dependency_coverage_complete=False,
                  no_native_or_payload_execution=True, prior_failed_run=40780887828,
                  prior_diagnostic_run=40782004065, files={})
    for name in ('source.properties', SCRIPT, TARGET):
        path = ndk / name
        C.require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ndk.resolve()),
                  'fixed NDK probe file absent/linked/escaping')
        report['files'][name] = dict(bytes=path.stat().st_size, sha256=C.digest(path))
    payload = (ndk / SCRIPT).read_bytes()
    C.require(len(payload) <= 4096, 'NDK script exceeds diagnostic budget')
    report['script_text'] = payload.decode('ascii')
    with (ndk / TARGET).open('rb') as stream:
        report['target_is_elf'] = stream.read(4) == b'\x7fELF'
    C.save(C.OUT / 'ndk-fixed-input-probe.json', report)
    report['input_tokens'] = verify_script(payload)
    C.require(report['target_is_elf'], 'selected NDK runtime target is not ELF')
    C.require('Pkg.Revision = 27.0.12077973' in (ndk / 'source.properties').read_text(), 'NDK revision differs')
    C.save(C.OUT / 'ndk-fixed-input-probe.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__': main()
