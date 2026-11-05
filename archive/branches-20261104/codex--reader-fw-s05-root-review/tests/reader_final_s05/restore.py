"""Authenticate the staging tar before restoring its exact observed bundle facts."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import bundle_copy
import identity
import zip_stage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--intake', type=Path, required=True)
    parser.add_argument('--implementation-sha', required=True)
    args = parser.parse_args()
    record = json.loads((args.intake / 'producer-source.json').read_text())
    identity.same_implementation(record['implementation'], identity.implementation(args.implementation_sha))
    archive = args.intake / 'staging.tar'
    identity.require(archive.stat().st_size == record['staging_tar']['bytes'] and
                     zip_stage.sha256(archive) == record['staging_tar']['sha256'], 'staging tar bytes differ')
    names = set()
    with tarfile.open(archive) as tar:
        for item in tar.getmembers():
            path = PurePosixPath(item.name)
            identity.require(not path.is_absolute() and '..' not in path.parts and '\\' not in item.name and
                             ':' not in item.name and path.parts and path.parts[0] == 'staging' and item.name not in names,
                             'unsafe/duplicate tar member')
            names.add(item.name)
            identity.require(item.isfile() or item.isdir(), 'tar links/special members require an authenticated original format')
    identity.require(not (args.intake / 'staging').exists(), 'staging restore must be fresh')
    subprocess.run(['tar', '-xf', str(archive), '-C', str(args.intake)], check=True)
    for chosen in record['chosen'].values():
        bundle_copy.same(bundle_copy.snapshot(args.intake / chosen['staged']), chosen['snapshot'])


if __name__ == '__main__':
    main()
