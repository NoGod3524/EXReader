"""Invoke unchanged F06 Windows producer, then retain its actual dependency inputs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import traceback
import zipfile

from capture_contract import (ROOT, OUT, F06, BUILD, STAGES, BUILDS, PROGRAM, MAP, RECIPE,
    MODULES, actions_only, identity, guard, save, require, diagnostic_argv,
    file_digest, validate_capture)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build():
    actions_only(windows=True)
    source = guard()
    require(not (ROOT / F06).exists(), 'fresh Actions build required; no old outputs')
    (ROOT / F06).mkdir(parents=True)
    save(ROOT / F06 / 'source.json', source)
    sys.path.insert(0, str(ROOT / 'tests/reader_windows_raw3'))
    import host_build as H
    F = load(RECIPE, 'f07_original_f06')
    C = F.module('tests/reader_wave3_c09/build.py', 'f07_original_c09')
    require(C.H is H, 'diagnostic wrapper must observe the original shared helper')
    require(tuple(Path(p).name for p in tuple(H.MODULES) + C.NEW_MODULES) == MODULES,
            'retained F06 module list drifted')
    journal = dict(identity(), commands=[])
    original_host_run, original_f06_run = H.run, F.run

    def record(argv, invoke, label):
        original = [str(v) for v in argv]
        actual = diagnostic_argv(original)
        row = dict(label=label, original=original, actual=actual,
                   cwd=str(ROOT), completed=False, exit_code=None)
        journal['commands'].append(row)
        save(OUT / 'commands.json', journal)
        try:
            result = invoke(actual)
            row.update(completed=True, exit_code=0)
            return result
        except BaseException as error:
            row.update(completed=True, exit_code=getattr(error, 'returncode', 1),
                       error=str(error))
            raise
        finally:
            save(OUT / 'commands.json', journal)

    def host_run(argv, name, timeout=1800):
        return record(argv, lambda actual: original_host_run(actual, name, timeout), name)

    def f06_run(*args):
        return record(args, lambda actual: original_f06_run(*actual), 'original-f06-subprocess')

    H.run, F.run = host_run, f06_run
    result = dict(identity(), producer_completed=False, f07_accepted=False)
    try:
        # Exactly the old producer body: no copied recipe, rewritten feature flag,
        # replacement fixture, changed assertion, or replacement package verifier.
        payload = F.windows()
        F.run(sys.executable, 'tests/reader_f06_packages/identity.py',
              'package', 'windows', payload)
        result['producer_completed'] = True
    except BaseException as error:
        result['failure'] = str(error)
        raise
    finally:
        H.run, F.run = original_host_run, original_f06_run
        save(OUT / 'producer.json', result)


def capture():
    actions_only(windows=True)
    guard()
    require((OUT / 'commands.json').is_file(), 'producer was not started')
    diagnostics = dict(identity(), commands=[])
    failures = []

    def diagnostic(argv, path, subject=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        row = dict(argv=[str(a) for a in argv], output=path.relative_to(OUT).as_posix())
        if subject:
            row.update(subject=subject.relative_to(ROOT).as_posix(), subject_identity=file_digest(subject))
        try:
            with path.open('wb') as stream:
                process = subprocess.run(row['argv'], cwd=ROOT, stdout=stream,
                    stderr=subprocess.STDOUT, timeout=300, check=False)
            row['exit_code'] = process.returncode
            if process.returncode:
                failures.append('diagnostic failed: ' + row['output'])
        except (OSError, subprocess.TimeoutExpired) as error:
            row.update(exit_code=None, failure=str(error))
            failures.append('diagnostic unavailable: ' + row['output'])
        diagnostics['commands'].append(row)
        save(OUT / 'diagnostics.json', diagnostics)

    for label in BUILDS:
        directory = ROOT / BUILD / label
        if (directory / 'build.ninja').is_file():
            diagnostic(['ninja', '-C', directory, '-t', 'commands'],
                       OUT / 'ninja' / (label + '.commands.txt'))
    for tool in ('cmake', 'ninja'):
        diagnostic([tool, '--version'], OUT / 'versions' / (tool + '.txt'))
    inputs = set()
    for stage in STAGES:
        inputs.update((ROOT / BUILD / stage).rglob('*.lib'))
    host = ROOT / BUILD / 'host'
    inputs.update(host.rglob('*.lib'))
    inputs.update(host.rglob('*.obj'))
    for path in sorted(inputs):
        relative = path.relative_to(ROOT / BUILD)
        diagnostic(['dumpbin', '/nologo', '/symbols', path],
            OUT / 'symbols' / (relative.as_posix() + '.txt'), path)
    if (ROOT / PROGRAM).is_file():
        for mode in ('headers', 'imports', 'exports', 'dependents'):
            diagnostic(['dumpbin', '/nologo', '/' + mode, ROOT / PROGRAM],
                OUT / 'image' / (mode + '.txt'), ROOT / PROGRAM)

    # Full installed trees (including public headers/CMake exports/vendor libs),
    # full host build, and every actually generated response file are retained.
    # SDK/module build trees contribute their actual graph and install records,
    # not their large downloaded third-party source directories.
    selected = {}
    def include(path, name=None):
        if path.is_file():
            require(not path.is_symlink(), 'source symlink cannot be captured: ' + str(path))
            selected[name or path.relative_to(ROOT).as_posix()] = path
    for relative in (F06 + 'windows', F06 + 'windows-payload', F06 + 'unpacked-windows',
            BUILD + 'logs', BUILD + 'host', *(BUILD + stage for stage in STAGES)):
        for path in (ROOT / relative).rglob('*'):
            include(path)
    include(ROOT / F06 / 'source.json')
    for label in BUILDS:
        directory = ROOT / BUILD / label
        for filename in ('CMakeCache.txt', 'build.ninja', 'cmake_install.cmake',
                'install_manifest.txt', 'CMakeFiles/rules.ninja', '.ninja_log', '.ninja_deps'):
            include(directory / filename)
        for path in directory.rglob('*.rsp'):
            include(path)
    for name in ('source.json', 'commands.json', 'producer.json', 'diagnostics.json', 'producer-console.log'):
        include(OUT / name, 'capture/' + name)
    for folder in ('ninja', 'symbols', 'image', 'versions'):
        for path in (OUT / folder).rglob('*'):
            include(path, 'capture/' + path.relative_to(OUT).as_posix())
    inventory = {}
    snapshot = OUT / 'snapshot.zip'
    # Produce an inner ZIP so upload-artifact cannot drop dotfiles or flatten
    # common roots. Every member is authenticated again in a separate job.
    with zipfile.ZipFile(snapshot, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as bundle:
        for name, path in sorted(selected.items()):
            before = file_digest(path)
            bundle.write(path, name)
            require(file_digest(path) == before, 'capture input changed: ' + name)
            inventory[name] = before
    manifest = dict(identity(), schema=1, archive=file_digest(snapshot), files=inventory)
    save(OUT / 'inventory.json', manifest)
    report = dict(identity(), capture_complete=False, f06_identity_verified=False,
                  f07_accepted=False, failures=failures)
    try:
        producer = json.loads((OUT / 'producer.json').read_text(encoding='utf-8'))
        require(producer['producer_completed'] is True, 'original F06 producer failed')
        require(not failures, 'one or more raw diagnostics failed')
        with zipfile.ZipFile(snapshot) as bundle:
            report.update(validate_capture(bundle, inventory, identity()))
    except Exception as error:
        report['failures'].append(str(error))
        traceback.print_exc()
    finally:
        save(OUT / 'report.json', report)
        print(json.dumps(report, indent=2), flush=True)
    require(report['capture_complete'], 'capture incomplete; partial evidence was retained')


if __name__ == '__main__':
    actions_only()
    operation = sys.argv[1]
    if operation == 'guard':
        guard()
    elif operation == 'build':
        build()
    elif operation == 'capture':
        capture()
    else:
        raise SystemExit('expected guard, build or capture')
