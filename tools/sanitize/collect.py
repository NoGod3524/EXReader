"""Export numeric coverage and build provenance; raw profiles stay outside git."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def main(args):
    args.output.mkdir(parents=True, exist_ok=True)
    objects = [args.build/'exreader-sanitize.exe'] + sorted((args.build/'engine').glob('exreader-fuzz*.exe'))
    versions = {}
    for tool in ('clang-cl', 'lld-link', 'llvm-cov', 'llvm-profdata', 'llvm-symbolizer'):
        versions[tool] = subprocess.check_output([args.llvm/'bin'/(tool+'.exe'), '--version'], text=True).strip()
    commands = json.loads((args.build/'compile_commands.json').read_text())
    # All translation units, including vendor code, inherit these global flags.
    assert all(all(flag in c['command'] for flag in ('-fsanitize=address,undefined',
               '-fno-omit-frame-pointer', '-fprofile-instr-generate', '-fcoverage-mapping')) for c in commands)
    runtimes = next((args.llvm/'lib/clang').glob('*/lib/windows'))
    runtime_files = [runtimes/name for name in ('clang_rt.asan_dynamic-x86_64.dll',
                     'clang_rt.ubsan_standalone-x86_64.lib', 'clang_rt.profile-x86_64.lib')]
    flags = next(line.split('=',1)[1] for line in (args.build/'CMakeCache.txt').read_text().splitlines()
                 if line.startswith('CMAKE_C_FLAGS:')).split()
    driver = subprocess.run([args.llvm/'bin/clang-cl.exe','-###','/c',ROOT/'tools/sanitize/control.c',*flags],
                            capture_output=True,text=True,check=True).stderr
    assert '-mframe-pointer=all' in driver and 'unknown argument' not in driver
    assert '-fsanitize-system-ignorelist=' not in driver
    (args.output/'compiler-driver.txt').write_text(driver,encoding='utf-8')
    provenance = dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                      platform=platform.platform(), python=platform.python_version(), versions=versions,
                      configured_compile_units=len(commands), all_compile_units_instrumented=True,
                      compiled_object_count=len(list(args.build.rglob('*.obj'))),
                      sanitizer_version=versions['clang-cl'].splitlines()[0],
                      binaries={p.relative_to(args.build).as_posix():digest(p) for p in objects},
                      control_binary_sha256=digest(args.build/'sanitize-control.exe'),
                      runtimes={p.name:digest(p) for p in runtime_files},
                      cmake_cache_sha256=digest(args.build/'CMakeCache.txt'),
                      compile_commands_sha256=digest(args.build/'compile_commands.json'),
                      cmake_configuration=[line for line in (args.build/'CMakeCache.txt').read_text().splitlines()
                          if line.startswith(('EXR_', 'CMAKE_C_FLAGS:', 'CMAKE_C_FLAGS_RELWITHDEBINFO:',
                                              'CMAKE_BUILD_TYPE:', 'CMAKE_TRY_COMPILE_CONFIGURATION:',
                                              'CMAKE_C_COMPILER:', 'FETCHCONTENT_SOURCE_DIR_'))],
                      sanitizer_options=dict(ASAN_OPTIONS='symbolize=1:halt_on_error=1:alloc_dealloc_mismatch=1',
                                             UBSAN_OPTIONS='print_stacktrace=1:report_error_type=1'),
                      suppressions=[], ignorelists=[])
    provenance['audit_sources'] = {p.name:digest(p) for p in sorted((ROOT/'tools/sanitize').iterdir())
                                   if p.suffix in ('.c','.py','.txt')}
    provenance['engine_sources'] = {p.relative_to(ROOT).as_posix():digest(p)
                                    for p in sorted((ROOT/'src').rglob('*')) if p.is_file()}
    provenance['dependency_source_hashes'] = {str(p):digest(p) for p in sorted({Path(c['file']) for c in commands})
                                            if not p.is_relative_to(ROOT) and p.is_file()}
    provenance['dependency_pins'] = dict(freetype='2.15.0',expat='2.9.0',miniz='3.1.2',
        sqlite='3.54.0',openjpeg='2.5.4',lcms='2.19.1',mbedtls='3.6.7',
        stb='2c980bb59875b0d32144a71867fbdebb2f77cd20',minimp3='ea99364f61c14656440e8d77e9c233ccf3124633')
    write(args.output/'build.json', provenance)
    coverage = {}
    for group in ('books', 'malformed', 'seeds', 'combined'):
        profiles = sorted((args.work/'profiles').glob(('*/' if group=='combined' else group+'/')+'*.profraw'))
        profiles = [p for p in profiles if p.parent.name in ('books','malformed','seeds')]
        assert profiles, group
        inputs = args.work/(group+'-profiles.txt')
        inputs.write_text(''.join(str(p)+'\n' for p in profiles), encoding='utf-8')
        merged = args.work/(group+'.profdata')
        subprocess.run([args.llvm/'bin/llvm-profdata.exe', 'merge', '-sparse', '-f', inputs, '-o', merged], check=True)
        command = [args.llvm/'bin/llvm-cov.exe', 'export', '-summary-only',
                   '-instr-profile='+str(merged), objects[0]]
        for obj in objects[1:]:
            command += ['-object', obj]
        raw = subprocess.check_output(command)
        (args.work/(group+'-coverage.json')).write_bytes(raw)
        exported = json.loads(raw)['data'][0]
        files = []
        for item in exported['files']:
            path = Path(item['filename'])
            if path.is_relative_to(ROOT):
                files.append(dict(file=path.relative_to(ROOT).as_posix(), **item['summary']))
        coverage[group] = dict(profile_count=len(profiles), files=files,
                               exported_totals_including_vendors=exported['totals'])
        engine = [f for f in files if f['file'].startswith('src/')]
        coverage[group]['engine_totals'] = {
            metric: dict(covered=sum(f[metric]['covered'] for f in engine),
                         count=sum(f[metric]['count'] for f in engine))
            for metric in ('lines','functions','regions','branches')}
    write(args.output/'coverage.json', coverage)
    print(json.dumps({g: dict(profiles=c['profile_count'], files=len(c['files'])) for g,c in coverage.items()}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'evidence/sanitize-20261107')
    parser.add_argument('--llvm', type=Path, default=Path(r'C:\Users\Oscar\Documents\Codex\sanitize-toolchain-20261107\llvm'))
    main(parser.parse_args())
