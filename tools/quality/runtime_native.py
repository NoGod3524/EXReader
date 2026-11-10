"""Build and run the complete native suite with MSVC ASan or MinGW gcov."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from runtime_routes import ROOT, OUT, LOCAL, msvc_env, progress


def run(name, command, env=None):
    started = time.monotonic()
    if (OUT / f'{name}.txt').exists():
        index = 1
        while (OUT / f'{name}-attempt{index}.txt').exists(): index += 1
        for suffix in ('.txt', '.json'):
            old = OUT / (name+suffix)
            if old.exists(): shutil.copy2(old, OUT / f'{name}-attempt{index}{suffix}')
    with (OUT / f'{name}.txt').open('w', encoding='utf-8') as log:
        log.write(json.dumps(command, ensure_ascii=False)+'\n')
        log.flush()
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    record = dict(command=command, exit_code=result.returncode, elapsed_seconds=time.monotonic()-started,
                  asan_options=(env or {}).get('ASAN_OPTIONS'), gcov_prefix=(env or {}).get('GCOV_PREFIX'))
    (OUT / f'{name}.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    progress(f'{name}: exit={result.returncode}; {record["elapsed_seconds"]:.1f}s; evidence/runtime-20261109/{name}.txt')
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['asan', 'coverage', 'control'])
    parser.add_argument('action', choices=['build', 'ctest', 'bridge', 'probe', 'fuzz', 'contracts', 'benchmark'])
    args = parser.parse_args()
    build = LOCAL / {'asan':'a', 'coverage':'g', 'control':'m'}[args.mode]
    is_msvc = args.mode != 'coverage'
    env = msvc_env() if is_msvc else os.environ.copy()
    env['ASAN_OPTIONS'] = 'alloc_dealloc_mismatch=1:halt_on_error=1'
    if args.mode == 'asan' and build.exists():
        runtime = Path(shutil.which('cl', path=env['PATH'])).parent / 'clang_rt.asan_dynamic-x86_64.dll'
        if not (build / runtime.name).exists():
            shutil.copy2(runtime, build / runtime.name)
    cmake, ctest, ninja = [shutil.which(name) for name in ('cmake', 'ctest', 'ninja')]
    if args.action == 'build':
        previous = json.loads((ROOT / 'evidence/quality-20261108/configure-command.json').read_text())['arguments']
        options = [arg for arg in previous if arg.startswith(('-DEXR_', '-DFETCHCONTENT_'))]
        options += ['-DEXR_BUILD_TESTS=ON', '-DEXR_BUILD_TOOLS=ON', '-DEXR_BUILD_FUZZ=ON', '-DCMAKE_BUILD_TYPE=Debug',
                    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_MAKE_PROGRAM='+ninja]
        if is_msvc:
            options += ['-DCMAKE_C_COMPILER='+shutil.which('cl', path=env['PATH']),
                        '-DCMAKE_C_FLAGS='+('/fsanitize=address' if args.mode == 'asan' else ''), '-DCMAKE_C_FLAGS_DEBUG=/Z7 /Od',
                        '-DCMAKE_EXE_LINKER_FLAGS=/INCREMENTAL:NO /DEBUG',
                        '-DCMAKE_SHARED_LINKER_FLAGS=/INCREMENTAL:NO /DEBUG',
                        '-DCMAKE_EXE_LINKER_FLAGS_DEBUG=/DEBUG /INCREMENTAL:NO',
                        '-DCMAKE_SHARED_LINKER_FLAGS_DEBUG=/DEBUG /INCREMENTAL:NO']
        else:
            options += ['-DCMAKE_C_COMPILER='+shutil.which('gcc'),
                        '-DCMAKE_C_FLAGS_DEBUG=-g -O1 --coverage -fprofile-update=atomic -Wno-error=format-truncation -Wno-error=maybe-uninitialized',
                        '-DCMAKE_EXE_LINKER_FLAGS=--coverage', '-DCMAKE_SHARED_LINKER_FLAGS=--coverage']
        code = run(args.mode+'-configure', [cmake, '-S', str(ROOT), '-B', str(build), '-G', 'Ninja']+options, env)
        if code == 0:
            code = run(args.mode+'-build', [cmake, '--build', str(build), '--parallel', '6']+(['--target', 'exreader'] if args.mode == 'control' else []), env)
    elif args.action in ('ctest', 'fuzz', 'benchmark'):
        if args.mode == 'asan':
            # Root CMake only selects this existing mode for non-MSVC sanitizers.
            # Adapt the generated test registration; retain the original RSS gate
            # in the independent gcov run and keep ASan quarantine at its default.
            testfile = build / 'CTestTestfile.cmake'
            lines = testfile.read_text(encoding='utf-8').splitlines()
            for i, line in enumerate(lines):
                if line.startswith('add_test("native-convert-benchmark"') and '--instrumented' not in line:
                    before = line
                    lines[i] = line[:-1]+' "--instrumented")'
                    (OUT / 'msvc-ctest-adapter.json').write_text(json.dumps(dict(
                        reason='Use existing sanitizer benchmark mode; root CMake excludes MSVC from its sanitizer branch',
                        file=str(testfile), before=before, after=lines[i]), indent=2)+'\n', encoding='utf-8')
                    testfile.write_text('\n'.join(lines)+'\n', encoding='utf-8')
                    break
        inventory = subprocess.check_output([ctest, '--test-dir', str(build), '--show-only=json-v1'], env=env)
        (OUT / f'{args.mode}-{args.action}-inventory.json').write_bytes(inventory)
        command = [ctest, '--test-dir', str(build), '--output-on-failure', '-j', '2',
                   '--output-junit', str(OUT / f'{args.mode}-{args.action}.xml')]
        if args.action == 'fuzz':
            command += ['-R', '^native-fuzz-']
        elif args.action == 'benchmark':
            original = build / 'native-convert-benchmark.json'
            if original.exists() and not (OUT / 'asan-benchmark-before.json').exists():
                shutil.copy2(original, OUT / 'asan-benchmark-before.json')
            command += ['-R', '^native-convert-benchmark$']
        code = run(args.mode+'-'+args.action, command, env)
        if args.action == 'benchmark':
            shutil.copy2(build / 'native-convert-benchmark.json', OUT / 'asan-benchmark-after.json')
    elif args.action in ('probe', 'contracts'):
        sources = [('typed-probe', 'tools/quality/typed_probe.c')] if args.action == 'probe' else [
            ('txt-scan', 'tests/bounded_txt_scan/check.c'), ('txt-view', 'tests/bounded_txt_scan/view.c'),
            ('txt-anchor', 'tests/txt_anchor_resolve/check.c')]
        code = 0
        if args.mode == 'coverage':
            env['GCOV_PREFIX'] = str(LOCAL / 'runtime-coverage/t')
            env['GCOV_PREFIX_STRIP'] = str(len(build.parts))
        for name, source in sources:
            if is_msvc:
                command = [shutil.which('cl', path=env['PATH']), '/nologo', '/MTd', '/Z7', '/Od',
                           *(['/fsanitize=address'] if args.mode == 'asan' else []), '/std:c11', '/utf-8', '/I'+str(ROOT / 'include'), str(ROOT/source),
                           '/Fo'+str(build / (name+'.obj')), '/Fe'+str(build / (name+'.exe')),
                           '/link', '/INCREMENTAL:NO', str(build / 'exreader.lib')]
            else:
                command = ['gcc', '-g', '-O1', '-I'+str(ROOT / 'include'), str(ROOT/source), '-o', str(build / (name+'.exe')),
                           '-L'+str(build), '-lexreader']
            code = run(args.mode+'-'+name+'-build', command, env)
            if code: break
            if args.action == 'contracts':
                code = run(args.mode+'-'+name, [str(build / (name+'.exe'))], env)
                if code: break
    else:
        source = str(ROOT / 'examples/windows/check_typography_font.c')
        bridge = str(build / 'quality-font-bridge.dll')
        libs = ['comdlg32', 'gdi32', 'uiautomationcore', 'shell32', 'user32', 'oleaut32', 'uuid']
        if is_msvc:
            command = [shutil.which('cl', path=env['PATH']), '/nologo', '/LD', '/MTd', '/Z7', '/Od',
                       *(['/fsanitize=address'] if args.mode == 'asan' else []), '/std:c11', '/utf-8', '/D_CRT_SECURE_NO_WARNINGS',
                       '/I'+str(ROOT / 'include'), source, '/Fo'+str(build / 'bridge.obj'),
                       '/Fe'+bridge, '/link', '/INCREMENTAL:NO', str(build / 'exreader.lib')]+[x+'.lib' for x in libs]
        else:
            command = ['gcc', '-shared', '-g', '-O1', '-I'+str(ROOT / 'include'), '-L'+str(build),
                       source, '-o', bridge, '-lexreader']+['-l'+x for x in libs]+['-lm']
        code = run(args.mode+'-bridge', command, env)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
