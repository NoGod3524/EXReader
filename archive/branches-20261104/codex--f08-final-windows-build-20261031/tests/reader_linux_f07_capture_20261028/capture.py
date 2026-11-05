"""Retain the existing final retained-host closure; never relink or change flags."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import contract as C


def collect():
    C.actions_only()
    report = dict(C.identity(), capture_complete=False, f07_accepted=False,
                  acceptance_gap='Capture authentication is not the final single-provider/private-entry F07 audit.')
    C.OUT.mkdir(parents=True, exist_ok=True)
    try:
        source = C.guard()
        stage = C.OUT / 'evidence'
        C.require(not stage.exists(), 'fresh capture stage required')
        stage.mkdir()
        records = {}
        workspace = C.ROOT.resolve()

        def copy(path):
            path = Path(path)
            C.require(path.is_file(), 'required capture file absent: ' + str(path))
            relative = path.relative_to(C.ROOT).as_posix(); C.safe_name(relative)
            if relative in records:
                return
            resolved = path.resolve(strict=True)
            C.require(resolved.is_relative_to(workspace), 'capture symlink escaped checkout')
            target = stage / relative; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            records[relative] = dict(bytes=target.stat().st_size, sha256=C.digest(target),
                mode=path.stat().st_mode & 0o777,
                symlink_target=os.readlink(path) if path.is_symlink() else None,
                resolved_source=resolved.relative_to(workspace).as_posix())

        def tree(relative):
            folder = C.ROOT / relative
            C.require(folder.is_dir() and not folder.is_symlink(), 'missing or aliased capture root: ' + relative)
            for path in sorted(folder.rglob('*')):
                C.require(not (path.is_dir() and path.is_symlink()), 'directory symlink needs explicit closure support')
                if path.is_file() or path.is_symlink():
                    copy(path)

        # Full installed SDK + module headers, archives, exports and manifests;
        # full final build, not the different raw-host or compact-host build.
        for prefix in (*C.PREFIXES, C.HOST, C.PAYLOAD, C.F06, C.UNPACK, 'build/gtk-sdk342'):
            tree(prefix)
        for name in ('build/gtk-navigation-ui/result.json', 'build/gtk-batch-ui/report.json'):
            copy(C.ROOT / name)
        for path in (C.ROOT / 'build/gtk-raw-wave3').iterdir():
            if path.is_file() and path.suffix in ('.log', '.json'):
                copy(path)
        for folder in [C.ROOT / 'build/reading-library', *sorted((C.ROOT / 'build/gtk-raw-wave3').glob('raw-*')),
                       *sorted((C.ROOT / 'build/gtk-raw-wave3').glob('legacy-*'))]:
            if folder.is_dir():
                for name in ('CMakeCache.txt', 'build.ninja', 'CMakeFiles/rules.ninja', 'cmake_install.cmake', 'install_manifest.txt'):
                    path = folder / name
                    if path.is_file():
                        copy(path)
        commands = []

        def inspect(label, args, cwd=C.ROOT):
            output = stage / 'commands' / (label + '.txt'); output.parent.mkdir(parents=True, exist_ok=True)
            done = subprocess.run(list(map(str, args)), cwd=cwd, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=False)
            output.write_bytes(done.stdout)
            error = output.with_suffix('.stderr.txt'); error.write_bytes(done.stderr)
            commands.append(dict(label=label, argv=list(map(str, args)), cwd=str(cwd), exit_code=done.returncode,
                                 stdout=output.relative_to(stage).as_posix(), stderr=error.relative_to(stage).as_posix()))
            C.require(done.returncode == 0, 'native inspection failed: ' + label)
            return done.stdout.decode('utf-8', errors='strict')

        # Ninja tools only print the existing graph. No build, configure or relink.
        graph = inspect('final-ninja-commands', ['ninja', '-t', 'commands', 'exreader-linux'], C.ROOT / C.HOST)
        inspect('final-ninja-query', ['ninja', '-t', 'query', 'gtk-host/exreader-linux'], C.ROOT / C.HOST)
        final = [line for line in graph.splitlines() if '-o gtk-host/exreader-linux ' in line]
        C.require(len(final) == 1 and 'gtk-account-host.map' in final[0], 'final linker command missing/ambiguous')
        loads = C.project_loads((stage / C.MAP).read_text(), str(workspace))
        for name in loads['project']:
            C.require(name in records, 'final map input not captured: ' + name)
        inspect('final-readelf-header', ['readelf', '-h', stage / C.PROGRAM])
        inspect('final-readelf-dynamic', ['readelf', '-d', stage / C.PROGRAM])
        inspect('final-readelf-symbols', ['readelf', '-Ws', stage / C.PROGRAM])
        inspect('final-nm', ['nm', '-A', '-g', stage / C.PROGRAM])
        native = sorted(name for name in records if name.endswith('.a') or '.so' in Path(name).name)
        C.require(native, 'no actual installed/native archives')
        for index, name in enumerate(native):
            inspect('archive-' + str(index) + '-nm', ['nm', '-A', '-g', stage / name])
            if name.endswith('.a'):
                inspect('archive-' + str(index) + '-members', ['ar', 't', stage / name])
            else:
                inspect('image-' + str(index) + '-dynamic', ['readelf', '-d', stage / name])
        for path in sorted((stage / 'commands').rglob('*')):
            if path.is_file():
                records[path.relative_to(stage).as_posix()] = dict(bytes=path.stat().st_size, sha256=C.digest(path), mode=0o644,
                                                                  symlink_target=None, resolved_source=None)
        package = C.verify_package(stage)
        inventory = dict(C.identity(), schema=1, source=source, producer_workspace=str(workspace),
            files=records, commands=commands, native_inputs=native, final_link_command=final[0],
            final_map_inputs=loads, package_identity=package, f07_accepted=False)
        C.save(stage / 'inventory.json', inventory)
        C.verify_files(stage, inventory)
        archive = C.OUT / 'evidence.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    bundle.write(path, path.relative_to(stage).as_posix())
        report.update(capture_complete=True, evidence=dict(name=archive.name, bytes=archive.stat().st_size,
            sha256=C.digest(archive)), inventory_sha256=C.digest(stage / 'inventory.json'), package_identity=package,
            installed_prefixes=list(C.PREFIXES), final_program=C.PROGRAM, final_link_map=C.MAP,
            files=len(records), native_inputs=len(native))
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        C.save(C.OUT / 'capture.json', report)


if __name__ == '__main__':
    C.actions_only()
    if sys.argv[1] == 'guard':
        C.save(C.OUT / 'source.json', C.guard())
    elif sys.argv[1] == 'collect':
        collect()
    else:
        raise ValueError(sys.argv[1])
