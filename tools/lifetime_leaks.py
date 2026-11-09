"""Record the 19-book Windows ASan/CRT or Linux ASan+LSan baseline."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def source_hashes():
    files = {path for pattern in ('src/*.c', 'src/*.h', 'include/exr/*.h', 'include/exreader.h',
                                  'tests/test_lifetime_leaks.c', 'tests/test_lifetime.c', 'tests/run_lifetime.py',
                                  'CMakeLists.txt', 'cmake/*.cmake',
                                  'tools/layers.json', 'tools/*lifetime*.py') for path in ROOT.glob(pattern)}
    return {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def progress(message):
    with (ROOT / 'S6-OUT.txt').open('a', encoding='utf-8') as output:
        output.write(f'[{datetime.now(timezone.utc).isoformat()}] {message}\n')
    print(message, flush=True)


def msvc_environment():
    cache = ROOT / 'build/lifetime-msvc-paths.json'
    if cache.exists():
        paths = json.loads(cache.read_text(encoding='utf-8'))
        if shutil.which('cl', path=paths['PATH']):
            return os.environ.copy() | paths
    vswhere = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    installation = subprocess.check_output(
        [str(vswhere), '-latest', '-products', '*', '-property', 'installationPath'], text=True).strip()
    setup = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
    result = subprocess.run(f'"{setup}" >nul && set', shell=True, capture_output=True, check=True)
    environment = os.environ.copy()
    for line in result.stdout.decode(errors='replace').splitlines():
        key, separator, value = line.partition('=')
        if separator and key:
            environment[key.upper()] = value
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({key: environment[key] for key in ('PATH', 'INCLUDE', 'LIB', 'LIBPATH')},
                               indent=2), encoding='utf-8')
    return environment


def run(command, name, output, environment):
    started = time.monotonic()
    if (output / f'{name}.txt').exists():
        attempt = 1
        while (output / f'{name}-attempt{attempt}.txt').exists():
            attempt += 1
        for extension in ('.txt', '.json'):
            previous = output / (name + extension)
            if previous.exists():
                shutil.copy2(previous, output / f'{name}-attempt{attempt}{extension}')
    with (output / f'{name}.txt').open('w', encoding='utf-8') as log:
        log.write(json.dumps(command) + '\n')
        log.flush()
        completed = subprocess.run(command, cwd=ROOT, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT)
    record = {'command': command, 'exit_code': completed.returncode,
              'elapsed_seconds': round(time.monotonic() - started, 3)}
    (output / f'{name}.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    progress(f'{name}: exit={completed.returncode}; {record["elapsed_seconds"]}s; {output / (name + ".txt")}')
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['asan', 'crt', 'lsan'])
    parser.add_argument('action', choices=['build', 'run'])
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/lifetime-20261109')
    parser.add_argument('--corpus', type=Path, default=ROOT / 'tools/regress/corpus.json')
    parser.add_argument('--font', type=Path, default=ROOT / 'tests/fixtures/fonts/primary.ttf')
    parser.add_argument('--source-revision', help='Git revision for an exported source snapshot')
    parser.add_argument('--dependency-options', type=Path,
                        help='Existing configure-command JSON; reuse only FETCHCONTENT source paths.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    build = ROOT / 'build' / ('lifetime-' + args.mode)
    if (args.mode == 'lsan') != (os.name != 'nt'):
        parser.error('Use asan/crt on Windows, or lsan on Linux')
    env = os.environ.copy() if args.mode == 'lsan' else msvc_environment()
    env['ASAN_OPTIONS'] = ('detect_leaks=1:' if args.mode == 'lsan' else '') + 'alloc_dealloc_mismatch=1:halt_on_error=1'
    if args.mode == 'lsan':
        env['LSAN_OPTIONS'] = 'exitcode=23'
    env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    cmake = shutil.which('cmake')
    if args.action == 'build':
        sources = source_hashes()
        dependency_options = args.dependency_options
        if dependency_options is None and os.name == 'nt':
            dependency_options = ROOT / 'evidence/quality-20261108/configure-command.json'
        previous = json.loads(dependency_options.read_text())['arguments'] if dependency_options else []
        options = [option for option in previous if option.startswith('-DFETCHCONTENT_')]
        options += ['-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                    '-DEXR_BUILD_TESTS=ON', '-DEXR_BUILD_TOOLS=ON', '-DEXR_BUILD_FUZZ=ON',
                    '-DEXR_BUILD_JNI=OFF', '-DEXR_SANITIZE=' + ('OFF' if args.mode == 'crt' else 'ON'),
                    '-DEXR_BUILD_SHARED_COMPAT=ON', '-DEXR_ENABLE_LCP=OFF',
                    '-DEXR_ENABLE_IMAGE_WEBP=OFF', '-DEXR_ENABLE_IMAGE_TIFF=OFF',
                    '-DEXR_ENABLE_IMAGE_AVIF=OFF', '-DEXR_ENABLE_ICC=OFF',
                    '-DEXR_ENABLE_PDF_CRYPTO=OFF', '-DEXR_ENABLE_MP3=OFF',
                    '-DEXR_ENABLE_PDF_JPX=ON', '-DCMAKE_MAKE_PROGRAM=' + shutil.which('ninja')]
        if os.name == 'nt':
            options += ['-DCMAKE_C_COMPILER=' + shutil.which('cl', path=env['PATH']),
                    '-DCMAKE_C_FLAGS=' + ('/fsanitize=address' if args.mode == 'asan' else ''),
                    '-DCMAKE_C_FLAGS_DEBUG=/Z7 /Od',
                    '-DCMAKE_EXE_LINKER_FLAGS=/INCREMENTAL:NO /DEBUG',
                    '-DCMAKE_EXE_LINKER_FLAGS_DEBUG=/DEBUG /INCREMENTAL:NO']
        run([cmake, '-S', str(ROOT), '-B', str(build), '-G', 'Ninja'] + options,
            args.mode + '-configure', args.output, env)
        run([cmake, '--build', str(build), '--parallel', '2', '--target', 'exreader-lifetime-leaks-test'],
            args.mode + '-build', args.output, env)
        if source_hashes() != sources:
            raise ValueError('Source changed during compilation; repeat the build before measuring')
        (build / 'lifetime-source.json').write_text(json.dumps(sources, indent=2) + '\n', encoding='utf-8')
        if args.mode == 'asan':
            probe = build / 'asan-control.exe'
            run([shutil.which('cl', path=env['PATH']), '/nologo', '/MTd', '/fsanitize=address',
                 '/Z7', '/Od', str(ROOT / 'tools/quality/address_probe.c'),
                 '/Fo' + str(build / 'asan-control.obj'), '/Fe' + str(probe),
                 '/link', '/INCREMENTAL:NO'], 'asan-control-build', args.output, env)
            control = subprocess.run([str(probe)], env=env, capture_output=True)
            diagnostic = (control.stdout + control.stderr).decode('utf-8', errors='replace')
            (args.output / 'asan-control.txt').write_text(diagnostic, encoding='utf-8')
            if not control.returncode or 'ERROR: AddressSanitizer: heap-buffer-overflow' not in diagnostic:
                raise ValueError('ASan failed to reject the intentional heap-buffer-overflow')
            (args.output / 'asan-control.json').write_text(json.dumps({
                'exit_code': control.returncode, 'expected': 'AddressSanitizer: heap-buffer-overflow',
                'detected': True}, indent=2) + '\n', encoding='utf-8')
            progress('ASan positive control rejected the intentional heap-buffer-overflow.')
        return
    books = json.loads(args.corpus.read_text(encoding='utf-8'))['books']
    sources = json.loads((build / 'lifetime-source.json').read_text(encoding='utf-8'))
    if source_hashes() != sources:
        raise ValueError('Source changed since compilation; rebuild before measuring')
    if len(books) != 19:
        raise ValueError(f'Expected the 19-book corpus, found {len(books)}')
    for book in books:
        actual = hashlib.sha256(Path(book['path']).read_bytes()).hexdigest()
        if actual != book['sha256']:
            raise ValueError(f'Corpus SHA256 mismatch: {book["id"]}')
    executable = build / ('exreader-lifetime-leaks-test.exe' if os.name == 'nt' else 'exreader-lifetime-leaks-test')
    if args.mode == 'lsan':
        control = subprocess.run([str(executable), '--lsan-control'], env=env, capture_output=True)
        diagnostic = (control.stdout + control.stderr).decode('utf-8', errors='replace')
        (args.output / 'lsan-control.txt').write_text(diagnostic, encoding='utf-8')
        if (control.returncode != 23 or 'ERROR: LeakSanitizer: detected memory leaks' not in diagnostic
                or 'exr_lifetime_new' not in diagnostic):
            raise ValueError('LSan failed to detect the deliberately unreleased SDK document')
        (args.output / 'lsan-control.json').write_text(json.dumps({
            'exit_code': control.returncode, 'expected': 'LeakSanitizer: SDK document leak',
            'detected': True}, indent=2) + '\n', encoding='utf-8')
        progress('LSan positive control detected the deliberately unreleased SDK document (exit 23).')
    command = [str(executable), str(args.font)]
    if args.mode == 'crt':
        command += ['--crt']
    command += [book['path'] for book in books]
    run(command, args.mode + '-19-books', args.output, env)
    if source_hashes() != sources:
        raise ValueError('Source changed during measurement; rebuild and repeat')
    for book in books:
        if hashlib.sha256(Path(book['path']).read_bytes()).hexdigest() != book['sha256']:
            raise ValueError(f'Corpus changed during measurement: {book["id"]}')
    log = (args.output / f'{args.mode}-19-books.txt').read_text(encoding='utf-8')
    successes = re.findall(r'^BOOK (\d+) PASS live=0(.*)$', log, re.M)
    counts = [{'type': name, 'created': int(created), 'freed': int(freed), 'live': int(live)}
              for name, created, freed, live in re.findall(r'^COUNT (\S+) (\d+) (\d+) (\d+)$', log, re.M)]
    if len(successes) != 19 or not counts or not any(row['created'] for row in counts):
        raise ValueError('Missing per-book success or instrumented object counts')
    if any(row['created'] != row['freed'] or row['live'] for row in counts):
        raise ValueError('Objects remain alive after the corpus run')
    if args.mode == 'crt' and ('CRT_CONTROL detected_blocks=1 detected_bytes=17' not in log or
                               any('heap_blocks=0 heap_bytes=0' not in suffix for _, suffix in successes)):
        raise ValueError('Missing live CRT leak-detector control or zero-heap evidence')
    if re.search(r'ERROR: (?:AddressSanitizer|LeakSanitizer)|runtime error:', log):
        raise ValueError('Sanitizer diagnostic in corpus run')
    record = {'mode': args.mode, 'books_passed': 19, 'books_total': 19,
              'workload': 'open, enumerate, load first part/page, render one page, free all objects',
              'source_revision': args.source_revision or subprocess.check_output(
                  ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'source_sha256': sources,
              'font_sha256': hashlib.sha256(args.font.read_bytes()).hexdigest(),
              'books': [{key: book[key] for key in ('id', 'sha256')} for book in books],
              'counts': counts, 'sanitizer_diagnostics': 0,
              'leak_detector': {'crt': 'MSVC debug CRT with positive control',
                                'asan': 'Object counters; MSVC ASan detects address errors, not leaks',
                                'lsan': 'Linux ASan+LSan with SDK document leak positive control'}[args.mode]}
    if args.mode == 'crt':
        record.update(leaked_blocks=0, leaked_bytes=0, control_leaked_blocks=1, control_leaked_bytes=17)
    elif args.mode == 'lsan':
        record.update(leaked_blocks=0, leaked_bytes=0, control_exit_code=23,
                      sanitizer_environment={key: env[key] for key in ('ASAN_OPTIONS', 'LSAN_OPTIONS', 'UBSAN_OPTIONS')})
    (args.output / f'{args.mode}-19-books-summary.json').write_text(
        json.dumps(record, indent=2) + '\n', encoding='utf-8')
    progress(f'{args.mode} 19/19 books PASS; {len(counts)} object kinds balanced; ' +
             ('CRT heap leak delta=0 blocks/0 bytes, positive control=1 block/17 bytes.' if args.mode == 'crt'
              else 'AddressSanitizer/LeakSanitizer diagnostics=0; object live counts=0.' if args.mode == 'lsan'
              else 'AddressSanitizer diagnostics=0; object live counts=0.'))


if __name__ == '__main__':
    main()
