#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Measure two clean builds from one frozen manifest; fail on any output difference."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from build_manifest import check, write_json
from verify_artifacts import digest, inventory, verify, write_sums


def package(stage, archive, epoch):
    with archive.open('xb') as destination, gzip.GzipFile(fileobj=destination, mode='wb', filename='', mtime=epoch) as zipped:
        with tarfile.open(fileobj=zipped, mode='w') as tar:
            for path in sorted(stage.rglob('*')):
                if not path.is_file():
                    continue
                name = path.relative_to(stage).as_posix()
                info = tarfile.TarInfo('EXReader/' + name)
                info.size, info.mtime = path.stat().st_size, epoch
                info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                with path.open('rb') as stream:
                    tar.addfile(info, stream)


def run(manifest_path, destination, jobs):
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    check(manifest)
    # A new evidence directory prevents mixing files from earlier measurements.
    destination.mkdir(parents=True, exist_ok=False)
    cmake = manifest['cmake']['path']
    build = manifest['build']['directory']
    runs = []
    for number in (1, 2):
        check(manifest)
        folder = destination / f'run-{number}'
        stage, artifacts = folder / 'stage', folder / 'artifacts'
        artifacts.mkdir(parents=True)
        build_command = [cmake, '--build', build, '--config', 'Release', '--clean-first', '--parallel', str(jobs)]
        install_command = [cmake, '--install', build, '--config', 'Release', '--prefix', str(stage.resolve())]
        print(f'Run {number}: clean build and install', flush=True)
        for name, command in (('build', build_command), ('install', install_command)):
            with (folder / (name + '.log')).open('w', encoding='utf-8') as log:
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
        check(manifest)
        if manifest_path.read_bytes() != raw:
            raise ValueError('manifest changed during the build')
        (stage / 'build_manifest.json').write_bytes(raw)
        write_sums(stage)
        verify(stage)
        (artifacts / 'build_manifest.json').write_bytes(raw)
        for name, path in inventory(stage).items():
            if path.suffix.lower() == '.dll':
                target = artifacts / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        archive = artifacts / 'EXReader-SDK.tar.gz'
        package(stage, archive, manifest['package']['source_date_epoch'])
        write_sums(artifacts)
        verified = verify(artifacts)
        runs.append({'run': number, 'build_command': build_command, 'install_command': install_command,
                     'stage_files': {n: digest(p) for n, p in inventory(stage).items()},
                     'artifact_sha256': {n: digest(p) for n, p in inventory(artifacts).items()},
                     'verified_files': verified})
        write_json(destination / f'run-{number}.json', runs[-1])
        print(f'Run {number}: PASS ({verified} release files verified)', flush=True)
    same = runs[0]['artifact_sha256'] == runs[1]['artifact_sha256'] and runs[0]['stage_files'] == runs[1]['stage_files']
    report = {'schema': 1, 'manifest_sha256': digest(manifest_path), 'identical': same,
              'method': 'two --clean-first builds in the same configured directory, new install stages', 'runs': runs}
    write_json(destination / 'reproducibility.json', report)
    if not same:
        raise ValueError('reproducibility mismatch; see reproducibility.json')
    print('PASS: both clean builds have identical DLL/package and installed-file hashes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('build_manifest.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    try:
        run(args.manifest, args.output.resolve(), args.jobs)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
