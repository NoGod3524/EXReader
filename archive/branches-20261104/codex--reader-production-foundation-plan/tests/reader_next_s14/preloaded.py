"""Actions-only actual-prefix controls for an already loaded SDK target graph."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    root = Path.cwd()
    sdk = Path(os.environ['S14_SDK_STAGE']).resolve()
    version = os.environ['S14_SDK_VERSION']
    out = root / 'build/s14-evidence/preloaded'
    out.mkdir(parents=True)
    clone = root / 'build/s14-preloaded-sdk-copy'
    shutil.copytree(sdk, clone)
    rows = []
    for mode in ('source', 'installed'):
        for foreign in (False, True):
            name = mode + ('-foreign-prefix' if foreign else '-same-prefix')
            selected = clone if foreign else sdk
            source = root / 'build/s14-preloaded' / name
            source.mkdir(parents=True)
            text = ('cmake_minimum_required(VERSION 3.24)\n'
                    'project(S14AlreadyLoaded LANGUAGES C CXX)\n'
                    f'find_package(EXReader {version} EXACT CONFIG REQUIRED COMPONENTS core PATHS "{sdk.as_posix()}/lib/cmake/EXReader" NO_DEFAULT_PATH)\n'
                    f'set(EXReader_DIR "{selected.as_posix()}/lib/cmake/EXReader" CACHE PATH "" FORCE)\n')
            if mode == 'source':
                text += ('set(READER_FONT_LIBRARY_BUILD ON CACHE BOOL "" FORCE)\n'
                         f'set(EXR_SDK_VERSION "{version}" CACHE STRING "" FORCE)\n'
                         f'set(EXR_SDK "{selected.as_posix()}" CACHE PATH "" FORCE)\n'
                         f'add_subdirectory("{root.as_posix()}/apps/reader/font-library" module)\n')
            else:
                text += (f'set(EXReaderFontLibrary_DIR "{root.as_posix()}/build/s14-stage/lib/cmake/EXReaderFontLibrary" CACHE PATH "" FORCE)\n'
                         'find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)\n')
            (source / 'CMakeLists.txt').write_text(text, encoding='utf-8')
            result = subprocess.run(['cmake', '-S', str(source), '-B', str(source / 'build'), '-G', 'Ninja'],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            raw = result.stdout.encode('utf-8')
            (out / (name + '.log')).write_bytes(raw)
            refused = result.returncode != 0 and 'SDK imported target' in result.stdout and re.search(r'origin\s+mismatch', result.stdout) is not None
            ok = refused if foreign else result.returncode == 0
            rows.append(dict(name=name, exit=result.returncode, expected_refusal=foreign, refused=refused,
                             passed=bool(ok), log_sha256=hashlib.sha256(raw).hexdigest()))
    helper = (root / 'apps/reader/font-library/EXReaderSdkTargetGuard.cmake').read_bytes()
    payload = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                   attempt=os.environ['GITHUB_RUN_ATTEMPT'], sdk_version=version,
                   platform=os.environ['RUNNER_OS'], accepted=all(row['passed'] for row in rows),
                   cases=rows, helper_sha256=hashlib.sha256(helper).hexdigest())
    (out / 'result.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload), flush=True)
    return 0 if payload['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
